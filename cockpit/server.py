#!/usr/bin/env python3
"""
AI Multi Cockpit — Local HTTP Server & Multi-Account Telemetry Backend.
Zero external dependencies (Python 3 stdlib only).
Binds strictly to 127.0.0.1 with Host validation and per-session CSRF token.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

APP_VERSION = "1.0.0"
DEFAULT_PORT = 19420

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
CODEX_SCRIPT = REPO_ROOT / "codex" / "Codex-Multi.ps1"
BRIDGE_INSTALL_SCRIPT = REPO_ROOT / "scripts" / "Install-AgyBridge.ps1"

LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
USER_PROFILE = Path(os.environ.get("USERPROFILE", str(Path.home())))
CURRENT_USER = os.environ.get("USERNAME", USER_PROFILE.name)

APP_DATA_ROOT = LOCAL_APPDATA / "AIMultiCockpit"
CODEX_PROFILES_ROOT = APP_DATA_ROOT / "codex-profiles"
CODEX_META_FILE = APP_DATA_ROOT / "codex-profiles.json"
USER_SETTINGS_FILE = APP_DATA_ROOT / "cockpit-settings.json"
LOCAL_TELEMETRY_DIR = APP_DATA_ROOT / "telemetry"

AGY_MULTI_ROOT = PROGRAM_DATA / "AntigravityMulti"
AGY_SHARED_TELEMETRY_DIR = AGY_MULTI_ROOT / "telemetry"
AGY_POOL_TELEMETRY_DIR = AGY_MULTI_ROOT / "sync_pool" / "telemetry"

SESSION_TOKEN = secrets.token_urlsafe(24)

_cache_lock = threading.Lock()
_process_cache: dict[str, Any] = {"ts": 0.0, "data": []}
_codex_exe_cache: dict[str, Any] = {"ts": 0.0, "exe": None, "desktop": None}


def ensure_dirs() -> None:
    APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    LOCAL_TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_email(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[0] + "***"
    else:
        masked = local[:2] + "***" + local[-1]
    return f"{masked}@{domain}"


def read_json_safe(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8-sig")
        return json.loads(text)
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_settings() -> dict[str, Any]:
    default = {
        "language": "zh",
        "theme": "dark",
        "privacyMode": False,
        "refreshIntervalSec": 30,
        "defaultWorkspace": "",
        "aliases": {},
        "notes": {},
    }
    saved = read_json_safe(USER_SETTINGS_FILE, {})
    if isinstance(saved, dict):
        default.update(saved)
    return default


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    cur = load_settings()
    for k in ("language", "theme", "privacyMode", "refreshIntervalSec", "defaultWorkspace"):
        if k in patch:
            cur[k] = patch[k]
    if isinstance(patch.get("aliases"), dict):
        cur.setdefault("aliases", {}).update(patch["aliases"])
    if isinstance(patch.get("notes"), dict):
        cur.setdefault("notes", {}).update(patch["notes"])
    write_json_atomic(USER_SETTINGS_FILE, cur)
    return cur


def run_powershell(args: list[str], timeout: int = 20) -> tuple[int, str, str]:
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"] + args
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=creation_flags,
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_codex_binaries(force: bool = False) -> tuple[str | None, str | None]:
    now = time.time()
    with _cache_lock:
        if not force and now - _codex_exe_cache["ts"] < 120:
            return _codex_exe_cache["exe"], _codex_exe_cache["desktop"]

    cli_exe: str | None = None
    desktop_exe: str | None = None

    local_bin = LOCAL_APPDATA / "OpenAI" / "Codex" / "bin"
    if local_bin.exists():
        found = sorted(local_bin.rglob("codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
        if found:
            cli_exe = str(found[0])

    rc, out, _ = run_powershell(
        [
            "-Command",
            "$p = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($p) { Write-Output $p.InstallLocation }",
        ],
        timeout=10,
    )
    if rc == 0 and out.strip():
        loc = Path(out.strip().splitlines()[0].strip())
        for rel in ("app\\ChatGPT.exe", "app\\Codex.exe"):
            cand = loc / rel
            if cand.exists():
                desktop_exe = str(cand)
                break
        if not cli_exe:
            bundled = loc / "app" / "resources" / "codex.exe"
            if bundled.exists():
                cli_exe = str(bundled)

    with _cache_lock:
        _codex_exe_cache["ts"] = now
        _codex_exe_cache["exe"] = cli_exe
        _codex_exe_cache["desktop"] = desktop_exe
    return cli_exe, desktop_exe


def get_running_processes(force: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    with _cache_lock:
        if not force and now - _process_cache["ts"] < 6.0:
            return list(_process_cache["data"])

    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$flt = \"Name='Antigravity.exe' OR Name='language_server.exe' OR Name='ChatGPT.exe' OR Name='Codex.exe' OR Name='codex.exe'\";"
        "$procs = @(Get-CimInstance Win32_Process -Filter $flt);"
        "$out = foreach ($p in $procs) {"
        "  $exe = if ($p.ExecutablePath) { $p.ExecutablePath } else { '' };"
        "  $owner = '';"
        "  if ($exe -match '^[A-Za-z]:\\\\Users\\\\([^\\\\]+)\\\\') { $owner = $Matches[1] }"
        "  elseif ($p.Name -eq 'language_server.exe') { try { $o = Invoke-CimMethod -InputObject $p -MethodName GetOwner; if ($o -and $o.User) { $owner = $o.User } } catch {} };"
        "  [PSCustomObject]@{ pid = $p.ProcessId; name = $p.Name; owner = $owner; exe = $exe; cmd = if ($p.CommandLine) { $p.CommandLine } else { '' } }"
        "};"
        "if ($out) { $out | ConvertTo-Json -Compress } else { '[]' }"
    )
    items: list[dict[str, Any]] = []
    try:
        rc, out, _ = run_powershell(["-Command", ps], timeout=12)
        if rc == 0 and out.strip():
            parsed = json.loads(out.strip())
            if isinstance(parsed, dict):
                items = [parsed]
            elif isinstance(parsed, list):
                items = parsed
    except Exception:
        with _cache_lock:
            return list(_process_cache["data"])

    with _cache_lock:
        _process_cache["ts"] = now
        _process_cache["data"] = items
    return items


# ---------------------------------------------------------------------------
# Codex Collectors & Quota Query (Official `codex app-server` JSON-RPC)
# ---------------------------------------------------------------------------

def get_codex_profiles_list() -> list[dict[str, Any]]:
    meta = read_json_safe(CODEX_META_FILE, {"profiles": {}})
    prof_meta = meta.get("profiles", {}) if isinstance(meta, dict) else {}

    def _entry(name: str, mode: str, codex_home: Path, user_data: str) -> dict[str, Any]:
        m = prof_meta.get(name, {}) if isinstance(prof_meta.get(name), dict) else {}
        sessions_dir = codex_home / "sessions"
        session_count = 0
        if sessions_dir.exists():
            try:
                session_count = sum(1 for _ in sessions_dir.rglob("*.jsonl"))
            except Exception:
                session_count = 0
        return {
            "name": name,
            "label": m.get("label") or ("Default (~/.codex)" if name == "default" else f"Codex - {name}"),
            "mode": mode,
            "codexHome": str(codex_home),
            "userData": user_data,
            "authExists": (codex_home / "auth.json").exists(),
            "proxy": m.get("proxy", ""),
            "sessionCount": session_count,
        }

    profiles = [_entry("default", "default", USER_PROFILE / ".codex", "")]
    if CODEX_PROFILES_ROOT.exists():
        for d in sorted(CODEX_PROFILES_ROOT.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir():
                profiles.append(_entry(d.name, "isolated", d / "codex_home", str(d / "user_data")))
    return profiles


def read_codex_session_fallback_limits(codex_home: Path) -> dict[str, Any] | None:
    """Fast local fallback: read latest rate_limits event from Codex sessions/*.jsonl."""
    sessions_dir = codex_home / "sessions"
    if not sessions_dir.exists():
        return None
    try:
        files = sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return None

    for sp in files[:8]:
        latest_rl = None
        latest_ts = None
        try:
            with sp.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "rate_limits" not in line:
                        continue
                    try:
                        obj = json.loads(line)
                        payload = obj.get("payload", {})
                        if isinstance(payload, dict) and payload.get("rate_limits"):
                            latest_rl = payload["rate_limits"]
                            latest_ts = obj.get("timestamp")
                    except Exception:
                        continue
        except Exception:
            continue
        if latest_rl:
            return {
                "source": "session_log",
                "updatedAt": latest_ts or utc_now_iso(),
                "rateLimits": normalize_codex_rate_limit(latest_rl),
                "extraLimits": [],
            }
    return None


def normalize_codex_rate_limit(rl: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(rl, dict):
        return None

    def _win(w: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(w, dict):
            return None
        used = w.get("usedPercent")
        if used is None:
            used = w.get("used_percent")
        if used is None:
            return None
        used_f = max(0.0, min(100.0, float(used)))
        rem_f = round(max(0.0, 100.0 - used_f), 1)
        mins = w.get("windowDurationMins") or w.get("window_minutes") or 0
        resets_at = w.get("resetsAt") or w.get("resets_at")
        reset_iso = None
        if isinstance(resets_at, (int, float)) and resets_at > 0:
            reset_iso = datetime.fromtimestamp(resets_at, tz=timezone.utc).isoformat()
        elif isinstance(resets_at, str):
            reset_iso = resets_at
        return {
            "usedPercent": round(used_f, 1),
            "remainingPercent": rem_f,
            "windowMinutes": int(mins),
            "resetsAt": reset_iso,
        }

    credits_raw = rl.get("credits") if isinstance(rl.get("credits"), dict) else {}
    return {
        "limitId": rl.get("limitId") or rl.get("limit_id") or "codex",
        "limitName": rl.get("limitName") or rl.get("limit_name"),
        "planType": rl.get("planType") or rl.get("plan_type"),
        "primary": _win(rl.get("primary")),
        "secondary": _win(rl.get("secondary")),
        "credits": {
            "hasCredits": bool(credits_raw.get("hasCredits") or credits_raw.get("has_credits")),
            "unlimited": bool(credits_raw.get("unlimited")),
            "balance": str(credits_raw.get("balance", "0")),
        },
        "spendControlReached": bool(rl.get("spendControlReached") or rl.get("spend_control_reached")),
    }


def query_codex_live_quota(profile: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    """Query live account & quota via official `codex app-server` JSON-RPC stdio."""
    cli_exe, _ = find_codex_binaries()
    snap_path = LOCAL_TELEMETRY_DIR / f"codex_{profile['name']}.json"
    if not cli_exe:
        return {"ok": False, "error": "Codex CLI (codex.exe) not found"}

    env = os.environ.copy()
    env["CODEX_HOME"] = profile["codexHome"]
    if profile.get("proxy"):
        env["HTTP_PROXY"] = profile["proxy"]
        env["HTTPS_PROXY"] = profile["proxy"]

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [cli_exe, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=creation_flags,
    )
    got: dict[int, Any] = {}
    try:
        reqs = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "ai-multi-cockpit", "version": APP_VERSION}},
            },
            {"jsonrpc": "2.0", "method": "initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "account/read", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "account/rateLimits/read", "params": {}},
        ]
        assert proc.stdin is not None and proc.stdout is not None
        for r in reqs:
            proc.stdin.write(json.dumps(r) + "\n")
        proc.stdin.flush()

        deadline = time.time() + timeout
        while time.time() < deadline and len(got) < 3:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                if "id" in msg and msg["id"] in (1, 2, 3):
                    got[msg["id"]] = msg
            except Exception:
                continue
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    acc_res = (got.get(2) or {}).get("result") or {}
    acc_obj = acc_res.get("account") if isinstance(acc_res, dict) else None
    rl_msg = got.get(3) or {}
    rl_res = rl_msg.get("result") if isinstance(rl_msg, dict) else None
    rl_err = rl_msg.get("error") if isinstance(rl_msg, dict) else None

    main_rl = None
    extra_limits: list[dict[str, Any]] = []
    ordinary_allowed = None
    if isinstance(rl_res, dict):
        ordinary_allowed = rl_res.get("ordinaryUsageAllowed")
        main_rl = normalize_codex_rate_limit(rl_res.get("rateLimits"))
        by_id = rl_res.get("rateLimitsByLimitId")
        if isinstance(by_id, dict):
            for lid, val in by_id.items():
                if lid == (main_rl or {}).get("limitId"):
                    continue
                norm = normalize_codex_rate_limit(val)
                if norm and (norm.get("primary") or norm.get("secondary")):
                    extra_limits.append(norm)

    snapshot = {
        "profile": profile["name"],
        "source": "codex_app_server",
        "updatedAt": utc_now_iso(),
        "signedIn": bool(acc_obj),
        "accountType": (acc_obj or {}).get("type") if isinstance(acc_obj, dict) else None,
        "emailMasked": mask_email((acc_obj or {}).get("email")) if isinstance(acc_obj, dict) else "",
        "planType": ((acc_obj or {}).get("planType") if isinstance(acc_obj, dict) else None)
        or ((main_rl or {}).get("planType")),
        "workspaceName": (acc_obj or {}).get("workspaceName") if isinstance(acc_obj, dict) else None,
        "ordinaryUsageAllowed": ordinary_allowed,
        "rateLimits": main_rl,
        "extraLimits": extra_limits,
        "error": (rl_err or {}).get("message") if isinstance(rl_err, dict) else None,
    }
    write_json_atomic(snap_path, snapshot)
    return {"ok": True, "snapshot": snapshot}


def build_codex_overview(procs: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
    cli_exe, desktop_exe = find_codex_binaries()
    profiles = get_codex_profiles_list()
    aliases = settings.get("aliases", {})
    notes = settings.get("notes", {})

    # Match running Codex Desktop (ChatGPT.exe / Codex.exe) processes by --user-data-dir
    desktop_procs = [p for p in procs if p.get("name", "").lower() in ("chatgpt.exe", "codex.exe")]

    items = []
    for prof in profiles:
        name = prof["name"]
        key = f"codex:{name}"
        snap = read_json_safe(LOCAL_TELEMETRY_DIR / f"codex_{name}.json")
        if not snap:
            fb = read_codex_session_fallback_limits(Path(prof["codexHome"]))
            if fb:
                snap = {
                    "profile": name,
                    "source": fb["source"],
                    "updatedAt": fb["updatedAt"],
                    "signedIn": prof["authExists"],
                    "planType": (fb.get("rateLimits") or {}).get("planType"),
                    "emailMasked": "",
                    "rateLimits": fb.get("rateLimits"),
                    "extraLimits": [],
                }

        # Check running state
        running_pids = []
        if prof["mode"] == "isolated" and prof["userData"]:
            needle = prof["userData"].lower()
            for p in desktop_procs:
                if needle in p.get("cmd", "").lower():
                    running_pids.append(p["pid"])
        else:
            # Default desktop instance has no custom codex-profiles user-data-dir
            prof_root_low = str(CODEX_PROFILES_ROOT).lower()
            for p in desktop_procs:
                cmd_low = p.get("cmd", "").lower()
                if p.get("name", "").lower() == "chatgpt.exe" and prof_root_low not in cmd_low:
                    running_pids.append(p["pid"])

        items.append(
            {
                "id": key,
                "tool": "codex",
                "name": name,
                "label": aliases.get(key) or prof["label"],
                "note": notes.get(key, ""),
                "mode": prof["mode"],
                "codexHome": prof["codexHome"],
                "authExists": prof["authExists"],
                "signedIn": bool((snap or {}).get("signedIn", prof["authExists"])),
                "planType": (snap or {}).get("planType") or "",
                "emailMasked": (snap or {}).get("emailMasked") or "",
                "workspaceName": (snap or {}).get("workspaceName") or "",
                "proxy": prof["proxy"],
                "sessionCount": prof["sessionCount"],
                "running": len(running_pids) > 0,
                "processCount": len(running_pids),
                "telemetrySource": (snap or {}).get("source") or "none",
                "updatedAt": (snap or {}).get("updatedAt"),
                "rateLimits": (snap or {}).get("rateLimits"),
                "extraLimits": (snap or {}).get("extraLimits") or [],
                "error": (snap or {}).get("error"),
            }
        )

    return {
        "installed": bool(cli_exe or desktop_exe),
        "cliInstalled": bool(cli_exe),
        "desktopInstalled": bool(desktop_exe),
        "profilesRoot": str(CODEX_PROFILES_ROOT),
        "accounts": items,
    }


# ---------------------------------------------------------------------------
# Antigravity Collector (Multi-Account + Official Sidecar Telemetry Bridge)
# ---------------------------------------------------------------------------

def count_agy_local_stats(user_home: Path) -> tuple[int | None, int | None]:
    """Count real (non-sidecar) projects & conversations for the current user safely (read-only)."""
    projects_count = None
    convs_count = None
    proj_dir = user_home / ".gemini" / "config" / "projects"
    if proj_dir.exists():
        try:
            cnt = 0
            for p in proj_dir.glob("*.json"):
                pj = read_json_safe(p, {})
                if isinstance(pj, dict) and not pj.get("sidecar"):
                    cnt += 1
            projects_count = cnt
        except Exception:
            pass
    db_path = user_home / ".gemini" / "antigravity" / "conversation_summaries.db"
    if db_path.exists():
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            row = con.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()
            convs_count = int(row[0]) if row else 0
            con.close()
        except Exception:
            pass
    return projects_count, convs_count


def read_agy_telemetry(account_user: str) -> dict[str, Any] | None:
    """Read sanctioned sidecar telemetry snapshot written by ai-multi-cockpit-bridge."""
    candidates = [
        AGY_POOL_TELEMETRY_DIR / f"antigravity_{account_user}.json",
        AGY_SHARED_TELEMETRY_DIR / f"antigravity_{account_user}.json",
        LOCAL_TELEMETRY_DIR / f"antigravity_{account_user}.json",
    ]
    best = None
    best_mtime = -1.0
    for fp in candidates:
        if fp.exists():
            try:
                mt = fp.stat().st_mtime
                if mt > best_mtime:
                    data = read_json_safe(fp)
                    if isinstance(data, dict):
                        best = data
                        best_mtime = mt
            except Exception:
                pass
    return best


def get_agy_sync_status() -> dict[str, Any]:
    sync_cfg = read_json_safe(AGY_MULTI_ROOT / "sync-config.json", {})
    pool_dir = AGY_MULTI_ROOT / "sync_pool"
    last_log = LOCAL_APPDATA / "AntigravityMulti" / "autosync.log"
    if not last_log.exists():
        last_log = AGY_MULTI_ROOT / "logs" / "autosync.log"
    last_line = ""
    last_time = None
    if last_log.exists():
        try:
            lines = [l.strip() for l in last_log.read_text(encoding="utf-8", errors="ignore").splitlines() if l.strip()]
            if lines:
                last_line = lines[-1][:180]
            last_time = datetime.fromtimestamp(last_log.stat().st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

    pool_convs = 0
    for cand_db in (pool_dir / "chats" / "conversation_summaries.db", pool_dir / "conversation_summaries.db"):
        if cand_db.exists():
            try:
                con = sqlite3.connect(f"file:{cand_db}?mode=ro", uri=True)
                row = con.execute("SELECT COUNT(*) FROM conversation_summaries").fetchone()
                pool_convs = int(row[0]) if row else 0
                con.close()
                break
            except Exception:
                pass

    pool_projects = 0
    pool_proj_dir = pool_dir / "projects"
    if pool_proj_dir.exists():
        try:
            pool_projects = sum(1 for p in pool_proj_dir.glob("*.json"))
        except Exception:
            pass

    auto_enabled = False
    interval_min = 10
    if isinstance(sync_cfg, dict) and sync_cfg:
        auto_enabled = bool(sync_cfg.get("autoSyncOnLaunch", sync_cfg.get("enabled", True)))
        interval_min = int(sync_cfg.get("backgroundIntervalMinutes", sync_cfg.get("intervalMinutes", 10)))

    return {
        "multiInstalled": AGY_MULTI_ROOT.exists(),
        "autoSyncEnabled": auto_enabled,
        "intervalMinutes": interval_min,
        "poolProjects": pool_projects,
        "poolConversations": pool_convs,
        "lastSyncAt": last_time,
        "lastLog": last_line,
    }


def build_agy_overview(procs: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
    aliases = settings.get("aliases", {})
    notes = settings.get("notes", {})
    multi_cfg = read_json_safe(AGY_MULTI_ROOT / "config.json", {})
    proxies_cfg = read_json_safe(AGY_MULTI_ROOT / "proxies.json", {})
    sync_status = get_agy_sync_status()

    # Build account roster: Main + any configured isolated Windows users
    roster: list[dict[str, Any]] = [
        {
            "user": CURRENT_USER,
            "defaultLabel": "Main Account",
            "isMain": True,
        }
    ]
    sub_accounts = multi_cfg.get("accounts", []) if isinstance(multi_cfg, dict) else []
    for idx, acc in enumerate(sub_accounts, start=2):
        if isinstance(acc, str):
            u = acc
            lbl = f"Account {idx} ({acc})"
        elif isinstance(acc, dict):
            u = acc.get("username") or acc.get("name") or ""
            lbl = acc.get("label") or f"Account {idx} ({u})"
        else:
            continue
        if u and u.lower() != CURRENT_USER.lower():
            roster.append({"user": u, "defaultLabel": lbl, "isMain": False})

    # Also auto-discover any AgyAcc* telemetry files or local users referenced in proxies.json
    known_low = {r["user"].lower() for r in roster}
    if isinstance(proxies_cfg, dict):
        acc_map = proxies_cfg.get("accounts", {})
        if isinstance(acc_map, dict):
            for u in acc_map.keys():
                if u.lower() not in known_low:
                    roster.append({"user": u, "defaultLabel": f"Antigravity ({u})", "isMain": False})
                    known_low.add(u.lower())

    # Also check Windows credential xmls under %LOCALAPPDATA%\AntigravityMulti\creds
    creds_dir = LOCAL_APPDATA / "AntigravityMulti" / "creds"
    if creds_dir.exists():
        for xml in sorted(creds_dir.glob("*.xml")):
            u = xml.stem
            if u.lower() not in known_low:
                roster.append({"user": u, "defaultLabel": f"Antigravity ({u})", "isMain": False})
                known_low.add(u.lower())

    agy_procs = [p for p in procs if p.get("name", "").lower() in ("antigravity.exe", "language_server.exe")]
    bridge_installed_main = (USER_PROFILE / ".gemini" / "config" / "plugins" / "ai-multi-cockpit-bridge" / "plugin.json").exists()

    default_proxy = ""
    if isinstance(proxies_cfg, dict):
        default_proxy = proxies_cfg.get("defaultProxy") or proxies_cfg.get("default") or ""

    items = []
    for r in roster:
        u = r["user"]
        key = f"antigravity:{u}"
        user_procs = [p for p in agy_procs if p.get("owner", "").lower() == u.lower()]
        ls_running = any(p.get("name", "").lower() == "language_server.exe" for p in user_procs)
        running = len(user_procs) > 0

        tele = read_agy_telemetry(u)
        proj_cnt = (tele or {}).get("projectsCount")
        conv_cnt = (tele or {}).get("conversationsCount")
        if r["isMain"]:
            p_c, c_c = count_agy_local_stats(USER_PROFILE)
            if p_c is not None and (proj_cnt is None or proj_cnt == 0):
                proj_cnt = p_c
            if c_c is not None and conv_cnt is None:
                conv_cnt = c_c

        acc_proxy = default_proxy
        if isinstance(proxies_cfg, dict):
            am = proxies_cfg.get("accounts", {})
            if isinstance(am, dict) and u in am:
                val = am[u]
                if isinstance(val, str):
                    acc_proxy = val
                elif isinstance(val, dict):
                    acc_proxy = val.get("proxy") or val.get("httpProxy") or acc_proxy

        items.append(
            {
                "id": key,
                "tool": "antigravity",
                "name": u,
                "label": aliases.get(key) or r["defaultLabel"],
                "note": notes.get(key, ""),
                "isMain": r["isMain"],
                "running": running,
                "languageServerRunning": ls_running,
                "processCount": len(user_procs),
                "proxy": acc_proxy,
                "projectsCount": proj_cnt,
                "conversationsCount": conv_cnt,
                "bridgeInstalled": bool(tele) or (r["isMain"] and bridge_installed_main),
                "updatedAt": (tele or {}).get("updatedAt"),
                "planTier": (tele or {}).get("planTier") or "",
                "cloudPaygo": bool((tele or {}).get("cloudPaygo", False)),
                "emailMasked": (tele or {}).get("emailMasked") or "",
                "quotaGroups": (tele or {}).get("quotaGroups") or [],
            }
        )

    return {
        "installed": (LOCAL_APPDATA / "Programs" / "antigravity" / "Antigravity.exe").exists() or AGY_MULTI_ROOT.exists(),
        "multiInstalled": sync_status["multiInstalled"],
        "bridgeInstalledMain": bridge_installed_main,
        "sync": sync_status,
        "accounts": items,
    }


def build_full_overview() -> dict[str, Any]:
    settings = load_settings()
    procs = get_running_processes()
    agy = build_agy_overview(procs, settings)
    codex = build_codex_overview(procs, settings)

    total_accounts = len(agy["accounts"]) + len(codex["accounts"])
    running_accounts = sum(1 for a in agy["accounts"] if a["running"]) + sum(1 for c in codex["accounts"] if c["running"])

    low_quota_alerts = 0
    for a in agy["accounts"]:
        for g in a.get("quotaGroups") or []:
            for b in g.get("buckets") or []:
                pct = b.get("remainingPercent")
                if isinstance(pct, (int, float)) and pct <= 20:
                    low_quota_alerts += 1
    for c in codex["accounts"]:
        rl = c.get("rateLimits") or {}
        for wk in ("primary", "secondary"):
            w = rl.get(wk)
            if isinstance(w, dict) and isinstance(w.get("remainingPercent"), (int, float)) and w["remainingPercent"] <= 20:
                low_quota_alerts += 1

    return {
        "version": APP_VERSION,
        "generatedAt": utc_now_iso(),
        "summary": {
            "totalAccounts": total_accounts,
            "runningAccounts": running_accounts,
            "antigravityCount": len(agy["accounts"]),
            "codexCount": len(codex["accounts"]),
            "lowQuotaAlerts": low_quota_alerts,
        },
        "settings": settings,
        "antigravity": agy,
        "codex": codex,
    }


# ---------------------------------------------------------------------------
# Action Handlers
# ---------------------------------------------------------------------------

def launch_antigravity_account(account_name: str) -> dict[str, Any]:
    if account_name.lower() == CURRENT_USER.lower():
        # Launch main Antigravity
        launcher_cmd = LOCAL_APPDATA / "AntigravityLauncher" / "Antigravity-Proxy.cmd"
        agy_exe = LOCAL_APPDATA / "Programs" / "antigravity" / "Antigravity.exe"
        if launcher_cmd.exists():
            subprocess.Popen(
                ["cmd.exe", "/c", str(launcher_cmd)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return {"ok": True, "launched": account_name, "via": "launcher"}
        if agy_exe.exists():
            subprocess.Popen([str(agy_exe)])
            return {"ok": True, "launched": account_name, "via": "direct"}
        return {"ok": False, "error": "Antigravity.exe not found for current user"}

    silent_vbs = AGY_MULTI_ROOT / "SilentLaunch.vbs"
    host_ps1 = AGY_MULTI_ROOT / "Host-Launch.ps1"
    if silent_vbs.exists():
        subprocess.Popen(["wscript.exe", str(silent_vbs), account_name])
        return {"ok": True, "launched": account_name, "via": "SilentLaunch.vbs"}
    if host_ps1.exists():
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(host_ps1), "-Account", account_name],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"ok": True, "launched": account_name, "via": "Host-Launch.ps1"}
    return {"ok": False, "error": f"AntigravityMulti launcher not found in {AGY_MULTI_ROOT}"}


def trigger_antigravity_sync() -> dict[str, Any]:
    tick_ps1 = AGY_MULTI_ROOT / "AutoSync-Tick.ps1"
    if not tick_ps1.exists():
        return {"ok": False, "error": f"AutoSync-Tick.ps1 not found in {AGY_MULTI_ROOT}"}
    rc, out, err = run_powershell(["-File", str(tick_ps1)], timeout=90)
    return {
        "ok": rc == 0,
        "exitCode": rc,
        "output": (out.strip() or err.strip())[-600:],
    }


def install_antigravity_bridge() -> dict[str, Any]:
    if not BRIDGE_INSTALL_SCRIPT.exists():
        return {"ok": False, "error": "Install-AgyBridge.ps1 not found"}
    rc, out, err = run_powershell(["-File", str(BRIDGE_INSTALL_SCRIPT)], timeout=60)
    return {
        "ok": rc == 0,
        "exitCode": rc,
        "output": (out.strip() or err.strip())[-800:],
    }


def run_codex_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    if not CODEX_SCRIPT.exists():
        return {"ok": False, "error": "Codex-Multi.ps1 not found"}
    ps_args = ["-File", str(CODEX_SCRIPT), "-Action", action, "-Json"]
    name = str(params.get("name", "default")).strip()
    if name:
        ps_args += ["-Name", name]
    if params.get("label"):
        ps_args += ["-Label", str(params["label"])]
    if params.get("proxy"):
        ps_args += ["-Proxy", str(params["proxy"])]
    if params.get("workspace"):
        ps_args += ["-Workspace", str(params["workspace"])]
    if action in ("Create", "SyncShared"):
        if params.get("shareConfig") is False:
            ps_args += ["-NoShareConfig"]
        if params.get("shareSkills") is False:
            ps_args += ["-NoShareSkills"]
        if params.get("shareAgentsMd") is False:
            ps_args += ["-NoShareAgentsMd"]

    rc, out, err = run_powershell(ps_args, timeout=30)
    if rc != 0:
        return {"ok": False, "error": (err.strip() or out.strip() or f"Exit code {rc}")[:500]}
    try:
        return json.loads(out.strip())
    except Exception:
        return {"ok": True, "output": out.strip()[:400]}


def refresh_codex_quotas(target_profile: str | None = None) -> dict[str, Any]:
    profiles = get_codex_profiles_list()
    if target_profile:
        profiles = [p for p in profiles if p["name"] == target_profile]
        if not profiles:
            return {"ok": False, "error": f"Profile '{target_profile}' not found"}

    results: dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(profiles)))) as pool:
        futs = {pool.submit(query_codex_live_quota, p): p["name"] for p in profiles}
        for fut in concurrent.futures.as_completed(futs):
            pname = futs[fut]
            try:
                results[pname] = fut.result()
            except Exception as exc:
                results[pname] = {"ok": False, "error": str(exc)}
    return {"ok": True, "refreshed": list(results.keys()), "results": results}


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class CockpitHandler(BaseHTTPRequestHandler):
    server_version = f"AIMultiCockpit/{APP_VERSION}"

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet console unless --verbose
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    def _valid_host(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host.startswith("127.0.0.1:") or host.startswith("localhost:") or host in ("127.0.0.1", "localhost")

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 1_048_576:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _check_csrf(self) -> bool:
        tok = self.headers.get("X-Cockpit-Token", "")
        return secrets.compare_digest(tok, SESSION_TOKEN)

    def do_GET(self) -> None:
        if not self._valid_host():
            self._send_json({"ok": False, "error": "Invalid Host header"}, 403)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json({"ok": True, "app": "ai-multi-cockpit", "version": APP_VERSION})
            return

        if path == "/api/overview":
            try:
                self._send_json(build_full_overview())
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, 500)
            return

        if path == "/api/config":
            self._send_json({"ok": True, "settings": load_settings()})
            return

        # Serve static web UI
        if path == "/" or path == "/index.html":
            idx = WEB_DIR / "index.html"
            if not idx.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Web UI missing")
                return
            html = idx.read_text(encoding="utf-8").replace("__COCKPIT_TOKEN__", SESSION_TOKEN)
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        rel = path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        ctype, _ = mimetypes.guess_type(str(target))
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        if not self._valid_host() or not self._check_csrf():
            self._send_json({"ok": False, "error": "Forbidden"}, 403)
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body_json()

        try:
            if path == "/api/codex/refresh":
                prof = body.get("profile") or None
                self._send_json(refresh_codex_quotas(prof))
                return

            if path == "/api/codex/create":
                self._send_json(run_codex_action("Create", body))
                return

            if path == "/api/codex/launch":
                mode = str(body.get("mode", "desktop")).lower()
                action = {"desktop": "LaunchDesktop", "cli": "LaunchCli", "login": "Login"}.get(mode, "LaunchDesktop")
                res = run_codex_action(action, body)
                with _cache_lock:
                    _process_cache["ts"] = 0.0
                self._send_json(res)
                return

            if path == "/api/codex/shortcut":
                self._send_json(run_codex_action("CreateShortcut", body))
                return

            if path == "/api/codex/sync":
                self._send_json(run_codex_action("SyncShared", {"name": body.get("name", "all")}))
                return

            if path == "/api/codex/delete":
                self._send_json(run_codex_action("Remove", body))
                return

            if path == "/api/antigravity/launch":
                acc = str(body.get("account", "")).strip()
                if not acc:
                    self._send_json({"ok": False, "error": "Missing account"}, 400)
                    return
                res = launch_antigravity_account(acc)
                with _cache_lock:
                    _process_cache["ts"] = 0.0
                self._send_json(res)
                return

            if path == "/api/antigravity/sync":
                self._send_json(trigger_antigravity_sync())
                return

            if path == "/api/antigravity/install-bridge":
                self._send_json(install_antigravity_bridge())
                return

            if path == "/api/config":
                updated = save_settings(body)
                self._send_json({"ok": True, "settings": updated})
                return

            if path == "/api/shutdown":
                self._send_json({"ok": True, "message": "Shutting down"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            self._send_json({"ok": False, "error": "Unknown endpoint"}, 404)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, 500)


def main() -> int:
    ensure_dirs()
    parser = argparse.ArgumentParser(description="AI Multi Cockpit local dashboard server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("COCKPIT_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), CockpitHandler)
    httpd.verbose = args.verbose  # type: ignore[attr-defined]
    print(f"AI Multi Cockpit v{APP_VERSION} listening on http://127.0.0.1:{args.port}", flush=True)

    # Background warm refresh for Codex quotas on startup
    def _warmup() -> None:
        try:
            refresh_codex_quotas(None)
        except Exception:
            pass

    threading.Thread(target=_warmup, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

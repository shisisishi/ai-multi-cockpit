# AI Multi Cockpit

**English** | [简体中文](README.md)

A zero-dependency Windows **side-by-side multi-account launcher & Cockpit-style quota dashboard** for **Google Antigravity** and **OpenAI Codex (Desktop & CLI)**.

> Seamlessly integrates with [antigravity-multi-windows](https://github.com/shisisishi/antigravity-multi-windows) when installed, and also works out-of-the-box on single-account setups.

---

## Key Features

### 1. Cockpit-Style Standalone Desktop App (Zero External Dependencies)
- **Frameless Desktop App Shell**: Served by a pure Python 3 stdlib backend (`127.0.0.1` only) and opened in an isolated Edge/Chrome `--app` window — launches cleanly from a desktop shortcut with no browser address bar or console flash.
- **Live Multi-Account Quota Overview**:
  - **Antigravity**: Uses a sanctioned Antigravity plugin sidecar (`ai-multi-cockpit-bridge`) to report each account's plan tier (`Google AI Pro`, `Cloud PAYG`, etc.), per-pool **5-hour** & **weekly** remaining quotas, and live reset countdowns.
  - **OpenAI Codex**: Queries official `codex app-server` JSON-RPC concurrently per profile (`CODEX_HOME`) to display plan tier (`Plus` / `Pro` / `Team` / `Free`), **5-hour** & **weekly** remaining quotas, reset countdowns, extra model pools, and credit balances.
- **Health & Sync Monitoring**: Live running state & process counts, project/conversation/session counters, Antigravity sync pool status, and `<= 20%` low-quota alerts.
- **Privacy & Personalization**: One-click **Privacy Blur Mode** (blurs usernames and masked emails for screenshots), EN/ZH toggle, Dark/Light theme, and custom aliases/notes.

### 2. OpenAI Codex Side-by-Side Multi-Account (Zero UAC)
- **True Concurrent Codex Desktop & CLI**: Combines official `CODEX_HOME` and Chromium `--user-data-dir` isolation so multiple Codex Desktop windows and Codex CLI terminals run **simultaneously side-by-side** with completely independent accounts — no extra Windows users and no UAC elevation required.
- **Optional Shared Config Sync**: Automatically copies/syncs non-secret `config.toml`, `skills/`, and `AGENTS.md` from default `~/.codex` while keeping `auth.json` and SQLite state strictly isolated.
- **Per-Profile Proxy & Desktop Shortcuts**: Optional dedicated HTTP/HTTPS proxy per profile and one-click silent desktop shortcuts.

### 3. Security & Compliance by Design
- **No Credential Scraping or Bypasses**: Never reads raw `auth.json` tokens or Windows Credential Manager secrets and never automates OAuth login. All authentication and quota queries strictly use official paths (`codex login`, `codex app-server`, and Antigravity's sanctioned sidecar plugin API).
- **Local-Only Protection**: Binds strictly to `127.0.0.1`, validates `Host` headers, and enforces a per-session random `X-Cockpit-Token` CSRF header on all `POST` endpoints.

---

## Project Layout

```text
ai-multi-cockpit/
├─ Launch-Cockpit.cmd / .vbs / .ps1     # Frameless desktop app launcher
├─ Install-DesktopShortcut.ps1          # Creates desktop shortcut (no UAC)
├─ cockpit/
│  ├─ server.py                         # Zero-dependency Python 3 backend & collectors
│  └─ web/                              # Cockpit UI (index.html / styles.css / app.js)
├─ codex/
│  ├─ Codex-Multi.ps1                   # Codex Desktop & CLI multi-account manager
│  ├─ SilentLaunchCodex.vbs             # Silent shortcut launcher
│  └─ Open-CodexManager.cmd             # Interactive CLI menu
├─ plugins/
│  └─ ai-multi-cockpit-bridge/          # Official Antigravity sidecar telemetry plugin
└─ scripts/
   └─ Install-AgyBridge.ps1             # Deploys bridge plugin to Main + sub-accounts
```

---

## Prerequisites

- Windows 10 / 11 (Windows PowerShell 5.1)
- Python 3.10+ (stdlib only — no `pip install` needed)
- Node.js 18+ (for the Antigravity telemetry sidecar plugin)
- Microsoft Edge or Google Chrome (for frameless `--app` desktop window mode)
- **OpenAI Codex** (MSIX Desktop app and/or CLI) and/or **Google Antigravity 2.0**

---

## Quick Start

1. Clone this repository or download the ZIP from [Releases](../../releases) and extract it to a permanent folder (e.g., `D:\Tools\ai-multi-cockpit`).
2. Run in PowerShell:

```powershell
# 1. Create the "AI Multi Cockpit" desktop shortcut (no UAC)
powershell -ExecutionPolicy Bypass -File .\Install-DesktopShortcut.ps1

# 2. Deploy the Antigravity quota bridge plugin (Main + any AntigravityMulti sub-accounts)
powershell -ExecutionPolicy Bypass -File .\scripts\Install-AgyBridge.ps1
```

3. Double-click **AI Multi Cockpit** on your desktop (or `Launch-Cockpit.cmd`).

---

## Codex Multi-Account CLI Reference

```powershell
# List all Codex profiles
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action List

# Create an isolated profile
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action Create -Name acc2 -Label "Codex Work"

# Sign in via official Codex OAuth flow
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action Login -Name acc2

# Launch Codex Desktop side-by-side
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action LaunchDesktop -Name acc2

# Launch Codex CLI side-by-side
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action LaunchCli -Name acc2

# Create a silent desktop shortcut
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action CreateShortcut -Name acc2

# Sync shared config.toml / skills / AGENTS.md from ~/.codex to all isolated profiles
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action SyncShared -Name all
```

Isolated profiles are stored under `%LOCALAPPDATA%\AIMultiCockpit\codex-profiles\<name>\`. Removing an isolated profile never touches `%USERPROFILE%\.codex`.

---

## License

[MIT License](LICENSE)

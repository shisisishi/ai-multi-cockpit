/**
 * AI Multi Cockpit — Official Antigravity Sidecar Telemetry Bridge
 *
 * Runs inside Antigravity's sanctioned plugin sidecar runtime using the host-provided
 * ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN environment variables.
 * Exports ONLY non-secret quota percentages, reset timestamps, plan tier, and counts.
 * Never reads or writes tokens, passwords, or raw email addresses.
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { homedir, userInfo } from 'node:os';
import { dirname, join } from 'node:path';

const POLL_MS = 30_000;
const USER_NAME = process.env.USERNAME || userInfo().username || 'unknown';
const HOME_DIR = homedir();
const PROGRAM_DATA = process.env.PROGRAMDATA || 'C:\\ProgramData';
const LOCAL_APPDATA = process.env.LOCALAPPDATA || join(HOME_DIR, 'AppData', 'Local');

function maskEmail(email) {
  if (!email || typeof email !== 'string' || !email.includes('@')) return '';
  const [local, domain] = email.split('@');
  if (!local || !domain) return '';
  const masked = local.length <= 2
    ? `${local[0]}***`
    : `${local.slice(0, 2)}***${local.slice(-1)}`;
  return `${masked}@${domain}`;
}

function safeCountProjects(dirPath) {
  try {
    if (!existsSync(dirPath)) return null;
    let cnt = 0;
    for (const f of readdirSync(dirPath)) {
      if (!f.endsWith('.json')) continue;
      try {
        const obj = JSON.parse(readFileSync(join(dirPath, f), 'utf8'));
        if (obj && !obj.sidecar) cnt += 1;
      } catch {}
    }
    return cnt;
  } catch {
    return null;
  }
}

function safeCountFiles(dirPath, suffix) {
  try {
    if (!existsSync(dirPath)) return null;
    return readdirSync(dirPath).filter(f => f.endsWith(suffix)).length;
  } catch {
    return null;
  }
}

function writeAtomic(filePath, payload) {
  try {
    const dir = dirname(filePath);
    if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    const tmp = `${filePath}.${process.pid}.tmp`;
    writeFileSync(tmp, JSON.stringify(payload, null, 2), 'utf8');
    renameSync(tmp, filePath);
    return true;
  } catch {
    return false;
  }
}

function normalizeGroups(rawGroups) {
  if (!Array.isArray(rawGroups)) return [];
  const order = { '5h': 0, weekly: 1 };
  return rawGroups.map(g => {
    const buckets = Array.isArray(g?.buckets) ? [...g.buckets] : [];
    buckets.sort((a, b) => (order[a?.window] ?? 2) - (order[b?.window] ?? 2));
    return {
      displayName: String(g?.displayName || g?.name || 'Pool').trim(),
      buckets: buckets.map(b => ({
        window: String(b?.window || ''),
        remainingPercent: Math.round(Math.max(0, Math.min(1, Number(b?.remainingFraction ?? 0))) * 100),
        resetTime: b?.resetTime || null,
      })),
    };
  });
}

async function rpcCall(lsAddr, csrf, method) {
  const res = await fetch(`http://${lsAddr}/exa.language_server_pb.LanguageServerService/${method}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-codeium-csrf-token': csrf,
    },
    body: '{}',
    signal: AbortSignal.timeout(4000),
  });
  if (!res.ok) return null;
  return res.json();
}

let consecutiveFailures = 0;
let latestSnapshot = null;

async function collectAndWrite() {
  const lsAddr = process.env.ANTIGRAVITY_LS_ADDRESS;
  const csrf = process.env.ANTIGRAVITY_CSRF_TOKEN;
  if (!lsAddr || !csrf) return;

  let quotaGroups = [];
  let cloudPaygo = false;
  let planTier = '';
  let emailMasked = '';
  let rpcOk = false;

  try {
    const qData = await rpcCall(lsAddr, csrf, 'RetrieveUserQuotaSummary');
    if (qData) {
      rpcOk = true;
      const groups = qData?.response?.groups ?? qData?.groups;
      quotaGroups = normalizeGroups(groups);
    }
  } catch {}

  try {
    const stData = await rpcCall(lsAddr, csrf, 'GetUserStatus');
    if (stData) {
      rpcOk = true;
      const us = stData?.userStatus || stData?.response?.userStatus || {};
      planTier = String(us?.userTier?.name || us?.userTier?.id || '').trim();
      cloudPaygo = us?.userTier?.id === 'agy-business-paygo-tier';
      emailMasked = maskEmail(us?.email || us?.userEmail || '');
    }
  } catch {}

  if (!rpcOk) {
    consecutiveFailures += 1;
    if (consecutiveFailures >= 6) process.exit(0);
    return;
  }
  consecutiveFailures = 0;

  const snapshot = {
    schemaVersion: 1,
    account: USER_NAME,
    planTier,
    cloudPaygo,
    emailMasked,
    projectsCount: safeCountProjects(join(HOME_DIR, '.gemini', 'config', 'projects')),
    conversationsCount: safeCountFiles(join(HOME_DIR, '.gemini', 'antigravity', 'conversations'), '.db'),
    quotaGroups,
    updatedAt: new Date().toISOString(),
  };
  latestSnapshot = snapshot;

  const fileName = `antigravity_${USER_NAME}.json`;
  const targets = [
    join(LOCAL_APPDATA, 'AIMultiCockpit', 'telemetry', fileName),
  ];
  const agyMultiRoot = join(PROGRAM_DATA, 'AntigravityMulti');
  if (existsSync(agyMultiRoot)) {
    targets.push(join(agyMultiRoot, 'sync_pool', 'telemetry', fileName));
    targets.push(join(agyMultiRoot, 'telemetry', fileName));
  }

  for (const t of targets) {
    writeAtomic(t, snapshot);
  }
}

// Optional lightweight health HTTP listener when host assigns a sidecar port
const webPort = Number(process.env.ANTIGRAVITY_SIDECAR_WEB_PORT || 0);
if (webPort > 0) {
  const srv = createServer((req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ ok: true, plugin: 'ai-multi-cockpit-bridge', snapshot: latestSnapshot }));
  });
  srv.listen(webPort, '127.0.0.1');
}

// Initial export + periodic heartbeat
collectAndWrite().catch(() => {});
setInterval(() => {
  collectAndWrite().catch(() => {});
}, POLL_MS);

// Keep alive quietly until Antigravity host exits
process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));

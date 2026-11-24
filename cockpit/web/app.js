(() => {
  const TOKEN = document.querySelector('meta[name="cockpit-token"]')?.content || '';

  const I18N = {
    zh: {
      subtitle: 'Antigravity & Codex 多账号并发控制台',
      tabAll: '全部',
      addCodex: '新增 Codex 账号',
      refreshQuota: '刷新额度',
      kpiAccounts: '已配置账号',
      kpiRunning: '正在运行',
      kpiAlerts: '低额度预警 (≤20%)',
      kpiAlertsSub: '5h / 周额度实时追踪',
      kpiSync: 'Antigravity 同步池',
      syncNow: '立即同步',
      installBridge: '安装/同步额度桥接插件',
      syncCodexShared: '同步共享 Skills/配置',
      running: '运行中',
      idle: '未启动',
      signedIn: '已登录',
      notSignedIn: '未登录',
      win5h: '5小时额度',
      winWeekly: '每周额度',
      left: '剩余',
      resetIn: '重置于',
      resetSoon: '即将重置',
      launch: '启动',
      desktop: '桌面端多开',
      cli: '终端 CLI',
      login: '登录',
      shortcut: '桌面快捷方式',
      refresh: '刷新',
      delete: '删除',
      noAgyQuota: '尚无额度快照（需安装桥接插件并启动该账号一次）',
      noCodexQuota: '暂无额度数据，点击刷新通过官方 codex app-server 拉取',
      cloudPaygo: '按量计费 (Cloud PAYG)',
      projects: '项目',
      convs: '对话',
      sessions: '会话',
      updated: '更新于',
      justNow: '刚刚',
      agoSec: '秒前',
      agoMin: '分钟前',
      agoHr: '小时前',
      modalAddTitle: '新增独立 Codex 账号配置',
      fieldProfileId: '配置 ID（字母/数字，如 acc2、work）',
      fieldLabel: '显示备注名称',
      fieldProxy: '专属代理（可选，留空继承系统）',
      optShareConfig: '复制默认 config.toml',
      optShareSkills: '同步默认 skills 目录',
      optShareAgents: '复制默认 AGENTS.md',
      optShortcut: '自动创建桌面快捷方式',
      optLogin: '创建后立即弹出官方登录终端 (codex login)',
      cancel: '取消',
      create: '创建配置',
      modalEditTitle: '编辑账号备注',
      fieldNote: '备忘标签（如用途 / 续费日）',
      save: '保存',
      confirmDelete: '确定删除独立 Codex 配置 "{name}" 吗？不会影响默认 ~/.codex。',
      syncPoolEmpty: '未安装多开同步池',
      autoSyncOn: '自动同步已启用',
    },
    en: {
      subtitle: 'Antigravity & Codex Side-by-Side Quota Cockpit',
      tabAll: 'All',
      addCodex: 'Add Codex Account',
      refreshQuota: 'Refresh Quotas',
      kpiAccounts: 'Configured Accounts',
      kpiRunning: 'Running Now',
      kpiAlerts: 'Low Quota Alerts (≤20%)',
      kpiAlertsSub: '5h & weekly windows tracked live',
      kpiSync: 'Antigravity Sync Pool',
      syncNow: 'Sync Now',
      installBridge: 'Install / Sync Quota Bridge',
      syncCodexShared: 'Sync Shared Skills/Config',
      running: 'Running',
      idle: 'Idle',
      signedIn: 'Signed In',
      notSignedIn: 'Not Signed In',
      win5h: '5-Hour',
      winWeekly: 'Weekly',
      left: 'left',
      resetIn: 'Resets in',
      resetSoon: 'Resetting',
      launch: 'Launch',
      desktop: 'Desktop',
      cli: 'CLI',
      login: 'Sign In',
      shortcut: 'Shortcut',
      refresh: 'Refresh',
      delete: 'Delete',
      noAgyQuota: 'No quota snapshot yet (install bridge plugin & open this account once)',
      noCodexQuota: 'No quota snapshot yet — click Refresh to query official codex app-server',
      cloudPaygo: 'Cloud Pay-As-You-Go',
      projects: 'projects',
      convs: 'chats',
      sessions: 'sessions',
      updated: 'Updated',
      justNow: 'just now',
      agoSec: 's ago',
      agoMin: 'm ago',
      agoHr: 'h ago',
      modalAddTitle: 'Add Isolated Codex Account',
      fieldProfileId: 'Profile ID (alphanumeric, e.g. acc2, work)',
      fieldLabel: 'Display Label',
      fieldProxy: 'Dedicated Proxy (optional)',
      optShareConfig: 'Copy default config.toml',
      optShareSkills: 'Sync default skills folder',
      optShareAgents: 'Copy default AGENTS.md',
      optShortcut: 'Create desktop shortcut',
      optLogin: 'Open official login terminal (codex login) right away',
      cancel: 'Cancel',
      create: 'Create Profile',
      modalEditTitle: 'Edit Account Label & Note',
      fieldNote: 'Note (purpose / billing day)',
      save: 'Save',
      confirmDelete: 'Delete isolated Codex profile "{name}"? Default ~/.codex is untouched.',
      syncPoolEmpty: 'Multi-sync pool not installed',
      autoSyncOn: 'Auto-sync active',
    },
  };

  let state = {
    lang: 'zh',
    theme: 'dark',
    privacy: false,
    filter: 'all',
    data: null,
    refreshing: false,
  };

  const $ = (sel) => document.querySelector(sel);
  const t = (key) => (I18N[state.lang] || I18N.zh)[key] || key;

  function esc(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toast(msg, kind = 'ok') {
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.textContent = msg;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), 3800);
  }

  async function apiGet(url) {
    const r = await fetch(url, { cache: 'no-store' });
    return r.json();
  }

  async function apiPost(url, body = {}) {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Cockpit-Token': TOKEN,
      },
      body: JSON.stringify(body),
    });
    return r.json();
  }

  function quotaTone(remPct) {
    if (remPct == null) return { text: '', fill: 'fill-good' };
    if (remPct <= 20) return { text: 'q-low', fill: 'fill-low' };
    if (remPct <= 50) return { text: 'q-warn', fill: 'fill-warn' };
    return { text: 'q-good', fill: 'fill-good' };
  }

  function formatCountdown(iso) {
    if (!iso) return '';
    const ms = new Date(iso).getTime() - Date.now();
    if (!Number.isFinite(ms)) return '';
    if (ms <= 0) return t('resetSoon');
    const sec = Math.floor(ms / 1000);
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (d > 0) return `${t('resetIn')} ${d}d ${h}h`;
    if (h > 0) return `${t('resetIn')} ${h}h ${m}m`;
    return `${t('resetIn')} ${m}m`;
  }

  function formatAge(iso) {
    if (!iso) return '--';
    const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
    if (!Number.isFinite(sec)) return '--';
    if (sec < 10) return t('justNow');
    if (sec < 60) return `${sec}${t('agoSec')}`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}${t('agoMin')}`;
    return `${Math.floor(min / 60)}${t('agoHr')}`;
  }

  function applyStaticI18n() {
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const k = el.getAttribute('data-i18n');
      if (k) el.textContent = t(k);
    });
    $('#btnLang').textContent = state.lang === 'zh' ? 'EN' : '中';
    $('#btnTheme').textContent = state.theme === 'dark' ? '☀' : '☾';
    document.documentElement.setAttribute('data-theme', state.theme);
    document.body.classList.toggle('privacy-on', state.privacy);
    $('#btnPrivacy').classList.toggle('active', state.privacy);
  }

  function renderAgyCard(acc) {
    const groups = acc.quotaGroups || [];
    let quotaHtml = '';
    if (acc.cloudPaygo && groups.length === 0) {
      quotaHtml = `<div class="quota-empty"><span class="badge badge-paygo">${esc(t('cloudPaygo'))}</span></div>`;
    } else if (groups.length === 0) {
      quotaHtml = `
        <div class="quota-empty">
          <span>${esc(t('noAgyQuota'))}</span>
          ${!acc.bridgeInstalled ? `<button class="btn-mini" data-action="install-bridge">${esc(t('installBridge'))}</button>` : ''}
        </div>`;
    } else {
      quotaHtml = groups.map((g) => {
        const buckets = (g.buckets || []).map((b) => {
          const pct = Math.round(b.remainingPercent ?? 0);
          const tone = quotaTone(pct);
          const wLabel = b.window === 'weekly' ? t('winWeekly') : b.window === '5h' ? t('win5h') : (b.window || '');
          const cd = b.resetTime ? `<span class="cd" data-reset="${esc(b.resetTime)}">${esc(formatCountdown(b.resetTime))}</span>` : '';
          return `
            <div class="bucket-mini">
              <div class="bucket-mini-top">
                <span>${esc(wLabel)}</span>
                <strong class="${tone.text}">${pct}%</strong>
              </div>
              <div class="bar-track"><div class="bar-fill ${tone.fill}" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>
              <div class="win-reset">${cd}</div>
            </div>`;
        }).join('');
        return `
          <div class="pool-row">
            <div class="pool-head"><span>${esc(g.displayName || g.name)}</span></div>
            <div class="pool-buckets">${buckets}</div>
          </div>`;
      }).join('');
    }

    const planBadge = acc.planTier ? `<span class="badge badge-plan">${esc(acc.planTier)}</span>` : '';
    const subParts = [
      `<span class="sensitive">${esc(acc.name)}</span>`,
      acc.emailMasked ? `<span class="sensitive">${esc(acc.emailMasked)}</span>` : '',
      acc.note ? `<span class="card-note">· ${esc(acc.note)}</span>` : '',
    ].filter(Boolean).join(' ');

    return `
      <article class="acc-card ${acc.running ? 'is-running' : ''}">
        <div class="card-head">
          <div class="card-title-block">
            <div class="card-title-row">
              <span class="card-title">${esc(acc.label)}</span>
              ${planBadge}
              <button class="edit-btn" data-action="edit-meta" data-id="${esc(acc.id)}" data-alias="${esc(acc.label)}" data-note="${esc(acc.note)}" title="Edit">✎</button>
            </div>
            <div class="card-sub">${subParts}</div>
          </div>
          <div class="status-pill ${acc.running ? 'running' : ''}">
            <span class="status-dot"></span>
            ${acc.running ? `${t('running')} (${acc.processCount})` : t('idle')}
          </div>
        </div>

        <div class="quota-box">${quotaHtml}</div>

        <div class="card-meta">
          <div class="meta-chips">
            ${acc.projectsCount != null ? `<span>📁 ${acc.projectsCount} ${t('projects')}</span>` : ''}
            ${acc.conversationsCount != null ? `<span>💬 ${acc.conversationsCount} ${t('convs')}</span>` : ''}
            ${acc.proxy ? `<span>🌐 ${esc(acc.proxy)}</span>` : ''}
          </div>
          <span>${acc.updatedAt ? `${t('updated')} ${formatAge(acc.updatedAt)}` : ''}</span>
        </div>

        <div class="card-actions">
          <button class="btn btn-sm btn-primary" data-action="agy-launch" data-account="${esc(acc.name)}">▶ ${t('launch')}</button>
          <button class="btn btn-sm btn-ghost" data-action="agy-sync">⇄ ${t('syncNow')}</button>
        </div>
      </article>`;
  }

  function renderCodexWindow(label, win) {
    if (!win) {
      return `
        <div class="win-block">
          <div class="win-top"><span class="win-label">${esc(label)}</span><span class="win-pct">--</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:0%"></div></div>
          <div class="win-reset">--</div>
        </div>`;
    }
    const pct = Math.round(win.remainingPercent ?? 0);
    const tone = quotaTone(pct);
    const cd = win.resetsAt ? `<span class="cd" data-reset="${esc(win.resetsAt)}">${esc(formatCountdown(win.resetsAt))}</span>` : '';
    return `
      <div class="win-block">
        <div class="win-top">
          <span class="win-label">${esc(label)}</span>
          <span class="win-pct ${tone.text}">${pct}% <small style="font-weight:500;font-size:11px;opacity:.75">${t('left')}</small></span>
        </div>
        <div class="bar-track"><div class="bar-fill ${tone.fill}" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>
        <div class="win-reset">${cd}</div>
      </div>`;
  }

  function renderCodexCard(acc) {
    const rl = acc.rateLimits;
    let quotaHtml = '';
    if (!acc.signedIn && !rl) {
      quotaHtml = `
        <div class="quota-empty">
          <span class="badge badge-warn">${t('notSignedIn')}</span>
          <button class="btn-mini" data-action="codex-launch" data-mode="login" data-name="${esc(acc.name)}">${t('login')}</button>
        </div>`;
    } else if (!rl) {
      quotaHtml = `
        <div class="quota-empty">
          <span>${esc(t('noCodexQuota'))}</span>
          <button class="btn-mini" data-action="codex-refresh" data-name="${esc(acc.name)}">${t('refresh')}</button>
        </div>`;
    } else {
      const credits = rl.credits;
      const creditLine = credits && (credits.unlimited || credits.hasCredits)
        ? `<div class="win-reset">Credits: ${credits.unlimited ? 'Unlimited' : esc(credits.balance)}</div>`
        : '';
      const extras = (acc.extraLimits || []).map((ex) => `
        <div class="pool-row" style="margin-top:6px;padding-top:6px;border-top:1px dashed var(--border);border-bottom:none;padding-bottom:0">
          <div class="pool-head"><span>${esc(ex.limitName || ex.limitId)}</span></div>
          <div class="codex-windows">
            ${renderCodexWindow(t('win5h'), ex.primary)}
            ${renderCodexWindow(t('winWeekly'), ex.secondary)}
          </div>
        </div>`).join('');
      quotaHtml = `
        <div class="codex-windows">
          ${renderCodexWindow(t('win5h'), rl.primary)}
          ${renderCodexWindow(t('winWeekly'), rl.secondary)}
        </div>
        ${creditLine}
        ${extras}`;
    }

    const planBadge = acc.planType
      ? `<span class="badge badge-codex-plan">${esc(acc.planType)}</span>`
      : (!acc.signedIn ? `<span class="badge badge-warn">${t('notSignedIn')}</span>` : '');

    const subParts = [
      `<span class="sensitive">${esc(acc.name)}</span>`,
      acc.emailMasked ? `<span class="sensitive">${esc(acc.emailMasked)}</span>` : '',
      acc.workspaceName ? `<span>· ${esc(acc.workspaceName)}</span>` : '',
      acc.note ? `<span class="card-note">· ${esc(acc.note)}</span>` : '',
    ].filter(Boolean).join(' ');

    return `
      <article class="acc-card ${acc.running ? 'is-running' : ''}">
        <div class="card-head">
          <div class="card-title-block">
            <div class="card-title-row">
              <span class="card-title">${esc(acc.label)}</span>
              ${planBadge}
              <button class="edit-btn" data-action="edit-meta" data-id="${esc(acc.id)}" data-alias="${esc(acc.label)}" data-note="${esc(acc.note)}" title="Edit">✎</button>
            </div>
            <div class="card-sub">${subParts}</div>
          </div>
          <div class="status-pill ${acc.running ? 'running' : ''}">
            <span class="status-dot"></span>
            ${acc.running ? `${t('running')} (${acc.processCount})` : t('idle')}
          </div>
        </div>

        <div class="quota-box">${quotaHtml}</div>

        <div class="card-meta">
          <div class="meta-chips">
            <span>💬 ${acc.sessionCount} ${t('sessions')}</span>
            <span>${acc.mode === 'default' ? '~/.codex' : 'CODEX_HOME'}</span>
            ${acc.proxy ? `<span>🌐 ${esc(acc.proxy)}</span>` : ''}
          </div>
          <span>${acc.updatedAt ? `${t('updated')} ${formatAge(acc.updatedAt)}` : ''}</span>
        </div>

        <div class="card-actions">
          <button class="btn btn-sm btn-primary" data-action="codex-launch" data-mode="desktop" data-name="${esc(acc.name)}">▶ ${t('desktop')}</button>
          <button class="btn btn-sm btn-ghost" data-action="codex-launch" data-mode="cli" data-name="${esc(acc.name)}">&gt;_ ${t('cli')}</button>
          <button class="btn btn-sm btn-ghost" data-action="codex-refresh" data-name="${esc(acc.name)}">↻ ${t('refresh')}</button>
          <button class="btn btn-sm btn-ghost" data-action="codex-launch" data-mode="login" data-name="${esc(acc.name)}">🔑 ${t('login')}</button>
          <button class="btn btn-sm btn-ghost" data-action="codex-shortcut" data-name="${esc(acc.name)}" title="${t('shortcut')}">📌</button>
          <span class="spacer"></span>
          ${acc.mode === 'isolated' ? `<button class="btn btn-sm btn-ghost btn-danger" data-action="codex-delete" data-name="${esc(acc.name)}">🗑</button>` : ''}
        </div>
      </article>`;
  }

  function render() {
    applyStaticI18n();
    const d = state.data;
    if (!d) return;

    $('#verTag').textContent = `v${d.version}`;
    $('#kpiTotal').textContent = d.summary.totalAccounts;
    $('#kpiBreakdown').textContent = `Antigravity ${d.summary.antigravityCount} · Codex ${d.summary.codexCount}`;
    $('#kpiRunning').textContent = d.summary.runningAccounts;
    $('#kpiLastCheck').textContent = `${t('updated')} ${formatAge(d.generatedAt)}`;

    const alertsEl = $('#kpiAlerts');
    alertsEl.textContent = d.summary.lowQuotaAlerts;
    alertsEl.className = `kpi-value ${d.summary.lowQuotaAlerts > 0 ? 'accent-red' : 'accent-green'}`;

    const sync = d.antigravity.sync || {};
    if (sync.multiInstalled) {
      $('#kpiSyncVal').textContent = `${sync.poolProjects} ${t('projects')} · ${sync.poolConversations} ${t('convs')}`;
      $('#kpiSyncFoot').textContent = sync.lastSyncAt
        ? `${sync.autoSyncEnabled ? t('autoSyncOn') : ''} · ${formatAge(sync.lastSyncAt)}`
        : t('autoSyncOn');
    } else {
      $('#kpiSyncVal').textContent = t('syncPoolEmpty');
      $('#kpiSyncFoot').textContent = '';
    }

    const agyAccs = d.antigravity.accounts || [];
    const codexAccs = d.codex.accounts || [];
    $('#agyCountPill').textContent = agyAccs.length;
    $('#codexCountPill').textContent = codexAccs.length;

    $('#agyCards').innerHTML = agyAccs.map(renderAgyCard).join('');
    $('#codexCards').innerHTML = codexAccs.map(renderCodexCard).join('');

    $('#sectionAntigravity').classList.toggle('hidden', state.filter === 'codex');
    $('#sectionCodex').classList.toggle('hidden', state.filter === 'antigravity');
  }

  async function loadOverview(silent = false) {
    try {
      const data = await apiGet('/api/overview');
      if (data.settings && !state.data) {
        state.lang = data.settings.language || 'zh';
        state.theme = data.settings.theme || 'dark';
        state.privacy = !!data.settings.privacyMode;
      }
      state.data = data;
      render();
    } catch (e) {
      if (!silent) toast(`Failed to load overview: ${e.message}`, 'err');
    }
  }

  async function persistSettings(patch) {
    try { await apiPost('/api/config', patch); } catch {}
  }

  async function refreshAllQuotas() {
    if (state.refreshing) return;
    state.refreshing = true;
    $('#refreshIcon').classList.add('spinning');
    try {
      const res = await apiPost('/api/codex/refresh', {});
      await loadOverview(true);
      if (res.ok) toast(state.lang === 'zh' ? '已通过官方接口刷新所有 Codex 额度' : 'Refreshed all Codex quotas');
      else toast(res.error || 'Refresh failed', 'err');
    } finally {
      state.refreshing = false;
      $('#refreshIcon').classList.remove('spinning');
    }
  }

  // Global event delegation
  document.addEventListener('click', async (ev) => {
    const tab = ev.target.closest('.tab-btn');
    if (tab) {
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      tab.classList.add('active');
      state.filter = tab.dataset.filter;
      render();
      return;
    }

    const closeBtn = ev.target.closest('[data-close]');
    if (closeBtn) {
      document.getElementById(closeBtn.dataset.close)?.classList.add('hidden');
      return;
    }

    const actBtn = ev.target.closest('[data-action]');
    if (!actBtn) return;
    const action = actBtn.dataset.action;

    if (action === 'edit-meta') {
      const f = $('#formEditMeta');
      f.elements.id.value = actBtn.dataset.id;
      f.elements.alias.value = actBtn.dataset.alias || '';
      f.elements.note.value = actBtn.dataset.note || '';
      $('#modalEditMeta').classList.remove('hidden');
      return;
    }

    if (action === 'agy-launch') {
      const acc = actBtn.dataset.account;
      const res = await apiPost('/api/antigravity/launch', { account: acc });
      toast(res.ok ? `Antigravity [${acc}] launched` : (res.error || 'Launch failed'), res.ok ? 'ok' : 'err');
      setTimeout(() => loadOverview(true), 2500);
      return;
    }

    if (action === 'agy-sync') {
      toast(state.lang === 'zh' ? '正在执行增量同步...' : 'Running incremental sync...');
      const res = await apiPost('/api/antigravity/sync', {});
      toast(res.ok ? (state.lang === 'zh' ? '同步完成' : 'Sync completed') : (res.error || 'Sync failed'), res.ok ? 'ok' : 'err');
      loadOverview(true);
      return;
    }

    if (action === 'install-bridge') {
      toast(state.lang === 'zh' ? '正在安装/同步 Antigravity 额度桥接插件...' : 'Installing Antigravity quota bridge...');
      const res = await apiPost('/api/antigravity/install-bridge', {});
      toast(res.ok ? (state.lang === 'zh' ? '桥接插件已部署，重启或开启账号后自动上报额度' : 'Bridge deployed') : (res.error || 'Failed'), res.ok ? 'ok' : 'err');
      loadOverview(true);
      return;
    }

    if (action === 'codex-launch') {
      const name = actBtn.dataset.name;
      const mode = actBtn.dataset.mode;
      const res = await apiPost('/api/codex/launch', { name, mode });
      toast(res.ok ? `Codex [${name}] (${mode}) launched` : (res.error || 'Launch failed'), res.ok ? 'ok' : 'err');
      setTimeout(() => loadOverview(true), 2500);
      return;
    }

    if (action === 'codex-refresh') {
      const name = actBtn.dataset.name;
      actBtn.disabled = true;
      try {
        const res = await apiPost('/api/codex/refresh', { profile: name });
        await loadOverview(true);
        toast(res.ok ? `Codex [${name}] quota refreshed` : (res.error || 'Failed'), res.ok ? 'ok' : 'err');
      } finally {
        actBtn.disabled = false;
      }
      return;
    }

    if (action === 'codex-shortcut') {
      const name = actBtn.dataset.name;
      const res = await apiPost('/api/codex/shortcut', { name });
      toast(res.ok ? `Desktop shortcut created for [${name}]` : (res.error || 'Failed'), res.ok ? 'ok' : 'err');
      return;
    }

    if (action === 'codex-delete') {
      const name = actBtn.dataset.name;
      if (!confirm(t('confirmDelete').replace('{name}', name))) return;
      const res = await apiPost('/api/codex/delete', { name });
      toast(res.ok ? `Removed [${name}]` : (res.error || 'Delete failed'), res.ok ? 'ok' : 'err');
      loadOverview(true);
    }
  });

  // Topbar & section controls
  $('#btnRefreshQuotas').addEventListener('click', refreshAllQuotas);
  $('#btnAddCodex').addEventListener('click', () => $('#modalAddCodex').classList.remove('hidden'));
  $('#btnAddCodex2').addEventListener('click', () => $('#modalAddCodex').classList.remove('hidden'));

  $('#btnPrivacy').addEventListener('click', () => {
    state.privacy = !state.privacy;
    applyStaticI18n();
    persistSettings({ privacyMode: state.privacy });
  });
  $('#btnLang').addEventListener('click', () => {
    state.lang = state.lang === 'zh' ? 'en' : 'zh';
    render();
    persistSettings({ language: state.lang });
  });
  $('#btnTheme').addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    applyStaticI18n();
    persistSettings({ theme: state.theme });
  });

  $('#btnSyncAgy').addEventListener('click', async () => {
    toast(state.lang === 'zh' ? '正在执行增量同步...' : 'Running sync...');
    const res = await apiPost('/api/antigravity/sync', {});
    toast(res.ok ? (state.lang === 'zh' ? '同步完成' : 'Sync completed') : (res.error || 'Sync failed'), res.ok ? 'ok' : 'err');
    loadOverview(true);
  });
  $('#btnSyncAgy2').addEventListener('click', () => $('#btnSyncAgy').click());

  $('#btnInstallBridge').addEventListener('click', async () => {
    toast(state.lang === 'zh' ? '正在部署额度桥接插件...' : 'Deploying bridge plugin...');
    const res = await apiPost('/api/antigravity/install-bridge', {});
    toast(res.ok ? (state.lang === 'zh' ? '桥接插件部署完成' : 'Bridge deployed') : (res.error || 'Failed'), res.ok ? 'ok' : 'err');
    loadOverview(true);
  });

  $('#btnSyncCodexShared').addEventListener('click', async () => {
    const res = await apiPost('/api/codex/sync', { name: 'all' });
    toast(res.ok ? (state.lang === 'zh' ? '已同步共享 Skills/配置到所有 Codex 独立配置' : 'Synced shared files') : (res.error || 'Failed'), res.ok ? 'ok' : 'err');
  });

  // Add Codex Form
  $('#formAddCodex').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const payload = {
      name: f.elements.name.value.trim(),
      label: f.elements.label.value.trim(),
      proxy: f.elements.proxy.value.trim(),
      shareConfig: f.elements.shareConfig.checked,
      shareSkills: f.elements.shareSkills.checked,
      shareAgentsMd: f.elements.shareAgentsMd.checked,
    };
    const res = await apiPost('/api/codex/create', payload);
    if (!res.ok) {
      toast(res.error || 'Create failed', 'err');
      return;
    }
    if (f.elements.createShortcut.checked) {
      await apiPost('/api/codex/shortcut', { name: payload.name });
    }
    if (f.elements.openLogin.checked) {
      await apiPost('/api/codex/launch', { name: payload.name, mode: 'login' });
    }
    $('#modalAddCodex').classList.add('hidden');
    f.reset();
    toast(state.lang === 'zh' ? `已创建 Codex 配置 [${payload.name}]` : `Created Codex profile [${payload.name}]`);
    loadOverview(true);
  });

  // Edit Meta Form
  $('#formEditMeta').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const id = f.elements.id.value;
    const alias = f.elements.alias.value.trim();
    const note = f.elements.note.value.trim();
    const res = await apiPost('/api/config', { aliases: { [id]: alias }, notes: { [id]: note } });
    if (res.ok) {
      $('#modalEditMeta').classList.add('hidden');
      loadOverview(true);
      toast(state.lang === 'zh' ? '已保存' : 'Saved');
    }
  });

  // Tick reset countdowns every 30s & poll overview every 20s
  setInterval(() => {
    document.querySelectorAll('.cd[data-reset]').forEach((el) => {
      el.textContent = formatCountdown(el.dataset.reset);
    });
  }, 30000);
  setInterval(() => loadOverview(true), 20000);

  loadOverview();
})();

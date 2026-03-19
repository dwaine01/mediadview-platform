// MediaView Dashboard — Application Logic
const API = '/api';
let token = localStorage.getItem('mv_t');
let user = JSON.parse(localStorage.getItem('mv_u') || 'null');

// ===== API Helper =====
async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { doLogout(); throw new Error('Session expired'); }
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || 'Request failed'); }
  return res.json();
}

// ===== Auth =====
async function doLogin() {
  const email = document.getElementById('in-email').value;
  const pwd = document.getElementById('in-pwd').value;
  const errEl = document.getElementById('login-err');
  errEl.style.display = 'none';
  try {
    const data = await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password: pwd }) });
    token = data.access_token; user = data.user;
    localStorage.setItem('mv_t', token); localStorage.setItem('mv_u', JSON.stringify(user));
    enterApp();
  } catch (e) { errEl.textContent = e.message; errEl.style.display = 'block'; }
}

function doLogout() {
  token = null; user = null; localStorage.removeItem('mv_t'); localStorage.removeItem('mv_u');
  document.getElementById('view-login').classList.remove('off');
  document.getElementById('view-app').classList.remove('on');
}

function enterApp() {
  document.getElementById('view-login').classList.add('off');
  document.getElementById('view-app').classList.add('on');
  document.getElementById('sb-name').textContent = user?.name || 'User';
  document.getElementById('sb-email').textContent = user?.email || '';
  document.getElementById('sb-av').textContent = (user?.name || 'U')[0].toUpperCase();
  go('dashboard');
}

// Enter key on password
document.getElementById('in-pwd')?.addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });

// ===== Navigation =====
function go(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('on'));
  const pg = document.getElementById('pg-' + page);
  if (pg) pg.classList.add('on');
  document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
  document.querySelector(`[data-p="${page}"]`)?.classList.add('active');
  loaders[page]?.();
}

// ===== Status Colors =====
function badge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}
function dotColor(status) {
  const m = { active: '#34d399', pending: '#fbbf24', approved: '#60a5fa', rejected: '#f87171', draft: '#94a3b8', completed: '#a78bfa' };
  return m[status] || '#94a3b8';
}

// ===== Screen Gradients =====
const screenGradients = [
  'linear-gradient(135deg,#2563eb,#1e40af)', 'linear-gradient(135deg,#ea580c,#c2410c)',
  'linear-gradient(135deg,#0d9488,#0f766e)', 'linear-gradient(135deg,#7c3aed,#6d28d9)',
  'linear-gradient(135deg,#d97706,#b45309)', 'linear-gradient(135deg,#db2777,#be185d)',
  'linear-gradient(135deg,#059669,#047857)', 'linear-gradient(135deg,#4f46e5,#4338ca)',
  'linear-gradient(135deg,#0891b2,#0e7490)', 'linear-gradient(135deg,#e11d48,#be123c)'
];

// ===== Page Loaders =====
const loaders = {
  async dashboard() {
    const el = document.getElementById('pg-dashboard');
    try {
      const d = await api('/analytics/dashboard');
      let adm = null;
      if (user?.role === 'admin') try { adm = await api('/admin/analytics'); } catch (e) {}
      const rev = adm?.total_revenue || d.total_spent || 0;
      const scr = adm?.active_screens || d.active_campaigns || 0;
      const camp = d.total_campaigns || 0;
      const pend = d.pending_campaigns || 0;

      const screens = await api('/screens');

      el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px">
          <div>
            <p style="font-size:11px;font-weight:700;color:var(--brand-l);text-transform:uppercase;letter-spacing:3px;margin-bottom:6px">Welcome back</p>
            <h1 style="font-size:32px;font-weight:800;letter-spacing:-.5px">${user?.name || 'User'}</h1>
            <p style="color:var(--t-3);font-size:14px;margin-top:4px">Your digital signage network overview</p>
          </div>
          <button class="btn-primary" onclick="go('campaigns')">
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14m7-7H5"/></svg>
            New Campaign
          </button>
        </div>

        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:32px">
          ${statCard('Revenue', '$' + rev.toLocaleString(), 'All time earnings', '--cyan', 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6')}
          ${statCard('Screens', scr, 'Online now', '--green', 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z')}
          ${statCard('Campaigns', camp, 'Total created', '--brand-l', 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2')}
          ${statCard('Pending', pend, 'Awaiting review', '--amber', 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z')}
        </div>

        <div style="display:grid;grid-template-columns:5fr 4fr 3fr;gap:20px">
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
              <h2 style="font-size:16px;font-weight:700">Recent Campaigns</h2>
              <a onclick="go('campaigns')" style="font-size:12px;color:var(--brand-l);cursor:pointer;font-weight:600">View All →</a>
            </div>
            <div class="card">
              ${(d.recent_campaigns || []).length === 0
                ? '<div style="padding:40px;text-align:center;color:var(--t-4)">No campaigns yet</div>'
                : (d.recent_campaigns || []).map((c, i) => `
                    <div class="list-row" onclick="go('campaigns')">
                      <div class="list-dot" style="background:${dotColor(c.status)}"></div>
                      <div style="flex:1;min-width:0">
                        <div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.name}</div>
                        <div style="font-size:11px;color:var(--t-4)">${c.screen_name || 'Screen'} · ${c.schedule?.start_date || ''}</div>
                      </div>
                      ${badge(c.status)}
                    </div>`).join('')}
            </div>
          </div>

          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
              <h2 style="font-size:16px;font-weight:700">Active Screens</h2>
              <a onclick="go('screens')" style="font-size:12px;color:var(--brand-l);cursor:pointer;font-weight:600">Browse →</a>
            </div>
            <div class="card">
              ${screens.slice(0, 6).map((s, i) => `
                <div class="list-row" onclick="go('screens')">
                  <div class="list-dot" style="background:#34d399"></div>
                  <div style="flex:1;min-width:0">
                    <div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.name}</div>
                    <div style="font-size:11px;color:var(--t-4)">${s.location?.city}, ${s.location?.state}</div>
                  </div>
                  <div style="font-size:14px;font-weight:700;color:var(--cyan)">$${s.pricing?.per_hour}<span style="font-size:10px;color:var(--t-4);font-weight:400">/hr</span></div>
                </div>`).join('')}
            </div>
          </div>

          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Quick Actions</h2>
            <div style="display:flex;flex-direction:column;gap:8px">
              ${actionCard('Create Campaign', 'Launch new ad', '#6366f1', 'M12 5v14m7-7H5', 'campaigns')}
              ${actionCard('Browse Screens', 'Explore displays', '#22d3ee', 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z', 'screens')}
              ${actionCard('Payments', 'Invoices & billing', '#34d399', 'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z', 'payments')}
              ${user?.role === 'admin' ? actionCard('Devices', 'Manage players', '#fbbf24', 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z', 'devices') : ''}
            </div>
          </div>
        </div>`;
    } catch (e) { el.innerHTML = `<p style="color:var(--red)">Error loading dashboard: ${e.message}</p>`; }
  },

  async screens() {
    const el = document.getElementById('pg-screens');
    try {
      const data = await api('/screens');
      el.innerHTML = `
        <h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Screens</h1>
        <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">${data.length} LED displays available</p>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">
          ${data.map((s, i) => `
            <div class="screen-card card-interactive">
              <div class="header" style="background:${screenGradients[i % screenGradients.length]}">
                <div class="city">${s.location?.city}, ${s.location?.state}</div>
              </div>
              <div class="body">
                <div class="name">${s.name}</div>
                <div class="addr">${s.location?.address}</div>
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span style="font-size:11px;color:var(--t-3)">${s.specs?.size || ''} · ${s.specs?.resolution || ''}</span>
                  <div class="price">$${s.pricing?.per_hour}<span>/hr</span></div>
                </div>
              </div>
            </div>`).join('')}
        </div>`;
    } catch (e) { el.innerHTML = `<p style="color:var(--red)">${e.message}</p>`; }
  },

  async campaigns() {
    const el = document.getElementById('pg-campaigns');
    try {
      const data = await api('/campaigns');
      el.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px">
          <div><h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Campaigns</h1><p style="color:var(--t-3);font-size:14px">${data.length} campaigns</p></div>
          <button class="btn-primary">+ New Campaign</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${data.length === 0 ? '<div class="card" style="padding:48px;text-align:center;color:var(--t-4)">No campaigns yet — create your first one</div>' :
            data.map(c => `
              <div class="card card-interactive" style="display:flex;align-items:center;gap:12px;padding:16px;cursor:pointer">
                <div style="width:3px;height:40px;border-radius:2px;background:${dotColor(c.status)};flex-shrink:0"></div>
                <div style="flex:1;min-width:0">
                  <div style="font-size:14px;font-weight:700">${c.name}</div>
                  <div style="font-size:12px;color:var(--t-4);margin-top:2px">${c.screen?.name || 'Screen'} · ${c.schedule?.start_date || ''} → ${c.schedule?.end_date || ''}</div>
                </div>
                ${badge(c.status)}
                <div style="font-size:20px;font-weight:800;color:var(--cyan);min-width:100px;text-align:right">$${(c.pricing?.total || 0).toLocaleString()}</div>
              </div>`).join('')}
        </div>`;
    } catch (e) { el.innerHTML = `<p style="color:var(--red)">${e.message}</p>`; }
  },

  async payments() {
    const el = document.getElementById('pg-payments');
    try {
      const data = await api('/payments');
      el.innerHTML = `
        <h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Payments</h1>
        <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">${data.length} transactions</p>
        <div style="display:flex;flex-direction:column;gap:8px">
          ${data.length === 0 ? '<div class="card" style="padding:48px;text-align:center;color:var(--t-4)">No payments yet</div>' :
            data.map(p => `
              <div class="card" style="display:flex;align-items:center;gap:14px;padding:16px">
                <div style="width:40px;height:40px;border-radius:10px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center;flex-shrink:0">
                  <svg width="18" height="18" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                </div>
                <div style="flex:1;min-width:0">
                  <div style="font-size:14px;font-weight:700">${p.campaign_name || 'Campaign'}</div>
                  <div style="font-size:12px;color:var(--t-4);margin-top:1px">${p.invoice_number} · ${p.screen_name || ''}</div>
                </div>
                <span class="badge badge-${p.status === 'completed' ? 'active' : 'pending'}">${p.status}</span>
                <div style="font-size:22px;font-weight:800;min-width:110px;text-align:right">$${(p.amount || 0).toLocaleString()}</div>
              </div>`).join('')}
        </div>`;
    } catch (e) { el.innerHTML = `<p style="color:var(--red)">${e.message}</p>`; }
  },

  async devices() {
    const el = document.getElementById('pg-devices');
    el.innerHTML = `
      <h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Devices</h1>
      <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">Connected players and screens</p>
      <div class="card" style="padding:48px;text-align:center;color:var(--t-4)">
        <svg width="48" height="48" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px"><path d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
        <p style="font-size:16px;font-weight:600;color:var(--t-2);margin-bottom:4px">Device Management</p>
        <p style="font-size:13px">Install MediaView Player on a TV to see devices here</p>
      </div>`;
  },

  settings() {
    const el = document.getElementById('pg-settings');
    el.innerHTML = `
      <h1 style="font-size:28px;font-weight:800;margin-bottom:28px">Settings</h1>
      <div style="max-width:560px">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:32px">
          <div style="width:64px;height:64px;border-radius:16px;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:900;color:#fff;box-shadow:0 4px 15px rgba(99,102,241,.25)">${(user?.name || 'U')[0]}</div>
          <div>
            <div style="font-size:20px;font-weight:700">${user?.name || ''}</div>
            <div style="font-size:13px;color:var(--t-3)">${user?.email || ''}</div>
            <span class="badge" style="margin-top:6px;background:${user?.role === 'admin' ? 'rgba(99,102,241,.12)' : 'rgba(52,211,153,.12)'};color:${user?.role === 'admin' ? 'var(--brand-l)' : 'var(--green)'}">${user?.role === 'admin' ? 'Administrator' : 'Customer'}</span>
          </div>
        </div>
        <div class="card" style="margin-bottom:20px">
          <div style="padding:14px 20px;border-bottom:1px solid var(--border)"><span style="font-size:10px;font-weight:700;color:var(--t-2);text-transform:uppercase;letter-spacing:1.5px">Account Information</span></div>
          ${[['Name', user?.name], ['Email', user?.email], ['Company', user?.company_name || '—'], ['Role', user?.role]].map(([l, v]) =>
            `<div style="padding:14px 20px;display:flex;justify-content:space-between;border-bottom:1px solid rgba(30,41,59,.2)"><span style="font-size:13px;color:var(--t-3)">${l}</span><span style="font-size:13px;font-weight:600">${v}</span></div>`
          ).join('')}
        </div>
        <button onclick="doLogout()" style="width:100%;padding:12px;border-radius:var(--radius-sm);background:none;border:1px solid var(--bg-3);color:var(--t-3);font-size:13px;font-weight:500;transition:all .2s;cursor:pointer" onmouseover="this.style.borderColor='rgba(248,113,113,.3)';this.style.color='#f87171'" onmouseout="this.style.borderColor='var(--bg-3)';this.style.color='var(--t-3)'">Sign Out</button>
      </div>`;
  }
};

// ===== Component Helpers =====
function statCard(label, value, sub, colorVar, iconPath) {
  return `<div class="stat-card" style="border-left-color:var(${colorVar})">
    <div style="display:flex;align-items:center;gap:8px">
      <div style="width:32px;height:32px;border-radius:8px;background:color-mix(in srgb, var(${colorVar}) 12%, transparent);display:flex;align-items:center;justify-content:center">
        <svg width="16" height="16" fill="none" stroke="var(${colorVar})" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${iconPath}"/></svg>
      </div>
      <span style="font-size:11px;font-weight:600;color:var(--t-3)">${label}</span>
    </div>
    <div class="stat-value" style="color:var(${colorVar})">${value}</div>
    <div class="stat-sub">${sub}</div>
  </div>`;
}

function actionCard(label, desc, color, iconPath, page) {
  return `<div class="card card-interactive" style="display:flex;align-items:center;gap:12px;padding:14px;cursor:pointer" onclick="go('${page}')">
    <div style="width:36px;height:36px;border-radius:10px;background:${color}15;border:1px solid ${color}25;display:flex;align-items:center;justify-content:center;flex-shrink:0">
      <svg width="16" height="16" fill="none" stroke="${color}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${iconPath}"/></svg>
    </div>
    <div style="flex:1"><div style="font-size:13px;font-weight:600">${label}</div><div style="font-size:10px;color:var(--t-4);margin-top:1px">${desc}</div></div>
    <svg width="14" height="14" fill="none" stroke="var(--t-4)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg>
  </div>`;
}

// ===== Auto-login =====
if (token && user) { enterApp(); }

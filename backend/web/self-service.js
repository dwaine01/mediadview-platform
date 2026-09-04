/**
 * self-service.js — MediaView Fase 2: Self-Service Portal
 * ─────────────────────────────────────────────────────────
 * Adds loaders for: my-org | locations | team | subscriptions | admin-orgs
 * Registers into the global `loaders` object used by app.js go() routing.
 * Also handles the #/invite/{token} hash flow.
 */

// ── Plan colour map ───────────────────────────────────────────────────────────
const PLAN_COLOR = { starter:'#6366f1', pro:'#0891b2', enterprise:'#10b981', free:'#94a3b8' };
const STATUS_COLOR = { active:'#34d399', trialing:'#a78bfa', suspended:'#fbbf24', cancelled:'#f87171', free:'#94a3b8' };

function ssBadge(status, text){
  const c = STATUS_COLOR[status]||'#94a3b8';
  const bg = c+'22';
  return `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;padding:3px 9px;border-radius:20px;background:${bg};color:${c};border:1px solid ${c}44">${text||status}</span>`;
}
function planBadge(plan){
  const c = PLAN_COLOR[plan]||'#94a3b8';
  return `<span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:12px;background:${c}22;color:${c};border:1px solid ${c}44;text-transform:uppercase;letter-spacing:.5px">${plan||'free'}</span>`;
}
function fmtDate(iso){
  if(!iso) return '—';
  try { return new Date(iso).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}); } catch { return iso; }
}
function copyText(txt, btn){
  navigator.clipboard.writeText(txt).then(()=>{
    const orig = btn.textContent;
    btn.textContent = '✓ Copied!';
    btn.style.color = '#34d399';
    setTimeout(()=>{ btn.textContent=orig; btn.style.color=''; }, 2000);
  });
}

// ── Shared empty state ────────────────────────────────────────────────────────
function ssEmpty(icon, title, desc, action=''){
  return `<div class="empty"><div class="empty-ico">${icon}</div><h3>${title}</h3><p>${desc}</p>${action}</div>`;
}

// ── Shared modal helpers ──────────────────────────────────────────────────────
function ssModal(id, title, body, footer){
  // Remove any existing modal with same id
  document.getElementById(id)?.remove();
  const m = document.createElement('div');
  m.id = id;
  m.style.cssText = 'position:fixed;inset:0;background:rgba(2,6,18,.85);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)';
  m.innerHTML = `
    <div style="width:90%;max-width:560px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--rl);overflow:hidden;box-shadow:var(--sh-lg)">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:20px 24px;border-bottom:1px solid var(--border)">
        <h3 style="font-size:16px;font-weight:700;color:var(--t-1)">${title}</h3>
        <button onclick="document.getElementById('${id}').remove()" style="width:28px;height:28px;border-radius:8px;background:var(--bg-2);border:1px solid var(--border);color:var(--t-3);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">✕</button>
      </div>
      <div style="padding:24px">${body}</div>
      ${footer?`<div style="padding:16px 24px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:10px">${footer}</div>`:''}
    </div>`;
  document.body.appendChild(m);
  return m;
}
function ssCloseModal(id){ document.getElementById(id)?.remove(); }
function ssBtn(label, onclick, variant='primary', extra=''){
  const bg = variant==='primary' ? 'var(--brand)' : variant==='danger' ? '#ef4444' : 'var(--bg-2)';
  const color = variant==='ghost' ? 'var(--t-2)' : '#fff';
  const border = variant==='ghost' ? '1px solid var(--border)' : 'none';
  return `<button onclick="${onclick}" style="padding:10px 20px;border-radius:var(--radius-sm);background:${bg};color:${color};border:${border};font-size:13px;font-weight:600;cursor:pointer;${extra}">${label}</button>`;
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: My Organization
// ══════════════════════════════════════════════════════════════════════════════
loaders['my-org'] = async function(){
  const el = document.getElementById('pg-my-org');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Loading…</div>';
  try {
    const org = await api('/organizations/mine');
    if(!org || org.org === null || !org.id){
      // No org yet — show onboarding
      el.innerHTML = `
        <div class="ph"><div><h1>My Organization</h1><p>Set up your organization to manage screens, locations and team.</p></div></div>
        <div style="max-width:560px;margin:0 auto">
          <div class="card" style="padding:32px">
            <div style="width:56px;height:56px;border-radius:16px;background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.2);display:flex;align-items:center;justify-content:center;margin-bottom:20px">
              <svg width="28" height="28" fill="none" stroke="#6366f1" stroke-width="1.8" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
            </div>
            <h2 style="font-size:20px;font-weight:700;margin-bottom:8px">Create your organization</h2>
            <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">Your organization groups all your screens, locations and team members under one account.</p>
            <div style="margin-bottom:16px"><label class="inp-label">Organization Name *</label><input class="inp" id="org-name" placeholder="e.g. Acme Corp Digital Signage"></div>
            <div style="margin-bottom:24px"><label class="inp-label">Billing Email</label><input class="inp" id="org-billing-email" placeholder="billing@company.com" type="email"></div>
            <button onclick="ssCreateOrg()" class="btn-p" style="width:100%;padding:13px">Create Organization →</button>
            <p id="org-err" style="color:var(--red);font-size:12px;margin-top:12px;display:none"></p>
          </div>
        </div>`;
      return;
    }
    const s = org.stats || {};
    const statusColor = org.status==='active' ? '#34d399' : org.status==='suspended' ? '#fbbf24' : '#f87171';
    el.innerHTML = `
      <div class="ph">
        <div style="display:flex;align-items:center;gap:16px">
          ${org.logo_url ? `<img src="${org.logo_url}" style="width:48px;height:48px;border-radius:12px;object-fit:cover;border:1px solid var(--border)">` : `<div style="width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:#fff">${(org.name||'O')[0]}</div>`}
          <div>
            <h1 style="margin-bottom:4px">${escapeHtml(org.name)}</h1>
            <div style="display:flex;gap:8px;align-items:center">
              ${planBadge(org.plan)}
              <span style="font-size:11px;color:${statusColor};font-weight:600">● ${org.status}</span>
            </div>
          </div>
        </div>
        <button onclick="ssEditOrgModal('${org.id}')" class="btn-s">Edit Details</button>
      </div>

      <div class="st-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:28px">
        <div class="st"><div class="st-h"><span class="st-label">Screens</span></div><div class="st-value">${s.screens||0}</div><div class="st-sub">Self-service</div></div>
        <div class="st"><div class="st-h"><span class="st-label">Locations</span></div><div class="st-value">${s.locations||0}</div><div class="st-sub">Physical sites</div></div>
        <div class="st"><div class="st-h"><span class="st-label">Team Members</span></div><div class="st-value">${s.members||0}</div><div class="st-sub">Active</div></div>
        <div class="st"><div class="st-h"><span class="st-label">Active Subs</span></div><div class="st-value">${s.active_subscriptions||0}</div><div class="st-sub">Subscriptions</div></div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div class="card" style="padding:24px">
          <div style="font-size:13px;font-weight:700;color:var(--t-2);margin-bottom:16px;text-transform:uppercase;letter-spacing:.5px">Organization Details</div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div><div style="font-size:11px;color:var(--t-4);margin-bottom:2px">Name</div><div style="font-size:14px;font-weight:600;color:var(--t-1)">${escapeHtml(org.name)}</div></div>
            <div><div style="font-size:11px;color:var(--t-4);margin-bottom:2px">Slug</div><div style="font-size:13px;color:var(--t-3);font-family:monospace">/${org.slug}</div></div>
            <div><div style="font-size:11px;color:var(--t-4);margin-bottom:2px">Billing Email</div><div style="font-size:13px;color:var(--t-2)">${escapeHtml(org.billing_email||'—')}</div></div>
            <div><div style="font-size:11px;color:var(--t-4);margin-bottom:2px">Plan</div><div>${planBadge(org.plan)}</div></div>
            <div><div style="font-size:11px;color:var(--t-4);margin-bottom:2px">Member since</div><div style="font-size:13px;color:var(--t-3)">${fmtDate(org.created_at)}</div></div>
          </div>
        </div>
        <div class="card" style="padding:24px">
          <div style="font-size:13px;font-weight:700;color:var(--t-2);margin-bottom:16px;text-transform:uppercase;letter-spacing:.5px">Quick Actions</div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <button onclick="go('locations')" class="btn-s" style="width:100%;text-align:left;padding:12px 16px;border-radius:var(--radius-sm)">
              <svg width="14" height="14" style="margin-right:8px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              Manage Locations
            </button>
            <button onclick="go('team')" class="btn-s" style="width:100%;text-align:left;padding:12px 16px;border-radius:var(--radius-sm)">
              <svg width="14" height="14" style="margin-right:8px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              Manage Team
            </button>
            <button onclick="go('subscriptions')" class="btn-s" style="width:100%;text-align:left;padding:12px 16px;border-radius:var(--radius-sm)">
              <svg width="14" height="14" style="margin-right:8px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>
              View Billing
            </button>
            <button onclick="go('screens')" class="btn-s" style="width:100%;text-align:left;padding:12px 16px;border-radius:var(--radius-sm)">
              <svg width="14" height="14" style="margin-right:8px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path stroke-linecap="round" d="M8 21h8m-4-4v4"/></svg>
              My Screens
            </button>
          </div>
        </div>
      </div>`;
  } catch(e){
    el.innerHTML = `<div class="empty"><h3>Error loading organization</h3><p>${e.message}</p></div>`;
  }
};

async function ssCreateOrg(){
  const name = document.getElementById('org-name')?.value?.trim();
  const email = document.getElementById('org-billing-email')?.value?.trim();
  const errEl = document.getElementById('org-err');
  if(!name){ errEl.textContent='Organization name is required'; errEl.style.display='block'; return; }
  errEl.style.display='none';
  try {
    await api('/organizations', {method:'POST', body: JSON.stringify({name, billing_email: email||undefined})});
    loaders['my-org']();
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}

async function ssEditOrgModal(orgId){
  const org = await api('/organizations/mine');
  ssModal('ss-edit-org', 'Edit Organization',
    `<div style="display:flex;flex-direction:column;gap:16px">
      <div><label class="inp-label">Organization Name</label><input class="inp" id="eo-name" value="${escapeHtml(org.name||'')}"></div>
      <div><label class="inp-label">Billing Email</label><input class="inp" id="eo-email" type="email" value="${escapeHtml(org.billing_email||'')}"></div>
      <div><label class="inp-label">Logo URL (optional)</label><input class="inp" id="eo-logo" value="${escapeHtml(org.logo_url||'')}" placeholder="https://..."></div>
      <p id="eo-err" style="color:var(--red);font-size:12px;display:none"></p>
    </div>`,
    `${ssBtn('Cancel', "ssCloseModal('ss-edit-org')", 'ghost')}${ssBtn('Save Changes', `ssUpdateOrg('${orgId}')`, 'primary')}`
  );
}
async function ssUpdateOrg(orgId){
  const name = document.getElementById('eo-name')?.value?.trim();
  const email = document.getElementById('eo-email')?.value?.trim();
  const logo = document.getElementById('eo-logo')?.value?.trim();
  const errEl = document.getElementById('eo-err');
  errEl.style.display='none';
  try {
    await api(`/organizations/${orgId}`, {method:'PUT', body: JSON.stringify({name, billing_email:email||undefined, logo_url:logo||undefined})});
    ssCloseModal('ss-edit-org');
    loaders['my-org']();
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Locations
// ══════════════════════════════════════════════════════════════════════════════
loaders['locations'] = async function(){
  const el = document.getElementById('pg-locations');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Loading…</div>';
  try {
    const locs = await api('/locations');
    el.innerHTML = `
      <div class="ph">
        <div><h1>Locations</h1><p>${locs.length} physical location${locs.length!==1?'s':''}</p></div>
        <button onclick="ssAddLocationModal()" class="btn-p">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>
          Add Location
        </button>
      </div>
      ${locs.length===0 ? ssEmpty(
          '<svg width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>',
          'No locations yet',
          'Add your first physical location to start organizing your screens.',
          `<button onclick="ssAddLocationModal()" class="btn-p">+ Add Location</button>`
        ) :
        `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px">
          ${locs.map(loc=>`
            <div class="card card-i" style="padding:20px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
                <div style="width:40px;height:40px;border-radius:10px;background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.18);display:flex;align-items:center;justify-content:center">
                  <svg width="20" height="20" fill="none" stroke="#6366f1" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0zM15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                </div>
                <div style="display:flex;gap:6px">
                  <button onclick="ssEditLocationModal('${loc.id}')" class="btn-icon" title="Edit" style="width:30px;height:30px">
                    <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                  </button>
                  <button onclick="ssDeleteLocation('${loc.id}', '${escapeHtml(loc.name)}')" class="btn-icon" title="Delete" style="width:30px;height:30px;color:var(--red)">
                    <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                  </button>
                </div>
              </div>
              <div style="font-size:15px;font-weight:700;color:var(--t-1);margin-bottom:4px">${escapeHtml(loc.name)}</div>
              <div style="font-size:12px;color:var(--t-4);margin-bottom:10px">${escapeHtml(loc.address||'')}${loc.city?', '+escapeHtml(loc.city):''}${loc.state?', '+escapeHtml(loc.state):''}</div>
              <div style="display:flex;align-items:center;gap:6px">
                <div style="width:6px;height:6px;border-radius:50%;background:#34d399"></div>
                <span style="font-size:12px;color:var(--t-4)">${loc.screen_count||0} screen${loc.screen_count!==1?'s':''}</span>
              </div>
            </div>`).join('')}
        </div>`}`;
  } catch(e){ el.innerHTML = `<p style="color:var(--red);padding:24px">${e.message}</p>`; }
};

function ssLocationForm(defaults={}){
  return `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div style="grid-column:1/-1"><label class="inp-label">Location Name *</label><input class="inp" id="lf-name" value="${escapeHtml(defaults.name||'')}" placeholder="e.g. Downtown Lobby"></div>
      <div style="grid-column:1/-1"><label class="inp-label">Address *</label><input class="inp" id="lf-address" value="${escapeHtml(defaults.address||'')}" placeholder="123 Main St"></div>
      <div><label class="inp-label">City *</label><input class="inp" id="lf-city" value="${escapeHtml(defaults.city||'')}" placeholder="Miami"></div>
      <div><label class="inp-label">State</label><input class="inp" id="lf-state" value="${escapeHtml(defaults.state||'')}" placeholder="FL"></div>
      <div><label class="inp-label">ZIP</label><input class="inp" id="lf-zip" value="${escapeHtml(defaults.zip||'')}" placeholder="33101"></div>
      <div><label class="inp-label">Country</label><input class="inp" id="lf-country" value="${escapeHtml(defaults.country||'US')}"></div>
      <div style="grid-column:1/-1"><label class="inp-label">Timezone</label>
        <select class="inp" id="lf-tz">
          ${['America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Phoenix','Pacific/Honolulu','America/Anchorage','Europe/London','Europe/Madrid','America/Bogota','America/Lima','America/Sao_Paulo'].map(tz=>`<option value="${tz}" ${(defaults.timezone||'America/New_York')===tz?'selected':''}>${tz}</option>`).join('')}
        </select>
      </div>
    </div>
    <p id="lf-err" style="color:var(--red);font-size:12px;margin-top:12px;display:none"></p>`;
}

function ssAddLocationModal(){
  ssModal('ss-add-loc', 'Add Location', ssLocationForm(),
    `${ssBtn('Cancel',"ssCloseModal('ss-add-loc')","ghost")}${ssBtn('Create Location',"ssSaveLocation(null)","primary")}`
  );
}

async function ssEditLocationModal(locId){
  try {
    const locs = await api('/locations');
    const loc = locs.find(l=>l.id===locId);
    if(!loc) return;
    ssModal('ss-edit-loc', 'Edit Location', ssLocationForm(loc),
      `${ssBtn('Cancel',"ssCloseModal('ss-edit-loc')","ghost")}${ssBtn('Save Changes',`ssSaveLocation('${locId}')`, "primary")}`
    );
  } catch(e){ alert(e.message); }
}

async function ssSaveLocation(locId){
  const name    = document.getElementById('lf-name')?.value?.trim();
  const address = document.getElementById('lf-address')?.value?.trim();
  const city    = document.getElementById('lf-city')?.value?.trim();
  const state   = document.getElementById('lf-state')?.value?.trim();
  const zip     = document.getElementById('lf-zip')?.value?.trim();
  const country = document.getElementById('lf-country')?.value?.trim();
  const timezone= document.getElementById('lf-tz')?.value;
  const errEl   = document.getElementById('lf-err');
  errEl.style.display='none';
  if(!name||!address||!city){ errEl.textContent='Name, address and city are required'; errEl.style.display='block'; return; }
  const payload = {name,address,city,state:state||null,zip:zip||null,country:country||'US',timezone};
  try {
    if(locId){
      await api(`/locations/${locId}`, {method:'PUT', body:JSON.stringify(payload)});
      ssCloseModal('ss-edit-loc');
    } else {
      await api('/locations', {method:'POST', body:JSON.stringify(payload)});
      ssCloseModal('ss-add-loc');
    }
    loaders['locations']();
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}

async function ssDeleteLocation(locId, name){
  if(!confirm(`Delete location "${name}"? This cannot be undone.`)) return;
  try {
    await api(`/locations/${locId}`, {method:'DELETE'});
    loaders['locations']();
  } catch(e){ alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Team
// ══════════════════════════════════════════════════════════════════════════════
loaders['team'] = async function(){
  const el = document.getElementById('pg-team');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Loading…</div>';
  try {
    const orgResp = await api('/organizations/mine');
    if(!orgResp || !orgResp.id){ el.innerHTML=ssEmpty('<svg width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>','No Organization','Create your organization first to manage team members.', '<button onclick="go(\'my-org\')" class="btn-p">Create Organization</button>'); return; }
    const orgId = orgResp.id;
    const data = await api(`/organizations/${orgId}/members`);
    const inviteBaseUrl = `${window.location.origin}/api/dashboard`;
    el.innerHTML = `
      <div class="ph">
        <div><h1>Team</h1><p>Manage who has access to <strong>${escapeHtml(orgResp.name)}</strong></p></div>
        <button onclick="ssInviteModal('${orgId}')" class="btn-p">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>
          Invite Member
        </button>
      </div>

      <div class="card" style="margin-bottom:20px">
        <div style="padding:18px 22px;border-bottom:1px solid var(--border);font-size:13px;font-weight:700;color:var(--t-2)">MEMBERS (${(data.members?.length||0) + 1})</div>
        ${[data.owner, ...(data.members||[])].filter(Boolean).map(m=>`
          <div style="display:flex;align-items:center;gap:14px;padding:16px 22px;border-bottom:1px solid var(--border)">
            <div style="width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;color:#fff;flex-shrink:0">${(m.name||m.email||'?')[0].toUpperCase()}</div>
            <div style="flex:1;min-width:0">
              <div style="font-size:14px;font-weight:600;color:var(--t-1)">${escapeHtml(m.name||'—')}</div>
              <div style="font-size:12px;color:var(--t-4)">${escapeHtml(m.email||'')}</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center">
              ${m.id===data.owner?.id ? '<span style="font-size:11px;font-weight:700;padding:3px 9px;border-radius:12px;background:rgba(99,102,241,.12);color:#6366f1;border:1px solid rgba(99,102,241,.2)">Owner</span>' :
                `<span style="font-size:11px;font-weight:600;padding:3px 9px;border-radius:12px;background:rgba(148,163,184,.08);color:var(--t-3);border:1px solid var(--border)">${m.rbac_role||m.role||'Member'}</span>
                <button onclick="ssRemoveMember('${orgId}','${m.id}','${escapeHtml(m.name||m.email||'')}')" class="btn-icon" title="Remove" style="width:28px;height:28px;color:var(--red)">
                  <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                </button>`}
            </div>
          </div>`).join('')}
      </div>

      ${(data.pending_invites||[]).length > 0 ? `
        <div class="card">
          <div style="padding:18px 22px;border-bottom:1px solid var(--border);font-size:13px;font-weight:700;color:var(--t-2)">PENDING INVITES (${data.pending_invites.length})</div>
          ${data.pending_invites.map(inv=>`
            <div style="display:flex;align-items:center;gap:14px;padding:16px 22px;border-bottom:1px solid var(--border)">
              <div style="width:38px;height:38px;border-radius:50%;background:rgba(148,163,184,.08);border:2px dashed var(--border);display:flex;align-items:center;justify-content:center;color:var(--t-4);font-size:16px;flex-shrink:0">?</div>
              <div style="flex:1;min-width:0">
                <div style="font-size:14px;font-weight:600;color:var(--t-2)">${escapeHtml(inv.email)}</div>
                <div style="font-size:12px;color:var(--t-4)">Invited · expires ${fmtDate(inv.expires_at)}</div>
              </div>
              <span style="font-size:11px;font-weight:600;padding:3px 9px;border-radius:12px;background:rgba(251,191,36,.1);color:#fbbf24;border:1px solid rgba(251,191,36,.2)">Pending</span>
              <button onclick="copyText('${inviteBaseUrl}#/invite/${inv.token}', this)" class="btn-s" style="font-size:12px;padding:6px 12px">Copy Link</button>
              <button onclick="ssRevokeInvite('${orgId}','${inv.id}')" class="btn-icon" title="Revoke" style="width:28px;height:28px;color:var(--red)">
                <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>`).join('')}
        </div>` : ''}`;
  } catch(e){ el.innerHTML=`<p style="color:var(--red);padding:24px">${e.message}</p>`; }
};

function ssInviteModal(orgId){
  ssModal('ss-invite', 'Invite Team Member',
    `<div style="display:flex;flex-direction:column;gap:16px">
      <div><label class="inp-label">Email Address *</label><input class="inp" id="inv-email" type="email" placeholder="colleague@company.com"></div>
      <div><label class="inp-label">Role</label>
        <select class="inp" id="inv-role">
          <option value="SELF_SERVICE_MANAGER">Manager — can create/edit content, not billing</option>
          <option value="SELF_SERVICE_OWNER">Owner — full access to this organization</option>
        </select>
      </div>
      <div style="background:rgba(99,102,241,.05);border:1px solid rgba(99,102,241,.15);border-radius:var(--radius-sm);padding:12px">
        <p style="font-size:12px;color:var(--t-3);margin:0">📧 Email sending is not configured yet. After creating the invite, you'll receive a shareable link to send manually.</p>
      </div>
      <p id="inv-err" style="color:var(--red);font-size:12px;display:none"></p>
      <div id="inv-success" style="display:none;background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.2);border-radius:var(--radius-sm);padding:16px">
        <div style="font-size:13px;font-weight:600;color:#34d399;margin-bottom:8px">✓ Invite created!</div>
        <div style="font-size:12px;color:var(--t-3);margin-bottom:8px">Share this link with your team member:</div>
        <div style="display:flex;gap:8px;align-items:center">
          <input id="inv-link" class="inp" readonly style="font-size:11px;font-family:monospace;flex:1">
          <button onclick="copyText(document.getElementById('inv-link').value, this)" class="btn-s" style="white-space:nowrap">Copy Link</button>
        </div>
      </div>
    </div>`,
    `<span id="inv-footer-btns">${ssBtn('Cancel',"ssCloseModal('ss-invite')","ghost")}${ssBtn('Send Invite',`ssSendInvite('${orgId}')`)}</span>`
  );
}
async function ssSendInvite(orgId){
  const email = document.getElementById('inv-email')?.value?.trim();
  const role = document.getElementById('inv-role')?.value;
  const errEl = document.getElementById('inv-err');
  errEl.style.display='none';
  if(!email){ errEl.textContent='Email is required'; errEl.style.display='block'; return; }
  try {
    const inv = await api(`/organizations/${orgId}/invites`, {method:'POST', body:JSON.stringify({email,role})});
    const link = `${window.location.origin}/api/dashboard${inv.invite_url}`;
    document.getElementById('inv-link').value = link;
    document.getElementById('inv-success').style.display='block';
    document.getElementById('inv-footer-btns').innerHTML = ssBtn('Close',"ssCloseModal('ss-invite');loaders.team()","ghost");
    document.getElementById('inv-email').closest('div').style.display='none';
    document.getElementById('inv-role').closest('div').style.display='none';
    document.querySelector('#ss-invite [style*="email sending"]').style.display='none';
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}
async function ssRemoveMember(orgId, userId, name){
  if(!confirm(`Remove "${name}" from the organization?`)) return;
  try { await api(`/organizations/${orgId}/members/${userId}`, {method:'DELETE'}); loaders['team'](); } catch(e){ alert(e.message); }
}
async function ssRevokeInvite(orgId, invId){
  if(!confirm('Revoke this invite?')) return;
  try { await api(`/organizations/${orgId}/invites/${invId}`, {method:'DELETE'}); loaders['team'](); } catch(e){ alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Billing / Subscriptions
// ══════════════════════════════════════════════════════════════════════════════
loaders['subscriptions'] = async function(){
  const el = document.getElementById('pg-subscriptions');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Loading…</div>';
  try {
    const [subs, plans] = await Promise.all([api('/subscriptions'), api('/subscriptions/plans')]);
    const active = subs.filter(s=>['trialing','active'].includes(s.status));
    const mrr = active.reduce((sum,s)=> {
      const p = plans[s.plan]||{};
      return sum + (s.billing_cycle==='annual' ? (p.price_annual||0)/12 : (p.price_monthly||0));
    },0);
    el.innerHTML = `
      <div class="ph">
        <div><h1>Billing & Subscriptions</h1><p>${subs.length} subscription${subs.length!==1?'s':''} · MRR <strong>$${mrr.toFixed(2)}</strong></p></div>
        <button onclick="ssNewSubModal()" class="btn-p">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>
          New Subscription
        </button>
      </div>

      <!-- Plan comparison -->
      <div class="sh"><h2>Available Plans</h2></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:32px">
        ${Object.entries(plans).map(([key,p])=>`
          <div class="card" style="padding:24px;border:1px solid ${PLAN_COLOR[key]}33;position:relative;overflow:hidden">
            <div style="font-size:12px;font-weight:700;color:${PLAN_COLOR[key]};text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px">${p.name}</div>
            <div style="font-size:28px;font-weight:800;color:var(--t-1);margin-bottom:2px">$${p.price_monthly}<span style="font-size:13px;font-weight:400;color:var(--t-4)">/mo</span></div>
            <div style="font-size:11px;color:var(--t-4);margin-bottom:16px">$${p.price_annual}/yr (save ${Math.round((1-(p.price_annual/(p.price_monthly*12)))*100)}%)</div>
            <div style="font-size:12px;color:var(--t-3);margin-bottom:16px">${p.description}</div>
            <ul style="padding:0;margin:0;list-style:none;display:flex;flex-direction:column;gap:6px">
              ${p.features.map(f=>`<li style="font-size:12px;color:var(--t-3);display:flex;gap:6px;align-items:flex-start"><span style="color:${PLAN_COLOR[key]};font-weight:700;flex-shrink:0">✓</span>${f}</li>`).join('')}
            </ul>
            <div style="position:absolute;top:0;right:0;width:80px;height:80px;background:${PLAN_COLOR[key]}08;border-radius:0 0 0 80px"></div>
          </div>`).join('')}
      </div>

      <!-- Active subscriptions -->
      <div class="sh"><h2>My Subscriptions</h2></div>
      ${subs.length===0 ? ssEmpty(
          '<svg width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>',
          'No subscriptions yet',
          'Create a subscription for each screen to unlock scheduling and publishing features.',
          '<button onclick="ssNewSubModal()" class="btn-p">+ Subscribe a Screen</button>'
        ) :
        `<div style="display:flex;flex-direction:column;gap:10px">
          ${subs.map(s=>`
            <div class="card" style="display:flex;align-items:center;gap:16px;padding:18px 22px">
              <div style="width:40px;height:40px;border-radius:10px;background:${PLAN_COLOR[s.plan]||'#94a3b8'}18;border:1px solid ${PLAN_COLOR[s.plan]||'#94a3b8'}33;display:flex;align-items:center;justify-content:center;flex-shrink:0">
                <svg width="20" height="20" fill="none" stroke="${PLAN_COLOR[s.plan]||'#94a3b8'}" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path stroke-linecap="round" d="M8 21h8m-4-4v4"/></svg>
              </div>
              <div style="flex:1;min-width:0">
                <div style="font-size:14px;font-weight:700;color:var(--t-1)">${escapeHtml(s.screen_name||'Unknown Screen')}</div>
                <div style="font-size:12px;color:var(--t-4);margin-top:2px">${planBadge(s.plan)} · ${s.billing_cycle} · $${s.price}/cycle</div>
              </div>
              <div style="text-align:right;min-width:120px">
                ${ssBadge(s.status)}
                <div style="font-size:11px;color:var(--t-4);margin-top:4px">
                  ${s.status==='trialing' ? 'Trial ends '+fmtDate(s.trial_ends_at) :
                    s.status==='cancelled' ? 'Cancelled '+fmtDate(s.cancelled_at) :
                    'Renews '+fmtDate(s.current_period_end)}
                </div>
              </div>
              <div style="display:flex;gap:6px">
                ${s.status!=='cancelled' ? `<button onclick="ssChangePlanModal('${s.id}','${s.plan}','${s.billing_cycle}')" class="btn-s" style="font-size:11px;padding:6px 10px">Change Plan</button>` : ''}
                ${s.status==='suspended' ? `<button onclick="ssActivateSub('${s.id}')" class="btn-s" style="font-size:11px;padding:6px 10px;color:#34d399">Reactivate</button>` : ''}
                ${!['cancelled'].includes(s.status) ? `<button onclick="ssCancelSub('${s.id}','${escapeHtml(s.screen_name||'')}')" class="btn-s" style="font-size:11px;padding:6px 10px;color:var(--red)">Cancel</button>` : ''}
              </div>
            </div>`).join('')}
        </div>`}`;
  } catch(e){ el.innerHTML=`<p style="color:var(--red);padding:24px">${e.message}</p>`; }
};

async function ssNewSubModal(){
  try {
    const [myScreens, plans] = await Promise.all([api('/screens/self-service/mine'), api('/subscriptions/plans')]);
    if(!myScreens.length){ alert('Add screens to your organization first (Self-Service → My Screens).'); return; }
    ssModal('ss-new-sub', 'New Subscription',
      `<div style="display:flex;flex-direction:column;gap:16px">
        <div>
          <label class="inp-label">Screen *</label>
          <select class="inp" id="sub-screen">${myScreens.map(s=>`<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('')}</select>
        </div>
        <div>
          <label class="inp-label">Plan *</label>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px" id="sub-plan-grid">
            ${Object.entries(plans).map(([key,p],i)=>`
              <div onclick="document.querySelectorAll('.plan-opt').forEach(x=>x.classList.remove('sel'));this.classList.add('sel');document.getElementById('sub-plan-val').value='${key}'"
                class="plan-opt" data-plan="${key}" style="border:2px solid ${i===0?PLAN_COLOR[key]:'var(--border)'};border-radius:var(--radius-sm);padding:12px;cursor:pointer;background:${i===0?PLAN_COLOR[key]+'0d':'transparent'};transition:.15s">
                <div style="font-size:12px;font-weight:700;color:${PLAN_COLOR[key]}">${p.name}</div>
                <div style="font-size:18px;font-weight:800;color:var(--t-1)">$${p.price_monthly}<span style="font-size:10px;color:var(--t-4)">/mo</span></div>
              </div>`).join('')}
          </div>
          <input type="hidden" id="sub-plan-val" value="starter">
        </div>
        <div>
          <label class="inp-label">Billing Cycle</label>
          <div style="display:flex;gap:8px">
            <button type="button" id="sub-monthly-btn" onclick="document.getElementById('sub-cycle').value='monthly';document.getElementById('sub-monthly-btn').style.background='rgba(99,102,241,.08)';document.getElementById('sub-monthly-btn').style.borderColor='var(--brand)';document.getElementById('sub-annual-btn').style.background='transparent';document.getElementById('sub-annual-btn').style.borderColor='var(--border)'"
              style="flex:1;padding:10px;border-radius:var(--radius-sm);border:2px solid var(--brand);background:rgba(99,102,241,.08);font-size:13px;font-weight:600;cursor:pointer;color:var(--t-1)">Monthly</button>
            <button type="button" id="sub-annual-btn" onclick="document.getElementById('sub-cycle').value='annual';document.getElementById('sub-annual-btn').style.background='rgba(99,102,241,.08)';document.getElementById('sub-annual-btn').style.borderColor='var(--brand)';document.getElementById('sub-monthly-btn').style.background='transparent';document.getElementById('sub-monthly-btn').style.borderColor='var(--border)'"
              style="flex:1;padding:10px;border-radius:var(--radius-sm);border:2px solid var(--border);background:transparent;font-size:13px;font-weight:600;cursor:pointer;color:var(--t-1)">Annual <span style="font-size:11px;color:#34d399">(Save ~17%)</span></button>
            <input type="hidden" id="sub-cycle" value="monthly">
          </div>
        </div>
        <div style="background:rgba(52,211,153,.05);border:1px solid rgba(52,211,153,.15);border-radius:var(--radius-sm);padding:12px">
          <p style="font-size:12px;color:var(--t-3);margin:0">🎉 Includes a <strong>14-day free trial</strong>. No payment required right now — billing is mocked.</p>
        </div>
        <p id="sub-err" style="color:var(--red);font-size:12px;display:none"></p>
      </div>`,
      `${ssBtn('Cancel',"ssCloseModal('ss-new-sub')","ghost")}${ssBtn('Start Trial','ssCreateSub()')}`
    );
  } catch(e){ alert(e.message); }
}

async function ssCreateSub(){
  const screenId = document.getElementById('sub-screen')?.value;
  const plan = document.getElementById('sub-plan-val')?.value;
  const cycle = document.getElementById('sub-cycle')?.value;
  const errEl = document.getElementById('sub-err');
  errEl.style.display='none';
  try {
    await api('/subscriptions', {method:'POST', body:JSON.stringify({screen_id:screenId, plan, billing_cycle:cycle})});
    ssCloseModal('ss-new-sub');
    loaders['subscriptions']();
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}

async function ssChangePlanModal(subId, currentPlan, currentCycle){
  const plans = await api('/subscriptions/plans');
  ssModal('ss-change-plan', 'Change Plan',
    `<div style="display:flex;flex-direction:column;gap:16px">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
        ${Object.entries(plans).map(([key,p])=>`
          <div onclick="document.querySelectorAll('.chplan-opt').forEach(x=>x.style.borderColor='var(--border)');this.style.borderColor='${PLAN_COLOR[key]}';document.getElementById('cp-plan').value='${key}'"
            class="chplan-opt" style="border:2px solid ${key===currentPlan?PLAN_COLOR[key]:'var(--border)'};border-radius:var(--radius-sm);padding:12px;cursor:pointer;transition:.15s">
            <div style="font-size:12px;font-weight:700;color:${PLAN_COLOR[key]}">${p.name}</div>
            <div style="font-size:18px;font-weight:800;color:var(--t-1)">$${p.price_monthly}<span style="font-size:10px;color:var(--t-4)">/mo</span></div>
          </div>`).join('')}
      </div>
      <input type="hidden" id="cp-plan" value="${currentPlan}">
      <p id="cp-err" style="color:var(--red);font-size:12px;display:none"></p>
    </div>`,
    `${ssBtn('Cancel',"ssCloseModal('ss-change-plan')","ghost")}${ssBtn('Save Changes',`ssUpdateSub('${subId}')`)}`
  );
}
async function ssUpdateSub(subId){
  const plan = document.getElementById('cp-plan')?.value;
  const errEl = document.getElementById('cp-err');
  errEl.style.display='none';
  try {
    await api(`/subscriptions/${subId}`, {method:'PUT', body:JSON.stringify({plan})});
    ssCloseModal('ss-change-plan');
    loaders['subscriptions']();
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}
async function ssCancelSub(subId, screenName){
  if(!confirm(`Cancel subscription for "${screenName}"? Service will continue until end of current period.`)) return;
  try { await api(`/subscriptions/${subId}/cancel`, {method:'POST'}); loaders['subscriptions'](); } catch(e){ alert(e.message); }
}
async function ssActivateSub(subId){
  try { await api(`/subscriptions/${subId}/activate`, {method:'POST'}); loaders['subscriptions'](); } catch(e){ alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Admin — Organizations
// ══════════════════════════════════════════════════════════════════════════════
loaders['admin-orgs'] = async function(){
  const el = document.getElementById('pg-admin-orgs');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Loading…</div>';
  try {
    const orgs = await api('/admin/organizations');
    const revenue = await api('/admin/subscriptions/revenue').catch(()=>({mrr:0,arr:0,total:0}));
    el.innerHTML = `
      <div class="ph"><div><h1>Organizations</h1><p>${orgs.length} organization${orgs.length!==1?'s':''} · MRR <strong>$${(revenue.mrr||0).toFixed(2)}</strong> · ARR <strong>$${(revenue.arr||0).toFixed(2)}</strong></p></div></div>

      <div class="st-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:28px">
        <div class="st"><div class="st-h"><span class="st-label">Total Orgs</span></div><div class="st-value">${orgs.length}</div></div>
        <div class="st"><div class="st-h"><span class="st-label">Active Subscriptions</span></div><div class="st-value">${revenue.by_status?.active||0}</div></div>
        <div class="st"><div class="st-h"><span class="st-label">In Trial</span></div><div class="st-value">${revenue.by_status?.trialing||0}</div></div>
        <div class="st"><div class="st-h"><span class="st-label">Monthly Revenue</span></div><div class="st-value">$${(revenue.mrr||0).toFixed(0)}</div></div>
      </div>

      ${orgs.length===0 ? ssEmpty('<svg width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>','No organizations yet','Self-service organizations will appear here once customers sign up.') :
      `<div class="card">
        <div style="display:grid;grid-template-columns:3fr 1fr 1fr 1fr 1fr 1fr 120px;gap:0;padding:12px 22px;border-bottom:1px solid var(--border);font-size:11px;font-weight:700;color:var(--t-4);text-transform:uppercase;letter-spacing:.5px">
          <span>Organization</span><span>Plan</span><span>Screens</span><span>Members</span><span>Subs</span><span>Status</span><span style="text-align:right">Actions</span>
        </div>
        ${orgs.map(org=>`
          <div style="display:grid;grid-template-columns:3fr 1fr 1fr 1fr 1fr 1fr 120px;gap:0;padding:16px 22px;border-bottom:1px solid var(--border);align-items:center">
            <div style="min-width:0">
              <div style="font-size:14px;font-weight:600;color:var(--t-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(org.name)}</div>
              <div style="font-size:11px;color:var(--t-4)">${escapeHtml(org.owner?.email||'—')}</div>
            </div>
            <div>${planBadge(org.plan)}</div>
            <div style="font-size:14px;font-weight:600;color:var(--t-2)">${org.screen_count||0}</div>
            <div style="font-size:14px;font-weight:600;color:var(--t-2)">${org.member_count||0}</div>
            <div style="font-size:14px;font-weight:600;color:${(org.active_subs||0)>0?'#34d399':'var(--t-4)'}">${org.active_subs||0}</div>
            <div>${ssBadge(org.status)}</div>
            <div style="display:flex;gap:6px;justify-content:flex-end">
              <button onclick="adminViewOrg('${org.id}')" class="btn-s" style="font-size:11px;padding:5px 10px">View</button>
              ${org.status==='active'?`<button onclick="adminSetOrgStatus('${org.id}','suspended')" class="btn-s" style="font-size:11px;padding:5px 10px;color:#fbbf24">Suspend</button>`:
                org.status==='suspended'?`<button onclick="adminSetOrgStatus('${org.id}','active')" class="btn-s" style="font-size:11px;padding:5px 10px;color:#34d399">Activate</button>`:''}
            </div>
          </div>`).join('')}
      </div>`}`;
  } catch(e){ el.innerHTML=`<p style="color:var(--red);padding:24px">${e.message}</p>`; }
};

async function adminViewOrg(orgId){
  try {
    const org = await api(`/admin/organizations/${orgId}`);
    ssModal('ss-org-detail', `Organization: ${escapeHtml(org.name)}`,
      `<div style="display:flex;flex-direction:column;gap:16px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div><span style="font-size:11px;color:var(--t-4)">Owner</span><div style="font-size:13px;font-weight:600;color:var(--t-1)">${escapeHtml(org.owner?.name||'—')}<br><span style="font-size:11px;color:var(--t-4)">${escapeHtml(org.owner?.email||'')}</span></div></div>
          <div><span style="font-size:11px;color:var(--t-4)">Status</span><div>${ssBadge(org.status)} ${planBadge(org.plan)}</div></div>
          <div><span style="font-size:11px;color:var(--t-4)">Screens</span><div style="font-size:22px;font-weight:700;color:var(--t-1)">${org.screens?.length||0}</div></div>
          <div><span style="font-size:11px;color:var(--t-4)">Locations</span><div style="font-size:22px;font-weight:700;color:var(--t-1)">${org.locations?.length||0}</div></div>
          <div><span style="font-size:11px;color:var(--t-4)">Members</span><div style="font-size:22px;font-weight:700;color:var(--t-1)">${org.members?.length||0}</div></div>
          <div><span style="font-size:11px;color:var(--t-4)">Subscriptions</span><div style="font-size:22px;font-weight:700;color:var(--t-1)">${org.subscriptions?.length||0}</div></div>
        </div>
        ${(org.members||[]).length>0?`<div><div style="font-size:11px;font-weight:700;color:var(--t-4);margin-bottom:8px">MEMBERS</div>${org.members.map(m=>`<div style="font-size:12px;color:var(--t-2);padding:4px 0;border-bottom:1px solid var(--border)">${escapeHtml(m.name||'—')} · ${escapeHtml(m.email||'')} · <span style="color:var(--t-4)">${m.rbac_role||m.role}</span></div>`).join('')}</div>`:''}
      </div>`,
      ssBtn('Close',"ssCloseModal('ss-org-detail')","ghost")
    );
  } catch(e){ alert(e.message); }
}

async function adminSetOrgStatus(orgId, status){
  const reason = status==='suspended' ? prompt('Reason for suspension (optional):') : null;
  try {
    await api(`/admin/organizations/${orgId}/status`, {method:'PUT', body:JSON.stringify({status, reason})});
    loaders['admin-orgs']();
  } catch(e){ alert(e.message); }
}

// ══════════════════════════════════════════════════════════════════════════════
//  INVITE ACCEPTANCE — Hash-based flow (#/invite/{token})
// ══════════════════════════════════════════════════════════════════════════════
async function handleInviteHash(){
  const hash = window.location.hash;
  if(!hash.startsWith('#/invite/')) return false;
  const token = hash.split('/invite/')[1];
  if(!token) return false;
  try {
    // Fetch public invite info (no auth)
    const inv = await fetch(`/api/invites/${token}`).then(r=>r.json());
    if(inv.detail){ showInviteError(inv.detail); return true; }
    showInviteAcceptModal(token, inv);
  } catch(e){ showInviteError('Failed to load invite. Please try again.'); }
  return true;
}

function showInviteError(msg){
  document.getElementById('view-login').classList.remove('off');
  const card = document.querySelector('#view-login .login-card');
  if(card) card.innerHTML += `<div style="margin-top:16px;padding:16px;background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);border-radius:var(--rl);text-align:center;font-size:13px;color:#f87171">${escapeHtml(msg)}</div>`;
}

function showInviteAcceptModal(token, inv){
  const isNew = !inv.has_account;
  ssModal('ss-accept-invite', `Join ${escapeHtml(inv.org_name)}`,
    `<div style="text-align:center;margin-bottom:20px">
      <div style="width:64px;height:64px;border-radius:20px;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:800;color:#fff;margin:0 auto 12px">${(inv.org_name||'O')[0]}</div>
      <div style="font-size:11px;color:var(--t-4);text-transform:uppercase;letter-spacing:.5px">${escapeHtml(inv.invited_by)} is inviting you to join</div>
      <h3 style="font-size:20px;font-weight:700;color:var(--t-1);margin:6px 0 4px">${escapeHtml(inv.org_name)}</h3>
      <div style="font-size:12px;color:var(--t-4)">as <strong>${escapeHtml(inv.role)}</strong></div>
    </div>
    <div style="background:rgba(99,102,241,.05);border:1px solid rgba(99,102,241,.15);border-radius:var(--radius-sm);padding:12px;margin-bottom:16px">
      <div style="font-size:12px;color:var(--t-3)">Invite sent to: <strong style="color:var(--t-1)">${escapeHtml(inv.email)}</strong></div>
    </div>
    ${isNew ? `
      <div style="display:flex;flex-direction:column;gap:12px">
        <div><label class="inp-label">Your Name *</label><input class="inp" id="ai-name" placeholder="Your full name"></div>
        <div><label class="inp-label">Password *</label><input class="inp" id="ai-pwd" type="password" placeholder="min. 8 characters"></div>
      </div>` : `
      <div style="background:rgba(52,211,153,.06);border:1px solid rgba(52,211,153,.15);border-radius:var(--radius-sm);padding:12px">
        <p style="font-size:12px;color:#34d399;margin:0">✓ Your account already exists. Click Accept to join this organization.</p>
      </div>`}
    <p id="ai-err" style="color:var(--red);font-size:12px;margin-top:12px;display:none"></p>`,
    `${ssBtn('Decline',"ssCloseModal('ss-accept-invite')","ghost")}${ssBtn(`${isNew?'Create Account & ':''}Accept Invite`,`ssAcceptInvite('${token}',${isNew})`)}`
  );
}

async function ssAcceptInvite(token, isNew){
  const errEl = document.getElementById('ai-err');
  errEl.style.display='none';
  const payload = {};
  if(isNew){
    payload.name = document.getElementById('ai-name')?.value?.trim();
    payload.password = document.getElementById('ai-pwd')?.value;
    if(!payload.name||!payload.password){ errEl.textContent='Name and password are required'; errEl.style.display='block'; return; }
    if(payload.password.length<8){ errEl.textContent='Password must be at least 8 characters'; errEl.style.display='block'; return; }
  }
  try {
    const r = await fetch(`/api/invites/${token}/accept`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}).then(res=>res.json());
    if(r.detail){ errEl.textContent=r.detail; errEl.style.display='block'; return; }
    ssCloseModal('ss-accept-invite');
    // Clear invite hash and show success
    history.replaceState(null, '', window.location.pathname);
    alert(`✓ ${r.message} Please sign in to continue.`);
  } catch(e){ errEl.textContent=e.message; errEl.style.display='block'; }
}

// ── Bootstrap: check for invite hash on page load ─────────────────────────────
window.addEventListener('DOMContentLoaded', async function(){
  await handleInviteHash();
});

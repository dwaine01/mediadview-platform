/**
 * crm-admin.js — Admin CRM + Plans Management + Full-Page Customer Creation Wizard
 * Phase 2C P1: Admin-side customer provisioning, plan management, and workspace CRM.
 *
 * ARCHITECTURE:
 *   loaders['customers']   — Customer list page
 *   loadCustomerDetail()   — Customer detail view (renders into pg-customers)
 *   loaders['cw-wizard']   — 6-step full-page customer creation wizard
 *   loaders['admin-plans'] — Plan management page
 *
 * WIZARD FLOW (no partial records until Step 6):
 *   Step 1: Customer Information
 *   Step 2: Organization / Workspace
 *   Step 3: Subscription Settings
 *   Step 4: Pricing Agreement
 *   Step 5: Customer User / Access
 *   Step 6: Review & Create → POST /api/admin/crm/provision
 */

/* ═══════════════════════════════════════════════════════
   SHARED HELPERS
═══════════════════════════════════════════════════════ */
function _crmDate(d) {
  if (!d) return '—';
  try { return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch (_) { return d; }
}
function _crmBadge(s) {
  const m = {
    active: '#34d399', prospect: '#a5b4fc', trial: '#60a5fa',
    suspended: '#f59e0b', churned: '#f87171', cancelled: '#f87171',
    free: '#94a3b8', starter: '#6366f1', pro: '#22d3ee', enterprise: '#f59e0b',
    standard: '#6366f1', custom: '#f59e0b',
  };
  const c = m[s?.toLowerCase()] || '#94a3b8';
  return `<span style="background:${c}22;color:${c};border:1px solid ${c}44;border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700">${s || '—'}</span>`;
}
function _crmErr(msg) {
  return `<div style="color:#f87171;font-size:13px;padding:12px 16px;background:#450a0a;border:1px solid #7f1d1d;border-radius:8px;margin-top:8px">${msg}</div>`;
}
let _toastTimeout = null;
function _showToast(msg, ok = true) {
  let t = document.getElementById('crm-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'crm-toast';
    t.style.cssText = 'position:fixed;bottom:32px;right:32px;padding:12px 22px;border-radius:12px;font-size:13px;font-weight:600;z-index:999;box-shadow:0 8px 30px rgba(0,0,0,.5);transition:opacity .3s';
    document.body.appendChild(t);
  }
  t.style.background = ok ? '#064e3b' : '#450a0a';
  t.style.color = ok ? '#34d399' : '#f87171';
  t.style.border = `1px solid ${ok ? '#065f46' : '#7f1d1d'}`;
  t.textContent = msg;
  t.style.opacity = '1';
  clearTimeout(_toastTimeout);
  _toastTimeout = setTimeout(() => { t.style.opacity = '0'; }, 3500);
}
function _crmRow(label, value, opts = {}) {
  return `<div style="display:flex;align-items:flex-start;gap:0;padding:10px 0;border-bottom:1px solid #1a2234">
    <span style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;min-width:${opts.lw || 180}px;padding-top:2px">${label}</span>
    <span style="font-size:13px;color:${opts.dim ? '#6b7280' : '#d1d5db'};flex:1">${value || '—'}</span>
  </div>`;
}
function _cwInp(id, label, type, placeholder, required, value = '') {
  return `<div>
    <label style="display:block;font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">${label}${required ? ' <span style="color:#f87171">*</span>' : ''}</label>
    <input id="${id}" type="${type}" class="inp" placeholder="${placeholder}" value="${escapeHtml(String(value || ''))}" style="width:100%;box-sizing:border-box">
  </div>`;
}
function _cwSel(id, label, options, value = '') {
  return `<div>
    <label style="display:block;font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">${label}</label>
    <select id="${id}" class="inp" style="width:100%;box-sizing:border-box">
      ${options.map(([v, l]) => `<option value="${v}" ${v === value ? 'selected' : ''}>${l}</option>`).join('')}
    </select>
  </div>`;
}
function _cwArea(id, label, placeholder, value = '') {
  return `<div>
    <label style="display:block;font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">${label}</label>
    <textarea id="${id}" class="inp" placeholder="${placeholder}" rows="3" style="width:100%;box-sizing:border-box;resize:vertical">${escapeHtml(String(value || ''))}</textarea>
  </div>`;
}

/* ═══════════════════════════════════════════════════════
   CUSTOMER LIST
═══════════════════════════════════════════════════════ */
loaders['customers'] = async function () {
  const el = document.getElementById('pg-customers');
  if (!el) return;
  try {
    const custs = await api('/admin/crm/customers?limit=200');
    el.innerHTML = `
      <div class="ph">
        <div>
          <h1>CRM Customers</h1>
          <p>${custs.length} customer${custs.length !== 1 ? 's' : ''}</p>
        </div>
        <button class="btn-p" onclick="openCreateCustomerWizard()">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>
          New Customer
        </button>
      </div>
      ${custs.length === 0
        ? `<div class="empty">
            <div class="empty-ico"><svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg></div>
            <h3>No customers yet</h3>
            <p>Use the "New Customer" button above to provision your first SaaS customer.</p>
          </div>`
        : `<div style="display:flex;flex-direction:column;gap:8px">
            ${custs.map(c => `
              <div class="card card-i" onclick="loadCustomerDetail('${c.id}')" style="display:flex;align-items:center;gap:14px;padding:16px 20px;cursor:pointer">
                <div style="width:40px;height:40px;border-radius:11px;background:linear-gradient(135deg,#4f46e5,#0891b2);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;color:#fff;flex-shrink:0">${(c.legal_name || '?')[0].toUpperCase()}</div>
                <div style="flex:1;min-width:0">
                  <div style="font-size:14px;font-weight:700;color:var(--t-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(c.legal_name || '—')}</div>
                  <div style="font-size:12px;color:var(--t-4);margin-top:2px">${escapeHtml(c.primary_contact_email || '')}${c.business_type ? ' · ' + c.business_type : ''}</div>
                </div>
                ${_crmBadge(c.status)}
                <div style="font-size:12px;color:var(--t-5)">${_crmDate(c.created_at)}</div>
                <svg width="16" height="16" fill="none" stroke="var(--t-5)" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M9 5l7 7-7 7"/></svg>
              </div>`).join('')}
           </div>`}`;
  } catch (e) {
    el.innerHTML = `<p style="color:var(--red);padding:40px">${e.message}</p>`;
  }
};

/* ═══════════════════════════════════════════════════════
   CUSTOMER DETAIL
═══════════════════════════════════════════════════════ */
async function loadCustomerDetail(customerId) {
  const el = document.getElementById('pg-customers');
  if (!el) return;
  // Make pg-customers visible
  document.querySelectorAll('.pg').forEach(x => x.classList.remove('on'));
  el.classList.add('on');
  document.querySelectorAll('.ni').forEach(n => n.classList.remove('on'));
  document.querySelector('[data-p="customers"]')?.classList.add('on');
  setMobileSidebar(false);

  el.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:280px;gap:14px"><div style="width:30px;height:30px;border:2.5px solid rgba(99,102,241,.15);border-top-color:var(--cyan,#22d3ee);border-radius:50%;animation:mvSpin 0.75s linear infinite"></div><p style="color:var(--t-4);font-size:13px">Loading customer…</p></div>`;

  try {
    const summary = await api(`/admin/crm/customers/${customerId}/summary`);
    const c = summary.customer;
    const orgSummaries = summary.organizations || [];
    const firstOrg = orgSummaries[0] || {};
    const org = firstOrg.organization;
    const sub = firstOrg.subscription;
    const pa = firstOrg.current_pricing_agreement;
    const planCfg = firstOrg.plan_config;
    const users = firstOrg.users || [];

    // Compute MRR from PA
    const mrr = pa?.agreed_monthly_price ?? planCfg?.monthly_price ?? 0;

    el.innerHTML = `
      <div style="max-width:900px">
        <!-- Header -->
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:28px">
          <button onclick="loaders['customers']()" style="padding:7px 14px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--t-3);font-size:12px;font-weight:600;cursor:pointer">
            ← All Customers
          </button>
          <div style="flex:1">
            <h1 style="font-size:24px;font-weight:800;color:var(--t-1);margin:0">${escapeHtml(c.legal_name || '—')}</h1>
            <div style="font-size:13px;color:var(--t-4);margin-top:2px">${escapeHtml(c.primary_contact_email || '')} ${c.source ? '· Source: ' + c.source : ''}</div>
          </div>
          ${_crmBadge(c.status)}
          ${mrr > 0 ? `<div style="text-align:right"><div style="font-size:22px;font-weight:800;color:var(--cyan)">$${Number(mrr).toLocaleString()}</div><div style="font-size:10px;color:var(--t-5);margin-top:2px">MRR</div></div>` : ''}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">
          <!-- Customer Info -->
          <div class="card" style="padding:20px">
            <h2 style="font-size:14px;font-weight:700;color:var(--t-1);margin-bottom:14px">Customer Information</h2>
            ${_crmRow('Legal Name', escapeHtml(c.legal_name))}
            ${_crmRow('Display Name', escapeHtml(c.display_name))}
            ${_crmRow('Contact', escapeHtml(c.primary_contact_name))}
            ${_crmRow('Email', escapeHtml(c.primary_contact_email))}
            ${_crmRow('Phone', escapeHtml(c.primary_contact_phone))}
            ${_crmRow('Business Type', escapeHtml(c.business_type))}
            ${_crmRow('Status', _crmBadge(c.status))}
            ${_crmRow('Created', _crmDate(c.created_at))}
            ${c.notes ? _crmRow('Notes', escapeHtml(c.notes)) : ''}
          </div>

          <!-- Organization -->
          <div class="card" style="padding:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
              <h2 style="font-size:14px;font-weight:700;color:var(--t-1)">Organization / Workspace</h2>
            </div>
            ${org ? `
              ${_crmRow('Name', escapeHtml(org.name))}
              ${_crmRow('Slug', org.slug || '—')}
              ${_crmRow('Plan', _crmBadge(org.plan))}
              ${_crmRow('Status', _crmBadge(org.status))}
              ${_crmRow('Timezone', org.timezone)}
              ${_crmRow('Language', org.language)}
              ${_crmRow('Account Ref', org.account_ref)}
              ${_crmRow('Created', _crmDate(org.created_at))}
            ` : '<p style="color:var(--t-4);font-size:13px">No organization found.</p>'}
          </div>
        </div>

        <!-- Subscription + Pricing -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">
          <div class="card" style="padding:20px">
            <h2 style="font-size:14px;font-weight:700;color:var(--t-1);margin-bottom:14px">Subscription</h2>
            ${sub ? `
              ${_crmRow('Status', _crmBadge(sub.status))}
              ${_crmRow('Billing Provider', sub.billing_provider)}
              ${_crmRow('Trial Ends', sub.trial_ends_at ? _crmDate(sub.trial_ends_at) : 'N/A')}
              ${_crmRow('Period Start', _crmDate(sub.current_period_start))}
              ${_crmRow('Period End', _crmDate(sub.current_period_end))}
              ${_crmRow('Created', _crmDate(sub.created_at))}
            ` : '<p style="color:var(--t-4);font-size:13px">No subscription found.</p>'}
          </div>
          <div class="card" style="padding:20px">
            <h2 style="font-size:14px;font-weight:700;color:var(--t-1);margin-bottom:14px">Pricing Agreement</h2>
            ${pa ? `
              ${_crmRow('Model', _crmBadge(pa.pricing_model))}
              ${_crmRow('Plan', _crmBadge(pa.plan_id))}
              ${_crmRow('Monthly Price', pa.agreed_monthly_price != null ? '$' + Number(pa.agreed_monthly_price).toLocaleString() : '—')}
              ${_crmRow('Screens Included', pa.screens_included)}
              ${_crmRow('Screens Limit', pa.screens_limit || 'Unlimited')}
              ${_crmRow('Extra Screen', pa.overage_price_per_screen != null ? '$' + pa.overage_price_per_screen + '/screen' : '—')}
              ${_crmRow('Billing Cycle', pa.billing_cycle)}
              ${_crmRow('Discount', pa.discount_percent != null ? pa.discount_percent + '%' : 'None')}
              ${_crmRow('Effective From', _crmDate(pa.effective_from))}
              ${pa.notes ? _crmRow('Notes', escapeHtml(pa.notes)) : ''}
            ` : '<p style="color:var(--t-4);font-size:13px">No pricing agreement found.</p>'}
          </div>
        </div>

        <!-- Users -->
        <div class="card" style="padding:20px;margin-bottom:20px">
          <h2 style="font-size:14px;font-weight:700;color:var(--t-1);margin-bottom:14px">Workspace Users (${users.length})</h2>
          ${users.length === 0
            ? '<p style="color:var(--t-4);font-size:13px">No users provisioned yet.</p>'
            : users.map(u => `
              <div style="display:flex;align-items:center;gap:14px;padding:10px 0;border-bottom:1px solid var(--border)">
                <div style="width:34px;height:34px;border-radius:50%;background:rgba(99,102,241,.15);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#818cf8;flex-shrink:0">${(u.name || u.email || 'U')[0].toUpperCase()}</div>
                <div style="flex:1;min-width:0">
                  <div style="font-size:14px;font-weight:600;color:var(--t-1)">${escapeHtml(u.name || '—')}</div>
                  <div style="font-size:12px;color:var(--t-4)">${escapeHtml(u.email)}</div>
                </div>
                ${_crmBadge(u.rbac_role?.replace('_', ' ') || u.role)}
                <div style="font-size:11px;color:var(--t-5)">${_crmDate(u.created_at)}</div>
              </div>`).join('')}
        </div>
      </div>`;
  } catch (e) {
    el.innerHTML = `<div style="padding:40px">
      <button onclick="loaders['customers']()" style="padding:7px 14px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--t-3);font-size:12px;font-weight:600;cursor:pointer;margin-bottom:16px">← All Customers</button>
      <p style="color:var(--red)">${e.message}</p>
    </div>`;
  }
}

/* ═══════════════════════════════════════════════════════
   PLANS MANAGEMENT
═══════════════════════════════════════════════════════ */
loaders['admin-plans'] = async function () {
  const el = document.getElementById('pg-admin-plans');
  if (!el) return;
  try {
    const plans = await api('/admin/plans');
    el.innerHTML = `
      <div class="ph">
        <div><h1>Pricing Plans</h1><p>Configure standard SaaS plans</p></div>
        <button class="btn-p" onclick="openCreatePlanModal()">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>
          New Plan
        </button>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px">
        ${plans.map(p => `
          <div class="card" style="padding:20px;position:relative">
            ${p.highlight ? `<div style="position:absolute;top:12px;right:12px;background:#6366f1;color:#fff;font-size:9px;font-weight:700;padding:2px 8px;border-radius:12px;letter-spacing:.05em">${escapeHtml(p.highlight_text || 'POPULAR')}</div>` : ''}
            <div style="font-size:18px;font-weight:800;color:var(--t-1);margin-bottom:4px">${escapeHtml(p.display_name)}</div>
            <div style="font-size:28px;font-weight:800;color:var(--cyan);margin-bottom:12px">${p.monthly_price === 0 ? 'Free' : '$' + p.monthly_price}<span style="font-size:13px;color:var(--t-4);font-weight:500">/mo</span></div>
            <div style="font-size:12px;color:var(--t-4);margin-bottom:14px">${p.screens_included} screen${p.screens_included !== 1 ? 's' : ''} included${p.price_per_extra_screen ? ' · $' + p.price_per_extra_screen + '/extra' : ''}</div>
            <div style="display:flex;gap:8px;margin-bottom:14px">
              ${_crmBadge(p.is_active ? 'active' : 'inactive')}
              ${_crmBadge(p.plan_id)}
            </div>
            <button onclick="openEditPlanModal('${p.plan_id}')" style="width:100%;padding:8px;background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.2);border-radius:8px;color:#818cf8;font-size:12px;font-weight:600;cursor:pointer">Edit Plan</button>
          </div>`).join('')}
      </div>`;
  } catch (e) {
    el.innerHTML = `<p style="color:var(--red);padding:40px">${e.message}</p>`;
  }
};

let _editingPlanId = null;
function openEditPlanModal(planId) {
  _editingPlanId = planId;
  api(`/admin/plans/${planId}`).then(plan => {
    const existing = document.getElementById('plan-modal');
    if (existing) existing.remove();
    const m = document.createElement('div');
    m.id = 'plan-modal';
    m.style.cssText = 'position:fixed;inset:0;background:rgba(2,6,18,.88);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)';
    m.innerHTML = `
      <div style="width:480px;max-height:90vh;overflow-y:auto;background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:28px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
          <h2 style="font-size:17px;font-weight:700">Edit Plan: ${escapeHtml(plan.display_name)}</h2>
          <button onclick="document.getElementById('plan-modal').remove()" class="btn-icon">✕</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px">
          <div><label class="inp-label">Display Name</label><input class="inp" id="pm-dname" value="${escapeHtml(plan.display_name || '')}"></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div><label class="inp-label">Monthly Price ($)</label><input class="inp" id="pm-price" type="number" step="0.01" min="0" value="${plan.monthly_price || 0}"></div>
            <div><label class="inp-label">Screens Included</label><input class="inp" id="pm-screens" type="number" min="0" value="${plan.screens_included || 1}"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div><label class="inp-label">Extra Screen Price ($)</label><input class="inp" id="pm-extra" type="number" step="0.01" min="0" value="${plan.price_per_extra_screen || 0}"></div>
            <div><label class="inp-label">Trial Days</label><input class="inp" id="pm-trial" type="number" min="0" value="${plan.trial_days || 0}"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
            <div><label class="inp-label">Active</label>
              <select class="inp" id="pm-active">
                <option value="true" ${plan.is_active ? 'selected' : ''}>Active</option>
                <option value="false" ${!plan.is_active ? 'selected' : ''}>Inactive</option>
              </select>
            </div>
            <div><label class="inp-label">Public</label>
              <select class="inp" id="pm-public">
                <option value="true" ${plan.is_public ? 'selected' : ''}>Public</option>
                <option value="false" ${!plan.is_public ? 'selected' : ''}>Hidden</option>
              </select>
            </div>
          </div>
          <div><label class="inp-label">Highlight Text (optional)</label><input class="inp" id="pm-hl" value="${escapeHtml(plan.highlight_text || '')}"></div>
          <button class="btn-p" onclick="_savePlan('${planId}')" style="width:100%;justify-content:center;margin-top:8px">Save Changes</button>
          <p id="pm-msg" style="font-size:12px;text-align:center;display:none"></p>
        </div>
      </div>`;
    document.body.appendChild(m);
  }).catch(e => _showToast('Failed to load plan: ' + e.message, false));
}

function openCreatePlanModal() {
  const existing = document.getElementById('plan-modal');
  if (existing) existing.remove();
  const m = document.createElement('div');
  m.id = 'plan-modal';
  m.style.cssText = 'position:fixed;inset:0;background:rgba(2,6,18,.88);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)';
  m.innerHTML = `
    <div style="width:480px;max-height:90vh;overflow-y:auto;background:var(--bg-card);border:1px solid var(--border);border-radius:16px;padding:28px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
        <h2 style="font-size:17px;font-weight:700">Create New Plan</h2>
        <button onclick="document.getElementById('plan-modal').remove()" class="btn-icon">✕</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px">
        <div><label class="inp-label">Plan ID <span style="color:var(--red)">*</span></label><input class="inp" id="pm-pid" placeholder="e.g. growth"></div>
        <div><label class="inp-label">Display Name <span style="color:var(--red)">*</span></label><input class="inp" id="pm-dname" placeholder="Growth"></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div><label class="inp-label">Monthly Price ($)</label><input class="inp" id="pm-price" type="number" step="0.01" min="0" value="0"></div>
          <div><label class="inp-label">Screens Included</label><input class="inp" id="pm-screens" type="number" min="1" value="1"></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div><label class="inp-label">Extra Screen Price ($)</label><input class="inp" id="pm-extra" type="number" step="0.01" min="0" value="0"></div>
          <div><label class="inp-label">Trial Days</label><input class="inp" id="pm-trial" type="number" min="0" value="14"></div>
        </div>
        <button class="btn-p" onclick="_createPlan()" style="width:100%;justify-content:center;margin-top:8px">Create Plan</button>
        <p id="pm-msg" style="font-size:12px;text-align:center;display:none"></p>
      </div>
    </div>`;
  document.body.appendChild(m);
}

async function _createPlan() {
  const msg = document.getElementById('pm-msg');
  const planId = document.getElementById('pm-pid')?.value.trim().toLowerCase();
  const dname = document.getElementById('pm-dname')?.value.trim();
  if (!planId) { msg.style.display = 'block'; msg.style.color = '#f87171'; msg.textContent = 'Plan ID is required.'; return; }
  if (!dname) { msg.style.display = 'block'; msg.style.color = '#f87171'; msg.textContent = 'Display Name is required.'; return; }
  try {
    const payload = {
      plan_id: planId,
      display_name: dname,
      monthly_price: parseFloat(document.getElementById('pm-price')?.value || 0),
      screens_included: parseInt(document.getElementById('pm-screens')?.value || 1),
      price_per_extra_screen: parseFloat(document.getElementById('pm-extra')?.value || 0),
      trial_days: parseInt(document.getElementById('pm-trial')?.value || 14),
      features: [],
      is_active: true,
      is_public: true,
      display_order: 99,
      highlight: false,
    };
    await api('/admin/plans', { method: 'POST', body: JSON.stringify(payload) });
    document.getElementById('plan-modal').remove();
    _showToast('Plan created!');
    loaders['admin-plans']();
  } catch (e) {
    msg.style.display = 'block'; msg.style.color = '#f87171'; msg.textContent = e.message;
  }
}

async function _savePlan(planId) {
  const msg = document.getElementById('pm-msg');
  try {
    const payload = {
      display_name: document.getElementById('pm-dname')?.value.trim(),
      monthly_price: parseFloat(document.getElementById('pm-price')?.value || 0),
      screens_included: parseInt(document.getElementById('pm-screens')?.value || 1),
      price_per_extra_screen: parseFloat(document.getElementById('pm-extra')?.value || 0),
      trial_days: parseInt(document.getElementById('pm-trial')?.value || 0),
      is_active: document.getElementById('pm-active')?.value === 'true',
      is_public: document.getElementById('pm-public')?.value === 'true',
      highlight_text: document.getElementById('pm-hl')?.value.trim() || null,
    };
    await api(`/admin/plans/${planId}`, { method: 'PUT', body: JSON.stringify(payload) });
    document.getElementById('plan-modal').remove();
    _showToast('Plan updated!');
    loaders['admin-plans']();
  } catch (e) {
    if (msg) { msg.style.display = 'block'; msg.style.color = '#f87171'; msg.textContent = e.message; }
  }
}

/* ═══════════════════════════════════════════════════════
   FULL-PAGE CUSTOMER CREATION WIZARD
   Steps: 1=Customer · 2=Organization · 3=Subscription · 4=Pricing · 5=User · 6=Review
═══════════════════════════════════════════════════════ */

let _cwState = {
  step: 1,
  plans: [],
  planMap: {},
  // Step 1
  legalName: '', displayName: '', contactName: '', contactEmail: '',
  contactPhone: '', businessType: '', billingAddress: '', customerNotes: '', customerStatus: 'prospect',
  // Step 2
  orgName: '', orgTimezone: 'America/New_York', orgLanguage: 'en', orgAccountRef: '',
  // Step 3
  subStatus: 'trial', subBillingProvider: 'manual', subTrialEndsAt: '',
  // Step 4
  planId: 'starter', pricingModel: 'standard',
  customMonthlyPrice: '', customScreensIncluded: '', customScreenExtraPrice: '',
  customScreensLimit: '', customBillingInterval: 'monthly', customDiscount: '', paNotes: '',
  // Step 5
  userEmail: '', userName: '', userRole: 'SELF_SERVICE_OWNER',
  // Result
  result: null,
};

// Entry point: reset state, load plans, navigate to wizard page
async function openCreateCustomerWizard() {
  // Reset state
  Object.assign(_cwState, {
    step: 1, plans: [], planMap: {},
    legalName: '', displayName: '', contactName: '', contactEmail: '',
    contactPhone: '', businessType: '', billingAddress: '', customerNotes: '', customerStatus: 'prospect',
    orgName: '', orgTimezone: 'America/New_York', orgLanguage: 'en', orgAccountRef: '',
    subStatus: 'trial', subBillingProvider: 'manual', subTrialEndsAt: '',
    planId: 'starter', pricingModel: 'standard',
    customMonthlyPrice: '', customScreensIncluded: '', customScreenExtraPrice: '',
    customScreensLimit: '', customBillingInterval: 'monthly', customDiscount: '', paNotes: '',
    userEmail: '', userName: '', userRole: 'SELF_SERVICE_OWNER',
    result: null,
  });
  // Pre-load plans
  try {
    const plans = await api('/admin/plans');
    _cwState.plans = plans;
    _cwState.planMap = {};
    plans.forEach(p => { _cwState.planMap[p.plan_id] = p; });
  } catch (_) { /* non-blocking */ }

  go('cw-wizard');
}

// Loader: renders the current wizard step into pg-cw-wizard
loaders['cw-wizard'] = function () {
  const el = document.getElementById('pg-cw-wizard');
  if (!el) return;

  if (_cwState.step === 7) {
    el.innerHTML = _cwRenderSuccess();
    return;
  }

  const stepLabels = ['Customer', 'Organization', 'Subscription', 'Pricing', 'User', 'Review'];
  const stepIndicator = `
    <div style="display:flex;align-items:center;gap:0;margin-bottom:32px;overflow-x:auto;padding-bottom:4px">
      ${stepLabels.map((label, i) => {
        const n = i + 1;
        const done = n < _cwState.step;
        const current = n === _cwState.step;
        const color = done ? '#34d399' : current ? '#6366f1' : '#374151';
        const bg = done ? '#064e3b' : current ? 'rgba(99,102,241,.15)' : '#1f2937';
        const tc = done ? '#34d399' : current ? '#a5b4fc' : '#6b7280';
        return `
          <div style="display:flex;align-items:center;gap:0;flex-shrink:0">
            <div style="display:flex;flex-direction:column;align-items:center;gap:4px">
              <div style="width:32px;height:32px;border-radius:50%;background:${bg};border:2px solid ${color};display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:${color}">${done ? '✓' : n}</div>
              <span style="font-size:10px;font-weight:600;color:${tc};white-space:nowrap">${label}</span>
            </div>
            ${i < 5 ? `<div style="width:40px;height:2px;background:${done ? '#34d399' : '#1f2937'};margin-bottom:16px;flex-shrink:0"></div>` : ''}
          </div>`;
      }).join('')}
    </div>`;

  const renders = [null, _cwRenderStep1, _cwRenderStep2, _cwRenderStep3, _cwRenderStep4, _cwRenderStep5, _cwRenderStep6];
  const stepContent = renders[_cwState.step] ? renders[_cwState.step]() : '';

  el.innerHTML = `
    <div style="max-width:820px">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px">
        <button onclick="go('customers')" style="padding:7px 14px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;color:var(--t-3);font-size:12px;font-weight:600;cursor:pointer">← Cancel</button>
        <div>
          <h1 style="font-size:22px;font-weight:800;color:var(--t-1);margin:0">New Customer</h1>
          <p style="font-size:13px;color:var(--t-4);margin:0">Complete all 6 steps to provision the customer</p>
        </div>
      </div>
      ${stepIndicator}
      <div class="card" style="padding:28px">
        ${stepContent}
      </div>
    </div>`;
};

// Save form values from the current step into state
function _cwSave(step) {
  const v = id => document.getElementById(id)?.value ?? '';
  switch (step) {
    case 1:
      _cwState.legalName = v('cw-legal').trim();
      _cwState.displayName = v('cw-display').trim();
      _cwState.contactName = v('cw-cn').trim();
      _cwState.contactEmail = v('cw-ce').trim();
      _cwState.contactPhone = v('cw-cp').trim();
      _cwState.businessType = v('cw-btype');
      _cwState.billingAddress = v('cw-addr').trim();
      _cwState.customerNotes = v('cw-notes').trim();
      _cwState.customerStatus = v('cw-status');
      break;
    case 2:
      _cwState.orgName = v('cw-org-name').trim();
      _cwState.orgTimezone = v('cw-tz');
      _cwState.orgLanguage = v('cw-lang');
      _cwState.orgAccountRef = v('cw-ref').trim();
      break;
    case 3:
      _cwState.subStatus = v('cw-sub-status');
      _cwState.subBillingProvider = v('cw-billing-prov');
      _cwState.subTrialEndsAt = v('cw-trial-end');
      break;
    case 4:
      _cwState.planId = v('cw-pa-plan');
      _cwState.pricingModel = v('cw-pm');
      _cwState.customMonthlyPrice = v('cw-price').trim();
      _cwState.customScreensIncluded = v('cw-screens').trim();
      _cwState.customScreenExtraPrice = v('cw-extra').trim();
      _cwState.customScreensLimit = v('cw-limit').trim();
      _cwState.customBillingInterval = v('cw-billing-int');
      _cwState.customDiscount = v('cw-discount').trim();
      _cwState.paNotes = v('cw-pa-notes').trim();
      break;
    case 5:
      _cwState.userEmail = v('cw-user-email').trim();
      _cwState.userName = v('cw-user-name').trim();
      _cwState.userRole = v('cw-user-role');
      break;
  }
}

function _cwValidate(step) {
  switch (step) {
    case 1: {
      if (!_cwState.legalName) return 'Legal / Business Name is required.';
      if (!_cwState.contactName) return 'Contact Name is required.';
      if (!_cwState.contactEmail || !_cwState.contactEmail.includes('@')) return 'A valid Contact Email is required.';
      return null;
    }
    case 2: {
      if (!_cwState.orgName) return 'Organization Name is required.';
      return null;
    }
    case 3: return null;
    case 4: {
      if (_cwState.pricingModel === 'custom') {
        const p = parseFloat(_cwState.customMonthlyPrice);
        const s = parseInt(_cwState.customScreensIncluded);
        if (isNaN(p) || p < 0) return 'Monthly Price must be a valid number ≥ 0.';
        if (isNaN(s) || s < 0) return 'Screens Included must be a valid number ≥ 0.';
      }
      return null;
    }
    case 5: {
      if (!_cwState.userEmail || !_cwState.userEmail.includes('@')) return 'A valid Login Email is required.';
      if (!_cwState.userName) return 'User Name is required.';
      return null;
    }
    default: return null;
  }
}

// Next: save + validate + advance
function _cwNext(fromStep) {
  _cwSave(fromStep);
  const err = _cwValidate(fromStep);
  if (err) {
    const errEl = document.getElementById(`cw-err-${fromStep}`);
    if (errEl) { errEl.style.display = 'block'; errEl.innerHTML = _crmErr(err); }
    return;
  }
  // Auto-fill Step 5 from Step 1 if empty
  if (fromStep === 1) {
    if (!_cwState.userEmail) _cwState.userEmail = _cwState.contactEmail;
    if (!_cwState.userName) _cwState.userName = _cwState.contactName;
    if (!_cwState.orgName) _cwState.orgName = _cwState.legalName;
  }
  _cwState.step = fromStep + 1;
  loaders['cw-wizard']();
}

// Back: save (no validation) + retreat
function _cwBack(fromStep) {
  _cwSave(fromStep);
  _cwState.step = fromStep - 1;
  loaders['cw-wizard']();
}

// ─── STEP RENDERERS ───────────────────────────────────────────────────────────

function _cwRenderStep1() {
  const s = _cwState;
  return `
    <h2 style="font-size:17px;font-weight:700;color:var(--t-1);margin-bottom:4px">Step 1: Customer Information</h2>
    <p style="font-size:13px;color:var(--t-4);margin-bottom:24px">Business details and primary contact for this customer account.</p>
    <div id="cw-err-1"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwInp('cw-legal', 'Legal / Business Name', 'text', 'Acme Corporation', true, s.legalName)}
      ${_cwInp('cw-display', 'Display Name', 'text', 'Acme (optional)', false, s.displayName)}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwInp('cw-cn', 'Primary Contact Name', 'text', 'Jane Smith', true, s.contactName)}
      ${_cwInp('cw-ce', 'Contact Email', 'email', 'jane@acme.com', true, s.contactEmail)}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwInp('cw-cp', 'Contact Phone', 'tel', '+1 (555) 123-4567', false, s.contactPhone)}
      ${_cwSel('cw-btype', 'Business Type', [
        ['', 'Select type…'], ['Restaurant', 'Restaurant'], ['Retail', 'Retail Store'],
        ['Healthcare', 'Healthcare'], ['Entertainment', 'Entertainment'], ['Corporate', 'Corporate'],
        ['Hotel', 'Hotel / Hospitality'], ['Education', 'Education'], ['Other', 'Other'],
      ], s.businessType)}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwInp('cw-addr', 'Billing Address', 'text', '123 Main St, City, State', false, s.billingAddress)}
      ${_cwSel('cw-status', 'Customer Status', [
        ['prospect', 'Prospect'], ['active', 'Active'],
      ], s.customerStatus)}
    </div>
    ${_cwArea('cw-notes', 'Notes', 'Internal notes about this customer…', s.customerNotes)}
    <div style="display:flex;justify-content:flex-end;margin-top:24px">
      <button class="btn-p" onclick="_cwNext(1)">Next: Organization →</button>
    </div>`;
}

function _cwRenderStep2() {
  const s = _cwState;
  const tzOptions = [
    ['America/New_York', 'Eastern (New York)'], ['America/Chicago', 'Central (Chicago)'],
    ['America/Denver', 'Mountain (Denver)'], ['America/Los_Angeles', 'Pacific (LA)'],
    ['America/Sao_Paulo', 'Brazil (São Paulo)'], ['America/Mexico_City', 'Mexico City'],
    ['Europe/London', 'London'], ['Europe/Madrid', 'Madrid'], ['Europe/Paris', 'Paris'],
    ['Asia/Tokyo', 'Tokyo'], ['Australia/Sydney', 'Sydney'], ['UTC', 'UTC'],
  ];
  return `
    <h2 style="font-size:17px;font-weight:700;color:var(--t-1);margin-bottom:4px">Step 2: Organization / Workspace</h2>
    <p style="font-size:13px;color:var(--t-4);margin-bottom:24px">The Organization is the technical tenant boundary — all screens, users, and content live here.</p>
    <div id="cw-err-2"></div>
    <div style="display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwInp('cw-org-name', 'Organization / Workspace Name', 'text', 'Acme Digital Signage', true, s.orgName || s.legalName)}
      ${_cwSel('cw-lang', 'Language', [
        ['en', 'English'], ['es', 'Español'], ['pt', 'Português'], ['fr', 'Français'],
      ], s.orgLanguage)}
    </div>
    <div style="display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwSel('cw-tz', 'Timezone', tzOptions, s.orgTimezone)}
      ${_cwInp('cw-ref', 'Account Reference', 'text', 'ACC-001 (optional)', false, s.orgAccountRef)}
    </div>
    <div style="display:flex;justify-content:space-between;margin-top:24px">
      <button onclick="_cwBack(2)" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
      <button class="btn-p" onclick="_cwNext(2)">Next: Subscription →</button>
    </div>`;
}

function _cwRenderStep3() {
  const s = _cwState;
  const today = new Date().toISOString().split('T')[0];
  const in14 = new Date(Date.now() + 14 * 864e5).toISOString().split('T')[0];
  return `
    <h2 style="font-size:17px;font-weight:700;color:var(--t-1);margin-bottom:4px">Step 3: Subscription Settings</h2>
    <p style="font-size:13px;color:var(--t-4);margin-bottom:24px">Configure subscription lifecycle and billing provider. Pricing terms are set in the next step.</p>
    <div id="cw-err-3"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwSel('cw-sub-status', 'Initial Status', [
        ['trial', 'Trial'], ['active', 'Active'],
        ['suspended', 'Suspended'],
      ], s.subStatus)}
      ${_cwSel('cw-billing-prov', 'Billing Provider', [
        ['manual', 'Manual / Invoice'], ['stripe', 'Stripe (mocked)'], ['other', 'Other'],
      ], s.subBillingProvider)}
    </div>
    <div style="margin-bottom:14px">
      ${_cwInp('cw-trial-end', 'Trial End Date (optional)', 'date', '', false, s.subTrialEndsAt || (s.subStatus === 'trial' ? in14 : ''))}
    </div>
    <div style="background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.15);border-radius:10px;padding:14px;font-size:12px;color:var(--t-4);margin-bottom:14px">
      <strong style="color:#a5b4fc">ℹ</strong> The subscription period starts today (${today}) and runs for 30 days by default. Pricing details are configured in the next step.
    </div>
    <div style="display:flex;justify-content:space-between;margin-top:24px">
      <button onclick="_cwBack(3)" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
      <button class="btn-p" onclick="_cwNext(3)">Next: Pricing Agreement →</button>
    </div>`;
}

function _cwRenderStep4() {
  const s = _cwState;
  const planOpts = (s.plans.length > 0 ? s.plans : [
    { plan_id: 'free', display_name: 'Free', monthly_price: 0, screens_included: 1 },
    { plan_id: 'starter', display_name: 'Starter', monthly_price: 49, screens_included: 3 },
    { plan_id: 'pro', display_name: 'Pro', monthly_price: 149, screens_included: 10 },
    { plan_id: 'enterprise', display_name: 'Enterprise', monthly_price: 499, screens_included: 50 },
  ]).map(p => [p.plan_id, `${p.display_name} — $${p.monthly_price}/mo · ${p.screens_included} screens`]);

  const selPlan = s.planMap[s.planId];
  const isCustom = s.pricingModel === 'custom';

  return `
    <h2 style="font-size:17px;font-weight:700;color:var(--t-1);margin-bottom:4px">Step 4: Pricing Agreement</h2>
    <p style="font-size:13px;color:var(--t-4);margin-bottom:24px">Define the commercial terms. Standard uses the plan's configured price. Custom lets you override any field.</p>
    <div id="cw-err-4"></div>

    <!-- Plan selector -->
    <div style="margin-bottom:16px">
      ${_cwSel('cw-pa-plan', 'Subscription Plan', planOpts, s.planId)}
    </div>

    <!-- Pricing mode -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px">
      <label onclick="_cwSelectPM('standard')" style="display:flex;align-items:center;gap:12px;padding:14px;border-radius:10px;cursor:pointer;border:2px solid ${!isCustom ? '#6366f1' : 'var(--border)'};background:${!isCustom ? 'rgba(99,102,241,.08)' : 'var(--bg-2)'}">
        <input type="radio" name="cw-pm-radio" value="standard" ${!isCustom ? 'checked' : ''} style="accent-color:#6366f1">
        <div>
          <div style="font-size:13px;font-weight:700;color:${!isCustom ? '#a5b4fc' : 'var(--t-2)'}">STANDARD</div>
          <div style="font-size:11px;color:var(--t-4)">Use plan's configured pricing</div>
        </div>
      </label>
      <label onclick="_cwSelectPM('custom')" style="display:flex;align-items:center;gap:12px;padding:14px;border-radius:10px;cursor:pointer;border:2px solid ${isCustom ? '#f59e0b' : 'var(--border)'};background:${isCustom ? 'rgba(245,158,11,.06)' : 'var(--bg-2)'}">
        <input type="radio" name="cw-pm-radio" value="custom" ${isCustom ? 'checked' : ''} style="accent-color:#f59e0b">
        <div>
          <div style="font-size:13px;font-weight:700;color:${isCustom ? '#fcd34d' : 'var(--t-2)'}">CUSTOM</div>
          <div style="font-size:11px;color:var(--t-4)">Override any pricing field</div>
        </div>
      </label>
    </div>
    <input type="hidden" id="cw-pm" value="${s.pricingModel}">

    <!-- Standard: show plan summary -->
    <div id="cw-plan-info-box" style="display:${!isCustom ? 'block' : 'none'};background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.18);border-radius:10px;padding:16px;margin-bottom:16px">
      ${selPlan ? `
        <div style="font-size:12px;font-weight:600;color:#818cf8;margin-bottom:8px">Plan: ${selPlan.display_name}</div>
        <div style="display:flex;gap:24px;flex-wrap:wrap">
          <div><span style="font-size:22px;font-weight:800;color:#f3f4f6">$${selPlan.monthly_price}</span><span style="font-size:12px;color:var(--t-4)">/mo</span></div>
          <div style="font-size:13px;color:var(--t-3);align-self:center">${selPlan.screens_included} screen${selPlan.screens_included !== 1 ? 's' : ''} included${selPlan.price_per_extra_screen ? ' · $' + selPlan.price_per_extra_screen + '/extra' : ''}</div>
          ${selPlan.trial_days > 0 ? `<div style="font-size:12px;color:#60a5fa;align-self:center">${selPlan.trial_days}-day trial</div>` : ''}
        </div>` : '<p style="color:var(--t-4);font-size:13px">Select a plan above to see its pricing.</p>'}
    </div>

    <!-- Custom pricing fields -->
    <div id="cw-custom-pricing" style="display:${isCustom ? 'block' : 'none'}">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
        ${_cwInp('cw-price', 'Monthly Price ($)', 'number', '299.00', true, s.customMonthlyPrice || (selPlan?.monthly_price ?? ''))}
        ${_cwInp('cw-screens', 'Screens Included', 'number', '12', true, s.customScreensIncluded || (selPlan?.screens_included ?? ''))}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px">
        ${_cwInp('cw-extra', 'Extra Screen Price ($)', 'number', '25.00', false, s.customScreenExtraPrice || (selPlan?.price_per_extra_screen ?? ''))}
        ${_cwInp('cw-limit', 'Screen Limit (blank=unlimited)', 'number', '100', false, s.customScreensLimit)}
        ${_cwInp('cw-discount', 'Discount (%)', 'number', '10', false, s.customDiscount)}
      </div>
      <div style="display:grid;grid-template-columns:1fr 2fr;gap:14px;margin-bottom:14px">
        ${_cwSel('cw-billing-int', 'Billing Interval', [
          ['monthly', 'Monthly'], ['quarterly', 'Quarterly'], ['annual', 'Annual'],
        ], s.customBillingInterval)}
        ${_cwArea('cw-pa-notes', 'Contract Notes', 'e.g. 12-screen deal for Supermarket XYZ…', s.paNotes)}
      </div>
    </div>

    <div style="display:flex;justify-content:space-between;margin-top:24px">
      <button onclick="_cwBack(4)" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
      <button class="btn-p" onclick="_cwNext(4)">Next: Customer User →</button>
    </div>`;
}

function _cwSelectPM(mode) {
  _cwState.pricingModel = mode;
  const hidInput = document.getElementById('cw-pm');
  if (hidInput) hidInput.value = mode;
  const customDiv = document.getElementById('cw-custom-pricing');
  const planBox = document.getElementById('cw-plan-info-box');
  if (customDiv) customDiv.style.display = mode === 'custom' ? 'block' : 'none';
  if (planBox) planBox.style.display = mode === 'standard' ? 'block' : 'none';
  // Update radio labels
  document.querySelectorAll('label[onclick^="_cwSelectPM"]').forEach(lbl => {
    const val = lbl.querySelector('input[type=radio]')?.value;
    const isChosen = val === mode;
    lbl.style.borderColor = isChosen ? (mode === 'custom' ? '#f59e0b' : '#6366f1') : 'var(--border)';
    lbl.style.background = isChosen ? (mode === 'custom' ? 'rgba(245,158,11,.06)' : 'rgba(99,102,241,.08)') : 'var(--bg-2)';
    const title = lbl.querySelector('div:first-child');
    if (title) title.style.color = isChosen ? (mode === 'custom' ? '#fcd34d' : '#a5b4fc') : 'var(--t-2)';
  });
}

function _cwRenderStep5() {
  const s = _cwState;
  return `
    <h2 style="font-size:17px;font-weight:700;color:var(--t-1);margin-bottom:4px">Step 5: Customer User / Access</h2>
    <p style="font-size:13px;color:var(--t-4);margin-bottom:24px">Create the workspace login for the customer. A secure temporary password will be generated — shown once after creation.</p>
    <div id="cw-err-5"></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
      ${_cwInp('cw-user-email', 'Login Email', 'email', 'owner@acme.com', true, s.userEmail || s.contactEmail)}
      ${_cwInp('cw-user-name', 'Full Name', 'text', 'Jane Smith', true, s.userName || s.contactName)}
    </div>
    <div style="margin-bottom:14px">
      ${_cwSel('cw-user-role', 'Workspace Role', [
        ['SELF_SERVICE_OWNER', 'Tenant Owner (full control)'],
        ['SELF_SERVICE_MANAGER', 'Tenant Manager (limited control)'],
      ], s.userRole)}
    </div>
    <div style="background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.15);border-radius:10px;padding:14px;font-size:12px;color:#fcd34d;margin-bottom:14px">
      <strong>⚠ Security Note:</strong> A random secure temporary password will be generated automatically and displayed <strong>once</strong> on the success screen. Share it securely with the customer. Do NOT store the plain-text password.
    </div>
    <div style="display:flex;justify-content:space-between;margin-top:24px">
      <button onclick="_cwBack(5)" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
      <button class="btn-p" onclick="_cwNext(5)">Next: Review & Create →</button>
    </div>`;
}

function _cwRenderStep6() {
  const s = _cwState;
  const plan = s.planMap[s.planId];
  const planName = plan?.display_name || s.planId;
  const monthlyPrice = s.pricingModel === 'custom'
    ? (s.customMonthlyPrice !== '' ? '$' + s.customMonthlyPrice + '/mo' : '—')
    : (plan ? '$' + plan.monthly_price + '/mo' : '—');
  const screensIncl = s.pricingModel === 'custom'
    ? (s.customScreensIncluded || plan?.screens_included || '—')
    : (plan?.screens_included || '—');

  const rSect = (title, color, rows) => `
    <div style="margin-bottom:20px">
      <div style="font-size:11px;font-weight:700;color:${color};text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;display:flex;align-items:center;gap:6px">
        <div style="width:8px;height:8px;border-radius:50%;background:${color}"></div>${title}
      </div>
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:4px 16px">
        ${rows.map(([k, v]) => `
          <div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)">
            <span style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.03em;min-width:170px">${k}</span>
            <span style="font-size:13px;color:#d1d5db">${v || '—'}</span>
          </div>`).join('')}
      </div>
    </div>`;

  return `
    <h2 style="font-size:17px;font-weight:700;color:var(--t-1);margin-bottom:4px">Step 6: Review & Create</h2>
    <p style="font-size:13px;color:var(--t-4);margin-bottom:24px">Review all details before provisioning. Records are only created after you click "Create Customer".</p>
    <div id="cw-err-6"></div>

    ${rSect('Customer', '#6366f1', [
      ['Legal Name', escapeHtml(s.legalName)],
      ['Contact', escapeHtml(s.contactName)],
      ['Email', escapeHtml(s.contactEmail)],
      ['Phone', escapeHtml(s.contactPhone)],
      ['Business Type', escapeHtml(s.businessType)],
      ['Status', s.customerStatus],
    ])}

    ${rSect('Organization', '#22d3ee', [
      ['Name', escapeHtml(s.orgName)],
      ['Timezone', s.orgTimezone],
      ['Language', s.orgLanguage],
      ['Account Ref', escapeHtml(s.orgAccountRef)],
    ])}

    ${rSect('Subscription', '#10b981', [
      ['Initial Status', s.subStatus],
      ['Billing Provider', s.subBillingProvider],
      ['Trial Ends', s.subTrialEndsAt || 'Not set'],
    ])}

    ${rSect('Pricing Agreement', '#f59e0b', [
      ['Plan', planName],
      ['Pricing Mode', s.pricingModel.toUpperCase()],
      ['Monthly Price', monthlyPrice],
      ['Screens Included', screensIncl],
      s.pricingModel === 'custom' && s.customScreenExtraPrice ? ['Extra Screen', '$' + s.customScreenExtraPrice + '/screen'] : ['Extra Screen', plan?.price_per_extra_screen ? '$' + plan.price_per_extra_screen + '/screen' : '—'],
      s.pricingModel === 'custom' && s.customDiscount ? ['Discount', s.customDiscount + '%'] : ['Discount', 'None'],
    ])}

    ${rSect('Customer User', '#a78bfa', [
      ['Login Email', escapeHtml(s.userEmail)],
      ['Name', escapeHtml(s.userName)],
      ['Role', s.userRole.replace('_', ' ')],
      ['Password', 'Auto-generated (shown once after creation)'],
    ])}

    <div id="cw-submit-err"></div>
    <div style="display:flex;justify-content:space-between;margin-top:28px;align-items:center">
      <button onclick="_cwBack(6)" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
      <button id="cw-create-btn" class="btn-p" onclick="_cwSubmit()" style="background:linear-gradient(135deg,#10b981,#059669);box-shadow:0 4px 14px rgba(16,185,129,.25);padding:12px 28px">
        ✓ Create Customer
      </button>
    </div>`;
}

async function _cwSubmit() {
  const btn = document.getElementById('cw-create-btn');
  const errEl = document.getElementById('cw-submit-err');
  if (btn) { btn.disabled = true; btn.textContent = 'Creating…'; }

  const s = _cwState;
  const payload = {
    // Customer
    legal_name: s.legalName,
    display_name: s.displayName || s.legalName,
    primary_contact_name: s.contactName,
    primary_contact_email: s.contactEmail,
    primary_contact_phone: s.contactPhone || null,
    business_type: s.businessType || null,
    billing_address: s.billingAddress || null,
    customer_notes: s.customerNotes || null,
    customer_status: s.customerStatus || 'prospect',
    // Organization
    org_name: s.orgName,
    org_timezone: s.orgTimezone || null,
    org_language: s.orgLanguage || 'en',
    org_account_ref: s.orgAccountRef || null,
    // Subscription
    sub_status: s.subStatus || 'trial',
    sub_billing_provider: s.subBillingProvider || 'manual',
    sub_trial_ends_at: s.subTrialEndsAt || null,
    // Pricing
    plan_id: s.planId || 'starter',
    pricing_model: s.pricingModel || 'standard',
    custom_monthly_price: s.customMonthlyPrice !== '' ? parseFloat(s.customMonthlyPrice) : null,
    custom_screens_included: s.customScreensIncluded !== '' ? parseInt(s.customScreensIncluded) : null,
    custom_screen_extra_price: s.customScreenExtraPrice !== '' ? parseFloat(s.customScreenExtraPrice) : null,
    custom_screens_limit: s.customScreensLimit !== '' ? parseInt(s.customScreensLimit) : null,
    custom_billing_interval: s.customBillingInterval || 'monthly',
    custom_discount: s.customDiscount !== '' ? parseFloat(s.customDiscount) : null,
    pa_notes: s.paNotes || null,
    // User
    user_email: s.userEmail,
    user_name: s.userName,
    user_role: s.userRole || 'SELF_SERVICE_OWNER',
  };

  try {
    const result = await api('/admin/crm/provision', { method: 'POST', body: JSON.stringify(payload) });
    _cwState.result = result;
    _cwState.step = 7;
    loaders['cw-wizard']();
  } catch (e) {
    if (errEl) { errEl.style.display = 'block'; errEl.innerHTML = _crmErr('Creation failed: ' + e.message); }
    if (btn) { btn.disabled = false; btn.textContent = '✓ Create Customer'; }
  }
}

function _cwRenderSuccess() {
  const r = _cwState.result;
  if (!r) return '<p style="color:var(--red);padding:40px">No result data. Please try again.</p>';
  const u = r.user || {};
  const c = r.customer || {};
  const org = r.organization || {};
  const sub = r.subscription || {};
  const pa = r.pricing_agreement || {};
  const mrr = pa.agreed_monthly_price != null ? pa.agreed_monthly_price : 0;

  return `
    <div style="max-width:640px;margin:0 auto;padding:8px 0">
      <!-- Success header -->
      <div style="text-align:center;margin-bottom:32px">
        <div style="width:64px;height:64px;border-radius:50%;background:rgba(16,185,129,.15);border:2px solid #10b981;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;font-size:28px">✓</div>
        <h1 style="font-size:24px;font-weight:800;color:#34d399;margin-bottom:8px">Customer Created!</h1>
        <p style="font-size:14px;color:var(--t-4)">The full SaaS stack has been provisioned: <strong style="color:var(--t-2)">${escapeHtml(c.legal_name)}</strong></p>
      </div>

      <!-- Temporary credentials — SHOW ONCE -->
      <div style="background:#1a1000;border:2px solid #f59e0b;border-radius:14px;padding:20px;margin-bottom:24px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
          <span style="font-size:16px">⚠️</span>
          <span style="font-size:13px;font-weight:700;color:#fcd34d">Temporary Access Credentials — Copy Now</span>
        </div>
        <p style="font-size:12px;color:#92400e;margin-bottom:14px">These credentials are shown <strong>only once</strong>. Share them securely with the customer. They can log in at the workspace URL.</p>
        <div style="display:flex;flex-direction:column;gap:10px">
          <div style="background:#0f0900;border:1px solid #78350f;border-radius:8px;padding:12px">
            <div style="font-size:10px;color:#92400e;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Login Email</div>
            <div style="font-size:16px;font-weight:700;color:#fcd34d;font-family:'JetBrains Mono',monospace">${escapeHtml(u.email || '')}</div>
          </div>
          <div style="background:#0f0900;border:1px solid #78350f;border-radius:8px;padding:12px">
            <div style="font-size:10px;color:#92400e;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Temporary Password</div>
            <div style="font-size:16px;font-weight:700;color:#fcd34d;font-family:'JetBrains Mono',monospace;letter-spacing:.08em">${escapeHtml(u.temporary_password || '')}</div>
          </div>
        </div>
        <p style="font-size:11px;color:#78350f;margin-top:12px">The customer must change their password after first login.</p>
      </div>

      <!-- Summary -->
      <div class="card" style="padding:20px;margin-bottom:20px">
        <h2 style="font-size:14px;font-weight:700;color:var(--t-1);margin-bottom:14px">Provisioning Summary</h2>
        ${_crmRow('Customer', escapeHtml(c.legal_name))}
        ${_crmRow('Organization', escapeHtml(org.name) + ` <span style="color:var(--t-5);font-size:11px">(slug: ${org.slug})</span>`)}
        ${_crmRow('Plan', _crmBadge(pa.plan_id || '') + ' ' + _crmBadge(pa.pricing_model || ''))}
        ${_crmRow('Monthly Price', mrr > 0 ? '$' + Number(mrr).toLocaleString() + '/mo' : 'Free')}
        ${_crmRow('Screens', pa.screens_included + ' included')}
        ${_crmRow('Subscription', _crmBadge(sub.status))}
        ${_crmRow('User Role', u.rbac_role?.replace('_', ' ') || '—')}
      </div>

      <div style="display:flex;gap:12px">
        <button onclick="_cwGoToCustomer('${c.id}')" class="btn-p" style="flex:1;justify-content:center;padding:13px">
          View Customer Detail →
        </button>
        <button onclick="loaders['customers']()" style="padding:13px 20px;background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">
          All Customers
        </button>
      </div>
    </div>`;
}

function _cwGoToCustomer(customerId) {
  // Navigate to customer detail without race conditions
  document.querySelectorAll('.pg').forEach(x => x.classList.remove('on'));
  const el = document.getElementById('pg-customers');
  if (el) el.classList.add('on');
  document.querySelectorAll('.ni').forEach(n => n.classList.remove('on'));
  document.querySelector('[data-p="customers"]')?.classList.add('on');
  setMobileSidebar(false);
  loadCustomerDetail(customerId);
}

// Expose globals needed by inline onclick handlers
window.openCreateCustomerWizard = openCreateCustomerWizard;
window.loadCustomerDetail = loadCustomerDetail;
window.openEditPlanModal = openEditPlanModal;
window.openCreatePlanModal = openCreatePlanModal;
window._cwNext = _cwNext;
window._cwBack = _cwBack;
window._cwSubmit = _cwSubmit;
window._cwSelectPM = _cwSelectPM;
window._cwGoToCustomer = _cwGoToCustomer;
window._savePlan = _savePlan;
window._createPlan = _createPlan;

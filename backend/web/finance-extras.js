// MediAd View — Finance Extras Module (Frontend)
// Depends on: app.js, finance.js
// Adds: SMTP Settings, Send Invoice, Users management, AR panel, Excel exports, Signature canvas

(function(){
  if (typeof loaders === 'undefined') return;
  const FAPI = '/finance';

  const fmt$ = v => '$' + Number(v||0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  const fmtDate = s => { if(!s) return '—'; const d=new Date(s); return isNaN(d)?s:d.toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}); };
  const esc = s => String(s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const status_badge = s => {
    const m = {active:'#10b981',pending:'#f59e0b',overdue:'#ef4444',paid:'#10b981',cancelled:'#94a3b8'};
    return `<span class="bdg" style="background:${m[s]||'#94a3b8'}22;color:${m[s]||'#94a3b8'}">${s||'—'}</span>`;
  };
  function val(id){ const e=document.getElementById(id); return e? e.value : ''; }

  // ============ Inject new tabs into finance dashboard ============
  const origFinance = loaders.finance;
  loaders.finance = async function(){
    const el = document.getElementById('pg-finance');
    if (!el) return;
    // Extra tabs beyond originals
    if (window._fTab === 'ar') return renderAR();
    if (window._fTab === 'users') return renderUsers();
    if (window._fTab === 'settings_email') return renderEmailSettings();
    return origFinance();
  };

  // Patch the tabs bar in original loader by waiting for it to render then appending tabs
  // We do this via observer
  const _origInner = HTMLDivElement.prototype.__finance_tabs_inject;
  function injectExtraTabs(){
    const el = document.getElementById('pg-finance');
    if (!el) return;
    const tabsBar = el.querySelector('div[style*="border-bottom:1px solid var(--border)"]');
    if (!tabsBar) return;
    if (tabsBar.dataset.extrasInjected) return;
    const extras = [
      {id:'ar', name:'Accounts Receivable', icon:'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2'},
      {id:'users', name:'Users & Roles', icon:'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2'},
      {id:'settings_email', name:'Email Settings', icon:'M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'},
    ];
    extras.forEach(t=>{
      const btn = document.createElement('button');
      btn.onclick = ()=>{ window._fTab=t.id; loaders.finance(); };
      btn.style.cssText = `display:flex;align-items:center;gap:8px;padding:9px 16px;border-radius:var(--rs);font-size:13px;font-weight:600;border:1px solid ${window._fTab===t.id?'rgba(37,99,235,.35)':'transparent'};cursor:pointer;background:${window._fTab===t.id?'var(--brand-tint)':'transparent'};color:${window._fTab===t.id?'var(--brand-dd)':'var(--t-3)'};transition:all .15s`;
      btn.innerHTML = `<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${t.icon}"/></svg>${t.name}`;
      tabsBar.appendChild(btn);
    });
    tabsBar.dataset.extrasInjected = '1';
  }
  new MutationObserver(()=>injectExtraTabs()).observe(document.body, {childList:true, subtree:true});

  function buildTabsBar(activeTab){
    const allTabs = [
      {id:'dashboard', name:'Dashboard'},
      {id:'clients', name:'Clients / CRM'},
      {id:'contracts', name:'Contracts'},
      {id:'invoices', name:'Invoices'},
      {id:'deposits', name:'Deposits'},
      {id:'payments', name:'Payments'},
      {id:'expenses', name:'Expenses'},
      {id:'ar', name:'💸 Accounts Receivable'},
      {id:'users', name:'👥 Users & Roles'},
      {id:'settings_email', name:'📧 Email Settings'},
    ];
    return `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:24px;border-bottom:1px solid var(--border);padding-bottom:14px">${allTabs.map(t=>`<button onclick="window._fTab='${t.id}';loaders.finance()" style="padding:9px 16px;border-radius:var(--rs);font-size:13px;font-weight:600;border:1px solid ${activeTab===t.id?'rgba(37,99,235,.35)':'transparent'};cursor:pointer;background:${activeTab===t.id?'var(--brand-tint)':'transparent'};color:${activeTab===t.id?'var(--brand-dd)':'var(--t-3)'};transition:all .15s">${t.name}</button>`).join('')}</div>`;
  }

  // ============ ACCOUNTS RECEIVABLE ============
  async function renderAR(){
    const el = document.getElementById('pg-finance');
    el.innerHTML = `<div class="ph"><div><h1>Accounts Receivable</h1><p>Outstanding invoices grouped by client</p></div></div>
    ${buildTabsBar(window._fTab)}
    <div id="f-content"><div class="card" style="padding:48px;text-align:center;color:var(--t-4)">Loading…</div></div>`;
    injectExtraTabs();
    const data = await api(FAPI + '/accounts-receivable');
    const s = data.summary;
    const c = document.getElementById('f-content');
    c.innerHTML = `
      <div class="st-grid">
        ${stat('Total Receivable', fmt$(s.total_ar), 'All open balances', '--amber', 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z')}
        ${stat('Clients Owing', s.total_clients_owing, '', '--brand', 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2')}
        ${stat('Overdue Invoices', s.total_overdue_invoices, '', '--red', 'M12 9v2m0 4h.01M5 19h14a2 2 0 001.84-2.75L13.74 4a2 2 0 00-3.48 0L3.16 16.25A2 2 0 005 19z')}
        ${stat('Open Invoices', s.total_open_invoices, '', '--cyan', 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2')}
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
        <h2 style="font-size:16px;font-weight:700">Outstanding by Client (${data.clients.length})</h2>
        <button class="btn-s" onclick="exportFile('accounts-receivable')">📥 Export Excel</button>
      </div>

      ${data.clients.length===0?'<div class="empty"><h3>🎉 No outstanding balances!</h3><p>All invoices are paid up</p></div>':
        data.clients.map(cl=>`<div class="card" style="padding:16px;margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
            <div style="flex:1;min-width:0">
              <div style="font-size:15px;font-weight:700;color:var(--t-1)">${esc(cl.client_name)}</div>
              <div style="font-size:12px;color:var(--t-4);margin-top:2px">${esc(cl.representative||'—')} · ${esc(cl.phone||'')}${cl.email?' · '+esc(cl.email):''}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:11px;color:var(--t-4)">Total Due</div>
              <div style="font-size:20px;font-weight:800;color:${cl.overdue_count>0?'var(--red)':'var(--amber)'}">${fmt$(cl.total_due)}</div>
              ${cl.overdue_count>0?'<div style="font-size:10px;color:var(--red);font-weight:700;margin-top:2px">'+cl.overdue_count+' OVERDUE</div>':''}
            </div>
          </div>
          <div style="background:var(--bg-1);border-radius:var(--rxs);padding:8px 12px">
            ${cl.invoices.map(i=>`<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-top:1px solid var(--border-l);font-size:12.5px">
              <span style="color:var(--brand-dd);font-weight:700">${esc(i.invoice_number)}</span>
              <span style="color:var(--t-4);font-size:11px">Due ${fmtDate(i.due_date)}</span>
              ${status_badge(i.status)}
              <span style="font-weight:700;color:var(--t-1);min-width:80px;text-align:right">${fmt$(i.balance||i.total)}</span>
              <button class="btn-s" style="padding:4px 10px;font-size:11px" onclick="sendInvoiceReminder('${i.id}','${esc(cl.email||'')}')">📧 Send Reminder</button>
            </div>`).join('')}
          </div>
        </div>`).join('')
      }`;
  }
  window.renderAR = renderAR;

  // ============ EMAIL SETTINGS ============
  async function renderEmailSettings(){
    const el = document.getElementById('pg-finance');
    el.innerHTML = `<div class="ph"><div><h1>Email / SMTP Settings</h1><p>Configure outgoing email server for invoices and reminders</p></div></div>
    ${buildTabsBar(window._fTab)}
    <div id="f-content"><div class="card" style="padding:48px;text-align:center;color:var(--t-4)">Loading…</div></div>`;
    injectExtraTabs();
    const c = document.getElementById('f-content');
    const s = await api(FAPI + '/settings/email');
    const enabled = s.enabled;
    c.innerHTML = `
      <div style="max-width:720px">
        <div class="card" style="padding:20px;margin-bottom:18px;background:${enabled?'var(--green-tint)':'var(--amber-tint)'};border-color:${enabled?'#a7f3d0':'#fde68a'}">
          <div style="display:flex;align-items:center;gap:10px">
            <div style="font-size:20px">${enabled?'✅':'⚠️'}</div>
            <div><div style="font-size:14px;font-weight:700;color:${enabled?'#047857':'#92400e'}">${enabled?'Email is enabled':'Email is disabled'}</div>
            <div style="font-size:12px;color:${enabled?'#065f46':'#78350f'}">${enabled?'Invoices and reminders will be sent automatically':'Configure SMTP and enable to start sending emails'}</div></div>
          </div>
        </div>

        <div class="card" style="padding:24px">
          <h2 style="font-size:15px;font-weight:700;margin-bottom:4px">SMTP Configuration</h2>
          <p style="font-size:12.5px;color:var(--t-4);margin-bottom:18px">For Titan email: <code style="background:var(--bg-1);padding:2px 6px;border-radius:4px">smtp.titan.email</code> port <code style="background:var(--bg-1);padding:2px 6px;border-radius:4px">587</code> (TLS)</p>

          <div class="row2">
            <div><label class="inp-label">SMTP Host <span class="req">*</span></label><input class="inp" id="es-host" value="${esc(s.smtp_host||'smtp.titan.email')}"></div>
            <div><label class="inp-label">SMTP Port <span class="req">*</span></label><input class="inp" id="es-port" type="number" value="${s.smtp_port||587}"></div>
          </div>
          <div class="row2" style="margin-top:12px">
            <div><label class="inp-label">SMTP Username (your email) <span class="req">*</span></label><input class="inp" id="es-user" value="${esc(s.smtp_user||'')}" placeholder="billing@mediadview.com"></div>
            <div><label class="inp-label">SMTP Password <span class="req">*</span></label><input class="inp" id="es-pwd" type="password" value="${s.password_set?'********':''}" placeholder="${s.password_set?'(unchanged)':'Your Titan password'}"></div>
          </div>
          <div class="row2" style="margin-top:12px">
            <div><label class="inp-label">From Name</label><input class="inp" id="es-fname" value="${esc(s.from_name||'MediAd View Billing')}" placeholder="MediAd View Billing"></div>
            <div><label class="inp-label">From Email</label><input class="inp" id="es-from" value="${esc(s.from_email||'')}" placeholder="billing@mediadview.com"></div>
          </div>
          <div style="margin-top:12px"><label class="inp-label">Reply-To (optional)</label><input class="inp" id="es-reply" value="${esc(s.reply_to||'')}" placeholder="Where customers reply when clicking 'Reply'"></div>

          <div style="margin-top:18px;padding:14px;background:var(--bg-1);border-radius:var(--rs);display:flex;align-items:center;gap:10px">
            <input type="checkbox" id="es-enabled" ${enabled?'checked':''} style="width:18px;height:18px;accent-color:var(--brand)">
            <label for="es-enabled" style="font-size:13px;font-weight:600;color:var(--t-1);cursor:pointer">Enable email sending</label>
          </div>

          <div style="display:flex;gap:10px;margin-top:20px">
            <button class="btn-p" onclick="saveEmailSettings()">💾 Save Settings</button>
            <button class="btn-s" onclick="testEmail()">🧪 Send Test Email</button>
          </div>
          <p id="es-msg" style="font-size:13px;margin-top:12px;display:none"></p>
        </div>

        <div class="card" style="padding:20px;margin-top:18px">
          <h3 style="font-size:14px;font-weight:700;margin-bottom:8px">📘 Titan Email Setup Help</h3>
          <ol style="font-size:13px;color:var(--t-3);padding-left:20px;line-height:1.7">
            <li>Login to your Titan dashboard (typically via <code>cp.titan.email</code> or your hosting provider).</li>
            <li>Make sure your email account (<code>billing@mediadview.com</code>) is active.</li>
            <li>Use <strong>smtp.titan.email</strong> with port <strong>587</strong> (TLS).</li>
            <li>Username = your full email address. Password = your Titan email password (or App Password if enabled).</li>
            <li>Click "Send Test Email" to verify your settings.</li>
          </ol>
        </div>
      </div>
    `;
  }
  window.renderEmailSettings = renderEmailSettings;

  window.saveEmailSettings = async function(){
    const msg = document.getElementById('es-msg');
    msg.style.display = 'none';
    const pwd = val('es-pwd');
    const body = {
      smtp_host: val('es-host'),
      smtp_port: parseInt(val('es-port'))||587,
      smtp_user: val('es-user'),
      smtp_password: pwd === '********' ? '' : pwd,  // empty keeps existing
      from_name: val('es-fname'),
      from_email: val('es-from'),
      reply_to: val('es-reply'),
      smtp_use_tls: true,
      enabled: document.getElementById('es-enabled').checked,
    };
    try {
      await api(FAPI + '/settings/email', {method:'PUT', body:JSON.stringify(body)});
      msg.textContent = '✓ Settings saved';
      msg.style.color = 'var(--green)';
      msg.style.display = 'block';
      setTimeout(()=>renderEmailSettings(), 800);
    } catch(e){
      msg.textContent = '✕ ' + e.message;
      msg.style.color = 'var(--red)';
      msg.style.display = 'block';
    }
  };

  window.testEmail = async function(){
    const to = prompt('Send test email to:', user.email);
    if (!to) return;
    const msg = document.getElementById('es-msg');
    msg.textContent = 'Sending test email...';
    msg.style.color = 'var(--t-3)';
    msg.style.display = 'block';
    try {
      // First save current settings if password changed
      await window.saveEmailSettings();
      await new Promise(r=>setTimeout(r,500));
      const r = await api(FAPI + '/settings/email/test', {method:'POST', body:JSON.stringify({to})});
      msg.textContent = '✓ ' + (r.message || 'Test email sent');
      msg.style.color = 'var(--green)';
    } catch(e){
      msg.textContent = '✕ ' + e.message;
      msg.style.color = 'var(--red)';
    }
  };

  // ============ SEND INVOICE BY EMAIL ============
  window.sendInvoiceEmail = async function(invoiceId, clientEmail){
    const inv = await api(FAPI + '/invoices/' + invoiceId);
    const cl = await api(FAPI + '/clients/' + inv.client_id);
    const to = clientEmail || cl.email || '';
    openSendInvoiceModal(invoiceId, to, cl, inv);
  };

  window.sendInvoiceReminder = async function(invoiceId, defaultEmail){
    sendInvoiceEmail(invoiceId, defaultEmail);
  };

  function openSendInvoiceModal(invoiceId, to, client, inv){
    closeFinModal();
    const html = `<div id="fin-modal" style="position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px);padding:20px;overflow-y:auto">
      <div style="width:100%;max-width:560px;background:#fff;border-radius:var(--rl);box-shadow:var(--sh-lg);overflow:hidden;display:flex;flex-direction:column">
        <div style="padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
          <div><div style="font-size:17px;font-weight:700">📧 Send Invoice</div>
          <div style="font-size:12px;color:var(--t-4);margin-top:2px">${esc(inv.invoice_number)} — ${esc(client.business_name)}</div></div>
          <button onclick="closeFinModal()" class="btn-icon">✕</button>
        </div>
        <div style="padding:24px;overflow-y:auto">
          <div><label class="inp-label">To <span class="req">*</span></label><input class="inp" id="si-to" value="${esc(to)}" placeholder="client@email.com"></div>
          <div style="margin-top:10px"><label class="inp-label">CC (optional)</label><input class="inp" id="si-cc"></div>
          <div style="margin-top:10px"><label class="inp-label">Custom message (added to email body, optional)</label><textarea class="inp" id="si-msg" rows="3" placeholder="e.g. Hi, please find this month's invoice attached. Reach out if you have any questions."></textarea></div>
          <div style="margin-top:14px;padding:12px;background:var(--brand-tint);border:1px solid #bfdbfe;border-radius:var(--rs);font-size:12px;color:var(--brand-dd)">
            📎 PDF will be attached automatically · Amount due: <strong>${fmt$(inv.balance||inv.total)}</strong>
          </div>
          <p id="si-msg-out" style="font-size:13px;margin-top:10px;display:none"></p>
        </div>
        <div style="padding:14px 24px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end;background:var(--bg-1)">
          <button class="btn-s" onclick="closeFinModal()">Cancel</button>
          <button class="btn-p" id="si-send">📧 Send Email</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    document.getElementById('si-send').onclick = async ()=>{
      const out = document.getElementById('si-msg-out');
      out.style.display='block';out.style.color='var(--t-3)';out.textContent='Sending...';
      try {
        const r = await api(FAPI + '/invoices/' + invoiceId + '/send', {method:'POST', body:JSON.stringify({
          to: val('si-to'), cc: val('si-cc'), custom_message: val('si-msg')
        })});
        out.style.color='var(--green)';
        out.textContent='✓ Email sent to ' + r.sent_to;
        setTimeout(()=>closeFinModal(), 1500);
      } catch(e){
        out.style.color='var(--red)';
        out.textContent='✕ ' + e.message;
      }
    };
  }

  // ============ USERS & ROLES ============
  async function renderUsers(){
    const el = document.getElementById('pg-finance');
    el.innerHTML = `<div class="ph"><div><h1>Users &amp; Roles</h1><p>Manage who can access the system and what they can do</p></div>
    <button class="btn-p" onclick="showNewUser()"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>New User</button></div>
    ${buildTabsBar(window._fTab)}
    <div id="f-content"><div class="card" style="padding:48px;text-align:center;color:var(--t-4)">Loading…</div></div>`;
    injectExtraTabs();
    const list = await api(FAPI + '/users');
    const c = document.getElementById('f-content');
    const roleInfo = {
      superadmin:{label:'Super Admin', color:'#7c3aed', desc:'Full access · Cannot be removed'},
      admin:{label:'Admin', color:'#2563eb', desc:'Full platform access'},
      accounting:{label:'Accounting', color:'#059669', desc:'Finance, invoicing, payments, reports'},
      sales:{label:'Sales', color:'#d97706', desc:'CRM, contracts, clients'},
      technical:{label:'Technical', color:'#0891b2', desc:'Screens, devices, deployments'},
      viewer:{label:'Viewer', color:'#64748b', desc:'Read-only access'},
      customer:{label:'Customer', color:'#94a3b8', desc:'External customer account'},
    };
    c.innerHTML = `
      <div class="card" style="padding:14px 18px;margin-bottom:16px;background:var(--brand-tint);border-color:#bfdbfe">
        <div style="font-size:13px;color:var(--brand-dd)">💡 <strong>Roles available:</strong> Super Admin · Admin · Accounting (finanzas) · Sales (ventas) · Technical (técnico) · Viewer (solo lectura)</div>
      </div>
      <div class="card">
        <div class="tbl-h" style="grid-template-columns:2fr 2fr 1.2fr 1fr auto"><span>Name</span><span>Email</span><span>Role</span><span>Status</span><span></span></div>
        ${list.map(u=>{
          const ri = roleInfo[u.role] || roleInfo.viewer;
          return `<div class="tbl-r" style="grid-template-columns:2fr 2fr 1.2fr 1fr auto">
            <div><div style="font-size:13.5px;font-weight:600">${esc(u.name)}</div><div style="font-size:11px;color:var(--t-4)">${esc(u.phone||'')}</div></div>
            <span style="font-size:13px;color:var(--t-3)">${esc(u.email)}</span>
            <span class="bdg" style="background:${ri.color}22;color:${ri.color};border-color:${ri.color}33" title="${ri.desc}">${ri.label}</span>
            ${u.active===false?'<span class="bdg bdg-cancelled">Disabled</span>':'<span class="bdg bdg-active">Active</span>'}
            <div style="display:flex;gap:4px">
              <button onclick="editUser('${u.id}')" class="btn-icon" style="width:28px;height:28px"><svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg></button>
              ${u.role==='superadmin'?'':`<button onclick="delUser('${u.id}')" class="btn-icon" style="width:28px;height:28px;color:var(--red)">✕</button>`}
            </div>
          </div>`;
        }).join('')}
      </div>
    `;
  }
  window.renderUsers = renderUsers;

  window.showNewUser = function(){
    openFormModal('New User', `
      <div class="row2"><div><label class="inp-label">Full Name <span class="req">*</span></label><input class="inp" id="nu-name"></div>
      <div><label class="inp-label">Email <span class="req">*</span></label><input class="inp" id="nu-email" type="email"></div></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">Phone</label><input class="inp" id="nu-phone"></div>
      <div><label class="inp-label">Password <span class="req">*</span></label><input class="inp" id="nu-pwd" type="password"></div></div>
      <div style="margin-top:12px"><label class="inp-label">Role <span class="req">*</span></label><select class="inp" id="nu-role">
        <option value="admin">Admin — Full access</option>
        <option value="accounting">Accounting — Finance, invoicing</option>
        <option value="sales">Sales — CRM, contracts, clients</option>
        <option value="technical">Technical — Screens, devices</option>
        <option value="viewer">Viewer — Read-only</option>
      </select></div>
    `, 'Create User', async ()=>{
      const body = {name:val('nu-name'),email:val('nu-email'),phone:val('nu-phone'),
                    password:val('nu-pwd'),role:val('nu-role')};
      if (!body.name||!body.email||!body.password) { alert('Name, email, password required'); return false; }
      await api(FAPI + '/users', {method:'POST', body:JSON.stringify(body)});
      renderUsers();
      return true;
    });
  };

  window.editUser = async function(id){
    const list = await api(FAPI + '/users');
    const u = list.find(x=>x.id===id);
    if (!u) return;
    openFormModal('Edit User', `
      <div class="row2"><div><label class="inp-label">Name</label><input class="inp" id="eu-name" value="${esc(u.name)}"></div>
      <div><label class="inp-label">Email</label><input class="inp" disabled value="${esc(u.email)}" style="opacity:.6"></div></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">Phone</label><input class="inp" id="eu-phone" value="${esc(u.phone||'')}"></div>
      <div><label class="inp-label">Role</label><select class="inp" id="eu-role">
        ${['admin','accounting','sales','technical','viewer'].map(r=>`<option value="${r}" ${u.role===r?'selected':''}>${r}</option>`).join('')}
      </select></div></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">New password (leave empty to keep)</label><input class="inp" id="eu-pwd" type="password"></div>
      <div><label class="inp-label">Status</label><select class="inp" id="eu-active">
        <option value="true" ${u.active!==false?'selected':''}>Active</option>
        <option value="false" ${u.active===false?'selected':''}>Disabled</option>
      </select></div></div>
    `, 'Save', async ()=>{
      const body = {name:val('eu-name'),phone:val('eu-phone'),role:val('eu-role'),
                    active:val('eu-active')==='true'};
      if (val('eu-pwd')) body.password = val('eu-pwd');
      await api(FAPI + '/users/' + id, {method:'PUT', body:JSON.stringify(body)});
      renderUsers();
      return true;
    });
  };

  window.delUser = async function(id){
    if (!confirm('Disable this user?')) return;
    await api(FAPI + '/users/' + id, {method:'DELETE'});
    renderUsers();
  };

  // Generic helper
  function openFormModal(title, contentHTML, primaryLabel, onSubmit){
    closeFinModal();
    document.body.insertAdjacentHTML('beforeend', `<div id="fin-modal" style="position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px);padding:20px;overflow-y:auto">
      <div style="width:100%;max-width:560px;background:#fff;border-radius:var(--rl);box-shadow:var(--sh-lg);overflow:hidden;max-height:90vh;display:flex;flex-direction:column">
        <div style="padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center"><div style="font-size:17px;font-weight:700">${title}</div><button onclick="closeFinModal()" class="btn-icon">✕</button></div>
        <div style="padding:24px;overflow-y:auto;flex:1">${contentHTML}<p id="fin-modal-msg" style="font-size:12px;margin-top:10px;display:none"></p></div>
        <div style="padding:14px 24px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end;background:var(--bg-1)"><button class="btn-s" onclick="closeFinModal()">Cancel</button><button class="btn-p" id="fm-submit">${primaryLabel}</button></div>
      </div></div>`);
    document.getElementById('fm-submit').onclick = async ()=>{
      try { const ok = await onSubmit(); if (ok!==false) closeFinModal(); }
      catch(e){ const m=document.getElementById('fin-modal-msg'); m.textContent=e.message;m.style.color='var(--red)';m.style.display='block'; }
    };
  }

  // ============ EXPORTS ============
  window.exportFile = async function(type){
    const tk = localStorage.getItem('mv_t');
    const map = {
      'invoices':'invoices.xlsx', 'payments':'payments.xlsx', 'expenses':'expenses.xlsx',
      'clients':'clients.xlsx', 'accounts-receivable':'accounts-receivable.xlsx',
    };
    const f = map[type] || type+'.xlsx';
    const resp = await fetch('/api/finance/export/'+f, {headers:{Authorization:'Bearer '+tk}});
    if (!resp.ok) { alert('Export failed'); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = f.replace('.xlsx','_'+new Date().toISOString().slice(0,10)+'.xlsx');
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  // ============ SIGNATURE CANVAS ============
  window.openSignatureModal = function(contractId, role){
    closeFinModal();
    const isLessor = role === 'lessor';
    document.body.insertAdjacentHTML('beforeend', `<div id="fin-modal" style="position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px);padding:20px">
      <div style="width:100%;max-width:560px;background:#fff;border-radius:var(--rl);box-shadow:var(--sh-lg);overflow:hidden">
        <div style="padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center"><div><div style="font-size:17px;font-weight:700">✍️ ${isLessor?'Lessor':'Lessee'} Signature</div><div style="font-size:12px;color:var(--t-4)">Sign below with your mouse or finger</div></div><button onclick="closeFinModal()" class="btn-icon">✕</button></div>
        <div style="padding:20px 24px">
          <canvas id="sig-canvas" width="500" height="180" style="width:100%;height:180px;border:2px dashed var(--border-s);border-radius:8px;background:#f8fafc;cursor:crosshair;touch-action:none"></canvas>
          <div style="display:flex;justify-content:space-between;margin-top:10px"><button class="btn-s" onclick="clearSig()">Clear</button><div style="font-size:11px;color:var(--t-4);align-self:center">Click and drag to sign</div></div>
        </div>
        <div style="padding:14px 24px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end;background:var(--bg-1)"><button class="btn-s" onclick="closeFinModal()">Cancel</button><button class="btn-p" id="sig-save">✓ Save Signature</button></div>
      </div></div>`);
    const canvas = document.getElementById('sig-canvas');
    const ctx = canvas.getContext('2d');
    // Set proper canvas resolution
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 2.2;
    ctx.lineCap = 'round';
    let drawing = false;
    const getPos = e => {
      const r = canvas.getBoundingClientRect();
      const t = e.touches ? e.touches[0] : e;
      return { x: t.clientX - r.left, y: t.clientY - r.top };
    };
    const start = e => { drawing=true; const p=getPos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); e.preventDefault(); };
    const move = e => { if(!drawing) return; const p=getPos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); e.preventDefault(); };
    const stop = () => { drawing=false; };
    canvas.addEventListener('mousedown', start);
    canvas.addEventListener('mousemove', move);
    canvas.addEventListener('mouseup', stop);
    canvas.addEventListener('mouseleave', stop);
    canvas.addEventListener('touchstart', start);
    canvas.addEventListener('touchmove', move);
    canvas.addEventListener('touchend', stop);
    window.clearSig = ()=>ctx.clearRect(0,0,canvas.width,canvas.height);
    document.getElementById('sig-save').onclick = async ()=>{
      const dataUrl = canvas.toDataURL('image/png');
      // Check if canvas is empty
      const blank = document.createElement('canvas');
      blank.width = canvas.width; blank.height = canvas.height;
      if (canvas.toDataURL() === blank.toDataURL()) { alert('Please sign first'); return; }
      const body = isLessor ? {lessor_signature:dataUrl} : {lessee_signature:dataUrl};
      await api(FAPI + '/contracts/' + contractId + '/sign', {method:'POST', body:JSON.stringify(body)});
      closeFinModal();
      window.open(FAPI + '/contracts/' + contractId + '/pdf', '_blank');
    };
  };

  // Override Generate Contract to also show signature buttons
  const origQuickContract = window.quickGenerateContract;
  window.quickGenerateContract = async function(clientId){
    if (!confirm('Generate a new contract using this client\'s locations & screens?')) return;
    try {
      const r = await api(FAPI + '/clients/' + clientId + '/quick-contract', {method:'POST', body:JSON.stringify({})});
      window.open(FAPI + '/contracts/' + r.contract.id + '/pdf', '_blank');
      window.open(FAPI + '/deposits/' + r.deposit.id + '/pdf', '_blank');
      viewClient(clientId);
    } catch(e){ alert('Error: ' + e.message); }
  };
  // Override view document buttons to use PDF where available
  window.viewContractPdf = id => window.open(FAPI + '/contracts/' + id + '/pdf', '_blank');
  window.viewInvoicePdf = id => window.open(FAPI + '/invoices/' + id + '/pdf', '_blank');
  window.viewDepositPdf = id => window.open(FAPI + '/deposits/' + id + '/pdf', '_blank');

})();

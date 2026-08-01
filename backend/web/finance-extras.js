// MediAd View — Finance Extras Module (Frontend)
// Depends on: app.js, finance.js
// Adds: SMTP Settings, Send Invoice, Users management, AR panel, Excel exports, Signature canvas

(function(){
  if (typeof loaders === 'undefined') return;
  const FAPI = '/finance';
  const FURL = '/api/finance'; // for direct browser URLs (window.open / iframe src)

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
    const map = {
      'invoices':'invoices.xlsx', 'payments':'payments.xlsx', 'expenses':'expenses.xlsx',
      'clients':'clients.xlsx', 'accounts-receivable':'accounts-receivable.xlsx',
    };
    const f = map[type] || type+'.xlsx';
    // Uses Auth.api.raw so it sends the memory access token, includes the
    // refresh cookie, and silently refreshes on 401 — no localStorage access.
    const resp = await window.Auth.api.raw('/finance/export/' + f);
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
      if (typeof openDocViewer === 'function') openDocViewer(FURL + '/contracts/' + contractId + '/render', 'Signed Contract');
      else window.open(FURL + '/contracts/' + contractId + '/render', '_blank');
    };
  };

  // Override Generate Contract to also show signature buttons (uses in-page viewer)
  window.quickGenerateContract = async function(clientId){
    if (!confirm('Generate a new contract using this client\'s locations & screens?')) return;
    try {
      const r = await api(FAPI + '/clients/' + clientId + '/quick-contract', {method:'POST', body:JSON.stringify({})});
      await viewClient(clientId);
      if (typeof openDocViewer === 'function') {
        openDocViewer(FURL + '/contracts/' + r.contract.id + '/render', 'Contract ' + (r.contract.contract_number||''));
      } else {
        window.open(FURL + '/contracts/' + r.contract.id + '/render', '_blank');
      }
    } catch(e){ alert('Error: ' + (e.message||e)); }
  };
  // View document helpers — always use in-page viewer (avoids popup blockers)
  window.viewContractPdf = id => (typeof openDocViewer==='function') ? openDocViewer(FURL + '/contracts/' + id + '/render', 'Contract') : window.open(FURL + '/contracts/' + id + '/render', '_blank');
  window.viewInvoicePdf  = id => (typeof openDocViewer==='function') ? openDocViewer(FURL + '/invoices/'  + id + '/render', 'Invoice')  : window.open(FURL + '/invoices/'  + id + '/render', '_blank');
  window.viewDepositPdf  = id => (typeof openDocViewer==='function') ? openDocViewer(FURL + '/deposits/'  + id + '/render', 'Deposit')  : window.open(FURL + '/deposits/'  + id + '/render', '_blank');

  // ====================================================
  //  PRINT QUEUE & PRINT AGENT
  // ====================================================
  window.enqueuePrint = async function(kind, docId, copies){
    try {
      copies = copies || 1;
      const r = await api(FAPI + '/print/queue', {method:'POST', body:JSON.stringify({kind, doc_id:docId, copies})});
      alert('✓ Document queued for printing — your local Windows agent will print it within 30 seconds.\n\nJob ID: ' + r.id.substring(0,8));
    } catch(e){ alert('Error: ' + (e.message||e)); }
  };

  window.renderPrintQueue = async function(){
    const main = document.getElementById('f-content') || document.querySelector('.main-content') || document.getElementById('main');
    if (!main) return;
    await window.renderPrintQueueInto(main);
  };

  window.renderPrintQueueInto = async function(container){
    const stats = await api(FAPI + '/print/stats').catch(()=>({pending:0,printed:0,failed:0,last_printed_at:null}));
    const list  = await api(FAPI + '/print/queue?status=pending').catch(()=>({jobs:[]}));
    const histo = await api(FAPI + '/print/queue?status=printed').catch(()=>({jobs:[]}));
    const fails = await api(FAPI + '/print/queue?status=failed').catch(()=>({jobs:[]}));
    const fmtTime = s => s ? new Date(s).toLocaleString() : '—';
    const rowFor = (j, withAct) => `
      <div style="display:grid;grid-template-columns:90px 1.5fr 1fr 1fr 1fr auto;gap:12px;align-items:center;padding:11px 16px;border-bottom:1px solid #e2e8f0">
        <div><span style="background:${j.kind==='invoice'?'#dbeafe':j.kind==='contract'?'#fef3c7':'#dcfce7'};color:${j.kind==='invoice'?'#1e40af':j.kind==='contract'?'#92400e':'#166534'};padding:3px 9px;border-radius:4px;font-size:11px;font-weight:700;text-transform:uppercase">${j.kind}</span></div>
        <div style="font-weight:600;color:#0f172a">${j.doc_number||'—'}</div>
        <div style="font-size:12px;color:#64748b">${fmtTime(j.queued_at)}</div>
        <div style="font-size:12px;color:#64748b">${fmtTime(j.printed_at)}</div>
        <div style="font-size:11.5px;color:${j.attempts>=3?'#dc2626':'#64748b'}">${j.attempts||0} attempt${(j.attempts||0)!==1?'s':''}${j.last_error?' · '+j.last_error.substring(0,30):''}</div>
        <div style="display:flex;gap:6px">
          ${withAct?`<button style="padding:5px 10px;font-size:11.5px;background:#fff;border:1px solid #cbd5e1;color:#475569;border-radius:6px;cursor:pointer" onclick="retryPrintJob('${j.id}')">🔄</button>
          <button style="padding:5px 10px;font-size:11.5px;background:#fff;border:1px solid #fca5a5;color:#dc2626;border-radius:6px;cursor:pointer" onclick="deletePrintJob('${j.id}')">✕</button>`:''}
        </div>
      </div>`;
    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
        <div>
          <h2 style="margin:0;font-size:20px;color:#0f172a;font-weight:700">🖨️ Print Queue</h2>
          <p style="margin:4px 0 0;color:#64748b;font-size:13.5px">Documents queued for the Windows print agent · auto-print on day 1 at 11:00 AM ET</p>
        </div>
        <div style="display:flex;gap:8px">
          <button style="background:#fff;color:#475569;border:1px solid #cbd5e1;padding:9px 16px;border-radius:8px;font-weight:600;cursor:pointer" onclick="renderPrintQueue()">🔄 Refresh</button>
          <button style="background:#2563eb;color:#fff;border:none;padding:9px 16px;border-radius:8px;font-weight:600;cursor:pointer" onclick="renderPrintAgentSetup()">⚙️ Agent Setup</button>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px">
        <div style="padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Pending</div><div style="font-size:26px;font-weight:700;color:#f59e0b;margin-top:4px">${stats.pending}</div></div>
        <div style="padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Printed</div><div style="font-size:26px;font-weight:700;color:#16a34a;margin-top:4px">${stats.printed}</div></div>
        <div style="padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Failed</div><div style="font-size:26px;font-weight:700;color:#dc2626;margin-top:4px">${stats.failed}</div></div>
        <div style="padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:10px"><div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.5px">Last Print</div><div style="font-size:12.5px;font-weight:600;color:#0f172a;margin-top:8px">${fmtTime(stats.last_printed_at)}</div></div>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;margin-bottom:20px;overflow:hidden">
        <div style="padding:14px 18px;border-bottom:1px solid #e2e8f0;background:#f8fafc"><b style="color:#0f172a">⏳ Pending (${list.jobs.length})</b></div>
        <div style="display:grid;grid-template-columns:90px 1.5fr 1fr 1fr 1fr auto;gap:12px;padding:10px 16px;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;background:#f8fafc;border-bottom:1px solid #e2e8f0">
          <div>Type</div><div>Document</div><div>Queued</div><div>Printed</div><div>Attempts</div><div>Actions</div>
        </div>
        ${list.jobs.length ? list.jobs.map(j=>rowFor(j,true)).join('') : '<div style="padding:30px;text-align:center;color:#94a3b8">No documents pending</div>'}
      </div>
      ${fails.jobs.length?`<div style="background:#fff;border:1px solid #fecaca;border-radius:10px;margin-bottom:20px;overflow:hidden">
        <div style="padding:14px 18px;border-bottom:1px solid #fecaca;background:#fef2f2"><b style="color:#dc2626">⚠️ Failed (${fails.jobs.length})</b></div>
        ${fails.jobs.map(j=>rowFor(j,true)).join('')}
      </div>`:''}
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
        <div style="padding:14px 18px;border-bottom:1px solid #e2e8f0;background:#f8fafc"><b style="color:#0f172a">✓ Recently Printed (showing ${Math.min(histo.jobs.length,15)})</b></div>
        ${histo.jobs.slice(0,15).map(j=>rowFor(j,false)).join('') || '<div style="padding:20px;text-align:center;color:#94a3b8">No prints yet</div>'}
      </div>`;
  };

  window.retryPrintJob = async function(id){
    await api(FAPI + '/print/queue/' + id + '/retry', {method:'POST'});
    renderPrintQueue();
  };
  window.deletePrintJob = async function(id){
    if (!confirm('Remove this job from the queue?')) return;
    await api(FAPI + '/print/queue/' + id, {method:'DELETE'});
    renderPrintQueue();
  };

  window.renderPrintAgentSetup = async function(){
    const t = await api(FAPI + '/print/token').catch(()=>({token:''}));
    const main = document.getElementById('f-content') || document.querySelector('.main-content') || document.getElementById('main');
    if (!main) { alert('Container not found'); return; }
    const downloadUrl = '/api/web/print-agent.zip';
    main.innerHTML = `
      <div style="max-width:920px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <h2 style="margin:0;font-size:22px;color:#0f172a;font-weight:700">🖨️ Print Agent Setup</h2>
          <button style="background:#fff;color:#475569;border:1px solid #cbd5e1;padding:8px 14px;border-radius:8px;font-weight:600;cursor:pointer" onclick="renderPrintQueue()">← Back to Queue</button>
        </div>
        <p style="color:#64748b;font-size:13.5px;margin:0 0 20px">Install this small agent on the Windows PC connected to your printer. It runs in the background and automatically prints invoices/contracts queued by MediAd View.</p>

        <div style="background:#eff6ff;border:1px solid #bfdbfe;padding:18px;border-radius:10px;margin-bottom:16px">
          <div style="font-weight:700;color:#1e40af;margin-bottom:8px">📥 Step 1 — Download the Agent</div>
          <a href="${downloadUrl}" download="MediAdView-PrintAgent.zip" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;font-size:13.5px">⬇ Download Print Agent (.zip)</a>
          <div style="font-size:12px;color:#475569;margin-top:10px">Includes: print_agent.py · start-print-agent.bat · README.md · setup instructions</div>
        </div>

        <div style="background:#fff;border:1px solid #e2e8f0;padding:18px;border-radius:10px;margin-bottom:16px">
          <div style="font-weight:700;color:#0f172a;margin-bottom:10px">🔑 Step 2 — Copy Your Agent Token</div>
          <p style="font-size:13px;color:#64748b;margin:0 0 10px">Paste this token into your <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:12px">print_agent.config.json</code> after extracting the ZIP.</p>
          <div style="display:flex;gap:8px;align-items:center">
            <input id="pa-token" readonly value="${t.token||''}" style="flex:1;font-family:monospace;font-size:13px;padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc;color:#0f172a">
            <button style="background:#2563eb;color:#fff;border:none;padding:10px 14px;border-radius:8px;font-weight:600;cursor:pointer" onclick="navigator.clipboard.writeText(document.getElementById('pa-token').value);this.textContent='✓ Copied';setTimeout(()=>this.innerHTML='📋 Copy',1500)">📋 Copy</button>
            <button style="background:#fff;color:#dc2626;border:1px solid #fecaca;padding:10px 14px;border-radius:8px;font-weight:600;cursor:pointer" onclick="rotatePrintToken()">🔄 Rotate</button>
          </div>
          <div style="font-size:12px;color:#64748b;margin-top:8px">Server URL to use: <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px">${location.origin}</code></div>
        </div>

        <div style="background:#fff;border:1px solid #e2e8f0;padding:18px;border-radius:10px;margin-bottom:16px">
          <div style="font-weight:700;color:#0f172a;margin-bottom:10px">⚙️ Step 3 — Install on Windows</div>
          <ol style="margin:0;padding-left:24px;color:#334155;font-size:13.5px;line-height:1.9">
            <li>Extract <code>MediAdView-PrintAgent.zip</code> into a folder (e.g. <code>C:\\MediAdViewAgent</code>)</li>
            <li>Install Python 3.10+ from <a href="https://www.python.org/downloads/" target="_blank" style="color:#2563eb">python.org</a> (check <b>"Add Python to PATH"</b>)</li>
            <li>Open Command Prompt: <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px">pip install requests pywin32</code></li>
            <li>Download <a href="https://www.sumatrapdfreader.org/download-free-pdf-viewer" target="_blank" style="color:#2563eb">SumatraPDF.exe</a> (portable) into the same folder</li>
            <li>Double-click <code>start-print-agent.bat</code> — creates <code>print_agent.config.json</code></li>
            <li>Edit the config: paste your token, set <code>server_url</code> to <code>${location.origin}</code></li>
            <li>Run <code>start-print-agent.bat</code> again — you should see <b>✓ Authenticated with server</b></li>
            <li>Auto-start on boot: copy shortcut of the .bat into <code>shell:startup</code></li>
          </ol>
        </div>

        <div style="background:#fffbeb;border:1px solid #fde68a;padding:14px 18px;border-radius:10px">
          <div style="font-weight:700;color:#92400e;margin-bottom:4px">💡 Tip</div>
          <p style="font-size:13px;color:#78350f;margin:0">Full step-by-step guide is inside the ZIP (README.md). The agent polls every 30s, so jobs print very quickly.</p>
        </div>
      </div>`;
  };

  window.rotatePrintToken = async function(){
    if (!confirm('Rotate the agent token? The current agent will stop working until you update its config.')) return;
    const r = await api(FAPI + '/print/token/rotate', {method:'POST'});
    renderPrintAgentSetup();
    setTimeout(()=>{ document.getElementById('pa-token').value = r.token; }, 100);
  };

})();

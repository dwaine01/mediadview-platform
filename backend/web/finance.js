// MediAd View — Finance & Admin Module (Frontend)
// Depends on: app.js (uses api(), badge(), go(), user, loaders, stat())

(function(){
  const FAPI = '/finance';
  if (typeof loaders === 'undefined') return;

  // tab state
  if (!window._fTab) window._fTab = 'dashboard';
  if (!window._fClient) window._fClient = null;

  // ===== utilities =====
  const fmt$ = v => '$' + Number(v||0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  const fmtDate = s => { if(!s) return '—'; const d=new Date(s); return isNaN(d)?s:d.toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric'}); };
  const esc = s => String(s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const status_badge = s => {
    const m = {active:'#34d399', pending:'#fbbf24', overdue:'#f87171', paid:'#34d399', cancelled:'#94a3b8', draft:'#94a3b8', received:'#34d399', archived:'#64748b', expired:'#f87171'};
    return `<span class="bdg" style="background:${m[s]||'#94a3b8'}22;color:${m[s]||'#94a3b8'}">${s||'—'}</span>`;
  };

  // ===== main loader =====
  loaders.finance = async function(){
    const el = document.getElementById('pg-finance');
    if (!el) return;
    const tabs = [
      {id:'dashboard', name:'Dashboard', icon:'M3 3v18h18M7 14l3-3 4 4 5-6'},
      {id:'clients', name:'Clients / CRM', icon:'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2m22 0v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75'},
      {id:'contracts', name:'Contracts', icon:'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'},
      {id:'invoices', name:'Invoices', icon:'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2'},
      {id:'deposits', name:'Deposits', icon:'M3 10h18M3 14h18M5 6h14a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2z'},
      {id:'payments', name:'Payments', icon:'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z'},
      {id:'expenses', name:'Expenses', icon:'M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z'},
    ];
    const tabHtml = `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:24px;border-bottom:1px solid var(--border);padding-bottom:14px">${tabs.map(t=>`
      <button onclick="window._fTab='${t.id}';loaders.finance()" style="display:flex;align-items:center;gap:8px;padding:9px 16px;border-radius:var(--rs);font-size:13px;font-weight:600;border:1px solid ${window._fTab===t.id?'rgba(99,102,241,.35)':'transparent'};cursor:pointer;background:${window._fTab===t.id?'rgba(99,102,241,.12)':'transparent'};color:${window._fTab===t.id?'var(--brand-l)':'var(--t-3)'};transition:all .15s"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${t.icon}"/></svg>${t.name}</button>`).join('')}</div>`;

    el.innerHTML = `<div class="ph"><div><h1>Finance &amp; CRM</h1><p>Manage clients, contracts, invoices, deposits and payments</p></div></div>${tabHtml}<div id="f-content"><div class="card" style="padding:48px;text-align:center;color:var(--t-4)">Loading…</div></div>`;

    const c = document.getElementById('f-content');
    try {
      if (window._fTab === 'dashboard') await renderFinDashboard(c);
      else if (window._fTab === 'clients') await renderClients(c);
      else if (window._fTab === 'contracts') await renderContracts(c);
      else if (window._fTab === 'invoices') await renderInvoices(c);
      else if (window._fTab === 'deposits') await renderDeposits(c);
      else if (window._fTab === 'payments') await renderPayments(c);
      else if (window._fTab === 'expenses') await renderExpenses(c);
    } catch(e){
      c.innerHTML = `<div class="empty"><div class="empty-ico">⚠️</div><h3>Error</h3><p>${esc(e.message)}</p></div>`;
    }
  };

  // ============ DASHBOARD ============
  async function renderFinDashboard(c){
    const d = await api(FAPI + '/dashboard');
    const s = d.stats;
    const cf = d.cashflow || [];
    const maxCf = Math.max(...cf.flatMap(x=>[x.revenue, x.expenses]), 1);

    c.innerHTML = `
      <div class="welcome-banner" style="margin-bottom:24px">
        <div class="greeting">Financial Overview · ${d.period}</div>
        <h1 style="font-size:22px">Net Profit: <span style="color:${s.net_profit>=0?'#34d399':'#f87171'}">${fmt$(s.net_profit)}</span></h1>
        <p>${fmt$(s.collected_this_month)} collected this month · ${fmt$(s.expenses_total)} in expenses</p>
      </div>

      <div class="st-grid">
        ${stat('Billed This Month', fmt$(s.billed_this_month), 'Total invoiced', '--brand-l', 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z')}
        ${stat('Collected', fmt$(s.collected_this_month), 'Paid this month', '--green-l', 'M5 13l4 4L19 7', {dir:'up', label:'Income'})}
        ${stat('Accounts Receivable', fmt$(s.ar_total), s.overdue_count + ' overdue', '--amber-l', 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z', s.overdue_count>0?{dir:'down', label:'Action'}:{dir:'flat', label:'OK'})}
        ${stat('Active Clients', s.total_clients, s.total_contracts + ' active contracts', '--cyan', 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2m22 0v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75')}
      </div>

      <div style="display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:24px">
        <div>
          <div class="sh"><h2>Cash Flow — Last 12 Months</h2><div style="display:flex;gap:12px;font-size:11px;color:var(--t-3)"><span style="display:inline-flex;align-items:center;gap:5px"><span style="width:10px;height:10px;background:var(--green-l);border-radius:2px"></span>Revenue</span><span style="display:inline-flex;align-items:center;gap:5px"><span style="width:10px;height:10px;background:var(--red-l);border-radius:2px"></span>Expenses</span></div></div>
          <div class="card" style="padding:24px">
            <div style="display:flex;align-items:flex-end;gap:8px;height:200px;border-bottom:1px solid var(--border);padding-bottom:8px">
              ${cf.map(m=>{
                const rH = (m.revenue/maxCf)*180;
                const eH = (m.expenses/maxCf)*180;
                return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;height:100%;justify-content:flex-end">
                  <div style="width:100%;display:flex;gap:2px;justify-content:center;height:100%;align-items:flex-end">
                    <div title="Revenue ${fmt$(m.revenue)}" style="width:14px;height:${rH}px;min-height:2px;background:linear-gradient(180deg,var(--green-l),var(--green));border-radius:3px 3px 0 0"></div>
                    <div title="Expenses ${fmt$(m.expenses)}" style="width:14px;height:${eH}px;min-height:2px;background:linear-gradient(180deg,var(--red-l),var(--red));border-radius:3px 3px 0 0"></div>
                  </div>
                </div>`;
              }).join('')}
            </div>
            <div style="display:flex;gap:8px;margin-top:6px">${cf.map(m=>`<div style="flex:1;text-align:center;font-size:9px;color:var(--t-4)">${m.month.substring(5)}</div>`).join('')}</div>
          </div>
        </div>
        <div>
          <div class="sh"><h2>Quick Actions</h2></div>
          <div style="display:flex;flex-direction:column;gap:8px">
            ${qaCard('New Client', 'Add to CRM', '#6366f1', 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7zM21 12h-6m3 -3v6', 'showNewClient()')}
            ${qaCard('New Contract', 'Create rental', '#22d3ee', 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z', 'showNewContract()')}
            ${qaCard('Generate Monthly Invoices', 'Auto-bill all', '#10b981', 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2', 'generateMonthlyInvoices()')}
            ${qaCard('Record Payment', 'Log income', '#a78bfa', 'M5 13l4 4L19 7', 'showNewPayment()')}
            ${qaCard('Add Expense', 'Log outflow', '#f59e0b', 'M12 8v4l3 3', 'showNewExpense()')}
          </div>
        </div>
      </div>

      <div class="sh"><h2>Recent Invoices</h2><a class="sh-link" onclick="window._fTab='invoices';loaders.finance()">View all →</a></div>
      <div class="card">
        ${(d.recent_invoices||[]).length===0 ? '<div style="padding:32px;text-align:center;color:var(--t-4);font-size:13px">No invoices yet</div>' :
          (d.recent_invoices||[]).map(i=>`<div class="lr" onclick="viewInvoice('${i.id}')">
            <div class="dot" style="background:${i.status==='paid'?'#34d399':i.status==='overdue'?'#f87171':'#fbbf24'};color:${i.status==='paid'?'#34d399':i.status==='overdue'?'#f87171':'#fbbf24'}"></div>
            <div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;color:var(--t-1)">${esc(i.invoice_number)} — ${esc(i.client_name||'')}</div><div style="font-size:11px;color:var(--t-4);margin-top:2px">${fmtDate(i.issue_date)} · Due ${fmtDate(i.due_date)}</div></div>
            ${status_badge(i.status)}
            <div style="font-size:15px;font-weight:800;color:var(--cyan);min-width:100px;text-align:right">${fmt$(i.total)}</div>
          </div>`).join('')}
      </div>
    `;
  }

  function qaCard(l, d, c, ic, fn){
    return `<div class="card card-i" style="display:flex;align-items:center;gap:12px;padding:13px 15px" onclick="${fn}">
      <div style="width:36px;height:36px;border-radius:10px;background:${c}20;border:1px solid ${c}30;display:flex;align-items:center;justify-content:center;flex-shrink:0;color:${c}"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg></div>
      <div style="flex:1"><div style="font-size:13px;font-weight:600;color:var(--t-1)">${l}</div><div style="font-size:10px;color:var(--t-4)">${d}</div></div>
    </div>`;
  }

  // ============ CLIENTS ============
  async function renderClients(c){
    const list = await api(FAPI + '/clients');
    c.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><h2 style="font-size:18px;font-weight:700">Clients (${list.length})</h2><p style="font-size:12px;color:var(--t-4)">Complete CRM with contracts, invoices and payment history</p></div>
        <button class="btn-p" onclick="showNewClient()"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>New Client</button>
      </div>
      ${list.length===0 ? '<div class="empty"><div class="empty-ico"><svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2m22 0v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg></div><h3>No clients yet</h3><p>Add your first client to start managing contracts and invoices</p><button class="btn-p" onclick="showNewClient()">+ Add Client</button></div>'
        : `<div class="card"><div class="tbl-h" style="grid-template-columns:2fr 1.5fr 1fr 1fr auto auto">
            <span>Business</span><span>Representative</span><span>Phone</span><span>City</span><span>Open Invoices</span><span></span>
          </div>${list.map(cl=>`<div class="tbl-r" style="grid-template-columns:2fr 1.5fr 1fr 1fr auto auto;cursor:pointer" onclick="viewClient('${cl.id}')">
            <div><div style="font-size:14px;font-weight:700;color:var(--t-1)">${esc(cl.business_name)}</div><div style="font-size:10px;color:var(--t-4)">${esc(cl.email||'—')}</div></div>
            <span style="font-size:13px">${esc(cl.representative)}</span>
            <span style="font-size:13px;color:var(--t-3)">${esc(cl.phone)}</span>
            <span style="font-size:13px;color:var(--t-3)">${esc(cl.city||'—')}</span>
            <span class="bdg" style="background:${cl.open_invoices>0?'rgba(245,158,11,.15)':'rgba(16,185,129,.12)'};color:${cl.open_invoices>0?'var(--amber-l)':'var(--green-l)'}">${cl.open_invoices}</span>
            <span style="color:var(--t-4)">›</span>
          </div>`).join('')}</div>`}
    `;
  }

  window.showNewClient = function(){
    openModal('New Client', `
      <div class="row2"><div><label class="inp-label">Business Name *</label><input class="inp" id="nc-name" placeholder="Jungle Juice Bar"></div>
      <div><label class="inp-label">Representative *</label><input class="inp" id="nc-rep" placeholder="Brittany Smith"></div></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">Email</label><input class="inp" id="nc-email" type="email" placeholder="contact@business.com"></div>
      <div><label class="inp-label">Phone *</label><input class="inp" id="nc-phone" placeholder="323-996-1375"></div></div>
      <div style="margin-top:12px"><label class="inp-label">Address *</label><input class="inp" id="nc-addr" placeholder="891 Oak St"></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">City</label><input class="inp" id="nc-city" placeholder="Columbus"></div>
      <div><label class="inp-label">State / ZIP</label><div style="display:flex;gap:6px"><input class="inp" id="nc-state" placeholder="OH" style="width:80px"><input class="inp" id="nc-zip" placeholder="43205"></div></div></div>
      <div style="margin-top:12px"><label class="inp-label">Notes</label><textarea class="inp" id="nc-notes" rows="2" placeholder="Internal notes..."></textarea></div>
    `, 'Create Client', async ()=>{
      const body = {
        business_name: val('nc-name'), representative: val('nc-rep'), email: val('nc-email'),
        phone: val('nc-phone'), address_line1: val('nc-addr'), city: val('nc-city'),
        state: val('nc-state'), zip: val('nc-zip'), notes: val('nc-notes'),
      };
      if (!body.business_name || !body.representative || !body.phone || !body.address_line1) { alert('Please fill required fields'); return false; }
      await api(FAPI + '/clients', {method:'POST', body:JSON.stringify(body)});
      loaders.finance();
      return true;
    });
  };

  window.viewClient = async function(id){
    const c = document.getElementById('f-content');
    const cl = await api(FAPI + '/clients/' + id);
    c.innerHTML = `
      <button class="btn-ghost" style="margin-bottom:14px" onclick="loaders.finance()">← Back to Clients</button>
      <div class="welcome-banner" style="margin-bottom:20px">
        <div class="greeting">Client Profile</div>
        <h1>${esc(cl.business_name)}</h1>
        <p>Rep: ${esc(cl.representative)} · ${esc(cl.phone)} · ${esc(cl.email||'—')}</p>
        <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-p" onclick="showNewContract('${cl.id}')"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>New Contract</button>
          <button class="btn-s" onclick="showNewPayment('','${cl.id}')">Record Payment</button>
          <button class="btn-s" onclick="editClient('${cl.id}')">Edit</button>
        </div>
      </div>

      <div class="st-grid" style="grid-template-columns:repeat(4,1fr)">
        ${stat('Total Invoiced', fmt$(cl.total_invoiced), '', '--brand-l', 'M9 12h6m-6 4h6')}
        ${stat('Total Paid', fmt$(cl.total_paid), '', '--green-l', 'M5 13l4 4L19 7')}
        ${stat('Balance', fmt$(cl.balance), cl.balance>0?'Outstanding':'Settled', cl.balance>0?'--amber-l':'--green-l', 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z')}
        ${stat('Contracts', cl.contracts.length, '', '--cyan', 'M9 12h6m-6 4h6')}
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div>
          <div class="sh"><h2>Contracts (${cl.contracts.length})</h2></div>
          <div class="card">
            ${cl.contracts.length===0?'<div style="padding:28px;text-align:center;color:var(--t-4);font-size:13px">No contracts yet</div>':
              cl.contracts.map(ct=>`<div class="lr" onclick="viewContract('${ct.id}')">
                <div style="flex:1"><div style="font-size:13px;font-weight:700">${esc(ct.contract_number)}</div><div style="font-size:11px;color:var(--t-4)">${fmtDate(ct.start_date)} → ${fmtDate(ct.end_date)} · ${ct.term_months}mo</div></div>
                ${status_badge(ct.status)}
                <div style="font-size:14px;font-weight:700;color:var(--cyan);min-width:90px;text-align:right">${fmt$(ct.monthly_total)}/mo</div>
              </div>`).join('')}
          </div>

          <div class="sh" style="margin-top:20px"><h2>Deposits (${cl.deposits.length})</h2></div>
          <div class="card">
            ${cl.deposits.length===0?'<div style="padding:24px;text-align:center;color:var(--t-4);font-size:13px">No deposits</div>':
              cl.deposits.map(d=>`<div class="lr" onclick="window.open('${FAPI}/deposits/${d.id}/render','_blank')">
                <div style="flex:1"><div style="font-size:13px;font-weight:600">${esc(d.receipt_number)}</div><div style="font-size:11px;color:var(--t-4)">${fmtDate(d.issue_date)}</div></div>
                ${status_badge(d.status)}
                <div style="font-size:14px;font-weight:700;color:var(--cyan)">${fmt$(d.total)}</div>
              </div>`).join('')}
          </div>
        </div>

        <div>
          <div class="sh"><h2>Invoices (${cl.invoices.length})</h2></div>
          <div class="card">
            ${cl.invoices.length===0?'<div style="padding:28px;text-align:center;color:var(--t-4);font-size:13px">No invoices yet</div>':
              cl.invoices.slice(0,12).map(i=>`<div class="lr" onclick="viewInvoice('${i.id}')">
                <div class="dot" style="background:${i.status==='paid'?'#34d399':i.status==='overdue'?'#f87171':'#fbbf24'};color:${i.status==='paid'?'#34d399':i.status==='overdue'?'#f87171':'#fbbf24'}"></div>
                <div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600">${esc(i.invoice_number)}</div><div style="font-size:11px;color:var(--t-4)">${fmtDate(i.issue_date)}</div></div>
                ${status_badge(i.status)}
                <div style="font-size:14px;font-weight:700;color:var(--cyan);min-width:80px;text-align:right">${fmt$(i.total)}</div>
              </div>`).join('')}
          </div>

          <div class="sh" style="margin-top:20px"><h2>Payments (${cl.payments.length})</h2></div>
          <div class="card">
            ${cl.payments.length===0?'<div style="padding:24px;text-align:center;color:var(--t-4);font-size:13px">No payments</div>':
              cl.payments.slice(0,10).map(p=>`<div class="lr">
                <div style="flex:1"><div style="font-size:13px;font-weight:600">${esc(p.method)}${p.reference?' · '+esc(p.reference):''}</div><div style="font-size:11px;color:var(--t-4)">${fmtDate(p.date)}</div></div>
                <div style="font-size:14px;font-weight:700;color:var(--green-l)">+${fmt$(p.amount)}</div>
              </div>`).join('')}
          </div>
        </div>
      </div>
    `;
  };

  window.editClient = async function(id){
    const cl = await api(FAPI + '/clients/' + id);
    openModal('Edit Client', `
      <div class="row2"><div><label class="inp-label">Business Name</label><input class="inp" id="ec-name" value="${esc(cl.business_name)}"></div>
      <div><label class="inp-label">Representative</label><input class="inp" id="ec-rep" value="${esc(cl.representative)}"></div></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">Email</label><input class="inp" id="ec-email" value="${esc(cl.email||'')}"></div>
      <div><label class="inp-label">Phone</label><input class="inp" id="ec-phone" value="${esc(cl.phone)}"></div></div>
      <div style="margin-top:12px"><label class="inp-label">Address</label><input class="inp" id="ec-addr" value="${esc(cl.address_line1)}"></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">City</label><input class="inp" id="ec-city" value="${esc(cl.city||'')}"></div>
      <div><label class="inp-label">State / ZIP</label><div style="display:flex;gap:6px"><input class="inp" id="ec-state" value="${esc(cl.state||'')}" style="width:80px"><input class="inp" id="ec-zip" value="${esc(cl.zip||'')}"></div></div></div>
    `, 'Save', async ()=>{
      await api(FAPI + '/clients/' + id, {method:'PUT', body:JSON.stringify({
        business_name:val('ec-name'),representative:val('ec-rep'),email:val('ec-email'),phone:val('ec-phone'),
        address_line1:val('ec-addr'),city:val('ec-city'),state:val('ec-state'),zip:val('ec-zip'),
      })});
      viewClient(id);
      return true;
    });
  };

  // ============ CONTRACTS ============
  async function renderContracts(c){
    const list = await api(FAPI + '/contracts');
    c.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><h2 style="font-size:18px;font-weight:700">Contracts (${list.length})</h2><p style="font-size:12px;color:var(--t-4)">LED rental agreements</p></div>
        <button class="btn-p" onclick="showNewContract()"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>New Contract</button>
      </div>
      ${list.length===0?'<div class="empty"><h3>No contracts yet</h3><p>Create a contract from a client profile or here</p></div>':
        `<div class="card"><div class="tbl-h" style="grid-template-columns:1fr 2fr 1fr 1fr 1fr auto"><span>#</span><span>Client</span><span>Start</span><span>End</span><span>Monthly</span><span></span></div>
        ${list.map(ct=>`<div class="tbl-r" style="grid-template-columns:1fr 2fr 1fr 1fr 1fr auto;cursor:pointer" onclick="viewContract('${ct.id}')">
          <span style="font-size:12px;font-weight:700;color:var(--brand-l)">${esc(ct.contract_number)}</span>
          <span style="font-size:13px;font-weight:600">${esc(ct.client_name)}</span>
          <span style="font-size:12px;color:var(--t-3)">${fmtDate(ct.start_date)}</span>
          <span style="font-size:12px;color:var(--t-3)">${fmtDate(ct.end_date)}</span>
          <span style="font-size:14px;font-weight:700;color:var(--cyan)">${fmt$(ct.monthly_total)}</span>
          ${status_badge(ct.status)}
        </div>`).join('')}</div>`}
    `;
  }

  window.showNewContract = async function(preClientId){
    const clients = await api(FAPI + '/clients');
    if (clients.length===0) { alert('Add a client first'); return; }
    const opts = clients.map(c=>`<option value="${c.id}" ${preClientId===c.id?'selected':''}>${esc(c.business_name)} — ${esc(c.representative)}</option>`).join('');
    const today = new Date().toISOString().substring(0,10);
    openModal('New Rental Contract', `
      <div class="row2"><div><label class="inp-label">Client *</label><select class="inp" id="ct-client">${opts}</select></div>
      <div><label class="inp-label">Start Date *</label><input class="inp" id="ct-start" type="date" value="${today}"></div></div>
      <div class="row2" style="margin-top:12px"><div><label class="inp-label">Contract Term *</label><select class="inp" id="ct-term">
        <option value="6">6 months</option><option value="12" selected>12 months</option><option value="18">18 months</option><option value="24">24 months</option>
      </select></div>
      <div><label class="inp-label">Security Deposit per Screen ($)</label><input class="inp" id="ct-dep" type="number" value="250" step="0.01"></div></div>

      <div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--border)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><label class="inp-label" style="margin:0">Rented Screens</label><button class="btn-s" onclick="addCtScreen()">+ Add Screen</button></div>
        <div id="ct-screens"></div>
      </div>

      <div class="row2" style="margin-top:14px"><div><label class="inp-label">Late Fee / day ($)</label><input class="inp" id="ct-late" type="number" value="50"></div>
      <div><label class="inp-label">NSF Fee ($)</label><input class="inp" id="ct-nsf" type="number" value="85"></div></div>
      <div style="margin-top:12px"><label class="inp-label">Additional Terms (optional)</label><textarea class="inp" id="ct-add" rows="2" placeholder="Custom clauses..."></textarea></div>
    `, 'Create Contract & Deposit Receipt', async ()=>{
      const screens = collectCtScreens();
      if (screens.length===0) { alert('Add at least one screen'); return false; }
      const body = {
        client_id: val('ct-client'),
        start_date: val('ct-start'),
        term_months: parseInt(val('ct-term'))||12,
        screens,
        security_deposit_per_screen: parseFloat(val('ct-dep'))||250,
        late_fee_per_day: parseFloat(val('ct-late'))||50,
        nsf_fee: parseFloat(val('ct-nsf'))||85,
        additional_terms: val('ct-add'),
      };
      const r = await api(FAPI + '/contracts', {method:'POST', body:JSON.stringify(body)});
      window.open(FAPI + '/contracts/' + r.contract.id + '/render', '_blank');
      window.open(FAPI + '/deposits/' + r.deposit.id + '/render', '_blank');
      loaders.finance();
      return true;
    });
    addCtScreen();
  };

  let _ctScreenIdx = 0;
  window.addCtScreen = function(){
    _ctScreenIdx++;
    const box = document.getElementById('ct-screens');
    if (!box) return;
    const row = document.createElement('div');
    row.style.cssText='display:grid;grid-template-columns:1.2fr 1fr 70px 100px auto;gap:8px;margin-bottom:6px;align-items:center';
    row.dataset.cts='1';
    row.innerHTML = `
      <input class="inp" placeholder="Model (MAV-30540S)" value="MAV-30540S" data-f="model" style="font-size:12px">
      <input class="inp" placeholder="Install address" data-f="location" style="font-size:12px">
      <input class="inp" type="number" placeholder="Units" value="1" data-f="units" style="font-size:12px">
      <input class="inp" type="number" step="0.01" placeholder="Day price" value="8.50" data-f="day_price" style="font-size:12px">
      <button onclick="this.parentNode.remove()" style="background:rgba(248,113,113,.15);color:var(--red-l);border:1px solid rgba(248,113,113,.3);border-radius:6px;padding:6px 10px;cursor:pointer;font-size:14px">✕</button>
    `;
    box.appendChild(row);
  };
  function collectCtScreens(){
    return Array.from(document.querySelectorAll('#ct-screens > [data-cts]')).map(r=>{
      const o = {};
      r.querySelectorAll('input').forEach(i=>{
        const f = i.dataset.f;
        if (f==='units') o[f] = parseInt(i.value)||1;
        else if (f==='day_price') o[f] = parseFloat(i.value)||8.5;
        else o[f] = i.value;
      });
      return o;
    });
  }

  window.viewContract = async function(id){
    window.open(FAPI + '/contracts/' + id + '/render', '_blank');
  };

  // ============ INVOICES ============
  async function renderInvoices(c){
    const list = await api(FAPI + '/invoices');
    const filters = ['all','pending','overdue','paid','cancelled'];
    if (!window._invFilter) window._invFilter='all';
    const filtered = window._invFilter==='all'? list : list.filter(i=>i.status===window._invFilter);
    c.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px">
        <h2 style="font-size:18px;font-weight:700">Invoices (${list.length})</h2>
        <div style="display:flex;gap:8px">
          <button class="btn-s" onclick="generateMonthlyInvoices()">⚡ Generate Monthly</button>
          <button class="btn-p" onclick="showNewManualInvoice()">+ Manual Invoice</button>
        </div>
      </div>
      <div style="display:flex;gap:6px;margin-bottom:16px">${filters.map(f=>`<button onclick="window._invFilter='${f}';loaders.finance()" style="padding:6px 14px;border-radius:8px;font-size:12px;font-weight:600;border:1px solid ${window._invFilter===f?'rgba(99,102,241,.35)':'var(--border)'};background:${window._invFilter===f?'rgba(99,102,241,.12)':'transparent'};color:${window._invFilter===f?'var(--brand-l)':'var(--t-3)'};cursor:pointer;text-transform:capitalize">${f}${f==='all'?'':' ('+list.filter(i=>i.status===f).length+')'}</button>`).join('')}</div>
      ${filtered.length===0?'<div class="empty"><h3>No invoices</h3><p>No invoices matching this filter</p></div>':
      `<div class="card"><div class="tbl-h" style="grid-template-columns:1fr 1.5fr 1fr 1fr 1fr 1fr auto"><span>Invoice #</span><span>Client</span><span>Period</span><span>Due</span><span>Status</span><span>Total</span><span></span></div>
      ${filtered.map(i=>`<div class="tbl-r" style="grid-template-columns:1fr 1.5fr 1fr 1fr 1fr 1fr auto;cursor:pointer" onclick="viewInvoice('${i.id}')">
        <span style="font-size:12px;font-weight:700;color:var(--brand-l)">${esc(i.invoice_number)}</span>
        <span style="font-size:13px;font-weight:600">${esc(i.client_name)}</span>
        <span style="font-size:11px;color:var(--t-3)">${fmtDate(i.period_start)} – ${fmtDate(i.period_end)}</span>
        <span style="font-size:12px;color:${i.status==='overdue'?'var(--red-l)':'var(--t-3)'}">${fmtDate(i.due_date)}</span>
        ${status_badge(i.status)}
        <span style="font-size:14px;font-weight:700;color:var(--cyan)">${fmt$(i.total)}</span>
        <span style="color:var(--t-4)">›</span>
      </div>`).join('')}</div>`}
    `;
  }

  window.viewInvoice = async function(id){
    const i = await api(FAPI + '/invoices/' + id);
    const c = document.getElementById('f-content');
    c.innerHTML = `
      <button class="btn-ghost" style="margin-bottom:14px" onclick="window._fTab='invoices';loaders.finance()">← Back to Invoices</button>
      <div class="ph"><div><h1>Invoice ${esc(i.invoice_number)}</h1><p>Period: ${fmtDate(i.period_start)} – ${fmtDate(i.period_end)}</p></div>
      <div style="display:flex;gap:8px">
        <button class="btn-s" onclick="window.open('${FAPI}/invoices/${id}/render','_blank')">View / Print PDF</button>
        ${i.status!=='paid' && i.status!=='cancelled' ? `<button class="btn-p" onclick="showNewPayment('${i.id}','${i.client_id}','${i.balance}')">Record Payment</button>` : ''}
        ${i.status!=='paid' ? `<button class="btn-s" style="color:var(--red-l)" onclick="cancelInvoice('${i.id}')">Cancel</button>` : ''}
      </div></div>
      <div class="card" style="padding:0;overflow:hidden;height:1000px"><iframe src="${FAPI}/invoices/${id}/render" style="width:100%;height:100%;border:none"></iframe></div>
    `;
  };

  window.cancelInvoice = async function(id){
    if (!confirm('Cancel this invoice?')) return;
    await api(FAPI + '/invoices/' + id, {method:'DELETE'});
    window._fTab='invoices';loaders.finance();
  };

  window.generateMonthlyInvoices = async function(){
    if (!confirm('Generate monthly invoices for all active contracts (current month)?')) return;
    const r = await api(FAPI + '/invoices/generate-monthly', {method:'POST'});
    alert(`✓ Generated ${r.created} invoices for ${r.period}`);
    window._fTab='invoices';loaders.finance();
  };

  window.showNewManualInvoice = async function(){
    const clients = await api(FAPI + '/clients');
    if (clients.length===0) { alert('Add a client first'); return; }
    const today = new Date().toISOString().substring(0,10);
    openModal('Manual Invoice', `
      <div class="row2"><div><label class="inp-label">Client *</label><select class="inp" id="mi-client">${clients.map(c=>`<option value="${c.id}">${esc(c.business_name)}</option>`).join('')}</select></div>
      <div><label class="inp-label">Issue Date *</label><input class="inp" id="mi-date" type="date" value="${today}"></div></div>
      <div class="row2" style="margin-top:10px"><div><label class="inp-label">Period Start</label><input class="inp" id="mi-ps" type="date" value="${today}"></div>
      <div><label class="inp-label">Period End</label><input class="inp" id="mi-pe" type="date" value="${today}"></div></div>
      <div style="margin-top:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><label class="inp-label" style="margin:0">Items</label><button class="btn-s" onclick="addMiItem()">+ Add Item</button></div>
        <div id="mi-items"></div>
      </div>
      <div class="row2" style="margin-top:14px"><div><label class="inp-label">Tax ($)</label><input class="inp" id="mi-tax" type="number" step="0.01" value="0"></div></div>
    `, 'Create Invoice', async ()=>{
      const items = collectMiItems();
      if (items.length===0) { alert('Add at least one item'); return false; }
      const r = await api(FAPI + '/invoices/manual', {method:'POST', body:JSON.stringify({
        client_id: val('mi-client'),
        issue_date: val('mi-date'),
        due_date: val('mi-date'),
        period_start: val('mi-ps'),
        period_end: val('mi-pe'),
        items, tax: parseFloat(val('mi-tax'))||0,
      })});
      loaders.finance();
      return true;
    });
    addMiItem();
  };

  let _miIdx = 0;
  window.addMiItem = function(){
    _miIdx++;
    const box = document.getElementById('mi-items');
    if (!box) return;
    const idx = box.children.length+1;
    const row = document.createElement('div');
    row.dataset.mi='1';
    row.style.cssText='display:grid;grid-template-columns:50px 2fr 1fr 70px 1fr auto;gap:6px;margin-bottom:5px;align-items:center';
    row.innerHTML=`<input class="inp" data-f="line_no" value="${String(idx).padStart(2,'0')}" style="font-size:12px;text-align:center">
      <input class="inp" data-f="description" placeholder="LED Ultra Brightness MAV-30540S" style="font-size:12px">
      <input class="inp" data-f="day_price" type="number" step="0.01" placeholder="8.50" style="font-size:12px">
      <input class="inp" data-f="days" type="number" placeholder="30" value="30" style="font-size:12px">
      <input class="inp" data-f="total" type="number" step="0.01" placeholder="auto" style="font-size:12px">
      <button onclick="this.parentNode.remove()" style="background:rgba(248,113,113,.15);color:var(--red-l);border:none;border-radius:6px;padding:5px 9px;cursor:pointer">✕</button>`;
    // auto compute total
    row.addEventListener('input', e=>{
      const dp = parseFloat(row.querySelector('[data-f=day_price]').value)||0;
      const dy = parseFloat(row.querySelector('[data-f=days]').value)||0;
      if (e.target.dataset.f==='day_price' || e.target.dataset.f==='days') {
        row.querySelector('[data-f=total]').value = (dp*dy).toFixed(2);
      }
    });
    box.appendChild(row);
  };
  function collectMiItems(){
    return Array.from(document.querySelectorAll('#mi-items > [data-mi]')).map(r=>{
      const o={};
      r.querySelectorAll('input').forEach(i=>{ const f=i.dataset.f;
        if (f==='days') o[f]=parseInt(i.value)||0;
        else if (f==='day_price'||f==='total') o[f]=parseFloat(i.value)||0;
        else o[f]=i.value;
      });
      o.units = 1;
      return o;
    });
  }

  // ============ DEPOSITS ============
  async function renderDeposits(c){
    const list = await api(FAPI + '/deposits');
    c.innerHTML = `
      <div style="margin-bottom:18px"><h2 style="font-size:18px;font-weight:700">Deposits (${list.length})</h2><p style="font-size:12px;color:var(--t-4)">Security deposits per contract</p></div>
      ${list.length===0?'<div class="empty"><h3>No deposits yet</h3><p>Deposits are auto-created when you create a contract</p></div>':
      `<div class="card"><div class="tbl-h" style="grid-template-columns:1.2fr 2fr 1fr 1fr 1fr auto"><span>Receipt #</span><span>Client</span><span>Date</span><span>Status</span><span>Amount</span><span></span></div>
      ${list.map(d=>`<div class="tbl-r" style="grid-template-columns:1.2fr 2fr 1fr 1fr 1fr auto;cursor:pointer" onclick="window.open('${FAPI}/deposits/${d.id}/render','_blank')">
        <span style="font-size:12px;font-weight:700;color:var(--brand-l)">${esc(d.receipt_number)}</span>
        <span style="font-size:13px;font-weight:600">${esc(d.client_name)}</span>
        <span style="font-size:12px;color:var(--t-3)">${fmtDate(d.issue_date)}</span>
        ${status_badge(d.status)}
        <span style="font-size:14px;font-weight:700;color:var(--cyan)">${fmt$(d.total)}</span>
        <span style="color:var(--t-4)">›</span>
      </div>`).join('')}</div>`}
    `;
  }

  // ============ PAYMENTS ============
  async function renderPayments(c){
    const list = await api(FAPI + '/payments');
    c.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <h2 style="font-size:18px;font-weight:700">Payments (${list.length})</h2>
        <button class="btn-p" onclick="showNewPayment()">+ Record Payment</button>
      </div>
      ${list.length===0?'<div class="empty"><h3>No payments recorded</h3><p>Record payments to track income</p></div>':
      `<div class="card"><div class="tbl-h" style="grid-template-columns:1fr 2fr 1fr 1fr 1fr auto"><span>Date</span><span>Client</span><span>Method</span><span>Reference</span><span>Amount</span><span></span></div>
      ${list.map(p=>`<div class="tbl-r" style="grid-template-columns:1fr 2fr 1fr 1fr 1fr auto">
        <span style="font-size:12px;color:var(--t-3)">${fmtDate(p.date)}</span>
        <span style="font-size:13px;font-weight:600">${esc(p.client_name)}</span>
        <span style="font-size:12px;color:var(--t-3);text-transform:uppercase">${esc(p.method)}</span>
        <span style="font-size:12px;color:var(--t-4)">${esc(p.reference||'—')}</span>
        <span style="font-size:14px;font-weight:700;color:var(--green-l)">+${fmt$(p.amount)}</span>
        <button onclick="delPayment('${p.id}')" style="background:rgba(248,113,113,.1);color:var(--red-l);border:none;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px;font-weight:600">Delete</button>
      </div>`).join('')}</div>`}
    `;
  }

  window.delPayment = async function(id){
    if (!confirm('Delete this payment?')) return;
    await api(FAPI + '/payments/' + id, {method:'DELETE'});
    loaders.finance();
  };

  window.showNewPayment = async function(invoiceId, clientId, balance){
    const clients = await api(FAPI + '/clients');
    if (clients.length===0) { alert('Add a client first'); return; }
    const today = new Date().toISOString().substring(0,10);
    const clientOpts = clients.map(c=>`<option value="${c.id}" ${clientId===c.id?'selected':''}>${esc(c.business_name)}</option>`).join('');
    openModal('Record Payment', `
      <div class="row2"><div><label class="inp-label">Client *</label><select class="inp" id="pay-client" ${clientId?'disabled':''}>${clientOpts}</select></div>
      <div><label class="inp-label">Date *</label><input class="inp" id="pay-date" type="date" value="${today}"></div></div>
      <div class="row2" style="margin-top:10px"><div><label class="inp-label">Amount * ($)</label><input class="inp" id="pay-amt" type="number" step="0.01" value="${balance||''}" placeholder="0.00"></div>
      <div><label class="inp-label">Method *</label><select class="inp" id="pay-method">
        <option value="ACH">ACH / Bank Transfer</option>
        <option value="check">Check</option>
        <option value="cash">Cash</option>
        <option value="card">Card</option>
        <option value="zelle">Zelle</option>
      </select></div></div>
      <div style="margin-top:10px"><label class="inp-label">Reference (check #, txn id...)</label><input class="inp" id="pay-ref" placeholder="optional"></div>
      <div style="margin-top:10px"><label class="inp-label">Notes</label><input class="inp" id="pay-notes" placeholder="optional"></div>
      ${invoiceId?`<input type="hidden" id="pay-inv" value="${invoiceId}">`:''}
    `, 'Record Payment', async ()=>{
      const body = {
        client_id: val('pay-client'),
        amount: parseFloat(val('pay-amt'))||0,
        method: val('pay-method'),
        reference: val('pay-ref'),
        date: val('pay-date'),
        notes: val('pay-notes'),
      };
      if (invoiceId) body.invoice_id = invoiceId;
      if (body.amount<=0) { alert('Enter amount'); return false; }
      await api(FAPI + '/payments', {method:'POST', body:JSON.stringify(body)});
      if (invoiceId) viewInvoice(invoiceId);
      else loaders.finance();
      return true;
    });
  };

  // ============ EXPENSES ============
  async function renderExpenses(c){
    const list = await api(FAPI + '/expenses');
    const total = list.reduce((s,e)=>s+e.amount,0);
    c.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><h2 style="font-size:18px;font-weight:700">Operating Expenses (${list.length})</h2><p style="font-size:12px;color:var(--t-4)">Total: ${fmt$(total)}</p></div>
        <button class="btn-p" onclick="showNewExpense()">+ Add Expense</button>
      </div>
      ${list.length===0?'<div class="empty"><h3>No expenses logged</h3><p>Track operating costs to calculate net profit</p></div>':
      `<div class="card"><div class="tbl-h" style="grid-template-columns:1fr 1fr 2fr 1fr 1fr auto"><span>Date</span><span>Category</span><span>Description</span><span>Vendor</span><span>Amount</span><span></span></div>
      ${list.map(e=>`<div class="tbl-r" style="grid-template-columns:1fr 1fr 2fr 1fr 1fr auto">
        <span style="font-size:12px;color:var(--t-3)">${fmtDate(e.date)}</span>
        <span style="font-size:12px;color:var(--brand-l);text-transform:uppercase;font-weight:600">${esc(e.category)}</span>
        <span style="font-size:13px">${esc(e.description)}</span>
        <span style="font-size:12px;color:var(--t-4)">${esc(e.vendor||'—')}</span>
        <span style="font-size:14px;font-weight:700;color:var(--red-l)">-${fmt$(e.amount)}</span>
        <button onclick="delExpense('${e.id}')" style="background:rgba(248,113,113,.1);color:var(--red-l);border:none;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:11px">✕</button>
      </div>`).join('')}</div>`}
    `;
  }

  window.delExpense = async function(id){
    if (!confirm('Delete this expense?')) return;
    await api(FAPI + '/expenses/' + id, {method:'DELETE'});
    loaders.finance();
  };

  window.showNewExpense = function(){
    const today = new Date().toISOString().substring(0,10);
    openModal('Add Expense', `
      <div class="row2"><div><label class="inp-label">Category *</label><select class="inp" id="ex-cat">
        <option value="rent">Rent / Lease</option>
        <option value="salaries">Salaries</option>
        <option value="marketing">Marketing</option>
        <option value="utilities">Utilities</option>
        <option value="equipment">Equipment</option>
        <option value="maintenance">Maintenance</option>
        <option value="travel">Travel</option>
        <option value="legal">Legal / Pro Fees</option>
        <option value="other">Other</option>
      </select></div>
      <div><label class="inp-label">Date *</label><input class="inp" id="ex-date" type="date" value="${today}"></div></div>
      <div style="margin-top:10px"><label class="inp-label">Description *</label><input class="inp" id="ex-desc" placeholder="Office rent — June 2026"></div>
      <div class="row2" style="margin-top:10px"><div><label class="inp-label">Amount ($) *</label><input class="inp" id="ex-amt" type="number" step="0.01" placeholder="0.00"></div>
      <div><label class="inp-label">Vendor</label><input class="inp" id="ex-vendor" placeholder="optional"></div></div>
      <div style="margin-top:10px"><label class="inp-label">Payment Method</label><select class="inp" id="ex-method"><option>ACH</option><option>Check</option><option>Cash</option><option>Card</option></select></div>
      <div style="margin-top:10px"><label class="inp-label">Notes</label><input class="inp" id="ex-notes"></div>
    `, 'Add Expense', async ()=>{
      const body = {
        category: val('ex-cat'),
        date: val('ex-date'),
        description: val('ex-desc'),
        amount: parseFloat(val('ex-amt'))||0,
        vendor: val('ex-vendor'),
        payment_method: val('ex-method'),
        notes: val('ex-notes'),
      };
      if (!body.description || body.amount<=0) { alert('Description and amount required'); return false; }
      await api(FAPI + '/expenses', {method:'POST', body:JSON.stringify(body)});
      loaders.finance();
      return true;
    });
  };

  // ============ Generic modal helper ============
  function val(id){ const e=document.getElementById(id); return e? e.value : ''; }

  function openModal(title, contentHTML, primaryLabel, onSubmit){
    closeFinModal();
    const html = `<div id="fin-modal" style="position:fixed;inset:0;background:rgba(2,6,18,.85);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);padding:20px;overflow-y:auto">
      <div style="width:100%;max-width:680px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--rl);box-shadow:var(--sh-lg);overflow:hidden;max-height:90vh;display:flex;flex-direction:column">
        <div style="padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;flex-shrink:0">
          <div style="font-size:17px;font-weight:700">${title}</div>
          <button onclick="closeFinModal()" class="btn-icon">✕</button>
        </div>
        <div style="padding:24px;overflow-y:auto;flex:1">${contentHTML}<p id="fin-modal-msg" style="font-size:12px;margin-top:10px;display:none"></p></div>
        <div style="padding:16px 24px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end;flex-shrink:0">
          <button class="btn-s" onclick="closeFinModal()">Cancel</button>
          <button class="btn-p" id="fin-modal-submit">${primaryLabel}</button>
        </div>
      </div>
    </div>`;
    document.body.insertAdjacentHTML('beforeend', html);
    document.getElementById('fin-modal-submit').onclick = async ()=>{
      try { const ok = await onSubmit(); if (ok!==false) closeFinModal(); }
      catch(e){ const m=document.getElementById('fin-modal-msg'); m.textContent=e.message; m.style.color='var(--red-l)'; m.style.display='block'; }
    };
  }
  window.closeFinModal = function(){ document.getElementById('fin-modal')?.remove(); };
})();

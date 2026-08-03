/* Admin — Customer Orders (Phase C.7)
 * Renders the /pg-custorders page inside the admin SPA (index.html).
 *
 * Data source (backend, already implemented in server.py):
 *   GET  /api/admin/customer-orders?status=...   → list
 *   GET  /api/admin/customer-orders/{id}          → detail (includes media_data_url)
 *   PUT  /api/admin/customer-orders/{id}/status   → update status + admin_note
 *
 * Depends on:
 *   - window.Auth.api.raw (from auth-client.js) via the app.js `api()` helper
 *   - `loaders` const declared in app.js (we attach loaders.custorders here)
 *   - `go(page)` function from app.js
 *
 * Loaded from index.html AFTER app.js so `loaders` and `api` are defined.
 */
(function(){
  'use strict';

  // ---------- One-time CSS injection ----------
  if(!document.getElementById('custorders-css')){
    const st=document.createElement('style');
    st.id='custorders-css';
    st.textContent=`
      .co-hd{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:20px}
      .co-hd h1{font-size:22px;font-weight:900;letter-spacing:-.3px;color:var(--t-1)}
      .co-hd p{color:var(--t-4);font-size:12px;margin-top:2px}
      .co-refresh{background:transparent;border:1px solid var(--border);color:var(--t-3);padding:8px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .15s;display:inline-flex;align-items:center;gap:6px}
      .co-refresh:hover{color:var(--t-1);border-color:var(--brand-l)}
      .co-filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
      .co-fbtn{padding:7px 13px;border-radius:8px;font-size:12px;font-weight:600;border:1px solid var(--border);background:transparent;color:var(--t-3);cursor:pointer;font-family:inherit;transition:all .15s}
      .co-fbtn:hover{color:var(--t-1);border-color:var(--t-4)}
      .co-fbtn.on{background:var(--brand-l);color:#fff;border-color:var(--brand-l)}
      .co-fbtn .n{margin-left:6px;background:rgba(0,0,0,.18);padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700}
      .co-table{width:100%;border-collapse:collapse;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
      .co-table th,.co-table td{padding:12px 14px;text-align:left;font-size:13px;border-bottom:1px solid var(--border)}
      .co-table th{background:rgba(2,6,23,.04);font-size:10px;font-weight:700;color:var(--t-4);text-transform:uppercase;letter-spacing:1px}
      .co-table tbody tr{cursor:pointer;transition:background .1s}
      .co-table tbody tr:hover{background:rgba(99,102,241,.04)}
      .co-table tbody tr:last-child td{border-bottom:none}
      .co-mono{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--t-4)}
      .co-total{font-weight:800;color:var(--cyan);font-variant-numeric:tabular-nums}
      .co-empty{padding:60px 20px;text-align:center;color:var(--t-4);font-size:13px}
      .co-badge{display:inline-block;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}
      .co-b-pending_payment{background:rgba(251,191,36,.12);color:#d97706}
      .co-b-paid{background:rgba(16,185,129,.12);color:#059669}
      .co-b-approved{background:rgba(99,102,241,.12);color:var(--brand-l)}
      .co-b-live{background:rgba(34,211,238,.12);color:#0891b2}
      .co-b-rejected{background:rgba(239,68,68,.12);color:#dc2626}
      .co-b-cancelled{background:rgba(148,163,184,.15);color:#64748b}

      /* Drawer */
      .co-drawer-ov{position:fixed;inset:0;background:rgba(2,6,23,.6);backdrop-filter:blur(6px);z-index:200;display:flex;justify-content:flex-end;padding:0}
      .co-drawer{background:var(--bg-card);border-left:1px solid var(--border);width:min(720px,100vw);height:100vh;overflow:auto;padding:24px 26px;position:relative;box-shadow:-12px 0 40px rgba(0,0,0,.15)}
      .co-drawer .close{position:absolute;top:22px;right:22px;background:transparent;border:1px solid var(--border);color:var(--t-4);padding:6px 10px;border-radius:8px;font-family:inherit;font-size:12px;cursor:pointer;transition:all .15s}
      .co-drawer .close:hover{color:#dc2626;border-color:#dc2626}
      .co-drawer h2{font-size:20px;font-weight:900;color:var(--t-1)}
      .co-drawer .ref{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--t-4);margin-top:2px}
      .co-sec{margin-top:22px}
      .co-sec h3{font-size:10px;font-weight:800;color:var(--t-4);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px}
      .co-kv{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px}
      .co-kv div{padding:6px 0;border-bottom:1px dashed var(--border);font-size:13px;display:flex;justify-content:space-between;gap:8px}
      .co-kv div span:first-child{color:var(--t-4);font-size:12px}
      .co-kv div span:last-child{color:var(--t-1);font-weight:500;text-align:right;word-break:break-all}
      .co-line{background:rgba(99,102,241,.04);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:8px;font-size:13px}
      .co-line .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
      .co-line .top .name{font-weight:700;color:var(--t-1)}
      .co-line .top .amt{color:var(--cyan);font-weight:800;font-variant-numeric:tabular-nums}
      .co-line .meta{color:var(--t-4);font-size:11.5px}
      .co-line .disc{color:#059669;font-weight:600}
      .co-grand{background:linear-gradient(135deg,rgba(34,211,238,.08),rgba(99,102,241,.06));border:1px solid rgba(34,211,238,.25);border-radius:12px;padding:14px 18px;display:flex;justify-content:space-between;align-items:center;margin-top:12px}
      .co-grand .lb{font-size:11px;color:var(--t-4);text-transform:uppercase;letter-spacing:2px;font-weight:700}
      .co-grand .val{font-size:28px;font-weight:900;color:var(--cyan);font-variant-numeric:tabular-nums}
      .co-media{margin-top:8px;background:#020617;border:1px solid var(--border);border-radius:10px;padding:8px;text-align:center}
      .co-media img,.co-media video{max-width:100%;max-height:280px;border-radius:6px;display:block;margin:0 auto}
      .co-media .none{color:var(--t-4);font-size:12px;padding:20px}
      .co-note{width:100%;background:var(--bg-card);border:1px solid var(--border);color:var(--t-1);padding:10px 12px;border-radius:8px;font-family:inherit;font-size:13px;resize:vertical;min-height:70px}
      .co-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
      .co-act{padding:10px 16px;border-radius:9px;font-size:12px;font-weight:700;border:none;cursor:pointer;font-family:inherit;transition:all .15s;color:#fff;letter-spacing:.3px}
      .co-act:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 14px rgba(0,0,0,.15)}
      .co-act:disabled{opacity:.4;cursor:not-allowed}
      .co-act-paid{background:linear-gradient(135deg,#10b981,#059669)}
      .co-act-approved{background:linear-gradient(135deg,#6366f1,#4f46e5)}
      .co-act-live{background:linear-gradient(135deg,#22d3ee,#0891b2)}
      .co-act-rejected{background:linear-gradient(135deg,#dc2626,#991b1b)}
      .co-act-cancelled{background:linear-gradient(135deg,#64748b,#334155)}
    `;
    document.head.appendChild(st);
  }

  // ---------- State ----------
  const STATUSES=['pending_payment','paid','approved','live','rejected','cancelled'];
  const state={filter:'all',orders:[]};

  function fmtDate(s){
    try{const d=new Date(s);if(isNaN(d))return '—';
      return d.toLocaleString('en-US',{month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'});
    }catch(e){return '—'}
  }
  function money(n){return '$'+Number(n||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
  function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c])}
  function statusLabel(s){return String(s||'').replace(/_/g,' ')}

  function counts(all){
    const c={all:all.length};
    STATUSES.forEach(s=>{c[s]=all.filter(o=>o.status===s).length});
    return c;
  }

  function renderList(){
    const filtered = state.filter==='all' ? state.orders : state.orders.filter(o=>o.status===state.filter);
    if(filtered.length===0){
      return `<div class="co-empty"><div style="font-size:14px;color:var(--t-4);margin-bottom:6px">No orders in this view</div><div style="font-size:11.5px;color:var(--t-5)">Orders submitted from mediadview.com/marketplace will appear here</div></div>`;
    }
    return `<table class="co-table">
      <thead><tr>
        <th>Ref</th><th>Customer</th><th>Screens</th><th>Total</th><th>Status</th><th>Received</th>
      </tr></thead>
      <tbody>${filtered.map(o=>{
        const nScreens=(o.lines||[]).length;
        const cust=esc(o.customer_name||o.customer_email||'—');
        return `<tr onclick="window.openCustOrder('${o.id}')">
          <td class="co-mono">${esc(o.ref||o.id?.slice(0,8)||'')}</td>
          <td><div style="font-weight:600;color:var(--t-1)">${cust}</div><div style="font-size:11px;color:var(--t-4);margin-top:2px">${esc(o.customer_email||'')}</div></td>
          <td>${nScreens} screen${nScreens===1?'':'s'}</td>
          <td class="co-total">${money(o.grand_total)}</td>
          <td><span class="co-badge co-b-${o.status}">${statusLabel(o.status)}</span></td>
          <td class="co-mono">${fmtDate(o.created_at)}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  }

  function render(el){
    const c=counts(state.orders);
    const chip=(k,label)=>`<button class="co-fbtn ${state.filter===k?'on':''}" onclick="window.custFilter('${k}')">${label}<span class="n">${c[k]||0}</span></button>`;
    el.innerHTML=`
      <div class="co-hd">
        <div>
          <h1>Customer Orders</h1>
          <p>Marketplace orders from the public advertising portal · Approve, mark paid, activate.</p>
        </div>
        <button class="co-refresh" onclick="loaders.custorders()"><svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Refresh</button>
      </div>
      <div class="co-filters">
        ${chip('all','All')}
        ${chip('pending_payment','Pending payment')}
        ${chip('paid','Paid')}
        ${chip('approved','Approved')}
        ${chip('live','Live')}
        ${chip('rejected','Rejected')}
        ${chip('cancelled','Cancelled')}
      </div>
      <div id="co-list">${renderList()}</div>
    `;
  }

  // ---------- Loader (invoked by go('custorders')) ----------
  if(typeof loaders!=='undefined'){
    loaders.custorders=async function(){
      const el=document.getElementById('pg-custorders');
      if(!el)return;
      el.innerHTML=`<div class="co-empty">Loading customer orders…</div>`;
      try{
        const data=await api('/admin/customer-orders');
        state.orders=Array.isArray(data)?data:[];
        render(el);
      }catch(e){
        el.innerHTML=`<div class="co-empty" style="color:#dc2626">Unable to load orders: ${esc(e.message||'unknown error')}</div>`;
      }
    };
  }

  // ---------- Public helpers on window ----------
  window.custFilter=function(k){
    state.filter=k;
    const list=document.getElementById('co-list');
    if(list)list.innerHTML=renderList();
    document.querySelectorAll('.co-fbtn').forEach(b=>b.classList.remove('on'));
    const bs=document.querySelectorAll('.co-fbtn');
    const idx=['all',...STATUSES].indexOf(k);
    if(idx>=0 && bs[idx])bs[idx].classList.add('on');
  };

  window.openCustOrder=async function(id){
    // Close any existing drawer
    document.querySelectorAll('.co-drawer-ov').forEach(x=>x.remove());
    const ov=document.createElement('div');
    ov.className='co-drawer-ov';
    ov.innerHTML=`<div class="co-drawer"><div class="co-empty">Loading order…</div></div>`;
    ov.addEventListener('click',(e)=>{if(e.target===ov)ov.remove()});
    document.body.appendChild(ov);
    try{
      const o=await api('/admin/customer-orders/'+encodeURIComponent(id));
      renderDrawer(ov.querySelector('.co-drawer'),o);
    }catch(e){
      ov.querySelector('.co-drawer').innerHTML=`<button class="close" onclick="this.closest('.co-drawer-ov').remove()">Close</button><div class="co-empty" style="color:#dc2626">Unable to load: ${esc(e.message||'unknown')}</div>`;
    }
  };

  function renderDrawer(root,o){
    const lines=(o.lines||[]).map(l=>`
      <div class="co-line">
        <div class="top"><div class="name">${esc(l.screen_name||'Screen')}</div><div class="amt">${money(l.line_total)}</div></div>
        <div class="meta">
          ${esc(l.screen_location?.city||'')}${l.screen_location?.state?', '+esc(l.screen_location.state):''} ·
          ${l.num_ads} ad${l.num_ads===1?'':'s'} × ${l.months} month${l.months===1?'':'s'} × ${money(l.price_per_ad_per_month)}
          ${l.discount_pct?` · <span class="disc">${l.discount_pct}% off</span>`:''}
        </div>
      </div>
    `).join('');

    let mediaHtml='<div class="none">No creative uploaded</div>';
    if(o.media_data_url){
      if(o.media_kind==='video' || /^data:video/.test(o.media_data_url)){
        mediaHtml=`<video controls src="${o.media_data_url}"></video>`;
      }else{
        mediaHtml=`<img src="${o.media_data_url}" alt="Customer creative"/>`;
      }
    }

    const isFinal = o.status==='live' || o.status==='rejected' || o.status==='cancelled';
    const actBtn=(newStatus,label,cls,confirmMsg)=>{
      if(o.status===newStatus)return '';
      return `<button class="co-act co-act-${newStatus}" onclick="window.setCustStatus('${o.id}','${newStatus}',${JSON.stringify(confirmMsg||'')})">${label}</button>`;
    };

    root.innerHTML=`
      <button class="close" onclick="this.closest('.co-drawer-ov').remove()">Close</button>
      <h2>${esc(o.customer_name||o.customer_email||'Order')}</h2>
      <div class="ref">${esc(o.ref||o.id)}</div>
      <div style="margin-top:6px"><span class="co-badge co-b-${o.status}">${statusLabel(o.status)}</span></div>

      <div class="co-sec">
        <h3>Customer</h3>
        <div class="co-kv">
          <div><span>Name</span><span>${esc(o.customer_name||'—')}</span></div>
          <div><span>Email</span><span>${esc(o.customer_email||'—')}</span></div>
          <div><span>Phone</span><span>${esc(o.customer_phone||'—')}</span></div>
          <div><span>Received</span><span>${fmtDate(o.created_at)}</span></div>
        </div>
      </div>

      <div class="co-sec">
        <h3>Cart · ${lines?(o.lines||[]).length:0} line${(o.lines||[]).length===1?'':'s'}</h3>
        ${lines || '<div class="co-empty">No lines</div>'}
        <div class="co-grand"><div class="lb">Grand total (${esc(o.currency||'USD')})</div><div class="val">${money(o.grand_total)}</div></div>
      </div>

      <div class="co-sec">
        <h3>Creative</h3>
        <div class="co-media">${mediaHtml}</div>
      </div>

      ${o.notes?`<div class="co-sec"><h3>Customer notes</h3><div style="background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.2);border-radius:10px;padding:12px 14px;font-size:13px;color:var(--t-1);white-space:pre-wrap">${esc(o.notes)}</div></div>`:''}

      <div class="co-sec">
        <h3>Admin note (optional)</h3>
        <textarea class="co-note" id="co-admin-note" placeholder="Internal note — visible only to admins">${esc(o.admin_note||'')}</textarea>
      </div>

      <div class="co-sec">
        <h3>Actions</h3>
        ${isFinal?`<div style="color:var(--t-4);font-size:12px;padding:8px 0">This order is in a final state (${statusLabel(o.status)}). No further transitions available.</div>`:''}
        <div class="co-actions">
          ${!isFinal?actBtn('paid','Mark as paid','','Mark this order as PAID?'):''}
          ${!isFinal?actBtn('approved','Approve','','Approve this order?'):''}
          ${!isFinal?actBtn('live','Mark as live','','Mark this order as LIVE (activated on screens)?'):''}
          ${!isFinal?actBtn('rejected','Reject','','Reject this order? The customer will need to submit again.'):''}
          ${!isFinal?actBtn('cancelled','Cancel','','Cancel this order?'):''}
        </div>
      </div>
    `;
  }

  window.setCustStatus=async function(id,status,confirmMsg){
    if(confirmMsg && !confirm(confirmMsg))return;
    const noteEl=document.getElementById('co-admin-note');
    const admin_note = noteEl ? (noteEl.value||'').trim() : '';
    try{
      await api('/admin/customer-orders/'+encodeURIComponent(id)+'/status',{
        method:'PUT',
        body: JSON.stringify({status, admin_note: admin_note||null})
      });
      // Close drawer + refresh list
      document.querySelectorAll('.co-drawer-ov').forEach(x=>x.remove());
      if(typeof loaders!=='undefined' && loaders.custorders)await loaders.custorders();
    }catch(e){
      alert('Failed to update status: '+(e.message||'unknown'));
    }
  };
})();

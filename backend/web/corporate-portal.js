/* Corporate Client Portal (Phase D.1)
 * ------------------------------------------------------------
 * Renders a dedicated dashboard for business/rental clients
 * (users with role === 'corporate'). Reuses the same visual
 * language as the admin panel (cyan/indigo, cards) but hides
 * the admin sidebar entirely and shows a location-first view.
 *
 * Overview:
 *  - Home:  locations grouped, screens shown as thumbnails,
 *           quick stats (locations, screens, monthly cost, balance)
 *  - Content: "My Content" placeholder (upload media/menus)
 *  - Schedule: placeholder (day/time scheduling per screen)
 *  - Billing: contracts + invoices from /api/corporate/*
 *
 * Entry point: window.renderCorporatePortal(user) — called by app.js
 * `enterApp()` when the logged-in user has role === 'corporate'.
 */
(function(){
  'use strict';

  // ---------- CSS ----------
  if(!document.getElementById('corp-css')){
    const st=document.createElement('style');
    st.id='corp-css';
    st.textContent=`
      #view-corporate{display:none;position:fixed;inset:0;background:#f4f6fb;z-index:5;overflow:auto}
      #view-corporate.on{display:block}
      .cp-shell{max-width:1200px;margin:0 auto;padding:24px 22px 60px}
      .cp-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:12px}
      .cp-brand{display:flex;align-items:center;gap:10px}
      .cp-brand img{height:52px}
      .cp-user{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #e2e8f0;padding:6px 12px 6px 6px;border-radius:100px;font-size:12.5px}
      .cp-user .av{width:32px;height:32px;background:linear-gradient(135deg,#6366f1,#22d3ee);color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px}
      .cp-user .who{display:flex;flex-direction:column;line-height:1.2}
      .cp-user .who b{font-weight:700;color:#0f172a}
      .cp-user .who span{color:#64748b;font-size:11px}
      .cp-logout{background:transparent;border:1px solid #e2e8f0;color:#64748b;padding:7px 12px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit}
      .cp-logout:hover{color:#dc2626;border-color:#dc2626}

      .cp-hero{background:linear-gradient(135deg,#6366f1 0%,#22d3ee 100%);color:#fff;border-radius:16px;padding:24px 26px;margin-bottom:20px;position:relative;overflow:hidden}
      .cp-hero::before{content:'';position:absolute;right:-40px;top:-40px;width:220px;height:220px;background:radial-gradient(circle,rgba(255,255,255,.18),transparent 70%);border-radius:50%}
      .cp-hero .greet{font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;opacity:.9}
      .cp-hero h1{font-size:26px;font-weight:900;margin-top:4px;letter-spacing:-.4px}
      .cp-hero .sub{margin-top:6px;font-size:13.5px;opacity:.92}

      .cp-tabs{display:flex;gap:6px;margin-bottom:20px;background:#fff;padding:5px;border-radius:12px;border:1px solid #e2e8f0;overflow:auto;-webkit-overflow-scrolling:touch}
      .cp-tab{padding:8px 16px;border-radius:8px;font-size:13px;font-weight:600;color:#64748b;border:none;background:transparent;cursor:pointer;font-family:inherit;white-space:nowrap;transition:all .15s;display:inline-flex;align-items:center;gap:7px}
      .cp-tab:hover{color:#0f172a}
      .cp-tab.on{background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;box-shadow:0 4px 10px rgba(99,102,241,.25)}
      .cp-tab svg{width:14px;height:14px}

      .cp-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}
      .cp-stat{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;position:relative;overflow:hidden}
      .cp-stat .l{font-size:10px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px;display:flex;align-items:center;gap:6px}
      .cp-stat .l svg{width:12px;height:12px}
      .cp-stat .v{font-size:24px;font-weight:900;color:#0f172a;font-variant-numeric:tabular-nums;letter-spacing:-.5px}
      .cp-stat .s{font-size:11.5px;color:#64748b;margin-top:2px}
      .cp-stat.brand{background:linear-gradient(135deg,rgba(99,102,241,.06),#fff);border-color:rgba(99,102,241,.2)}
      .cp-stat.cyan .v{color:#0891b2}
      .cp-stat.green .v{color:#059669}
      .cp-stat.red .v{color:#dc2626}

      .cp-section-title{display:flex;justify-content:space-between;align-items:flex-end;margin:8px 0 12px}
      .cp-section-title h2{font-size:16px;font-weight:800;color:#0f172a;letter-spacing:-.2px}
      .cp-section-title p{font-size:12px;color:#64748b;margin-top:2px}

      .cp-locations{display:grid;grid-template-columns:1fr 1fr;gap:16px}
      .cp-loc{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px 20px 16px;transition:all .15s;position:relative}
      .cp-loc:hover{border-color:#6366f1;box-shadow:0 8px 24px rgba(99,102,241,.08);transform:translateY(-2px)}
      .cp-loc-hd{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px}
      .cp-loc-hd .name{font-size:15px;font-weight:800;color:#0f172a;line-height:1.25}
      .cp-loc-hd .addr{font-size:12px;color:#64748b;margin-top:3px;line-height:1.4}
      .cp-loc-badge{padding:3px 8px;border-radius:6px;font-size:9.5px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;white-space:nowrap}
      .cp-loc-badge.active{background:rgba(16,185,129,.12);color:#059669}
      .cp-loc-badge.paused{background:rgba(148,163,184,.15);color:#64748b}

      .cp-screens{margin-top:14px;display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}
      .cp-screen{background:linear-gradient(160deg,#0f172a,#1e293b);border-radius:10px;padding:12px 10px 10px;color:#fff;position:relative;overflow:hidden;transition:all .15s}
      .cp-screen:hover{transform:scale(1.03);box-shadow:0 10px 22px rgba(15,23,42,.28)}
      .cp-screen::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#22d3ee,#6366f1)}
      .cp-screen .frame{background:linear-gradient(135deg,rgba(34,211,238,.18),rgba(99,102,241,.16));border:1px solid rgba(255,255,255,.1);border-radius:6px;height:56px;display:flex;align-items:center;justify-content:center;margin-bottom:8px;position:relative}
      .cp-screen .frame svg{width:22px;height:22px;color:#22d3ee}
      .cp-screen .frame::after{content:'';position:absolute;bottom:-4px;left:50%;transform:translateX(-50%);width:22px;height:2px;background:rgba(255,255,255,.15);border-radius:2px}
      .cp-screen .model{font-size:11px;font-weight:800;letter-spacing:.5px;color:#e2e8f0}
      .cp-screen .units{font-size:10.5px;color:#94a3b8;margin-top:2px}
      .cp-screen .price{font-size:11px;color:#22d3ee;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums}

      .cp-empty{background:#fff;border:2px dashed #e2e8f0;border-radius:14px;padding:44px 24px;text-align:center}
      .cp-empty h3{font-size:15px;font-weight:800;color:#0f172a;margin-bottom:6px}
      .cp-empty p{font-size:13px;color:#64748b}

      /* Sub-pages */
      .cp-placeholder{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:60px 30px;text-align:center}
      .cp-placeholder .ico{width:64px;height:64px;margin:0 auto 14px;border-radius:16px;background:linear-gradient(135deg,rgba(99,102,241,.1),rgba(34,211,238,.1));display:flex;align-items:center;justify-content:center}
      .cp-placeholder .ico svg{width:32px;height:32px;color:#6366f1}
      .cp-placeholder h3{font-size:20px;font-weight:800;color:#0f172a;margin-bottom:8px}
      .cp-placeholder p{font-size:14px;color:#64748b;max-width:420px;margin:0 auto}
      .cp-placeholder .soon{margin-top:16px;display:inline-block;padding:6px 12px;border-radius:100px;background:rgba(99,102,241,.1);color:#6366f1;font-size:11px;font-weight:800;letter-spacing:1px;text-transform:uppercase}

      /* Billing list */
      .cp-list{background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden}
      .cp-list .row{display:grid;grid-template-columns:1fr auto auto auto;gap:14px;padding:14px 18px;align-items:center;border-bottom:1px solid #f1f5f9;font-size:13.5px}
      .cp-list .row:last-child{border-bottom:none}
      .cp-list .row .no{font-weight:700;color:#0f172a}
      .cp-list .row .dt{font-size:11.5px;color:#64748b;margin-top:2px}
      .cp-list .row .amt{font-weight:800;color:#0891b2;font-variant-numeric:tabular-nums}
      .cp-list .row .stat{padding:3px 8px;border-radius:6px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.5px}
      .cp-list .row .stat.paid{background:rgba(16,185,129,.12);color:#059669}
      .cp-list .row .stat.pending{background:rgba(251,191,36,.15);color:#d97706}
      .cp-list .row .stat.overdue{background:rgba(239,68,68,.12);color:#dc2626}
      .cp-list .row .stat.draft{background:rgba(148,163,184,.15);color:#64748b}
      .cp-list .row .stat.active{background:rgba(16,185,129,.12);color:#059669}
      .cp-list .row .stat.expired{background:rgba(148,163,184,.15);color:#64748b}
      .cp-list .row .stat.cancelled{background:rgba(239,68,68,.12);color:#dc2626}

      /* Password-change banner */
      .cp-warn{background:linear-gradient(135deg,#fef3c7,#fde68a);border:1px solid #fbbf24;color:#78350f;padding:12px 16px;border-radius:10px;font-size:13px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:12px}
      .cp-warn a{color:#78350f;font-weight:700;text-decoration:underline}

      /* Modal */
      .cp-modal-ov{position:fixed;inset:0;background:rgba(2,6,23,.55);z-index:900;display:flex;justify-content:center;align-items:center;padding:20px}
      .cp-modal{background:#fff;border-radius:14px;padding:24px 26px;max-width:460px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.25)}
      .cp-modal h3{font-size:18px;font-weight:800;color:#0f172a;margin-bottom:6px}
      .cp-modal p.sub{font-size:13px;color:#64748b;margin-bottom:16px}
      .cp-modal label{display:block;font-size:11px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px;margin-top:12px}
      .cp-modal input{width:100%;padding:10px 12px;border:1.5px solid #e2e8f0;border-radius:8px;font-size:14px;font-family:inherit}
      .cp-modal input:focus{outline:none;border-color:#6366f1}
      .cp-modal .actions{display:flex;gap:8px;margin-top:20px;justify-content:flex-end}
      .cp-btn{padding:10px 18px;border-radius:9px;font-weight:700;font-size:13px;cursor:pointer;border:none;font-family:inherit;transition:all .15s}
      .cp-btn.primary{background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff}
      .cp-btn.primary:hover{transform:translateY(-1px);box-shadow:0 6px 16px rgba(99,102,241,.3)}
      .cp-btn.ghost{background:transparent;border:1px solid #e2e8f0;color:#64748b}
      .cp-err{color:#dc2626;font-size:12.5px;margin-top:8px}

      @media (max-width: 720px){
        .cp-shell{padding:16px 14px 40px}
        .cp-hero{padding:20px 20px}
        .cp-hero h1{font-size:22px}
        .cp-stats{grid-template-columns:1fr 1fr;gap:10px}
        .cp-stat{padding:12px 14px}
        .cp-stat .v{font-size:20px}
        .cp-locations{grid-template-columns:1fr}
        .cp-screens{grid-template-columns:repeat(2,1fr)}
        .cp-list .row{grid-template-columns:1fr auto;font-size:12.5px;padding:12px 14px}
        .cp-list .row .stat{display:none}
      }
    `;
    document.head.appendChild(st);
  }

  // ---------- Helpers ----------
  function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c])}
  function money(n){return '$'+Number(n||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}
  function fmtDate(s){try{const d=new Date(s);return isNaN(d)?'—':d.toLocaleDateString('en-US',{month:'short',day:'2-digit',year:'numeric'});}catch(e){return '—'}}

  const state={data:null,tab:'home'};

  function tabBtn(id,label,ic){
    return `<button class="cp-tab ${state.tab===id?'on':''}" onclick="window.corpGo('${id}')">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg>${label}
    </button>`;
  }

  function screenCard(sc){
    const price = Number(sc.day_price||0);
    const units = Number(sc.units||1);
    return `<div class="cp-screen" title="${esc(sc.model)} · ${units} unit${units===1?'':'s'} · ${money(price)}/day">
      <div class="frame">
        <svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25"/></svg>
      </div>
      <div class="model">${esc(sc.model||'MAV-30540S')}</div>
      <div class="units">${units} unit${units===1?'':'s'}</div>
      <div class="price">${money(price)}/day</div>
    </div>`;
  }

  function renderHome(root){
    const d = state.data;
    const cl = d.client;
    const s = d.summary;

    const locations = (cl.locations||[]).map(loc=>{
      const screens = (loc.screens||[]).map(screenCard).join('') || '<div style="grid-column:1/-1;padding:12px;text-align:center;color:#94a3b8;font-size:12px">No screens configured for this location</div>';
      return `<div class="cp-loc">
        <div class="cp-loc-hd">
          <div>
            <div class="name">${esc(loc.name||'Location')}</div>
            <div class="addr">${esc([loc.address_line1, loc.city, loc.state, loc.zip].filter(Boolean).join(', ') || '—')}</div>
          </div>
          <span class="cp-loc-badge ${loc.status==='paused'?'paused':'active'}">${esc(loc.status||'active')}</span>
        </div>
        <div class="cp-screens">${screens}</div>
      </div>`;
    }).join('');

    root.innerHTML = `
      <div class="cp-hero">
        <div class="greet">WELCOME</div>
        <h1>${esc(cl.business_name)}</h1>
        <div class="sub">${esc(cl.address_line1 || '')}${cl.city?', '+esc(cl.city):''}${cl.state?', '+esc(cl.state):''}</div>
      </div>

      <div class="cp-stats">
        <div class="cp-stat brand">
          <div class="l"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><circle cx="12" cy="11" r="3" stroke-linecap="round" stroke-linejoin="round"/></svg>Locations</div>
          <div class="v">${s.total_locations}</div>
          <div class="s">${s.active_locations} active</div>
        </div>
        <div class="cp-stat cyan">
          <div class="l"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>Screens</div>
          <div class="v">${s.total_screens}</div>
          <div class="s">across all locations</div>
        </div>
        <div class="cp-stat green">
          <div class="l"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Monthly Rent</div>
          <div class="v">${money(s.monthly_total)}</div>
          <div class="s">${s.active_contract_id?'contract active':'no active contract'}</div>
        </div>
        <div class="cp-stat ${s.balance_due>0?'red':'green'}">
          <div class="l"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>Balance Due</div>
          <div class="v">${money(s.balance_due)}</div>
          <div class="s">${s.open_invoice_count} open invoice${s.open_invoice_count===1?'':'s'}</div>
        </div>
      </div>

      <div class="cp-section-title">
        <div>
          <h2>My Locations & Screens</h2>
          <p>Your rented displays grouped by location.</p>
        </div>
      </div>

      ${locations || '<div class="cp-empty"><h3>No locations yet</h3><p>Your MediAd View admin will add your rented locations here.</p></div>'}
    `;
  }

  async function renderContent(root){
    root.innerHTML = `<div class="cp-placeholder">
      <div class="ico"><svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z"/></svg></div>
      <h3>My Content</h3>
      <p>Upload images, videos, and menus that display on your screens. Manage what your customers see 24/7.</p>
      <div class="soon">Coming soon</div>
    </div>`;
  }

  async function renderSchedule(root){
    root.innerHTML = `<div class="cp-placeholder">
      <div class="ico"><svg fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5"/></svg></div>
      <h3>Content Scheduling</h3>
      <p>Program what shows on each screen by day of the week and hour. Different content for lunch, dinner, or weekends.</p>
      <div class="soon">Coming soon</div>
    </div>`;
  }

  async function renderBilling(root){
    root.innerHTML = `<div style="text-align:center;padding:40px;color:#64748b">Loading…</div>`;
    try{
      const [contracts, invoices] = await Promise.all([
        window.Auth.api.raw('/corporate/contracts',{credentials:'include'}).then(r=>r.json()),
        window.Auth.api.raw('/corporate/invoices',{credentials:'include'}).then(r=>r.json()),
      ]);

      const cList = contracts.length ? contracts.map(ct=>`
        <div class="row">
          <div>
            <div class="no">${esc(ct.contract_number||'Contract')}</div>
            <div class="dt">${fmtDate(ct.start_date)} → ${fmtDate(ct.end_date)} · ${ct.term_months||12} months</div>
          </div>
          <span></span>
          <span class="stat ${esc(ct.status||'draft')}">${esc(ct.status||'draft')}</span>
          <span class="amt">${money(ct.monthly_total||0)}/mo</span>
        </div>
      `).join('') : '<div style="padding:32px;text-align:center;color:#94a3b8;font-size:13px">No contracts yet.</div>';

      const iList = invoices.length ? invoices.map(iv=>{
        const bal = Number(iv.total||0) - Number(iv.amount_paid||0);
        return `<div class="row">
          <div>
            <div class="no">${esc(iv.invoice_number||'Invoice')}</div>
            <div class="dt">Issued ${fmtDate(iv.issue_date)}${iv.due_date?' · Due '+fmtDate(iv.due_date):''}</div>
          </div>
          <span></span>
          <span class="stat ${esc(iv.status||'pending')}">${esc(iv.status||'pending')}</span>
          <span class="amt">${money(iv.total||0)}${bal>0&&iv.status!=='paid'?`<br><span style="font-size:11px;color:#dc2626;font-weight:600">${money(bal)} due</span>`:''}</span>
        </div>`;
      }).join('') : '<div style="padding:32px;text-align:center;color:#94a3b8;font-size:13px">No invoices yet.</div>';

      root.innerHTML = `
        <div class="cp-section-title"><div><h2>Contracts (${contracts.length})</h2><p>Your rental agreements with MediAd View.</p></div></div>
        <div class="cp-list" style="margin-bottom:26px">${cList}</div>
        <div class="cp-section-title"><div><h2>Invoices (${invoices.length})</h2><p>Monthly billing history.</p></div></div>
        <div class="cp-list">${iList}</div>
      `;
    }catch(e){
      root.innerHTML = `<div class="cp-empty"><h3>Unable to load billing</h3><p>${esc(e.message||'Unknown error')}</p></div>`;
    }
  }

  // ---------- Change password modal (forced on first login) ----------
  function openChangePasswordModal(force){
    if(document.getElementById('cp-pw-modal'))return;
    const ov=document.createElement('div');
    ov.className='cp-modal-ov';
    ov.id='cp-pw-modal';
    ov.innerHTML=`
      <div class="cp-modal">
        <h3>${force?'Set a new password':'Change password'}</h3>
        <p class="sub">${force?'Your account uses a temporary password. Please choose a new one before continuing.':'Enter your current password and choose a new one.'}</p>
        <label>Current password</label>
        <input type="password" id="cp-cur" placeholder="Temporary password" autocomplete="current-password">
        <label>New password</label>
        <input type="password" id="cp-new" placeholder="Min 8 characters" autocomplete="new-password">
        <label>Confirm new password</label>
        <input type="password" id="cp-new2" placeholder="Repeat new password" autocomplete="new-password">
        <div id="cp-pw-err" class="cp-err" style="display:none"></div>
        <div class="actions">
          ${force?'':'<button class="cp-btn ghost" onclick="document.getElementById(\'cp-pw-modal\').remove()">Cancel</button>'}
          <button class="cp-btn primary" onclick="window.corpSubmitPw(${force?'true':'false'})">Save</button>
        </div>
      </div>
    `;
    document.body.appendChild(ov);
    setTimeout(()=>document.getElementById('cp-cur')?.focus(),50);
  }

  window.corpSubmitPw = async function(force){
    const cur=document.getElementById('cp-cur').value;
    const nw=document.getElementById('cp-new').value;
    const nw2=document.getElementById('cp-new2').value;
    const err=document.getElementById('cp-pw-err');
    err.style.display='none';
    if(!cur || !nw || nw.length<8){err.textContent='New password must be at least 8 characters.';err.style.display='block';return}
    if(nw!==nw2){err.textContent='New passwords do not match.';err.style.display='block';return}
    try{
      const r = await window.Auth.api.raw('/auth/v2/change-password',{
        method:'POST', credentials:'include',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({current_password:cur, new_password:nw})
      });
      if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Change failed')}
      // Clear must_change_password on server via re-login? Simpler: mark it locally.
      // We also patch flag via a direct users update — endpoint doesn't exist so we just close.
      // The next full reload of /me will show the flag is still true but user can dismiss it.
      document.getElementById('cp-pw-modal').remove();
      // Update state so banner disappears
      if(state.data && state.data.user){state.data.user.must_change_password=false;renderShell();}
      alert('Password updated. You can log in again with your new password next time.');
    }catch(e){
      err.textContent = e.message || 'Failed to change password';
      err.style.display='block';
    }
  };

  // ---------- Shell ----------
  function renderShell(){
    const view = document.getElementById('view-corporate');
    if(!view)return;
    view.classList.add('on');
    const d = state.data;
    const initial = ((d.user.name||d.client.business_name||'U')[0]||'U').toUpperCase();
    view.innerHTML = `
      <div class="cp-shell">
        <div class="cp-top">
          <div class="cp-brand">
            <img src="/api/web/logo-dark.png" alt="MediAd View">
          </div>
          <div style="display:flex;align-items:center;gap:10px">
            <div class="cp-user">
              <div class="av">${esc(initial)}</div>
              <div class="who"><b>${esc(d.user.name||'User')}</b><span>${esc(d.user.email||'')}</span></div>
            </div>
            <button class="cp-logout" onclick="window.corpLogout()">Sign out</button>
          </div>
        </div>

        ${d.user.must_change_password?`<div class="cp-warn">
          <div>🔒 Your account is using a temporary password. <a href="#" onclick="event.preventDefault();window.corpChangePw()">Change it now</a> for better security.</div>
        </div>`:''}

        <div class="cp-tabs">
          ${tabBtn('home','Overview','M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25')}
          ${tabBtn('content','My Content','M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5z')}
          ${tabBtn('schedule','Schedule','M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75')}
          ${tabBtn('billing','Contracts & Invoices','M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z')}
        </div>

        <div id="cp-body"></div>
      </div>
    `;
    renderTab();

    // If must_change_password → open modal automatically
    if(d.user.must_change_password && !document.getElementById('cp-pw-modal')){
      openChangePasswordModal(true);
    }
  }

  function renderTab(){
    const body = document.getElementById('cp-body');
    if(!body)return;
    if(state.tab==='home')renderHome(body);
    else if(state.tab==='content')renderContent(body);
    else if(state.tab==='schedule')renderSchedule(body);
    else if(state.tab==='billing')renderBilling(body);
  }

  window.corpGo = function(tab){ state.tab=tab; renderShell(); };
  window.corpLogout = async function(){ try{await window.Auth.logout()}catch(_){}; location.reload(); };
  window.corpChangePw = function(){ openChangePasswordModal(false); };

  // ---------- Entry point ----------
  window.renderCorporatePortal = async function(user){
    // Ensure the corporate view container exists
    let view = document.getElementById('view-corporate');
    if(!view){
      view = document.createElement('div');
      view.id = 'view-corporate';
      document.body.appendChild(view);
    }
    // Hide the admin view
    const app = document.getElementById('view-app');
    if(app) app.classList.remove('on');
    view.classList.add('on');
    view.innerHTML = `<div style="padding:80px;text-align:center;color:#64748b">Loading your portal…</div>`;

    try{
      const r = await window.Auth.api.raw('/corporate/me',{credentials:'include'});
      if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Failed to load')}
      state.data = await r.json();
      state.tab = 'home';
      renderShell();
    }catch(e){
      view.innerHTML = `<div style="padding:60px;text-align:center;color:#dc2626;font-size:14px">Unable to load your portal: ${esc(e.message)}<br><br><button class="cp-btn ghost" onclick="window.corpLogout()">Sign out</button></div>`;
    }
  };
})();

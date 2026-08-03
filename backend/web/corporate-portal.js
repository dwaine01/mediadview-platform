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

      /* Media grid (D.1.b — My Content) */
      .cp-media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
      .cp-media-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;transition:all .15s}
      .cp-media-card:hover{box-shadow:0 10px 24px rgba(15,23,42,.08);transform:translateY(-2px);border-color:#c7d2fe}
      .cp-media-preview{position:relative;aspect-ratio:16/9;background:#020617;overflow:hidden}
      .cp-media-preview img,.cp-media-preview video{width:100%;height:100%;object-fit:cover}
      .cp-media-kind{position:absolute;top:8px;left:8px;background:rgba(0,0,0,.7);color:#fff;font-size:10px;font-weight:800;padding:3px 8px;border-radius:5px;letter-spacing:.5px}
      .cp-media-status{position:absolute;top:8px;right:8px;font-size:9.5px;font-weight:800;padding:3px 7px;border-radius:5px;letter-spacing:.5px;background:rgba(16,185,129,.9);color:#fff}
      .cp-media-status.paused{background:rgba(148,163,184,.9)}
      .cp-media-body{padding:12px 14px}
      .cp-media-name{font-size:13.5px;font-weight:800;color:#0f172a;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .cp-media-meta{display:flex;justify-content:space-between;font-size:11px;color:#64748b;margin-top:4px;gap:8px}
      .cp-media-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .cp-media-actions{display:flex;gap:6px;margin-top:12px}
      .cp-media-actions .cp-btn{flex:1;padding:7px 8px;font-size:11.5px}

      /* Schedule tab (D.1.c) */
      .cp-sched-list{display:flex;flex-direction:column;gap:12px}
      .cp-sched-card{display:grid;grid-template-columns:120px 1fr;gap:16px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px}
      .cp-sched-thumb{aspect-ratio:16/9;border-radius:8px;overflow:hidden;background:#020617}
      .cp-sched-thumb img,.cp-sched-thumb video{width:100%;height:100%;object-fit:cover}
      .cp-sched-name{font-size:15px;font-weight:800;color:#0f172a}
      .cp-sched-kind{font-size:12px;color:#64748b;margin-top:2px}
      .cp-days{display:flex;gap:6px;flex-wrap:wrap}
      .cp-day{padding:6px 12px;border-radius:8px;border:1.5px solid #e2e8f0;background:transparent;color:#64748b;font-size:11.5px;font-weight:700;cursor:pointer;transition:all .12s;font-family:inherit}
      .cp-day:hover{border-color:#94a3b8;color:#0f172a}
      .cp-day.on{background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;border-color:transparent}
      .cp-times{display:flex;align-items:center;gap:10px;margin-top:10px;font-size:12.5px;flex-wrap:wrap}
      .cp-times label{color:#64748b;font-weight:600;margin-right:2px}
      .cp-times input[type="time"]{border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 10px;font-family:inherit;font-size:13px}
      .cp-times input[type="time"]:focus{outline:none;border-color:#6366f1}
      .cp-toggle{display:inline-flex;align-items:center;gap:6px;margin-left:auto;cursor:pointer;color:#475569;font-weight:600}
      .cp-toggle input{width:16px;height:16px;cursor:pointer;accent-color:#6366f1}
      .cp-sched-status{margin-top:6px;font-size:11px;font-weight:600;min-height:14px}
      .cp-sched-status.ok{color:#059669}
      .cp-sched-status.err{color:#dc2626}

      /* Upload modal */
      .cp-upload-drop{border:2px dashed #cbd5e1;border-radius:12px;padding:36px 20px;text-align:center;background:#f8fafc;cursor:pointer;transition:all .15s;margin-top:12px}
      .cp-upload-drop:hover,.cp-upload-drop.hover{border-color:#6366f1;background:rgba(99,102,241,.04)}
      .cp-upload-drop .ico{width:44px;height:44px;margin:0 auto 10px;border-radius:12px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center}
      .cp-upload-drop .ico svg{width:24px;height:24px;color:#6366f1}
      .cp-upload-drop .prim{font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px}
      .cp-upload-drop .sec{font-size:12px;color:#64748b}
      .cp-upload-preview{margin-top:14px;border-radius:10px;overflow:hidden;background:#020617;aspect-ratio:16/9;position:relative}
      .cp-upload-preview img,.cp-upload-preview video{width:100%;height:100%;object-fit:contain}
      .cp-screen-list{max-height:180px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;padding:6px;margin-top:6px;background:#fafafa}
      .cp-screen-list label{display:flex!important;align-items:center;gap:10px;padding:8px 10px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500!important;color:#0f172a!important;text-transform:none!important;letter-spacing:0!important;margin:0!important;transition:background .1s}
      .cp-screen-list label:hover{background:#fff}
      .cp-screen-list input{accent-color:#6366f1;width:16px;height:16px}
      .cp-screen-list .loc{color:#64748b;font-size:11.5px;margin-left:auto}

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
        .cp-media-grid{grid-template-columns:1fr 1fr;gap:10px}
        .cp-sched-card{grid-template-columns:1fr;gap:10px}
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
    root.innerHTML = `<div style="text-align:center;padding:40px;color:#64748b">Loading your content…</div>`;
    try{
      const [media, screens] = await Promise.all([
        window.Auth.api.raw('/corporate/media',{credentials:'include'}).then(r=>r.json()),
        window.Auth.api.raw('/corporate/screens',{credentials:'include'}).then(r=>r.json()),
      ]);
      state.screens = screens;
      state.media = media;

      const grid = media.length ? media.map(m => mediaCard(m, screens)).join('') : '';
      root.innerHTML = `
        <div class="cp-section-title">
          <div>
            <h2>My Content (${media.length})</h2>
            <p>Upload images and videos that display on your screens.</p>
          </div>
          <button class="cp-btn primary" onclick="window.corpUploadOpen()">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" style="vertical-align:-2px;margin-right:4px"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>Upload Content
          </button>
        </div>
        ${media.length===0
          ? `<div class="cp-empty">
              <h3>No content uploaded yet</h3>
              <p>Upload your first image or video — it will start showing on your screens as soon as you assign it and set a schedule.</p>
            </div>`
          : `<div class="cp-media-grid">${grid}</div>`}
      `;
    }catch(e){
      root.innerHTML = `<div class="cp-empty"><h3>Unable to load content</h3><p>${esc(e.message||'Unknown error')}</p></div>`;
    }
  }

  function mediaCard(m, screens){
    const isVideo = m.kind === 'video';
    const kb = m.size_bytes ? (m.size_bytes/1024).toFixed(0)+' KB' : '';
    const scNames = (m.screen_ids||[])
      .map(id => (screens||[]).find(s=>s.id===id))
      .filter(Boolean)
      .map(s => (s.location_name||'')+' ('+s.model+')');
    const scLabel = scNames.length===0 ? 'Not assigned yet' :
                    scNames.length===1 ? scNames[0] :
                    scNames.length+' screens';
    const preview = isVideo
      ? `<video muted playsinline src="${m.data_url}" style="width:100%;height:100%;object-fit:cover"></video>`
      : `<img src="${m.data_url}" alt="${esc(m.name)}" style="width:100%;height:100%;object-fit:cover">`;
    return `
      <div class="cp-media-card">
        <div class="cp-media-preview">
          ${preview}
          <div class="cp-media-kind">${isVideo?'🎬 VIDEO':'🖼 IMAGE'}</div>
          <div class="cp-media-status ${m.status==='paused'?'paused':'active'}">${m.status==='paused'?'PAUSED':'ACTIVE'}</div>
        </div>
        <div class="cp-media-body">
          <div class="cp-media-name">${esc(m.name)}</div>
          <div class="cp-media-meta">
            <span title="${esc(scNames.join(', ')||'')}">📺 ${esc(scLabel)}</span>
            ${kb?`<span>${kb}</span>`:''}
          </div>
          <div class="cp-media-actions">
            <button class="cp-btn ghost" onclick="window.corpMediaEdit('${m.id}')">Edit</button>
            <button class="cp-btn ghost" style="color:#dc2626;border-color:#fca5a5" onclick="window.corpMediaDelete('${m.id}')">Delete</button>
          </div>
        </div>
      </div>
    `;
  }

  async function renderSchedule(root){
    root.innerHTML = `<div style="text-align:center;padding:40px;color:#64748b">Loading schedule…</div>`;
    try{
      const [media, screens] = await Promise.all([
        window.Auth.api.raw('/corporate/media',{credentials:'include'}).then(r=>r.json()),
        window.Auth.api.raw('/corporate/screens',{credentials:'include'}).then(r=>r.json()),
      ]);
      state.screens = screens;
      state.media = media;
      if(media.length === 0){
        root.innerHTML = `<div class="cp-empty">
          <h3>No content to schedule yet</h3>
          <p>Upload your first image or video in the <a href="#" onclick="event.preventDefault();window.corpGo('content')" style="color:#6366f1;font-weight:700">My Content</a> tab, then come back to set when it should show.</p>
        </div>`;
        return;
      }
      root.innerHTML = `
        <div class="cp-section-title">
          <div><h2>Content Schedule</h2><p>Choose when each piece of content plays. Days of the week and hours.</p></div>
        </div>
        <div class="cp-sched-list">${media.map(scheduleCard).join('')}</div>
      `;
    }catch(e){
      root.innerHTML = `<div class="cp-empty"><h3>Unable to load schedule</h3><p>${esc(e.message||'Unknown error')}</p></div>`;
    }
  }

  const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

  function scheduleCard(m){
    const s = m.schedule || {enabled:true, days:[0,1,2,3,4,5,6], start_time:'00:00', end_time:'23:59', priority:1};
    const dayBtns = DAYS.map((d, i) => {
      const on = (s.days||[]).includes(i);
      return `<button class="cp-day ${on?'on':''}" onclick="window.corpToggleDay('${m.id}',${i})">${d}</button>`;
    }).join('');
    const isVideo = m.kind === 'video';
    return `
      <div class="cp-sched-card" data-media-id="${m.id}">
        <div class="cp-sched-thumb">
          ${isVideo
            ? `<video muted playsinline src="${m.data_url}"></video>`
            : `<img src="${m.data_url}" alt="${esc(m.name)}">`}
        </div>
        <div class="cp-sched-info">
          <div class="cp-sched-name">${esc(m.name)}</div>
          <div class="cp-sched-kind">${isVideo?'🎬 Video':'🖼 Image'} · ${m.status==='paused'?'⏸ Paused':'▶ Active'}</div>
          <div class="cp-days" style="margin-top:10px">${dayBtns}</div>
          <div class="cp-times">
            <label>From</label>
            <input type="time" value="${esc(s.start_time||'00:00')}" onchange="window.corpSchedSet('${m.id}','start_time',this.value)">
            <label>To</label>
            <input type="time" value="${esc(s.end_time||'23:59')}" onchange="window.corpSchedSet('${m.id}','end_time',this.value)">
            <label class="cp-toggle">
              <input type="checkbox" ${s.enabled?'checked':''} onchange="window.corpSchedSet('${m.id}','enabled',this.checked)">
              <span>Schedule enabled</span>
            </label>
          </div>
          <div class="cp-sched-status" id="ss-${m.id}"></div>
        </div>
      </div>
    `;
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

  // ---------- D.1.b — Upload / edit / delete media ----------
  function fileToDataUrl(file){
    return new Promise((resolve, reject)=>{
      const r = new FileReader();
      r.onload = ()=>resolve(r.result);
      r.onerror = ()=>reject(new Error('Failed to read file'));
      r.readAsDataURL(file);
    });
  }

  function screenChecklist(selectedIds){
    const scr = state.screens || [];
    if(scr.length === 0)return '<div style="color:#94a3b8;font-size:12px;padding:8px">No screens available yet.</div>';
    // Group by location
    const groups = {};
    scr.forEach(s => {
      const k = s.location_id || 'default';
      groups[k] = groups[k] || {name: s.location_name || 'Location', items: []};
      groups[k].items.push(s);
    });
    return Object.values(groups).map(g => `
      <div style="padding:4px 8px;font-size:10.5px;font-weight:800;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:4px">${esc(g.name)}</div>
      ${g.items.map(s => `
        <label>
          <input type="checkbox" name="cp-scr" value="${s.id}" ${(selectedIds||[]).includes(s.id)?'checked':''}>
          <span>${esc(s.model)} · ${s.units} unit${s.units===1?'':'s'}</span>
        </label>
      `).join('')}
    `).join('');
  }

  function openMediaModal({title, item}){
    // Common form for upload + edit. When `item` is passed, edit mode.
    const isEdit = !!item;
    // Load screens if not already loaded
    const loadScreens = async () => {
      if(state.screens)return;
      const r = await window.Auth.api.raw('/corporate/screens',{credentials:'include'});
      state.screens = await r.json();
    };

    document.querySelectorAll('.cp-modal-ov').forEach(x=>x.remove());
    const ov=document.createElement('div');
    ov.className='cp-modal-ov';
    ov.innerHTML=`
      <div class="cp-modal" style="max-width:520px">
        <h3>${title}</h3>
        <p class="sub">${isEdit?'Update name, screens or status. To change the file itself, delete this and upload again.':'Choose an image or video (max 6 MB), give it a name, and pick which screens should show it.'}</p>

        ${isEdit ? '' : `
        <div class="cp-upload-drop" id="cp-drop">
          <div class="ico"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M7 16a4 4 0 01-.88-7.9A5 5 0 0115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg></div>
          <div class="prim">Drop file here or click to browse</div>
          <div class="sec">JPG, PNG, WebP · MP4, WebM · up to 6 MB</div>
        </div>
        <input type="file" id="cp-file" accept="image/*,video/*" style="display:none">
        <div id="cp-preview-holder"></div>
        `}

        <label>Name</label>
        <input type="text" id="cp-name" placeholder="e.g. Summer promo" value="${esc((item&&item.name)||'')}">

        <label>Show on these screens</label>
        <div class="cp-screen-list" id="cp-screens-list">Loading screens…</div>

        ${isEdit ? `
        <label>Status</label>
        <select id="cp-status" style="width:100%;padding:10px 12px;border:1.5px solid #e2e8f0;border-radius:8px;font-size:14px;font-family:inherit">
          <option value="active"${item.status==='active'?' selected':''}>Active — playing</option>
          <option value="paused"${item.status==='paused'?' selected':''}>Paused — stop showing</option>
        </select>
        ` : ''}

        <div id="cp-modal-err" class="cp-err" style="display:none"></div>
        <div class="actions">
          <button class="cp-btn ghost" onclick="document.querySelector('.cp-modal-ov')?.remove()">Cancel</button>
          <button class="cp-btn primary" id="cp-modal-save">${isEdit?'Save changes':'Upload'}</button>
        </div>
      </div>
    `;
    document.body.appendChild(ov);

    // Load screens then render checklist
    loadScreens().then(()=>{
      const list = document.getElementById('cp-screens-list');
      if(list) list.innerHTML = screenChecklist(item?item.screen_ids:[]);
    }).catch(e=>{
      const list = document.getElementById('cp-screens-list');
      if(list) list.innerHTML = '<div style="color:#dc2626;font-size:12px;padding:8px">Failed to load screens: '+esc(e.message)+'</div>';
    });

    // Upload flow (only for new)
    let dataUrl = null;
    if(!isEdit){
      const drop = document.getElementById('cp-drop');
      const fileInput = document.getElementById('cp-file');
      const preview = document.getElementById('cp-preview-holder');
      drop.onclick = ()=>fileInput.click();
      drop.ondragover = e=>{e.preventDefault();drop.classList.add('hover')};
      drop.ondragleave = ()=>drop.classList.remove('hover');
      drop.ondrop = async e=>{
        e.preventDefault();drop.classList.remove('hover');
        const f = e.dataTransfer.files[0]; if(f) await handleFile(f);
      };
      fileInput.onchange = async e=>{const f=e.target.files[0]; if(f) await handleFile(f);};
      async function handleFile(f){
        if(f.size > 6*1024*1024){
          document.getElementById('cp-modal-err').textContent='File is too large. Maximum is 6 MB.';
          document.getElementById('cp-modal-err').style.display='block';
          return;
        }
        document.getElementById('cp-modal-err').style.display='none';
        try{
          dataUrl = await fileToDataUrl(f);
          const isVid = /^video\//.test(f.type);
          preview.innerHTML = `<div class="cp-upload-preview">${isVid?`<video controls muted playsinline src="${dataUrl}"></video>`:`<img src="${dataUrl}" alt="preview">`}</div>
          <div style="font-size:11.5px;color:#64748b;margin-top:6px">${esc(f.name)} · ${(f.size/1024).toFixed(0)} KB · ${esc(f.type)}</div>`;
          // Auto-fill name if empty
          const nm = document.getElementById('cp-name');
          if(nm && !nm.value) nm.value = f.name.replace(/\.[^/.]+$/,'').slice(0,60);
        }catch(err){
          document.getElementById('cp-modal-err').textContent = err.message;
          document.getElementById('cp-modal-err').style.display = 'block';
        }
      }
    }

    // Save
    document.getElementById('cp-modal-save').onclick = async () => {
      const err = document.getElementById('cp-modal-err');
      err.style.display = 'none';
      const nm = (document.getElementById('cp-name').value||'').trim();
      if(!nm){ err.textContent='Please enter a name.'; err.style.display='block'; return; }
      const selectedIds = Array.from(document.querySelectorAll('input[name="cp-scr"]:checked')).map(x=>x.value);

      const btn = document.getElementById('cp-modal-save');
      btn.disabled = true;
      const originalTxt = btn.textContent;
      btn.textContent = 'Saving…';

      try{
        if(isEdit){
          const payload = { name: nm, screen_ids: selectedIds };
          const stEl = document.getElementById('cp-status');
          if(stEl) payload.status = stEl.value;
          const r = await window.Auth.api.raw('/corporate/media/'+encodeURIComponent(item.id),{
            method:'PUT', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify(payload)
          });
          if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Failed to save')}
        }else{
          if(!dataUrl){ throw new Error('Please select a file to upload.'); }
          const r = await window.Auth.api.raw('/corporate/media',{
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({data_url: dataUrl, name: nm, screen_ids: selectedIds})
          });
          if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Failed to upload')}
        }
        document.querySelector('.cp-modal-ov')?.remove();
        renderTab(); // refresh the current tab
      }catch(e){
        err.textContent = e.message;
        err.style.display = 'block';
        btn.disabled = false;
        btn.textContent = originalTxt;
      }
    };
  }

  window.corpUploadOpen = function(){ openMediaModal({title:'Upload Content', item:null}); };
  window.corpMediaEdit = function(id){
    const item = (state.media||[]).find(m=>m.id===id);
    if(!item) return;
    openMediaModal({title:'Edit '+item.name, item});
  };
  window.corpMediaDelete = async function(id){
    const item = (state.media||[]).find(m=>m.id===id);
    if(!confirm(`Delete "${item?item.name:'this content'}"? This cannot be undone.`))return;
    try{
      const r = await window.Auth.api.raw('/corporate/media/'+encodeURIComponent(id),{method:'DELETE',credentials:'include'});
      if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Failed to delete')}
      renderTab();
    }catch(e){ alert('Failed to delete: '+e.message); }
  };

  // ---------- D.1.c — Schedule handlers ----------
  // Debounce all schedule updates by 500ms so quick toggling batches into one PUT.
  const _saveTimers = {};
  function _saveSchedule(mediaId){
    clearTimeout(_saveTimers[mediaId]);
    _saveTimers[mediaId] = setTimeout(async ()=>{
      const item = (state.media||[]).find(m=>m.id===mediaId);
      if(!item)return;
      const statusEl = document.getElementById('ss-'+mediaId);
      if(statusEl){ statusEl.textContent='Saving…'; statusEl.className='cp-sched-status'; }
      try{
        const r = await window.Auth.api.raw('/corporate/media/'+encodeURIComponent(mediaId),{
          method:'PUT', credentials:'include',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({schedule: item.schedule})
        });
        if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Failed')}
        if(statusEl){ statusEl.textContent='✓ Saved'; statusEl.className='cp-sched-status ok'; }
        setTimeout(()=>{if(statusEl && statusEl.textContent==='✓ Saved')statusEl.textContent=''},1800);
      }catch(e){
        if(statusEl){ statusEl.textContent='✗ '+e.message; statusEl.className='cp-sched-status err'; }
      }
    }, 500);
  }

  window.corpToggleDay = function(mediaId, dayIdx){
    const item = (state.media||[]).find(m=>m.id===mediaId);
    if(!item) return;
    item.schedule = item.schedule || {enabled:true, days:[], start_time:'00:00', end_time:'23:59', priority:1};
    const s = item.schedule;
    s.days = Array.isArray(s.days)?s.days.slice():[];
    const i = s.days.indexOf(dayIdx);
    if(i>=0) s.days.splice(i,1); else s.days.push(dayIdx);
    // Toggle the button UI
    const btns = document.querySelectorAll(`[data-media-id="${mediaId}"] .cp-day`);
    if(btns[dayIdx]) btns[dayIdx].classList.toggle('on');
    _saveSchedule(mediaId);
  };

  window.corpSchedSet = function(mediaId, key, value){
    const item = (state.media||[]).find(m=>m.id===mediaId);
    if(!item) return;
    item.schedule = item.schedule || {enabled:true, days:[0,1,2,3,4,5,6], start_time:'00:00', end_time:'23:59', priority:1};
    item.schedule[key] = value;
    _saveSchedule(mediaId);
  };

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

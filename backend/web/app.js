// MediAd View Dashboard v2 — Complete SPA
// AUTH v2: refresh token lives in HttpOnly cookie (server-set), access token
// lives in JS memory via window.Auth (see auth-client.js). We no longer read
// tokens from localStorage — the wrapper handles Authorization + refresh.
const API='/api';let token=null,user=null;
let wizardData={step:0,screen:null,name:'',startDate:'',endDate:'',startTime:'08:00',endTime:'22:00',duration:15,mediaId:null,mediaName:'',mediaPreview:'',mediaType:'',pricing:null};
function escapeHtml(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}

// Universal API wrapper: uses Auth.api.raw so cookies travel and 401 → silent refresh.
async function api(p,o={}){const body=o.body;const opts={method:o.method||'GET',credentials:'include',headers:{'Content-Type':'application/json',...(o.headers||{})}};if(body)opts.body=body;let r;try{r=await window.Auth.api.raw(p,opts)}catch(e){if(e?.code==='SESSION_EXPIRED'){showLogin();throw new Error('Session expired')}throw e}if(r.status===401){showLogin();throw new Error('Session expired')}if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(typeof e.detail==='string'?e.detail:(e.detail?.message||e.message||'Error'))}if(r.status===204)return null;const ct=r.headers.get('content-type')||'';return ct.includes('application/json')?r.json():r.text()}
async function doLogin(){const e=document.getElementById('in-email').value,p=document.getElementById('in-pwd').value,err=document.getElementById('login-err');err.style.display='none';try{const u=await window.Auth.login(e,p);user=u;token=null;enterApp()}catch(x){err.textContent=x.message;err.style.display='block'}}
function showLogin(){token=null;user=null;document.getElementById('view-login').classList.remove('off');document.getElementById('view-app').classList.remove('on')}
async function doLogout(){try{await window.Auth.logout()}catch(_){/* best-effort logout */}showLogin()}
window.Auth.on(evt=>{if(evt==='unauthenticated'||evt==='logout')showLogin()});
// On page load, if the refresh cookie is still valid, hydrate the session silently.
window.addEventListener('DOMContentLoaded',async function(){const ok=await window.Auth.bootstrap();if(ok){user=window.Auth.user();enterApp()}});
function enterApp(){
  // Corporate portal — business/rental clients get their own dedicated view
  if(user?.role==='corporate'){
    if(typeof window.renderCorporatePortal==='function'){
      document.getElementById('view-login').classList.add('off');
      window.renderCorporatePortal(user);
      return;
    }
  }
  document.getElementById('view-login').classList.add('off');document.getElementById('view-app').classList.add('on');
  document.getElementById('sb-name').textContent=user?.name||'User';document.getElementById('sb-email').textContent=user?.email||'';
  document.getElementById('sb-av').textContent=(user?.name||'U')[0].toUpperCase();
  // ── RBAC-aware role detection ──────────────────────────────────────────────
  const ADMIN_RBAC=['SUPER_ADMIN','MEDIAVIEW_ADMIN','SUPPORT'];
  const SS_RBAC=['SELF_SERVICE_OWNER','SELF_SERVICE_MANAGER'];
  const isAdm=ADMIN_RBAC.includes(user?.rbac_role)||user?.role==='admin'||user?.role==='superadmin';
  const isSS=SS_RBAC.includes(user?.rbac_role)||(user?.role==='customer'&&!isAdm);
  const isSA=user?.rbac_role==='SUPER_ADMIN'||user?.role==='superadmin';
  // Expose globally for other modules (self-service.js etc.)
  window._isAdmin=()=>isAdm;
  window._isSS=()=>isSS;
  window._isSA=()=>isSA;
  // Show/hide role-specific nav items + section labels
  document.querySelectorAll('[data-role-admin]').forEach(e=>e.style.display=isAdm?'':'none');
  document.querySelectorAll('[data-role-ss]').forEach(e=>e.style.display=isSS?'':'none');
  document.querySelectorAll('[data-p="superadmin"]').forEach(e=>e.style.display=isSA?'':'none');
  if(isSS&&!isAdm)go('my-org');else go('dashboard');
}
document.getElementById('in-pwd')?.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin()});
function setMobileSidebar(open){const sb=document.querySelector('.sb'),bd=document.querySelector('.sb-backdrop');if(!sb)return;sb.classList.toggle('open',open);bd?.classList.toggle('on',open);if(innerWidth<=900){sb.style.setProperty('transition','none','important');sb.getAnimations().forEach(animation=>animation.cancel());sb.style.setProperty('transform',open?'translate3d(0,0,0)':'translate3d(-100%,0,0)','important')}else{sb.style.removeProperty('transition');sb.style.removeProperty('transform')}}
window.addEventListener('resize',()=>{if(innerWidth>900)setMobileSidebar(false)});
function go(p){document.querySelectorAll('.pg').forEach(x=>x.classList.remove('on'));document.getElementById('pg-'+p)?.classList.add('on');document.querySelectorAll('.ni').forEach(n=>n.classList.remove('on'));document.querySelector(`[data-p="${p}"]`)?.classList.add('on');setMobileSidebar(false);loaders[p]?.()}
function badge(s){return`<span class="bdg bdg-${s}">${s}</span>`}
function dot(s){const m={active:'#34d399',pending:'#fbbf24',approved:'#a5b4fc',rejected:'#f87171',draft:'#94a3b8',completed:'#c4b5fd'};return m[s]||'#94a3b8'}
const SG=['linear-gradient(135deg,#2563eb,#1e40af)','linear-gradient(135deg,#ea580c,#c2410c)','linear-gradient(135deg,#0d9488,#0f766e)','linear-gradient(135deg,#7c3aed,#6d28d9)','linear-gradient(135deg,#d97706,#b45309)','linear-gradient(135deg,#db2777,#be185d)','linear-gradient(135deg,#059669,#047857)','linear-gradient(135deg,#4f46e5,#4338ca)','linear-gradient(135deg,#0891b2,#0e7490)','linear-gradient(135deg,#e11d48,#be123c)'];
// Premium stat card: label / icon / value / sub trend
function stat(label,value,sub,colorVar,iconPath,trend){
  var trendHtml='';
  if(trend){var dir=trend.dir||'up';var arrow=dir==='up'?'M5 15l7-7 7 7':dir==='down'?'M19 9l-7 7-7-7':'M5 12h14';trendHtml='<span class="st-trend '+dir+'"><svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="'+arrow+'"/></svg>'+trend.label+'</span>'}
  return '<div class="st">'+
    '<div class="st-h">'+
      '<span class="st-label">'+label+'</span>'+
      '<div class="st-icon"><svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="'+iconPath+'"/></svg></div>'+
    '</div>'+
    '<div class="st-value">'+value+'</div>'+
    '<div class="st-sub">'+sub+'</div>'+
    trendHtml+
  '</div>';
}
function actCard(l,d,c,ic,p){return`<div class="qa-card" onclick="go('${p}')"><div class="qa-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg></div><div class="qa-meta"><div class="qa-title">${l}</div><div class="qa-desc">${d}</div></div><svg width="13" height="13" fill="none" stroke="var(--ds-text-quiet)" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M9 5l7 7-7 7"/></svg></div>`}

const loaders={
  async dashboard(){
    const el=document.getElementById('pg-dashboard');
    try{
      const d=await api('/analytics/dashboard');let a=null;if(user?.role==='admin'||user?.role==='superadmin')try{a=await api('/admin/analytics')}catch(e){/* optional admin analytics */}
      const rev=a?.total_revenue||d.total_spent||0,scr=a?.active_screens||d.active_campaigns||0,camp=a?.total_campaigns||d.total_campaigns||0,pend=a?.pending_campaigns||d.pending_campaigns||0;
      const screens=await api('/screens');
      const recentCamps=a?.recent_campaigns||d.recent_campaigns||[];
      const now=new Date();const hour=now.getHours();
      const greet=hour<12?'Good morning':hour<18?'Good afternoon':'Good evening';
      const today=now.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'});
      el.innerHTML=`
        <div class="welcome-banner fade">
          <div class="greeting">${greet} · ${today}</div>
          <h1>Welcome back, ${user?.name?.split(' ')[0]||'there'}</h1>
          <p>Here's what's happening across your digital signage network today.</p>
        </div>

        <div class="st-grid">
          ${stat('Total Revenue','$'+Number(rev).toLocaleString(),'All-time earnings','--cyan','M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z',{dir:'up',label:'12%'})}
          ${stat('Active Screens',scr,'Currently broadcasting','--green-l','M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',{dir:'up',label:scr>0?'Online':'—'})}
          ${stat('Total Campaigns',camp,'Created campaigns','--brand-l','M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z',{dir:'flat',label:'Live'})}
          ${stat('Pending Approval',pend,pend>0?'Awaiting review':'All clear','--amber-l','M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',pend>0?{dir:'down',label:'Action'}:{dir:'up',label:'Done'})}
        </div>

        <div style="display:grid;grid-template-columns:5fr 4fr 3fr;gap:20px;margin-bottom:24px">
          <div>
            <div class="sh"><h2>Recent Campaigns</h2><a class="sh-link" onclick="go('campaigns')">View all <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M9 5l7 7-7 7"/></svg></a></div>
            <div class="card">
              ${recentCamps.length===0?'<div style="padding:48px;text-align:center"><div style="font-size:13px;color:var(--t-4);margin-bottom:6px">No campaigns yet</div><div style="font-size:11px;color:var(--t-5)">Launch your first campaign to get started</div></div>':
                recentCamps.slice(0,6).map(c=>`<div class="lr" onclick="go('campaigns')"><div class="dot" style="background:${dot(c.status)};color:${dot(c.status)}"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--t-1)">${c.name}</div><div style="font-size:11px;color:var(--t-4);margin-top:2px">${c.user_name||c.screen_name||''}${c.schedule?.start_date?' · '+c.schedule.start_date:''}</div></div>${badge(c.status)}</div>`).join('')}
            </div>
          </div>
          <div>
            <div class="sh"><h2>Active Screens</h2><a class="sh-link" onclick="go('screens')">Browse <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M9 5l7 7-7 7"/></svg></a></div>
            <div class="card">
              ${screens.length===0?'<div style="padding:48px;text-align:center;color:var(--t-4);font-size:13px">No screens available</div>':
                screens.slice(0,6).map(s=>`<div class="lr" onclick="go('screens')"><div class="dot" style="background:#34d399;color:#34d399"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--t-1)">${s.name}</div><div style="font-size:11px;color:var(--t-4);margin-top:2px">${s.location?.city||''}${s.location?.state?', '+s.location.state:''}</div></div><div style="font-size:14px;font-weight:700;color:var(--cyan);font-variant-numeric:tabular-nums">$${s.pricing?.per_hour||0}<span style="font-size:10px;color:var(--t-4);font-weight:400">/hr</span></div></div>`).join('')}
            </div>
          </div>
          <div>
            <div class="sh"><h2>Quick Actions</h2></div>
            <div style="display:flex;flex-direction:column;gap:8px">
              ${actCard('Launch Campaign','Start advertising','#6366f1','M13 10V3L4 14h7v7l9-11h-7z','create')}
              ${actCard('Browse Marketplace','Explore screens','#22d3ee','M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z','screens')}
              ${actCard('Create Menu','Restaurant menus','#10b981','M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253','menus')}
              ${actCard('View Analytics','Performance data','#a78bfa','M3 3v18h18M7 14l3-3 4 4 5-6','analytics')}
              ${user?.role==='admin'||user?.role==='superadmin'?actCard('Manage Devices','Connected players','#f59e0b','M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z','devices'):''}
            </div>
          </div>
        </div>

        <div>
          <div class="sh"><h2>Proof of Play <span style="font-size:11px;color:var(--t-4);font-weight:500;margin-left:6px">Last 7 days</span></h2></div>
          <div id="proof-of-play" class="card" style="padding:24px"><p style="color:var(--t-4);font-size:13px;text-align:center">Loading play logs…</p></div>
        </div>`;
      loadProofOfPlay();
    }catch(e){el.innerHTML=`<div class="empty"><div class="empty-ico"><svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.74-2.97l-6.93-12a2 2 0 00-3.48 0l-6.93 12A2 2 0 005.07 19z"/></svg></div><h3>Unable to load dashboard</h3><p>${e.message}</p></div>`}
  },

  async screens(){const el=document.getElementById('pg-screens');try{const d=await api('/screens');el.innerHTML=`<div class="ph"><div><h1>Screens Marketplace</h1><p>${d.length} LED displays available to advertise on</p></div></div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px">${d.map((s,i)=>`<div class="sc card-i"><div class="hd" style="background:${SG[i%SG.length]}"><div class="city">${s.location?.city||''}${s.location?.state?', '+s.location.state:''}</div></div><div class="ct"><div class="nm">${s.name}</div><div class="ad">${s.location?.address||''}</div><div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11px;color:var(--t-4)">${s.specs?.size||''} · ${s.specs?.resolution||''}</span><div class="pr">$${s.pricing?.per_hour||0}<span>/hr</span></div></div></div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  async campaigns(){const el=document.getElementById('pg-campaigns');try{const isA=user?.role==='admin'||user?.role==='superadmin';const d=isA?await api('/admin/campaigns'):await api('/campaigns');el.innerHTML=`<div class="ph"><div><h1>Campaigns</h1><p>${d.length} ${d.length===1?'campaign':'campaigns'} total</p></div><button class="btn-p" onclick="go('create')"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 5v14m7-7H5"/></svg>New Campaign</button></div><div style="display:flex;flex-direction:column;gap:8px">${d.length===0?'<div class="empty"><div class="empty-ico"><svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6"/></svg></div><h3>No campaigns yet</h3><p>Launch your first advertising campaign to start reaching audiences</p><button class="btn-p" onclick="go(\'create\')">+ Create Campaign</button></div>':d.map(c=>`<div class="card card-i" style="display:flex;align-items:center;gap:14px;padding:18px;cursor:pointer"><div style="width:4px;align-self:stretch;border-radius:3px;background:${dot(c.status)};flex-shrink:0"></div><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700;color:var(--t-1)">${c.name}</div><div style="font-size:12px;color:var(--t-4);margin-top:3px">${c.user?.name||c.screen?.name||''}${c.schedule?.start_date?' · '+c.schedule.start_date+' → '+(c.schedule.end_date||''):''}</div></div>${badge(c.status)}<div style="font-size:20px;font-weight:800;color:var(--cyan);min-width:110px;text-align:right;font-variant-numeric:tabular-nums">$${(c.pricing?.total||0).toLocaleString()}</div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  async payments(){const el=document.getElementById('pg-payments');try{const d=user?.role==='admin'?await api('/admin/payments'):await api('/payments');const total=d.reduce((s,p)=>s+(p.amount||0),0);el.innerHTML=`<div class="ph"><div><h1>Payments</h1><p>${d.length} ${d.length===1?'transaction':'transactions'} · $${total.toLocaleString()} total</p></div></div><div style="display:flex;flex-direction:column;gap:8px">${d.length===0?'<div class="empty"><div class="empty-ico"><svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div><h3>No payments yet</h3><p>Payment transactions will appear here once campaigns are submitted</p></div>':d.map(p=>`<div class="card" style="display:flex;align-items:center;gap:14px;padding:18px"><div style="width:44px;height:44px;border-radius:12px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center;flex-shrink:0;border:1px solid rgba(99,102,241,.18)"><svg width="20" height="20" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700;color:var(--t-1)">${p.campaign_name||'Campaign'}</div><div style="font-size:12px;color:var(--t-4);margin-top:2px">${p.user_name?p.user_name+' · ':''}${p.invoice_number||''}${p.screen_name?' · '+p.screen_name:''}</div></div><span class="bdg bdg-${p.status==='completed'?'active':'pending'}">${p.status}</span><div style="font-size:22px;font-weight:800;min-width:120px;text-align:right;font-variant-numeric:tabular-nums;color:var(--t-1)">$${(p.amount||0).toLocaleString()}</div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  // Campaign Creation Wizard
  async create(){
    const el=document.getElementById('pg-create');
    if(wizardData.step===0){
      const screens=await api('/screens');
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Create Campaign</h1>
        <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">Launch a new advertising campaign</p>
        <div class="wz-steps">
          <div class="wz-s on"><div class="n">1</div>Screen</div><div class="wz-c"></div>
          <div class="wz-s"><div class="n">2</div>Schedule</div><div class="wz-c"></div>
          <div class="wz-s"><div class="n">3</div>Media</div><div class="wz-c"></div>
          <div class="wz-s"><div class="n">4</div>Review</div>
        </div>
        <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Select a Screen</h2>
        <div class="sel-grid">${screens.map((s,i)=>`
          <div class="sel-opt ${wizardData.screen?.id===s.id?'selected':''}" onclick="selectScreen(${JSON.stringify(s).replace(/"/g,'&quot;')})">
            <div style="display:flex;gap:12px;align-items:center">
              <div style="width:48px;height:48px;border-radius:12px;background:${SG[i%SG.length]};flex-shrink:0"></div>
              <div><div style="font-size:14px;font-weight:700">${s.name}</div><div style="font-size:11px;color:var(--t-4)">${s.location?.city} · $${s.pricing?.per_hour}/hr</div></div>
            </div>
          </div>`).join('')}</div>
        <div style="display:flex;justify-content:flex-end;margin-top:24px">
          <button class="btn-p" onclick="wizardNext()" ${!wizardData.screen?'disabled style="opacity:.4"':''}>Next: Schedule →</button>
        </div>`;
    } else if(wizardData.step===1){
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Create Campaign</h1>
        <div class="wz-steps">
          <div class="wz-s ok"><div class="n">✓</div>Screen</div><div class="wz-c ok"></div>
          <div class="wz-s on"><div class="n">2</div>Schedule</div><div class="wz-c"></div>
          <div class="wz-s"><div class="n">3</div>Media</div><div class="wz-c"></div>
          <div class="wz-s"><div class="n">4</div>Review</div>
        </div>
        <div style="max-width:600px">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Campaign Details</h2>
          <div style="margin-bottom:16px"><label class="inp-label">Campaign Name</label><input class="inp" id="wz-name" value="${wizardData.name}" placeholder="e.g. Summer Sale Promo"></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label class="inp-label">Start Date</label><input class="inp" id="wz-sd" type="date" value="${wizardData.startDate}"></div>
            <div><label class="inp-label">End Date</label><input class="inp" id="wz-ed" type="date" value="${wizardData.endDate}"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label class="inp-label">Start Time</label><select class="inp" id="wz-st">${['06:00','08:00','10:00','12:00','14:00','16:00','18:00','20:00','22:00'].map(t=>`<option value="${t}" ${wizardData.startTime===t?'selected':''}>${t}</option>`).join('')}</select></div>
            <div><label class="inp-label">End Time</label><select class="inp" id="wz-et">${['06:00','08:00','10:00','12:00','14:00','16:00','18:00','20:00','22:00'].map(t=>`<option value="${t}" ${wizardData.endTime===t?'selected':''}>${t}</option>`).join('')}</select></div>
          </div>
          <label class="inp-label">Slot Duration</label>
          <div style="display:flex;gap:8px;margin-bottom:20px">${[10,15,30].map(d=>`<button onclick="wizardData.duration=${d};loaders.create()" style="flex:1;padding:12px;border-radius:var(--radius-sm);border:2px solid ${wizardData.duration===d?'var(--brand)':'var(--border)'};background:${wizardData.duration===d?'rgba(99,102,241,.08)':'var(--bg-2)'};color:${wizardData.duration===d?'var(--brand-l)':'var(--t-3)'};font-size:16px;font-weight:700;cursor:pointer">${d}s</button>`).join('')}</div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=0;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button class="btn-p" onclick="wizardNext()">Next: Media →</button>
          </div>
        </div>`;
    } else if(wizardData.step===2){
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Create Campaign</h1>
        <div class="wz-steps">
          <div class="wz-s ok"><div class="n">✓</div>Screen</div><div class="wz-c ok"></div>
          <div class="wz-s ok"><div class="n">✓</div>Schedule</div><div class="wz-c ok"></div>
          <div class="wz-s on"><div class="n">3</div>Media</div><div class="wz-c"></div>
          <div class="wz-s"><div class="n">4</div>Review</div>
        </div>
        <div style="max-width:600px">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Upload Media</h2>
          ${wizardData.mediaId?`
          <div id="wz-media-area" data-testid="campaign-media-selected" style="border:2px solid rgba(52,211,153,.35);background:rgba(52,211,153,.04);border-radius:var(--radius);padding:12px;cursor:pointer" onclick="document.getElementById('wz-file').click()">
            <img data-testid="campaign-media-preview" src="${wizardData.mediaPreview}" alt="Selected creative" style="display:block;width:100%;max-height:300px;object-fit:contain;background:#020617;border-radius:10px;margin-bottom:12px">
            <div style="display:flex;align-items:center;gap:10px;padding:4px 6px">
              <svg width="20" height="20" fill="none" stroke="var(--green)" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
              <div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:700;color:var(--green);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(wizardData.mediaName)}</div><div style="font-size:11px;color:var(--t-4);margin-top:2px">Upload complete · Click image to replace</div></div>
              <button data-testid="campaign-media-remove" type="button" onclick="clearWizardMedia(event)" style="padding:6px 10px;border-radius:7px;background:rgba(248,113,113,.1);color:var(--red);border:none;font-size:11px;font-weight:700;cursor:pointer">Remove</button>
            </div>
          </div>`:`
          <div id="wz-media-area" data-testid="campaign-media-dropzone" style="border:2px dashed var(--border);border-radius:var(--radius);padding:48px;text-align:center;cursor:pointer" onclick="document.getElementById('wz-file').click()">
            <svg width="48" height="48" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
            <p style="color:var(--t-2);font-weight:600">Click to upload image</p>
            <p style="color:var(--t-4);font-size:12px;margin-top:4px">JPG, PNG, WebP or GIF · Maximum 20 MB</p>
          </div>`}
          <input data-testid="campaign-media-file-input" type="file" id="wz-file" accept=".jpg,.jpeg,.png,.webp,.gif,image/jpeg,image/png,image/webp,image/gif" style="display:none" onchange="uploadMedia(this)">
          <div data-testid="campaign-media-status" id="wz-media-status" style="margin-top:12px">${wizardData.mediaId?'<p style="color:var(--green);font-size:12px;font-weight:600">Image ready. Continue to Review.</p>':''}</div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=1;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button data-testid="campaign-media-next" class="btn-p" onclick="wizardNext()" ${!wizardData.mediaId?'disabled style="opacity:.4"':''}>Next: Review →</button>
          </div>
        </div>`;
    } else if(wizardData.step===3){
      let pricing=null;
      try{pricing=await api('/screens/'+wizardData.screen.id+'/calculate-price',{method:'POST',body:JSON.stringify({start_date:wizardData.startDate,end_date:wizardData.endDate,start_time:wizardData.startTime,end_time:wizardData.endTime,slot_duration:wizardData.duration,frequency:5})});wizardData.pricing=pricing}catch(e){/* review still renders without pricing */}
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Create Campaign</h1>
        <div class="wz-steps">
          <div class="wz-s ok"><div class="n">✓</div>Screen</div><div class="wz-c ok"></div>
          <div class="wz-s ok"><div class="n">✓</div>Schedule</div><div class="wz-c ok"></div>
          <div class="wz-s ok"><div class="n">✓</div>Media</div><div class="wz-c ok"></div>
          <div class="wz-s on"><div class="n">4</div>Review</div>
        </div>
        <div style="max-width:600px">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Review & Confirm</h2>
          <div class="card" style="padding:20px;margin-bottom:12px"><div style="font-size:12px;color:var(--t-3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Campaign</div><div style="font-size:16px;font-weight:700">${wizardData.name}</div></div>
          <div class="card" style="padding:20px;margin-bottom:12px"><div style="font-size:12px;color:var(--t-3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Screen</div><div style="font-size:16px;font-weight:700">${wizardData.screen?.name}</div><div style="font-size:12px;color:var(--t-4)">${wizardData.screen?.location?.city}</div></div>
          <div class="card" style="padding:20px;margin-bottom:12px"><div style="font-size:12px;color:var(--t-3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Schedule</div><div style="font-size:14px">${wizardData.startDate} → ${wizardData.endDate}</div><div style="font-size:12px;color:var(--t-4)">${wizardData.startTime} - ${wizardData.endTime} · ${wizardData.duration}s slots</div></div>
          ${pricing?`<div class="prc-box"><div class="prc-r"><span style="color:var(--t-3)">${pricing.total_hours} hours × $${pricing.per_hour}/hr</span><span>$${pricing.subtotal?.toLocaleString()}</span></div><div class="prc-r"><span style="color:var(--t-3)">Tax (8%)</span><span>$${pricing.tax?.toLocaleString()}</span></div><div class="prc-t"><span>Total</span><span style="color:var(--cyan)">$${pricing.total?.toLocaleString()}</span></div></div>`:''}
          <div style="background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.15);border-radius:var(--radius-sm);padding:12px;margin-top:16px;font-size:12px;color:var(--amber)">Payment: **** **** **** 4242 (Simulated)</div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=2;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button class="btn-p" onclick="submitCampaign()" style="background:linear-gradient(135deg,#10b981,#059669);box-shadow:0 4px 14px rgba(16,185,129,.3)">✓ Pay & Submit Campaign</button>
          </div>
        </div>`;
    }
  },

  // Analytics
  async analytics(){
    const el=document.getElementById('pg-analytics');
    try{
      const d=await api('/analytics/dashboard');let a=null;if(user?.role==='admin'||user?.role==='superadmin')try{a=await api('/admin/analytics')}catch(e){/* optional admin analytics */}
      const rev=a?.total_revenue||d.total_spent||0;const monthly=a?.monthly_revenue||{};
      const months=Object.keys(monthly).sort().slice(-6);const maxVal=Math.max(...Object.values(monthly).map(Number),1);
      const activeC=a?.active_campaigns??d.active_campaigns??0;
      const pendingC=a?.pending_campaigns??d.pending_campaigns??0;
      const totalC=a?.total_campaigns??d.total_campaigns??0;
      el.innerHTML=`
        <div class="ph"><div><h1>Analytics</h1><p>Platform performance &amp; revenue insights</p></div></div>
        <div style="display:grid;grid-template-columns:2fr 1fr;gap:20px">
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:16px">Monthly Revenue</h2>
            <div class="card" style="padding:24px">
              ${months.length===0?'<p style="color:var(--t-4);text-align:center;padding:24px">No revenue data yet</p>':months.map(m=>{const v=monthly[m]||0;const pct=Math.round(v/maxVal*100);return`<div class="bar-r"><div class="bar-l">${m.substring(5)}</div><div class="bar-t"><div class="bar-f" style="width:${pct}%;background:linear-gradient(90deg,var(--brand),var(--cyan))">$${v.toLocaleString()}</div></div></div>`}).join('')}
            </div>
          </div>
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:16px">Campaign Status</h2>
            <div class="card" style="padding:24px">
              ${[{l:'Active',v:activeC,c:'var(--green)'},{l:'Pending',v:pendingC,c:'var(--amber)'},{l:'Total',v:totalC,c:'var(--brand-l)'}].map(s=>`
                <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--border)">
                  <div style="display:flex;align-items:center;gap:8px"><div style="width:8px;height:8px;border-radius:50%;background:${s.c}"></div><span style="font-size:13px;color:var(--t-2)">${s.l}</span></div>
                  <span style="font-size:18px;font-weight:800;color:${s.c}">${s.v}</span>
                </div>`).join('')}
            </div>
            <h2 style="font-size:16px;font-weight:700;margin:24px 0 16px">Summary</h2>
            <div class="card" style="padding:20px">
              <div style="font-size:32px;font-weight:800;color:var(--cyan)">$${rev.toLocaleString()}</div>
              <div style="font-size:12px;color:var(--t-4);margin-top:4px">Total Revenue</div>
            </div>
          </div>
        </div>`;
    }catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}
  },

  // Admin Panel
  async admin(){
    const el=document.getElementById('pg-admin');
    if(user?.role!=='admin'&&user?.role!=='superadmin'){el.innerHTML='<p style="color:var(--red)">Admin access required</p>';return}
    if(!window._adminTab)window._adminTab='screens';
    try{
      const screens=await api('/screens');

      // Tabs
      var tabs=[
        {id:'screens',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/></svg>',name:'Screens'},
        {id:'pending',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',name:'Pending'},
        {id:'users',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2m22 0v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',name:'Users'},
        {id:'colorlight',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',name:'LED Cloud'}
      ];

      var tabHtml='<div style="display:flex;gap:6px;margin-bottom:24px">'+tabs.map(t=>
        '<button onclick="window._adminTab=\''+t.id+'\';loaders.admin()" style="display:flex;align-items:center;gap:8px;padding:10px 20px;border-radius:10px;font-size:13px;font-weight:600;border:none;cursor:pointer;font-family:inherit;transition:all .15s;'+(window._adminTab===t.id?'background:rgba(99,102,241,.12);color:#818cf8;border:1px solid rgba(99,102,241,.2)':'background:#0f172a;color:#64748b;border:1px solid #1e293b')+'">'+t.icon+t.name+'</button>').join('')+'</div>';

      // ===== SCREENS TAB =====
      if(window._adminTab==='screens'){
        el.innerHTML='<div class="ph"><div><h1>Screens</h1><p>Manage your screens and playlists</p></div><button class="btn-p" onclick="document.getElementById(\'add-screen-form\').style.display=document.getElementById(\'add-screen-form\').style.display===\'none\'?\'block\':\'none\'">+ Add Screen</button></div>'+tabHtml+
        '<div id="add-screen-form" style="display:none;margin-bottom:16px"><div class="card" style="padding:20px"><div style="font-size:15px;font-weight:700;margin-bottom:14px">Add New Screen</div>'
        +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px"><div><div class="lbl">Screen Name</div><input class="inp" id="ns-name" placeholder="Downtown LED Display"></div><div><div class="lbl">City</div><input class="inp" id="ns-city" placeholder="New York"></div></div>'
        +'<div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px;margin-bottom:10px"><div><div class="lbl">Address</div><input class="inp" id="ns-addr" placeholder="123 Main St"></div><div><div class="lbl">State</div><input class="inp" id="ns-state" placeholder="NY"></div><div><div class="lbl">Size</div><input class="inp" id="ns-size" placeholder="20ft x 10ft"></div></div>'
        +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px"><div><div class="lbl">Price/Month ($)</div><input class="inp" id="ns-pm" type="number" placeholder="5000"></div><div><div class="lbl">Resolution</div><input class="inp" id="ns-res" value="1920x1080"></div><div><div class="lbl">Orientation</div><select class="inp" id="ns-orient"><option value="landscape">Landscape</option><option value="portrait">Portrait</option></select></div></div>'
        +'<div style="margin-bottom:14px"><div class="lbl" style="margin-bottom:8px">Screen Operation Type</div>'
        +'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">'
        +'<label id="ot-ss" onclick="selectOpType(\'SELF_SERVICE\')" style="display:flex;flex-direction:column;gap:4px;padding:12px;border:2px solid #6366F1;border-radius:10px;cursor:pointer;background:#6366F110"><span style="font-size:12px;font-weight:800;color:#6366F1">SELF SERVICE</span><span style="font-size:11px;color:#94a3b8">Client manages own screens</span><input type="radio" name="op_type" value="SELF_SERVICE" checked style="display:none"></label>'
        +'<label id="ot-pa" onclick="selectOpType(\'PUBLIC_ADVERTISING\')" style="display:flex;flex-direction:column;gap:4px;padding:12px;border:2px solid #e2e8f0;border-radius:10px;cursor:pointer;background:transparent"><span style="font-size:12px;font-weight:800;color:#64748b">PUBLIC ADS</span><span style="font-size:11px;color:#94a3b8">Advertisers buy slots via QR</span><input type="radio" name="op_type" value="PUBLIC_ADVERTISING" style="display:none"></label>'
        +'<label id="ot-mm" onclick="selectOpType(\'MEDIAVIEW_MANAGED\')" style="display:flex;flex-direction:column;gap:4px;padding:12px;border:2px solid #e2e8f0;border-radius:10px;cursor:pointer;background:transparent"><span style="font-size:12px;font-weight:800;color:#64748b">MV MANAGED</span><span style="font-size:11px;color:#94a3b8">MediaView controls content</span><input type="radio" name="op_type" value="MEDIAVIEW_MANAGED" style="display:none"></label>'
        +'</div></div>'
        +'<div style="display:flex;gap:8px"><button class="btn-p" onclick="addScreen()">Create Screen</button><button class="btn-s" onclick="document.getElementById(\'add-screen-form\').style.display=\'none\'">Cancel</button></div><p id="ns-msg" style="font-size:12px;margin-top:10px;display:none"></p></div></div>'+
        '<div style="display:flex;flex-direction:column;gap:8px">'+screens.map(s=>
          '<div class="card card-i" style="padding:16px;display:flex;align-items:center;gap:14px" onclick="showScreenPlaylist(\''+s.id+'\')">'+
            '<div style="width:56px;height:36px;border-radius:8px;background:'+(s._g||'linear-gradient(135deg,#4338ca,#818cf8)')+';flex-shrink:0"></div>'+
            '<div style="flex:1">'+
              '<div style="font-size:15px;font-weight:700">'+s.name+'</div>'+
              '<div style="font-size:11px;color:#475569">'+(s.location_code||'')+' · '+s.location?.city+' · $'+(s.pricing?.per_month||0).toLocaleString()+'/mo · '+(s.specs?.orientation==='portrait'?'↕ Portrait':'↔ Landscape')+'</div>'+
            '</div>'+
            '<div style="display:flex;gap:6px" onclick="event.stopPropagation()">'+
              '<button onclick="editAdminScreen(\''+s.id+'\')" style="padding:5px 14px;border-radius:6px;background:rgba(99,102,241,.1);color:#818cf8;font-size:11px;font-weight:600;border:none;cursor:pointer">Edit</button>'+
              '<button onclick="removeScreen(\''+s.id+'\')" style="padding:5px 14px;border-radius:6px;background:rgba(248,113,113,.1);color:#f87171;font-size:11px;font-weight:600;border:none;cursor:pointer">Remove</button>'+
            '</div>'+
            '<svg width="18" height="18" fill="none" stroke="#334155" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg>'+
          '</div>').join('')+'</div>';

      // ===== PENDING TAB =====
      }else if(window._adminTab==='pending'){
        var campaigns=await api('/admin/campaigns');
        var pending=campaigns.filter(c=>c.status==='pending');
        var others=campaigns.filter(c=>c.status!=='pending');
        
        el.innerHTML='<div class="ph"><div><h1>Pending Approvals</h1><p>'+pending.length+' campaigns waiting for review</p></div></div>'+tabHtml+
        (pending.length===0?'<div class="card" style="padding:48px;text-align:center"><svg width="40" height="40" fill="none" stroke="#22d3ee" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><div style="font-size:16px;font-weight:700;color:#22d3ee">All Clear!</div><div style="font-size:13px;color:#475569;margin-top:4px">No pending campaigns to review</div></div>':
        '<div style="display:flex;flex-direction:column;gap:12px">'+pending.map(c=>{
          var hasMedia=c.media_ids&&c.media_ids.length>0;
          var mid=hasMedia?c.media_ids[0]:'';
          return '<div class="card" style="padding:0;overflow:hidden"><div style="display:flex">'+
            (hasMedia?'<div style="width:240px;min-height:180px;background:#020617;flex-shrink:0;cursor:pointer;position:relative" onclick="openReview(\''+c.id+'\',\''+mid+'\',\'m\',\''+c.name.replace(/'/g,'')+'\',\''+(c.user?.name||'').replace(/'/g,'')+'\',\''+c.status+'\')"><img src="/api/player/media/'+mid+'" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display=\'none\'"><div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.3);opacity:0;transition:opacity .2s" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0"><div style="background:rgba(255,255,255,.9);padding:8px 20px;border-radius:8px;font-size:13px;font-weight:700;color:#000">View Full Size</div></div></div>':
            '<div style="width:240px;min-height:180px;background:#020617;flex-shrink:0;display:flex;align-items:center;justify-content:center"><span style="color:#334155">No media</span></div>')+
            '<div style="flex:1;padding:20px;display:flex;flex-direction:column">'+
              '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><span style="font-size:18px;font-weight:700">'+c.name+'</span>'+badge(c.status)+'</div>'+
              '<div style="font-size:13px;color:#64748b;margin-bottom:4px">Client: <span style="color:#e2e8f0;font-weight:600">'+(c.user?.name||'Unknown')+'</span></div>'+
              '<div style="font-size:13px;color:#64748b;margin-bottom:4px">Screen: <span style="color:#e2e8f0">'+(c.screen?.name||'Unknown')+'</span></div>'+
              '<div style="font-size:13px;color:#64748b;margin-bottom:4px">Dates: '+(c.schedule?.start_date||'')+' → '+(c.schedule?.end_date||'')+'</div>'+
              '<div style="font-size:18px;font-weight:800;color:#22d3ee;margin-bottom:12px">$'+(c.pricing?.total||0).toLocaleString()+'</div>'+
              '<div style="margin-top:auto;display:flex;flex-direction:column;gap:8px">'+
                '<div><div style="font-size:10px;font-weight:600;color:#475569;margin-bottom:4px">REJECT REASON (optional)</div><input class="inp" id="reject-'+c.id+'" placeholder="Tell the client why..." style="font-size:12px;padding:8px 12px"></div>'+
                '<div style="display:flex;gap:8px">'+
                  '<button onclick="modalApprove(\''+c.id+'\')" style="flex:1;padding:10px;border-radius:8px;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-weight:700;font-size:13px;border:none;cursor:pointer">Approve</button>'+
                  '<button onclick="rejectWithNote(\''+c.id+'\')" style="flex:1;padding:10px;border-radius:8px;background:rgba(248,113,113,.12);color:#f87171;font-weight:700;font-size:13px;border:1px solid rgba(248,113,113,.2);cursor:pointer">Reject</button>'+
                '</div>'+
              '</div>'+
            '</div></div></div>'
        }).join('')+'</div>')+
        (others.length>0?'<h2 style="font-size:15px;font-weight:700;margin:24px 0 12px;color:#64748b">Recent Campaigns ('+others.length+')</h2><div style="display:flex;flex-direction:column;gap:6px">'+others.slice(0,10).map(c=>
          '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:#0f172a;border-radius:8px;border:1px solid #1e293b"><div class="dot" style="background:'+dot(c.status)+'"></div><div style="flex:1;font-size:13px;font-weight:600">'+c.name+'</div><span style="font-size:11px;color:#475569">'+(c.user?.name||'')+'</span>'+badge(c.status)+'<span style="font-size:13px;font-weight:700;color:#22d3ee">$'+(c.pricing?.total||0).toLocaleString()+'</span></div>'
        ).join('')+'</div>':'');

      // ===== USERS TAB =====
      }else if(window._adminTab==='users'){
        var users2=await api('/admin/users');
        el.innerHTML='<div class="ph"><div><h1>Users</h1><p>'+users2.length+' registered accounts</p></div></div>'+tabHtml+
        '<div class="card"><div class="tbl-h" style="grid-template-columns:2fr 2fr 1fr auto"><span>Name</span><span>Email</span><span>Company</span><span>Status</span></div>'+
        users2.map(u=>'<div class="tbl-r" style="grid-template-columns:2fr 2fr 1fr auto"><div><div style="font-size:14px;font-weight:600">'+u.name+'</div><div style="font-size:10px;color:#475569">'+u.role+'</div></div><span style="font-size:13px;color:#94a3b8">'+u.email+'</span><span style="font-size:13px;color:#475569">'+(u.company_name||'—')+'</span><span class="'+(u.active!==false?'tag-on':'tag-off')+'">'+(u.active!==false?'Active':'Disabled')+'</span></div>').join('')+'</div>';
      }else if(window._adminTab==='colorlight'){
        el.innerHTML='<div class="ph"><div><h1>LED Cloud</h1><p>Direct push to ColorlightCloud LED screens</p></div></div>'+tabHtml+
          '<div id="cl-panel"><div style="padding:60px;text-align:center;color:var(--t-4)">Loading ColorlightCloud…</div></div>';
        loadColorlightPanel();
      }
    }catch(e){el.innerHTML='<p style="color:var(--red)">'+e.message+'</p>'}
  },

  screenPlaylist: null,


  async superadmin(){
    const el=document.getElementById('pg-superadmin');
    if(user?.role!=='superadmin'){el.innerHTML='<p style="color:var(--red);padding:40px">Super Admin access required</p>';return}
    try{
      const [overview,admins]=await Promise.all([api('/superadmin/overview'),api('/superadmin/admins')]);
      el.innerHTML=`
        <div class="ph"><div><h1 style="font-size:28px;font-weight:800">Super Admin</h1><p style="color:var(--t-3)">Platform management</p></div></div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:28px">
          ${[{l:'Admins',v:overview.total_admins,c:'--brand-l'},{l:'Customers',v:overview.total_customers,c:'--cyan'},{l:'Screens',v:overview.total_screens,c:'--green'},{l:'Campaigns',v:overview.total_campaigns,c:'--amber'},{l:'Devices',v:overview.total_devices,c:'--violet'},{l:'Revenue',v:'$'+overview.total_revenue?.toLocaleString(),c:'--cyan'}].map(s=>stat(s.l,s.v,'',s.c,'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6')).join('')}
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Admin Accounts (${admins.length})</h2>
            <div class="card">${admins.length===0?'<div style="padding:32px;text-align:center;color:var(--t-4)">No admins yet</div>':admins.map((a,i)=>`
              <div class="lr" style="gap:14px">
                <div style="width:36px;height:36px;border-radius:10px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:var(--brand-l);flex-shrink:0">${(a.name||'A')[0]}</div>
                <div style="flex:1;min-width:0">
                  <div style="font-size:14px;font-weight:700">${a.name}</div>
                  <div style="font-size:11px;color:var(--t-4)">${a.email}${a.company_name?' · '+a.company_name:''}</div>
                </div>
                <span class="${a.active!==false?'tag-on':'tag-off'}">${a.active!==false?'Active':'Disabled'}</span>
                <button onclick="toggleAdmin('${a.id}')" class="btn-s" style="font-size:10px;padding:4px 10px">${a.active!==false?'Disable':'Enable'}</button>
              </div>`).join('')}</div>
          </div>
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Create New Admin</h2>
            <div class="card" style="padding:20px">
              <div style="margin-bottom:12px"><label class="inp-label">Name</label><input class="inp" id="sa-name" placeholder="Admin name" autocomplete="off"></div>
              <div style="margin-bottom:12px"><label class="inp-label">Email</label><input class="inp" id="sa-email" placeholder="admin@company.com" autocomplete="off" name="sa-new-admin-email"></div>
              <div style="margin-bottom:12px"><label class="inp-label">Password</label><input class="inp" id="sa-pwd" type="password" placeholder="Min 6 characters" autocomplete="new-password" name="sa-new-admin-password"></div>
              <div style="margin-bottom:16px"><label class="inp-label">Department / Team</label><input class="inp" id="sa-company" placeholder="e.g. Sales, Operations, Support (optional)" autocomplete="off"></div>
              <button class="btn-p" onclick="createAdmin()" style="width:100%;justify-content:center">Create Admin Account</button>
              <p id="sa-msg" style="font-size:12px;text-align:center;margin-top:12px;display:none"></p>
            </div>
          </div>
        </div>`;
    }catch(e){el.innerHTML=`<p style="color:var(--red);padding:40px">${e.message}</p>`}
  },

  async widgets(){
    const el=document.getElementById('pg-widgets');
    if(!el){return}
    try{
      const screens=await api('/screens');
      const widgets=user?.role==='admin'||user?.role==='superadmin'?await api('/admin/widgets'):[];
      const screenOpts=screens.map(s=>'<option value="'+s.id+'">'+s.name+' ('+s.location_code+')</option>').join('');
      const types=[
        {id:'weather',name:'Weather',icon:'🌤️',desc:'Live temperature',fields:'<div class="lbl">City</div><input class="inp" id="wf-v1" placeholder="New York" value="New York">'},
        {id:'clock',name:'Clock/Date',icon:'🕐',desc:'Real-time clock',fields:'<div class="lbl">Format</div><select class="inp" id="wf-v1"><option value="12h">12 Hour</option><option value="24h">24 Hour</option></select>'},
        {id:'ticker',name:'News Ticker',icon:'📰',desc:'Scrolling text',fields:'<div class="lbl">Ticker Text</div><input class="inp" id="wf-v1" placeholder="Welcome to our store!">'},
        {id:'qrcode',name:'QR Code',icon:'📱',desc:'QR for scanning',fields:'<div class="lbl">URL</div><input class="inp" id="wf-v1" placeholder="https://mediadview.com"><div class="lbl" style="margin-top:8px">Label</div><input class="inp" id="wf-v2" placeholder="Scan Me">'},
        {id:'countdown',name:'Countdown',icon:'⏳',desc:'Event timer',fields:'<div class="lbl">Target Date</div><input class="inp" type="date" id="wf-v1"><div class="lbl" style="margin-top:8px">Title</div><input class="inp" id="wf-v2" placeholder="Coming Soon">'},
        {id:'slides',name:'Google Slides',icon:'📊',desc:'Presentations',fields:'<div class="lbl">Embed URL</div><input class="inp" id="wf-v1" placeholder="https://docs.google.com/presentation/d/.../embed">'},
        {id:'youtube',name:'YouTube',icon:'▶️',desc:'YouTube videos',fields:'<div class="lbl">Video ID</div><input class="inp" id="wf-v1" placeholder="dQw4w9WgXcQ"><div style="font-size:10px;color:var(--t-4);margin-top:4px">youtube.com/watch?v=<b>THIS_PART</b></div>'},
        {id:'webpage',name:'Web Page',icon:'🌐',desc:'Any website',fields:'<div class="lbl">Website URL</div><input class="inp" id="wf-v1" placeholder="https://google.com">'},
        {id:'menu',name:'Menu',icon:'🍔',desc:'Menu with prices',fields:'<div class="lbl">Menu Title</div><input class="inp" id="wf-v1" placeholder="Today Menu"><div class="lbl" style="margin-top:8px">Items (name:price per line)</div><textarea class="inp" id="wf-v2" rows="4" placeholder="Burger:$12\nPizza:$15" style="resize:vertical"></textarea>'},
        {id:'calendar',name:'Calendar',icon:'📅',desc:'Monthly calendar',fields:''},
      ];
      window._wtypes=types;
      el.innerHTML=`<div class="ph"><div><h1>Widgets & Integrations</h1><p>Add dynamic content to your screens</p></div></div>
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px">${types.map(t=>'<div class="card card-i" style="padding:14px;text-align:center" onclick="showWF(\''+t.id+'\')"><div style="font-size:28px;margin-bottom:6px">'+t.icon+'</div><div style="font-size:13px;font-weight:700">'+t.name+'</div><div style="font-size:10px;color:var(--t-4)">'+t.desc+'</div></div>').join('')}</div>
        <div id="wf-box" style="display:none;margin-bottom:20px"><div class="card" style="padding:20px;border-color:rgba(34,211,238,.2)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><div style="display:flex;align-items:center;gap:10px"><span id="wf-icon" style="font-size:24px"></span><span id="wf-tname" style="font-size:16px;font-weight:700"></span></div><button onclick="document.getElementById('wf-box').style.display='none'" style="background:none;border:none;color:var(--t-4);font-size:16px;cursor:pointer">✕</button></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px"><div><div class="lbl">Screen</div><select class="inp" id="wf-screen">${screenOpts}</select></div><div><div class="lbl">Widget Name</div><input class="inp" id="wf-name" placeholder="My Widget"></div></div>
          <div id="wf-fields" style="margin-bottom:12px"></div>
          <button class="btn-p" onclick="submitWF()" style="width:100%;justify-content:center">Add Widget</button>
          <p id="wf-msg" style="font-size:12px;text-align:center;margin-top:8px;display:none"></p>
        </div></div>
        <h2 style="font-size:16px;font-weight:700;margin-bottom:10px">Active Widgets (${widgets.length})</h2>
        ${widgets.length===0?'<div class="card" style="padding:28px;text-align:center;color:var(--t-4)">No widgets yet. Click a widget type above to add one.</div>':
        '<div style="display:flex;flex-direction:column;gap:8px">'+widgets.map(w=>{var screen=screens.find(s=>s.id===w.screen_id);var ti=types.find(t=>t.id===w.widget_type);return'<div class="card" style="display:flex;align-items:center;gap:12px;padding:14px"><div style="font-size:24px">'+(ti?ti.icon:'📦')+'</div><div style="flex:1"><div style="font-size:14px;font-weight:700">'+w.name+'</div><div style="font-size:11px;color:var(--t-4)">'+w.widget_type+' · '+(screen?.name||'Unknown')+'</div></div><a href="/api/widgets/'+w.id+'/render" target="_blank" style="padding:4px 10px;border-radius:5px;background:rgba(34,211,238,.1);color:var(--cyan);font-size:10px;font-weight:600;text-decoration:none">Preview</a><button onclick="toggleWid(\''+w.id+'\',event)" style="padding:4px 10px;border-radius:5px;background:'+(w.enabled?'rgba(52,211,153,.1)':'rgba(248,113,113,.1)')+';color:'+(w.enabled?'var(--green)':'var(--red)')+';font-size:10px;font-weight:600;border:none;cursor:pointer">'+(w.enabled?'ON':'OFF')+'</button><button onclick="delWid(\''+w.id+'\',event)" style="padding:4px 10px;border-radius:5px;background:rgba(248,113,113,.1);color:var(--red);font-size:10px;font-weight:600;border:none;cursor:pointer">Delete</button></div>'}).join('')+'</div>'}`;
    }catch(e){el.innerHTML='<p style="color:var(--red)">'+e.message+'</p>'}
  },

  async devices(){
    const el=document.getElementById('pg-devices');
    const isAdmin=user?.role==='admin'||user?.role==='superadmin';
    try{
      const devs=isAdmin?await api('/admin/devices'):[];
      const screens=await api('/screens');
      const screenMap={};screens.forEach(s=>screenMap[s.id]=s.name);
      const screenOpts=screens.map(s=>`<option value="${s.id}">${s.name} (${s.location?.city})</option>`).join('');
      el.innerHTML=`
        <div class="ph"><div><h1>Devices</h1><p>${devs.length} registered players</p></div></div>

        <!-- Link Device + Download APK -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">
          <div class="card" style="padding:20px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
              <div style="width:36px;height:36px;border-radius:10px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center"><svg width="18" height="18" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg></div>
              <div><div style="font-size:15px;font-weight:700">Link Device by Code</div><div style="font-size:11px;color:var(--t-4)">Enter the code shown on the TV screen</div></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
              <div><label class="inp-label">Activation Code</label><input class="inp" id="dev-code" placeholder="e.g. MV7K2N" maxlength="6" style="text-transform:uppercase;letter-spacing:3px;font-weight:700;font-size:18px;text-align:center"></div>
              <div><label class="inp-label">Assign to Screen</label><select class="inp" id="dev-screen"><option value="">Select screen...</option>${screenOpts}</select></div>
            </div>
            <button class="btn-p" onclick="linkDevice()" style="width:100%;justify-content:center">Link Device to Screen</button>
            <p id="dev-msg" style="font-size:12px;text-align:center;margin-top:10px;display:none"></p>
          </div>

          <div class="card" style="padding:20px">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
              <div style="width:36px;height:36px;border-radius:10px;background:rgba(52,211,153,.1);display:flex;align-items:center;justify-content:center"><svg width="18" height="18" fill="none" stroke="var(--green)" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg></div>
              <div><div style="font-size:15px;font-weight:700">Download MediAd View Player</div><div style="font-size:11px;color:var(--t-4)">Install on Android TV, Fire TV or any Smart TV</div></div>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px">
              <div style="padding:12px;border-radius:var(--rs);background:var(--bg-1);border:1px solid var(--border);display:flex;align-items:center;gap:12px">
                <div style="width:32px;height:32px;border-radius:8px;background:rgba(52,211,153,.1);display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="16" height="16" fill="none" stroke="var(--green)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg></div>
                <div style="flex:1"><div style="font-size:13px;font-weight:600">Android TV / Google TV APK</div><div style="font-size:10px;color:var(--t-4)">For TCL, Philips, Onn, Sony TVs</div></div>
                <span class="bdg bdg-active">Ready</span>
              </div>
              <div style="padding:12px;border-radius:var(--rs);background:var(--bg-1);border:1px solid var(--border);display:flex;align-items:center;gap:12px">
                <div style="width:32px;height:32px;border-radius:8px;background:rgba(34,211,238,.1);display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="16" height="16" fill="none" stroke="var(--cyan)" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/></svg></div>
                <div style="flex:1"><div style="font-size:13px;font-weight:600">Web Player (Any Browser)</div><div style="font-size:10px;color:var(--t-4)">Works on any device with a browser</div></div>
                <a href="/api/player/${screens[0]?.id||''}/web" target="_blank" class="btn-s" style="font-size:10px;padding:4px 12px;text-decoration:none">Open</a>
              </div>
            </div>
            <div style="margin-top:12px;padding:10px;border-radius:8px;background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.12)">
              <div style="font-size:11px;color:var(--amber)">Install via ADB: <code style="background:var(--bg-3);padding:2px 6px;border-radius:4px;font-size:10px">adb install mediaview-player.apk</code></div>
            </div>
          </div>
        </div>

        <!-- Device List -->
        ${devs.length===0?'<div class="card" style="padding:40px;text-align:center"><p style="font-size:14px;color:var(--t-3)">No devices registered yet</p><p style="font-size:12px;color:var(--t-4);margin-top:4px">Install MediAd View Player on a TV — it will appear here with an activation code</p></div>':
        `<div style="display:flex;flex-direction:column;gap:10px">${devs.map(d=>{
          const isOnline=d.last_heartbeat&&(new Date()-new Date(d.last_heartbeat))<120000;
          const upH=d.diagnostics?.uptime_seconds?Math.floor(d.diagnostics.uptime_seconds/3600):0;
          const upD=Math.floor(upH/24);
          const syncAgo=d.last_sync?Math.round((new Date()-new Date(d.last_sync))/60000):null;
          return `<div class="card" style="padding:18px">
            <div style="display:flex;align-items:flex-start;gap:14px">
              <div style="width:44px;height:44px;border-radius:12px;background:${d.status==='active'?'rgba(52,211,153,.1)':d.status==='pending'?'rgba(251,191,36,.1)':'rgba(148,163,184,.1)'};display:flex;align-items:center;justify-content:center;flex-shrink:0">
                <svg width="20" height="20" fill="none" stroke="${d.status==='active'?'var(--green)':d.status==='pending'?'var(--amber)':'var(--t-3)'}" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/></svg>
              </div>
              <div style="flex:1;min-width:0">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                  <span style="font-size:15px;font-weight:700">${d.device_name||'MediAd View Player'}</span>
                  <span class="bdg bdg-${d.status}">${d.status}</span>
                  <span class="${isOnline?'tag-on':'tag-off'}" style="margin-left:4px">${isOnline?'Online':'Offline'}</span>
                </div>
                <div style="font-size:12px;color:var(--t-3);margin-bottom:8px">${d.device_info?.model||'Unknown'} · ${d.tier==='player_dedicated'?'Dedicated':'TV Direct'} · Code: <span style="color:var(--brand-l);font-weight:600">${d.activation_code}</span></div>
                <div style="display:flex;gap:8px;margin-bottom:8px">${d.screen_id?'<button onclick="openPowerSchedule(\''+d.id+'\',\''+(d.device_name||'Device').replace(/\x27/g,'')+'\',event)" style="padding:3px 10px;border-radius:5px;background:rgba(99,102,241,.12);color:var(--brand-l);font-size:10px;font-weight:600;border:1px solid rgba(99,102,241,.2);cursor:pointer;display:inline-flex;align-items:center;gap:4px"><svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M12 8v4l3 3"/><circle cx="12" cy="12" r="9"/></svg>Power Schedule</button>':''}${d.screen_id?'<button onclick="unlinkDev(\''+d.id+'\',event)" style="padding:3px 10px;border-radius:5px;background:rgba(251,191,36,.1);color:var(--amber);font-size:10px;font-weight:600;border:none;cursor:pointer">Unlink</button>':''}<button onclick="removeDev(\''+d.id+'\',event)" style="padding:3px 10px;border-radius:5px;background:rgba(248,113,113,.1);color:var(--red);font-size:10px;font-weight:600;border:none;cursor:pointer">Remove</button></div><div style="display:flex;gap:20px;flex-wrap:wrap">
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">Screen:</span> ${d.screen_name||screenMap[d.screen_id]||'Not assigned'}</div>
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">IP:</span> ${d.diagnostics?.ip_address||'—'}</div>
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">Uptime:</span> ${upD>0?upD+'d ':''}${upH%24}h</div>
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">Sync:</span> ${syncAgo!==null?(syncAgo<1?'Just now':syncAgo+'m ago'):'Never'}</div>
                  ${d.power_schedule?.enabled?'<div style="font-size:11px;color:var(--brand-l)"><span style="font-weight:600">⏰ Schedule:</span> '+d.power_schedule.power_on+' → '+d.power_schedule.power_off+'</div>':''}
                </div>
              </div>
            </div>
          </div>`}).join('')}</div>`}`;
    }catch(e){el.innerHTML=`<div class="ph"><div><h1>Devices</h1><p>Connected players</p></div></div><div class="card" style="padding:48px;text-align:center;color:var(--t-4)">Sign in as admin to manage devices</div>`}
  },

  settings(){document.getElementById('pg-settings').innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:28px">Settings</h1><div style="max-width:560px"><div style="display:flex;align-items:center;gap:16px;margin-bottom:32px"><div style="width:64px;height:64px;border-radius:16px;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:900;color:#fff;box-shadow:0 4px 15px rgba(99,102,241,.25)">${(user?.name||'U')[0]}</div><div><div style="font-size:20px;font-weight:700">${user?.name}</div><div style="font-size:13px;color:var(--t-3)">${user?.email}</div><span class="bdg" style="margin-top:6px;background:${user?.role==='admin'?'rgba(99,102,241,.12)':'rgba(52,211,153,.12)'};color:${user?.role==='admin'?'var(--brand-l)':'var(--green)'}">${user?.role==='admin'?'Administrator':'Customer'}</span></div></div><div class="card" style="margin-bottom:20px"><div style="padding:14px 20px;border-bottom:1px solid var(--border);font-size:10px;font-weight:700;color:var(--t-2);text-transform:uppercase;letter-spacing:1.5px">Account</div>${[['Name',user?.name],['Email',user?.email],[user?.role==='customer'?'Company':'Department',user?.company_name||'—'],['Role',user?.role]].map(([l,v])=>`<div style="padding:14px 20px;display:flex;justify-content:space-between;border-bottom:1px solid rgba(30,41,59,.2)"><span style="font-size:13px;color:var(--t-3)">${l}</span><span style="font-size:13px;font-weight:600">${v}</span></div>`).join('')}</div><button onclick="doLogout()" style="width:100%;padding:12px;border-radius:var(--radius-sm);background:none;border:1px solid var(--bg-3);color:var(--t-3);font-size:13px;cursor:pointer">Sign Out</button></div>`}
};

// Wizard helpers
function selectScreen(s){wizardData.screen=s;loaders.create()}
function wizardNext(){
  if(wizardData.step===1){wizardData.name=document.getElementById('wz-name')?.value||'';wizardData.startDate=document.getElementById('wz-sd')?.value||'';wizardData.endDate=document.getElementById('wz-ed')?.value||'';wizardData.startTime=document.getElementById('wz-st')?.value||'08:00';wizardData.endTime=document.getElementById('wz-et')?.value||'22:00'}
  wizardData.step++;loaders.create()
}
async function uploadMedia(input){
  const file=input.files&&input.files[0];if(!file)return;
  const st=document.getElementById('wz-media-status');
  const ext=(file.name.split('.').pop()||'').toLowerCase();
  const mimeByExt={jpg:'image/jpeg',jpeg:'image/jpeg',png:'image/png',webp:'image/webp',gif:'image/gif'};
  const contentType=file.type||mimeByExt[ext]||'application/octet-stream';
  if(!mimeByExt[ext]){st.innerHTML='<p style="color:var(--red);font-weight:600">Unsupported image. Choose JPG, PNG, WebP or GIF.</p>';input.value='';return}
  if(file.size>20*1024*1024){st.innerHTML='<p style="color:var(--red);font-weight:600">Image exceeds the 20 MB limit.</p>';input.value='';return}
  st.innerHTML=`<div style="display:flex;align-items:center;gap:10px;color:var(--brand-l);font-size:13px;font-weight:600"><span class="spin" style="width:16px;height:16px;border-width:2px"></span>Uploading ${escapeHtml(file.name)}…</div>`;
  const reader=new FileReader();
  reader.onerror=function(){st.innerHTML='<p style="color:var(--red);font-weight:600">The browser could not read this image. Try another file.</p>';input.value=''};
  reader.onabort=reader.onerror;
  reader.onload=async function(){
    const b64=String(reader.result||'').split(',')[1];
    if(!b64){reader.onerror();return}
    try{
      const r=await api('/media/upload',{method:'POST',body:JSON.stringify({filename:file.name,content_type:contentType,data:b64})});
      if(wizardData.mediaPreview)URL.revokeObjectURL(wizardData.mediaPreview);
      wizardData.mediaId=r.id;wizardData.mediaName=file.name;wizardData.mediaType=r.content_type||contentType;wizardData.mediaPreview=URL.createObjectURL(file);
      loaders.create();
    }catch(e){st.innerHTML=`<p style="color:var(--red);font-weight:600">Upload failed: ${escapeHtml(e.message)}</p>`;input.value=''}
  };
  reader.readAsDataURL(file)
}
function clearWizardMedia(e){if(e){e.preventDefault();e.stopPropagation()}if(wizardData.mediaPreview)URL.revokeObjectURL(wizardData.mediaPreview);wizardData.mediaId=null;wizardData.mediaName='';wizardData.mediaPreview='';wizardData.mediaType='';loaders.create()}
async function submitCampaign(){
  try{
    const r=await api('/campaigns',{method:'POST',body:JSON.stringify({name:wizardData.name,screen_id:wizardData.screen.id,schedule:{start_date:wizardData.startDate,end_date:wizardData.endDate,start_time:wizardData.startTime,end_time:wizardData.endTime,slot_duration:wizardData.duration,frequency:5},media_ids:wizardData.mediaId?[wizardData.mediaId]:[]})});
    await api('/payments',{method:'POST',body:JSON.stringify({campaign_id:r.id,method:'card',card_last4:'4242'})});
    if(wizardData.mediaPreview)URL.revokeObjectURL(wizardData.mediaPreview);
    wizardData={step:0,screen:null,name:'',startDate:'',endDate:'',startTime:'08:00',endTime:'22:00',duration:15,mediaId:null,mediaName:'',mediaPreview:'',mediaType:'',pricing:null};
    alert('Campaign submitted for review!');go('campaigns')
  }catch(e){alert('Error: '+e.message)}
}
function openReview(campId,mediaId,type,campName,userName,status){
  var modal=document.getElementById('modal');
  modal.style.display='flex';
  document.getElementById('modal-title').textContent=campName;
  document.getElementById('modal-sub').textContent='By: '+userName+' | Status: '+status;
  var url='/api/player/media/'+mediaId;
  document.getElementById('modal-media').innerHTML='<img src="'+url+'" style="max-width:100%;max-height:500px;object-fit:contain" onerror="this.outerHTML=\'<video src=\\\''+url+'\\\' controls autoplay muted style=\\\'max-width:100%;max-height:500px\\\' ></video>\'">';
  var h='';
  if(status==='pending'){
    h='<div style="margin-bottom:12px"><div style="font-size:11px;font-weight:600;color:#64748b;margin-bottom:6px">REJECT REASON (optional)</div><input class="inp" id="modal-reason" placeholder="Tell the client why..."></div>';
    h+='<div style="display:flex;gap:10px"><button onclick="modalApprove(\''+campId+'\');closeModal()" style="flex:1;padding:12px;border-radius:10px;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-weight:700;font-size:14px;border:none;cursor:pointer">Approve</button>';
    h+='<button onclick="modalReject(\''+campId+'\');closeModal()" style="flex:1;padding:12px;border-radius:10px;background:rgba(248,113,113,.15);color:#f87171;font-weight:700;font-size:14px;border:1px solid rgba(248,113,113,.2);cursor:pointer">Reject</button></div>';
  }else{
    h='<div style="text-align:center;padding:8px;color:#64748b;font-size:13px">Status: <span style="color:#22d3ee;font-weight:700">'+status.toUpperCase()+'</span></div>';
  }
  document.getElementById('modal-actions').innerHTML=h;
}
function closeModal(){document.getElementById('modal').style.display='none';document.getElementById('modal-media').innerHTML=''}
async function modalApprove(id){try{await api('/admin/campaigns/'+id+'/approve',{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}
async function modalReject(id){var reason=document.getElementById('modal-reason')?.value||'';try{await api('/admin/campaigns/'+id+'/reject?notes='+encodeURIComponent(reason),{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}

async function rejectWithNote(id){var reason=document.getElementById('reject-'+id)?.value||'';try{await api('/admin/campaigns/'+id+'/reject?notes='+encodeURIComponent(reason),{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}
async function rejectCamp(id,e){if(e)e.stopPropagation();if(!confirm('Reject this campaign?'))return;try{await api('/admin/campaigns/'+id+'/reject',{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}
async function approveCamp(id){try{await api('/admin/campaigns/'+id+'/approve',{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}
function selectOpType(type) {
  var types = ['SELF_SERVICE','PUBLIC_ADVERTISING','MEDIAVIEW_MANAGED'];
  var ids = {SELF_SERVICE:'ot-ss',PUBLIC_ADVERTISING:'ot-pa',MEDIAVIEW_MANAGED:'ot-mm'};
  var colors = {SELF_SERVICE:'#6366F1',PUBLIC_ADVERTISING:'#10B981',MEDIAVIEW_MANAGED:'#F59E0B'};
  types.forEach(function(t){
    var el = document.getElementById(ids[t]);
    if (!el) return;
    el.style.borderColor = t === type ? colors[t] : '#e2e8f0';
    el.style.background = t === type ? colors[t]+'18' : 'transparent';
    el.querySelector('span').style.color = t === type ? colors[t] : '#64748b';
    el.querySelector('input[type=radio]').checked = t === type;
  });
}
async function addScreen(){
  var name=document.getElementById('ns-name')?.value,city=document.getElementById('ns-city')?.value,addr=document.getElementById('ns-addr')?.value,state=document.getElementById('ns-state')?.value,size=document.getElementById('ns-size')?.value,pm=document.getElementById('ns-pm')?.value,res=document.getElementById('ns-res')?.value;
  var opType=document.querySelector('input[name="op_type"]:checked')?.value||'SELF_SERVICE';
  var msg=document.getElementById('ns-msg');msg.style.display='none';
  if(!name||!city||!pm){msg.textContent='Name, city and monthly price are required';msg.style.color='var(--red)';msg.style.display='block';return}
  try{
    await api('/admin/screens',{method:'POST',body:JSON.stringify({name:name,description:name+' in '+city,location:{city:city,address:addr||city,state:state||'',country:'US'},pricing:{per_month:parseFloat(pm)||5000,per_day:Math.round((parseFloat(pm)||5000)/30),per_hour:Math.round((parseFloat(pm)||5000)/30/14),per_slot:Math.round((parseFloat(pm)||5000)/30/14/10),currency:'USD'},specs:{size:size||'20ft x 10ft',type:'LED',resolution:res||'1920x1080',orientation:document.getElementById('ns-orient')?.value||'landscape'},status:'active',operation_type:opType})});
    msg.textContent='Screen created ('+opType.replace(/_/g,' ')+')!';msg.style.color='var(--green)';msg.style.display='block';
    setTimeout(()=>loaders.admin(),800);
  }catch(e){msg.textContent=e.message;msg.style.color='var(--red)';msg.style.display='block'}}
async function editAdminScreen(id){
  var s=null;try{s=await api('/screens/'+id)}catch(e){alert('Error');return}
  var el=document.getElementById('pg-admin');
  var orient=s.specs?.orientation||'landscape';
  el.innerHTML='<div style="max-width:700px;margin:0 auto"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px"><h1 style="font-size:24px;font-weight:800">Edit Screen</h1><button class="btn-s" onclick="loaders.admin()">Cancel</button></div>'+
  '<div style="display:flex;gap:20px;margin-bottom:20px"><div id="es-preview" style="width:200px;height:'+(orient==='portrait'?'300':'130')+'px;background:'+(s._g||'linear-gradient(135deg,#4338ca,#818cf8)')+';border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;border:2px solid #1e293b;transition:all .3s"><span style="font-size:12px;color:rgba(255,255,255,.5)">'+orient.toUpperCase()+'</span></div>'+
  '<div style="flex:1"><div class="row2" style="margin-bottom:10px"><div><div class="lbl">Screen Name</div><input class="inp" id="es-name" value="'+s.name+'"></div><div><div class="lbl">Location Code <span style="color:var(--green);font-size:8px">(auto-generated, permanent)</span></div><div style="padding:10px 12px;background:var(--bg-1);border:1px solid var(--border);border-radius:8px;font-size:16px;font-weight:700;color:var(--cyan);letter-spacing:1px">'+(s.location_code||'—')+'</div></div></div>'+
  '<div class="row2" style="margin-bottom:10px"><div><div class="lbl">City</div><input class="inp" id="es-city" value="'+(s.location?.city||'')+'"></div><div><div class="lbl">Address</div><input class="inp" id="es-addr" value="'+(s.location?.address||'')+'"></div></div>'+
  '<div class="row2" style="margin-bottom:10px"><div><div class="lbl">State</div><input class="inp" id="es-state" value="'+(s.location?.state||'')+'"></div><div><div class="lbl">Price per Month ($)</div><input class="inp" id="es-pm" type="number" value="'+(s.pricing?.per_month||0)+'"></div></div>'+
  '<div class="row2" style="margin-bottom:10px"><div><div class="lbl">Size</div><input class="inp" id="es-size" value="'+(s.specs?.size||'')+'"></div><div><div class="lbl">Resolution</div><input class="inp" id="es-res" value="'+(s.specs?.resolution||'')+'"></div></div>'+
  '<div style="margin-bottom:16px"><div class="lbl">Orientation</div><div style="display:flex;gap:8px"><button onclick="setOrientPreview(\'landscape\')" id="es-oland" style="flex:1;padding:12px;border-radius:8px;border:2px solid '+(orient==='landscape'?'var(--cyan)':'var(--border)')+';background:'+(orient==='landscape'?'rgba(34,211,238,.08)':'var(--bg-1)')+';color:'+(orient==='landscape'?'var(--cyan)':'var(--t-4)')+';font-size:13px;font-weight:600;cursor:pointer">↔ Landscape</button><button onclick="setOrientPreview(\'portrait\')" id="es-oport" style="flex:1;padding:12px;border-radius:8px;border:2px solid '+(orient==='portrait'?'var(--cyan)':'var(--border)')+';background:'+(orient==='portrait'?'rgba(34,211,238,.08)':'var(--bg-1)')+';color:'+(orient==='portrait'?'var(--cyan)':'var(--t-4)')+';font-size:13px;font-weight:600;cursor:pointer">↕ Portrait</button></div></div>'+
  '</div></div>'+
  // ===== LED/TV PAIRING CREDENTIALS — ONE unified panel (Direct Mode) =====
  // Auto-provision in the background if this screen doesn't have credentials yet.
  '<div class="card" id="pair-card-'+id+'" style="padding:20px;margin-bottom:20px;background:linear-gradient(180deg,rgba(34,211,238,.06),transparent);border:1px solid rgba(34,211,238,.25)">'+
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'+
      '<svg width="22" height="22" fill="none" stroke="var(--cyan)" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/></svg>'+
      '<div style="flex:1"><div style="font-size:14px;font-weight:700;color:var(--cyan)">Cloud Account — Paste these into the LED device</div>'+
      '<div style="font-size:11px;color:var(--t-4)">Open the A40 → Settings → Cloud account → paste URL + Device ID + Secret Key → Apply.</div></div>'+
      '<button class="btn-s" onclick="regenDirectCreds(\''+id+'\')" style="font-size:10px;padding:4px 10px;color:var(--red)" title="Generate new credentials (current device will disconnect)">↻ Regen</button>'+
    '</div>'+
    '<div id="pair-body-'+id+'" style="display:grid;grid-template-columns:1fr;gap:10px">'+
      '<div style="padding:10px;background:var(--bg-1);border-radius:8px"><div style="font-size:10px;font-weight:700;color:var(--t-3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px">1️⃣ URL</div><div style="display:flex;gap:6px;align-items:center"><input class="inp" readonly id="pair-url-'+id+'" value="" style="font-family:ui-monospace,monospace;font-size:12px;color:var(--cyan)"><button class="btn-s" onclick="copyText(this,document.getElementById(\'pair-url-'+id+'\').value)" style="padding:6px 10px">📋</button></div></div>'+
      '<div style="padding:10px;background:var(--bg-1);border-radius:8px"><div style="font-size:10px;font-weight:700;color:var(--t-3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px">2️⃣ Device ID</div><div style="display:flex;gap:6px;align-items:center"><input class="inp" readonly id="pair-did-'+id+'" value="" style="font-family:ui-monospace,monospace;font-size:14px;font-weight:700;color:var(--cyan);letter-spacing:1px"><button class="btn-s" onclick="copyText(this,document.getElementById(\'pair-did-'+id+'\').value)" style="padding:6px 10px">📋</button></div></div>'+
      '<div style="padding:10px;background:var(--bg-1);border-radius:8px"><div style="font-size:10px;font-weight:700;color:var(--t-3);text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px">3️⃣ Secret Key</div><div style="display:flex;gap:6px;align-items:center"><input class="inp" readonly id="pair-sec-'+id+'" type="password" value="" style="font-family:ui-monospace,monospace;font-size:14px;font-weight:700;color:#22d3ee"><button class="btn-s" onclick="document.getElementById(\'pair-sec-'+id+'\').type=document.getElementById(\'pair-sec-'+id+'\').type===\'password\'?\'text\':\'password\'" style="padding:6px 10px">👁</button><button class="btn-s" onclick="copyText(this,document.getElementById(\'pair-sec-'+id+'\').value)" style="padding:6px 10px">📋</button></div></div>'+
    '</div>'+
    '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px;padding-top:12px;border-top:1px solid var(--border)">'+
      '<div id="pair-status-'+id+'" style="font-size:11px;color:var(--t-4)">⏳ Loading credentials…</div>'+
      '<button class="btn-s" onclick="copyAllPairing(\''+id+'\')" style="font-size:11px;padding:5px 12px">📋 Copy All 3</button>'+
    '</div>'+
  '</div>'+
  // ===== PUBLIC MARKETPLACE (advertising for walk-in / QR customers) =====
  '<div class="card" id="adv-card-'+id+'" style="padding:20px;margin-bottom:20px;background:linear-gradient(180deg,rgba(99,102,241,.06),transparent);border:1px solid rgba(99,102,241,.25)">'+
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'+
      '<svg width="22" height="22" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path d="M3 3h18v18H3V3z"/><path d="M8 12l3 3 5-6"/></svg>'+
      '<div style="flex:1"><div style="font-size:14px;font-weight:700;color:var(--brand-l)">Public marketplace (QR / walk-in customers)</div>'+
      '<div style="font-size:11px;color:var(--t-4)">These settings drive the /portal customer catalog and the QR landing page.</div></div>'+
    '</div>'+
    // Photo
    '<div style="margin-bottom:14px"><div class="lbl">Photo of this screen (base64 stored, ~300 KB max)</div>'+
      '<div id="adv-photo-preview-'+id+'" style="width:100%;aspect-ratio:16/9;background:var(--bg-1);border:1.5px dashed var(--border);border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden;margin-bottom:8px">'+
        (s.advertising?.photo_base64 ? '<img src="'+(s.advertising.photo_base64.startsWith('data:')?s.advertising.photo_base64:'data:image/jpeg;base64,'+s.advertising.photo_base64)+'" style="width:100%;height:100%;object-fit:cover">' : '<span style="color:var(--t-4);font-size:12px">No photo — customers will see a placeholder</span>')+
      '</div>'+
      '<input type="file" id="adv-photo-file-'+id+'" accept="image/*" onchange="advPickPhoto(\''+id+'\',this)" style="display:none">'+
      '<div style="display:flex;gap:8px"><button class="btn-s" onclick="document.getElementById(\'adv-photo-file-'+id+'\').click()" style="flex:1;padding:8px;font-size:12px">📷 '+(s.advertising?.photo_base64?'Replace photo':'Upload photo')+'</button>'+
      (s.advertising?.photo_base64 ? '<button class="btn-s" onclick="advClearPhoto(\''+id+'\')" style="padding:8px 12px;font-size:12px;color:var(--red);border-color:rgba(239,68,68,.35)">Remove</button>' : '')+'</div>'+
    '</div>'+
    // Price and public toggle
    '<div class="row2" style="margin-bottom:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px">'+
      '<div><div class="lbl">Price per ad / month (USD)</div>'+
        '<input class="inp" id="adv-price-'+id+'" type="number" min="0" step="1" value="'+(s.advertising?.price_per_ad_per_month ?? '')+'" placeholder="e.g. 50">'+
        '<div style="font-size:10px;color:var(--t-4);margin-top:4px">Total = ads × months × price × (1 − scale discount)</div>'+
      '</div>'+
      '<div><div class="lbl">Show in public catalog</div>'+
        '<label style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg-1);border:1.5px solid var(--border);border-radius:8px;cursor:pointer">'+
          '<input type="checkbox" id="adv-public-'+id+'" '+((s.advertising?.is_public ?? true)?'checked':'')+' style="accent-color:var(--brand-l);width:18px;height:18px">'+
          '<span style="font-size:13px;font-weight:600" id="adv-public-lbl-'+id+'">'+((s.advertising?.is_public ?? true)?'Visible to visitors':'Hidden from catalog')+'</span>'+
        '</label>'+
        '<div style="font-size:10px;color:var(--t-4);margin-top:4px">Disable for screens rented under a corporate contract.</div>'+
      '</div>'+
    '</div>'+
    '<button class="btn-p" style="width:100%;justify-content:center;padding:12px;font-size:14px" onclick="saveAdvertising(\''+id+'\')">💾 Save marketplace settings</button>'+
    '<div id="adv-msg-'+id+'" style="font-size:12px;text-align:center;margin-top:10px;display:none"></div>'+
  '</div>'+
  '<button class="btn-p" style="width:100%;justify-content:center;padding:14px;font-size:15px" onclick="saveScreen(\''+id+'\')">Save Changes</button></div>';
  window._editOrient=orient;
  // Trigger auto-load of pairing credentials (innerHTML doesn't execute <script> tags)
  setTimeout(()=>autoLoadPairing(id, s.colorlight||{}, s.name||''), 30);
}
async function removeScreen(id){
  if(!confirm('⚠ Remove this screen?\n\nThis will permanently delete the screen and unlink any paired devices.'))return;
  try{
    await api('/admin/screens/'+id,{method:'DELETE'});
    loaders.admin();
  }catch(e){
    // If the error is about active campaigns, offer cascade delete
    if((e.message||'').toLowerCase().includes('active campaign')){
      if(confirm('⚠ This screen has active campaigns.\n\nDo you want to delete the screen AND all its campaigns?\n\nThis action is irreversible.')){
        try{
          await api('/admin/screens/'+id+'?cascade=true',{method:'DELETE'});
          loaders.admin();
          return;
        }catch(e2){alert('Cascade delete failed: '+e2.message);return}
      }
    }else{
      alert('Could not delete: '+e.message);
    }
  }
}
async function linkDevice(){
  const code=document.getElementById('dev-code')?.value,screenId=document.getElementById('dev-screen')?.value;
  const msg=document.getElementById('dev-msg');msg.style.display='none';
  if(!code||!screenId){msg.textContent='Enter activation code and select a screen';msg.style.color='var(--red)';msg.style.display='block';return}
  try{await api('/admin/devices/activate',{method:'POST',body:JSON.stringify({activation_code:code.toUpperCase(),screen_id:screenId})});
    msg.textContent='Device linked successfully!';msg.style.color='var(--green)';msg.style.display='block';
    document.getElementById('dev-code').value='';setTimeout(()=>loaders.devices(),1000);
  }catch(e){msg.textContent=e.message;msg.style.color='var(--red)';msg.style.display='block'}}
async function createAdmin(){
  const name=document.getElementById('sa-name')?.value,email=document.getElementById('sa-email')?.value,pwd=document.getElementById('sa-pwd')?.value,company=document.getElementById('sa-company')?.value;
  const msg=document.getElementById('sa-msg');msg.style.display='none';
  if(!name||!email||!pwd){msg.textContent='Fill in all required fields';msg.style.color='var(--red)';msg.style.display='block';return}
  try{await api('/superadmin/create-admin',{method:'POST',body:JSON.stringify({name,email,password:pwd,company_name:company||null})});
    msg.textContent='Admin created successfully!';msg.style.color='var(--green)';msg.style.display='block';
    document.getElementById('sa-name').value='';document.getElementById('sa-email').value='';document.getElementById('sa-pwd').value='';document.getElementById('sa-company').value='';
    setTimeout(()=>loaders.superadmin(),1000);
  }catch(e){msg.textContent=e.message;msg.style.color='var(--red)';msg.style.display='block'}}
function setOrientPreview(o){
  window._editOrient=o;
  var pv=document.getElementById('es-preview');
  pv.style.height=o==='portrait'?'300px':'130px';pv.querySelector('span').textContent=o.toUpperCase();
  document.getElementById('es-oland').style.borderColor=o==='landscape'?'var(--cyan)':'var(--border)';
  document.getElementById('es-oland').style.background=o==='landscape'?'rgba(34,211,238,.08)':'var(--bg-1)';
  document.getElementById('es-oland').style.color=o==='landscape'?'var(--cyan)':'var(--t-4)';
  document.getElementById('es-oport').style.borderColor=o==='portrait'?'var(--cyan)':'var(--border)';
  document.getElementById('es-oport').style.background=o==='portrait'?'rgba(34,211,238,.08)':'var(--bg-1)';
  document.getElementById('es-oport').style.color=o==='portrait'?'var(--cyan)':'var(--t-4)';
}

async function saveScreen(id){
  var nm=document.getElementById('es-name').value,city=document.getElementById('es-city').value,addr=document.getElementById('es-addr').value,state=document.getElementById('es-state').value,pm=document.getElementById('es-pm').value,size=document.getElementById('es-size').value,res=document.getElementById('es-res').value,orient=window._editOrient||'landscape';
  try{await api('/admin/screens/'+id,{method:'PUT',body:JSON.stringify({name:nm,location:{city:city,address:addr,state:state,country:'US'},pricing:{per_month:parseFloat(pm),per_day:Math.round(parseFloat(pm)/30),per_hour:Math.round(parseFloat(pm)/30/14),per_slot:Math.round(parseFloat(pm)/30/14/10),currency:'USD'},specs:{size:size,type:'LED',resolution:res,orientation:orient}})});loaders.admin()}catch(e){alert(e.message)}}

// ===== Public marketplace helpers (photo, price, is_public) =====
window._advPhotoData = window._advPhotoData || {};   // { screen_id: base64 dataURL }
window._advPhotoDirty = window._advPhotoDirty || {}; // { screen_id: 'set' | 'clear' }

function advPickPhoto(id, input){
  var f = input.files && input.files[0];
  if(!f) return;
  if(f.size > 5*1024*1024){ alert('Image too large. Max 5 MB.'); input.value=''; return; }
  var reader = new FileReader();
  reader.onload = function(ev){
    var dataUrl = ev.target.result;
    // Downscale big images so we don't bloat MongoDB documents.
    var img = new Image();
    img.onload = function(){
      var maxW = 1200;
      var canvas = document.createElement('canvas');
      var scale = img.width > maxW ? maxW/img.width : 1;
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      var ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      var jpeg = canvas.toDataURL('image/jpeg', 0.82);
      window._advPhotoData[id] = jpeg;
      window._advPhotoDirty[id] = 'set';
      var prev = document.getElementById('adv-photo-preview-'+id);
      if(prev) prev.innerHTML = '<img src="'+jpeg+'" style="width:100%;height:100%;object-fit:cover">';
    };
    img.onerror = function(){ alert('Could not read this image.'); };
    img.src = dataUrl;
  };
  reader.readAsDataURL(f);
}

function advClearPhoto(id){
  if(!confirm('Remove the marketplace photo for this screen?')) return;
  window._advPhotoData[id] = null;
  window._advPhotoDirty[id] = 'clear';
  var prev = document.getElementById('adv-photo-preview-'+id);
  if(prev) prev.innerHTML = '<span style="color:var(--t-4);font-size:12px">Photo will be removed on save</span>';
}

async function saveAdvertising(id){
  var priceInp = document.getElementById('adv-price-'+id);
  var pubInp   = document.getElementById('adv-public-'+id);
  var msg = document.getElementById('adv-msg-'+id);
  var body = {
    is_public: !!pubInp.checked,
  };
  if(priceInp.value !== '') body.price_per_ad_per_month = parseFloat(priceInp.value);
  if(window._advPhotoDirty[id] === 'set')   body.photo_base64 = window._advPhotoData[id];
  if(window._advPhotoDirty[id] === 'clear') body.photo_base64 = null;
  try{
    await api('/admin/screens/'+id+'/advertising', { method:'PUT', body: JSON.stringify(body) });
    msg.textContent = '✓ Marketplace settings saved';
    msg.style.color = 'var(--green)';
    msg.style.display = 'block';
    delete window._advPhotoDirty[id];
    var lbl = document.getElementById('adv-public-lbl-'+id);
    if(lbl) lbl.textContent = pubInp.checked ? 'Visible to visitors' : 'Hidden from catalog';
  }catch(e){
    msg.textContent = e.message || 'Error saving';
    msg.style.color = 'var(--red)';
    msg.style.display = 'block';
  }
}

// Keep toggle label in sync live (nicer UX).
document.addEventListener('change', function(ev){
  if(ev.target && ev.target.id && ev.target.id.indexOf('adv-public-')===0){
    var id = ev.target.id.replace('adv-public-','');
    var lbl = document.getElementById('adv-public-lbl-'+id);
    if(lbl) lbl.textContent = ev.target.checked ? 'Visible to visitors' : 'Hidden from catalog';
  }
});

async function unlinkDev(id,e){if(e)e.stopPropagation();if(!confirm('Unlink this device?'))return;try{await api('/admin/devices/'+id+'/unlink',{method:'PUT'});loaders.devices()}catch(e){alert(e.message)}}
async function removeDev(id,e){if(e)e.stopPropagation();if(!confirm('Remove device?'))return;try{await api('/admin/devices/'+id,{method:'DELETE'});loaders.devices()}catch(e){alert(e.message)}}
async function setAnim(mediaId,anim,e){if(e)e.stopPropagation();try{await api('/media/'+mediaId+'/animation?animation='+anim,{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}
async function delMedia(campId,mediaId,e){if(e)e.stopPropagation();if(!confirm('Remove from playlist?'))return;try{await api('/admin/campaigns/'+campId+'/media/'+mediaId,{method:'DELETE'});loaders.admin()}catch(e){alert(e.message)}}

async function loadProofOfPlay(){
  try{
    var d=await api('/admin/playlogs?days=7');
    var el=document.getElementById('proof-of-play');if(!el)return;
    var s=d.stats;
    el.innerHTML='<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px">'+
      '<div style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--cyan)">'+s.total_plays+'</div><div style="font-size:10px;color:var(--t-4)">Total Plays</div></div>'+
      '<div style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--green)">'+s.unique_media+'</div><div style="font-size:10px;color:var(--t-4)">Unique Media</div></div>'+
      '<div style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--brand-l)">'+s.unique_screens+'</div><div style="font-size:10px;color:var(--t-4)">Screens</div></div>'+
      '<div style="text-align:center"><div style="font-size:24px;font-weight:800;color:var(--amber)">'+s.total_play_time_minutes+'</div><div style="font-size:10px;color:var(--t-4)">Minutes Played</div></div>'+
      '</div>'+
      (d.logs.length===0?'<p style="color:var(--t-4);text-align:center;padding:12px">No play data yet. Content plays will be logged here.</p>':
      '<div style="max-height:300px;overflow-y:auto">'+d.logs.slice(0,50).map(function(l){return'<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid rgba(30,41,59,.2);font-size:12px"><span style="color:var(--green);flex-shrink:0">▶</span><span style="flex:1;color:var(--t-2)">'+l.media_name+'</span><span style="color:var(--t-4)">'+l.screen_name+'</span><span style="color:var(--t-4);flex-shrink:0">'+(l.played_at?new Date(l.played_at).toLocaleString():'')+'</span></div>'}).join('')+'</div>');
  }catch(e){var el=document.getElementById('proof-of-play');if(el)el.innerHTML='<p style="color:var(--t-4)">Login as admin to view play logs</p>'}
}

function showWF(type){
  var t=window._wtypes.find(x=>x.id===type);if(!t)return;
  document.getElementById('wf-box').style.display='block';
  document.getElementById('wf-icon').textContent=t.icon;
  document.getElementById('wf-tname').textContent=t.name;
  document.getElementById('wf-name').value=t.name+' Widget';
  document.getElementById('wf-fields').innerHTML=t.fields;
  document.getElementById('wf-msg').style.display='none';
  window._wtype=type;
  document.getElementById('wf-box').scrollIntoView({behavior:'smooth'});
}
async function submitWF(){
  var type=window._wtype,screenId=document.getElementById('wf-screen')?.value,name=document.getElementById('wf-name')?.value;
  var msg=document.getElementById('wf-msg');msg.style.display='none';
  if(!screenId||!name){msg.textContent='Select a screen and enter a name';msg.style.color='var(--red)';msg.style.display='block';return}
  var config={};var v1=document.getElementById('wf-v1')?.value||'';var v2=document.getElementById('wf-v2')?.value||'';
  if(type==='weather')config.city=v1||'New York';
  if(type==='clock')config.format=v1||'12h';
  if(type==='ticker')config.text=v1||'Welcome';
  if(type==='qrcode'){config.url=v1||'https://mediadview.com';config.label=v2||'Scan Me'}
  if(type==='countdown'){config.target_date=v1||'2026-12-31';config.title=v2||'Coming Soon'}
  if(type==='slides')config.url=v1;
  if(type==='youtube')config.video_id=v1;
  if(type==='webpage')config.url=v1||'https://google.com';
  if(type==='menu'){config.title=v1||'Menu';config.items=(v2||'Burger:$12').split('\n').map(i=>{var p=i.split(':');return{name:(p[0]||'').trim(),price:(p[1]||'').trim()}})}
  try{await api('/admin/widgets',{method:'POST',body:JSON.stringify({screen_id:screenId,widget_type:type,name:name,config:config,duration:30,enabled:true})});
    msg.textContent='Widget added!';msg.style.color='var(--green)';msg.style.display='block';
    setTimeout(()=>loaders.widgets(),800);
  }catch(e){msg.textContent=e.message;msg.style.color='var(--red)';msg.style.display='block'}
}

async function delWid(id,e){if(e)e.stopPropagation();if(!confirm('Delete widget?'))return;try{await api('/admin/widgets/'+id,{method:'DELETE'});loaders.widgets()}catch(e){alert(e.message)}}
async function toggleWid(id,e){if(e)e.stopPropagation();try{await api('/admin/widgets/'+id+'/toggle',{method:'PUT'});loaders.widgets()}catch(e){alert(e.message)}}

async function sendCmd(id,cmd,e){if(e)e.stopPropagation();try{await api('/admin/devices/'+id+'/command?command='+cmd,{method:'PUT'});alert('Command "'+cmd+'" sent!')}catch(e){alert(e.message)}}

async function toggleAdmin(id){try{await api('/superadmin/admins/'+id+'/toggle',{method:'PUT'});loaders.superadmin()}catch(e){alert(e.message)}}

async function showScreenPlaylist(screenId){
  var el=document.getElementById('pg-admin');
  try{
    var screen=await api('/screens/'+screenId);
    var playlist=await api('/player/'+screenId+'/playlist');
    var widgets=[];try{widgets=await api('/admin/widgets?screen_id='+screenId)}catch(e){/* widgets are optional */}
    var items=playlist.items||[];
    el.innerHTML='<div style="margin-bottom:20px"><button onclick="window._adminView=\'screens\';loaders.admin()" style="font-size:13px;color:#6366f1;cursor:pointer;font-weight:600;background:none;border:none;font-family:inherit;display:flex;align-items:center;gap:4px"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7"/></svg>Back to Screens</button></div>'+
    '<div style="display:flex;align-items:center;gap:16px;margin-bottom:24px"><div style="width:56px;height:38px;border-radius:8px;background:'+(screen._g||'linear-gradient(135deg,#4338ca,#818cf8)')+';flex-shrink:0"></div><div><div style="font-size:22px;font-weight:800">'+screen.name+'</div><div style="font-size:13px;color:#475569">'+(screen.location_code||'')+' · '+screen.location?.city+', '+screen.location?.state+' · $'+(screen.pricing?.per_month||0).toLocaleString()+'/mo · '+(screen.specs?.orientation==='portrait'?'↕ Portrait':'↔ Landscape')+'</div></div></div>'+
    '<h2 style="font-size:16px;font-weight:700;margin-bottom:14px">Playlist ('+items.length+' items'+(widgets.length>0?' + '+widgets.length+' widgets':'')+')</h2>'+
    (items.length===0&&widgets.length===0?'<div class="card" style="padding:32px;text-align:center;color:#475569">No content on this screen</div>':
    '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px">'+
    items.map(function(item){
      var rot=item.rotation||0;
      var anim=item.animation||'fade';
      return '<div class="card" style="padding:0;overflow:hidden">'+
        '<div style="height:140px;background:#020617;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative" onclick="openReview(\'\',\''+item.media_id+'\',\'m\',\''+item.filename.replace(/'/g,'')+'\',\'\',\'active\')">'+
          '<img src="/api/player/media/'+item.media_id+'" style="width:100%;height:100%;object-fit:cover" onerror="this.outerHTML=\'<div style=\\\'color:#334155;font-size:12px\\\'>Video</div>\'">'+
          '<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.4);opacity:0;transition:opacity .2s" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0"><div style="background:rgba(99,102,241,.9);padding:6px 14px;border-radius:6px;font-size:12px;font-weight:700;color:#fff">View</div></div>'+
        '</div>'+
        '<div style="padding:10px">'+
          '<div style="font-size:12px;font-weight:600;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+item.filename+'</div>'+
          '<div style="font-size:10px;color:#475569;margin-bottom:8px">'+item.duration+'s · '+anim+' · '+rot+'°</div>'+
          '<div style="display:flex;gap:3px;flex-wrap:wrap;margin-bottom:4px">'+
            ['none','fade','slide','zoom'].map(function(a){return '<button onclick="setAnim(\''+item.media_id+'\',\''+a+'\',event)" style="padding:2px 6px;border-radius:4px;border:1px solid '+(anim===a?'var(--green)':'#1e293b')+';background:'+(anim===a?'rgba(52,211,153,.12)':'none')+';color:'+(anim===a?'#34d399':'#475569')+';font-size:9px;font-weight:600;cursor:pointer">'+a+'</button>'}).join('')+
          '</div>'+
          '<div style="display:flex;gap:3px;flex-wrap:wrap">'+
            [0,90,180,270].map(function(deg){return '<button onclick="rotateMedia(\''+item.media_id+'\','+deg+')" style="padding:2px 6px;border-radius:4px;border:1px solid '+(rot===deg?'#22d3ee':'#1e293b')+';background:'+(rot===deg?'rgba(34,211,238,.12)':'none')+';color:'+(rot===deg?'#22d3ee':'#475569')+';font-size:9px;font-weight:600;cursor:pointer">'+deg+'°</button>'}).join('')+
            '<button onclick="delMedia(\''+item.campaign_id+'\',\''+item.media_id+'\',event)" style="padding:2px 6px;border-radius:4px;background:rgba(248,113,113,.1);color:#f87171;font-size:9px;font-weight:700;border:none;cursor:pointer;margin-left:auto">✕</button>'+
          '</div>'+
        '</div></div>'
    }).join('')+'</div>');
  }catch(e){el.innerHTML='<p style="color:var(--red)">'+e.message+'</p>'}
}

async function loadPlaylists(screens){
  var container=document.getElementById('admin-playlists');if(!container)return;
  var html='';
  for(var s of screens){
    try{
      var r=await api('/player/'+s.id+'/playlist');
      var items=r.items||[];
      html+='<div class="card" style="padding:16px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><div style="font-size:15px;font-weight:700">'+s.name+'</div><span style="font-size:12px;color:var(--cyan);font-weight:600">'+items.length+' items</span></div>';
      if(items.length===0){html+='<div style="font-size:12px;color:var(--t-4);padding:12px 0;text-align:center">No content scheduled</div>'}
      else{
        html+='<div style="display:flex;gap:10px;flex-wrap:wrap">';
        items.forEach(function(item){
          var rot=item.rotation||0;
          html+='<div style="width:200px;border-radius:10px;overflow:hidden;border:1px solid var(--border);background:var(--bg-1)">';
          html+='<div style="height:100px;overflow:hidden;background:#000;display:flex;align-items:center;justify-content:center"><img src="'+location.origin+item.media_url+'" style="width:100%;height:100%;object-fit:cover;transform:rotate('+rot+'deg)"></div>';
          html+='<div style="padding:8px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><div style="font-size:10px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1">'+item.filename+'</div><button onclick="delMedia(\''+item.campaign_id+'\',\''+item.media_id+'\',event)" style="padding:2px 8px;border-radius:4px;background:rgba(248,113,113,.15);color:var(--red);font-size:10px;font-weight:700;border:none;cursor:pointer;flex-shrink:0">✕</button></div>';
          html+='<div style="display:flex;gap:2px;flex-wrap:wrap;margin-bottom:4px">';
          ['none','fade','slide','zoom'].forEach(function(anim){
            var aActive=(item.animation||'fade')===anim;
            html+='<button onclick="setAnim(\''+item.media_id+'\',\''+anim+'\',event)" style="padding:2px 6px;border-radius:4px;border:1px solid '+(aActive?'var(--green)':'var(--border)')+';background:'+(aActive?'rgba(52,211,153,.15)':'none')+';color:'+(aActive?'var(--green)':'var(--t-4)')+';font-size:9px;font-weight:600;cursor:pointer">'+anim+'</button>';
          });
          html+='</div>';
          html+='<div style="display:flex;gap:2px;flex-wrap:wrap">';
          [0,90,180,270].forEach(function(deg){
            var active=rot===deg;
            html+='<button onclick="rotateMedia(\''+item.media_id+'\','+deg+')" style="padding:2px 7px;border-radius:4px;border:1px solid '+(active?'var(--cyan)':'var(--border)')+';background:'+(active?'rgba(34,211,238,.15)':'none')+';color:'+(active?'var(--cyan)':'var(--t-4)')+';font-size:10px;font-weight:600;cursor:pointer">'+deg+'°</button>';
          });
          html+='<span style="font-size:10px;color:var(--t-4);margin-left:auto">'+item.duration+'s</span>';
          html+='</div></div></div>';
        });
        html+='</div>';
      }
      html+='</div>';
    }catch(e){html+='<div class="card" style="padding:16px"><div style="font-size:14px;font-weight:700">'+s.name+'</div><div style="font-size:12px;color:var(--t-4)">Error</div></div>'}
  }
  container.innerHTML=html;
}

async function rotateMedia(mediaId,degrees){
  try{await api('/media/'+mediaId+'/rotate?rotation='+degrees,{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}
}

// ============ DIGITAL MENU SYSTEM ============
var currentMenu = null;

loaders.menus = async function(){
  var el=document.getElementById('pg-menus');
  try{
    var menus=await api('/menus');
    var templates=await api('/menu-templates');
    var html='<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px">';
    html+='<div><h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Digital Menus</h1>';
    html+='<p style="color:var(--t-3);font-size:14px">Create and manage restaurant menus for your screens</p></div>';
    html+='<button class="btn-p" onclick="showCreateMenu()"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14m7-7H5"/></svg>Create Menu</button>';
    html+='</div>';
    
    if(menus.length===0){
      html+='<div class="card" style="padding:60px;text-align:center">';
      html+='<svg width="48" height="48" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 16px"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>';
      html+='<h3 style="font-size:18px;font-weight:700;margin-bottom:8px">No menus yet</h3>';
      html+='<p style="color:var(--t-4);margin-bottom:20px">Create your first digital menu for your restaurant</p>';
      html+='<button class="btn-p" onclick="showCreateMenu()">+ Create Your First Menu</button>';
      html+='</div>';
    } else {
      html+='<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">';
      menus.forEach(function(m){
        var tpl=templates.find(function(t){return t.id===m.template_id})||{name:'Classic',accent_color:'#d4af37',preview_color:'#1a1a2e'};
        var catCount=m.categories?m.categories.length:0;
        var itemCount=0;
        (m.categories||[]).forEach(function(c){itemCount+=(c.items||[]).length});
        html+='<div class="card card-i" style="overflow:hidden;cursor:pointer" onclick="editMenu(\''+m.id+'\')">';
        html+='<div style="height:80px;background:'+tpl.preview_color+';display:flex;align-items:center;justify-content:center;position:relative">';
        html+='<span style="font-size:20px;font-weight:900;color:'+tpl.accent_color+';letter-spacing:2px">'+(m.restaurant_name||m.name)+'</span>';
        html+='<span class="bdg bdg-'+(m.status==='published'?'active':'pending')+'" style="position:absolute;top:8px;right:8px;font-size:9px">'+m.status+'</span>';
        html+='</div>';
        html+='<div style="padding:16px">';
        html+='<div style="font-size:15px;font-weight:700;margin-bottom:4px">'+m.name+'</div>';
        html+='<div style="font-size:12px;color:var(--t-4);margin-bottom:12px">Template: '+tpl.name+'</div>';
        html+='<div style="display:flex;gap:16px">';
        html+='<div style="font-size:11px;color:var(--t-3)"><strong style="color:var(--cyan)">'+catCount+'</strong> categories</div>';
        html+='<div style="font-size:11px;color:var(--t-3)"><strong style="color:var(--cyan)">'+itemCount+'</strong> items</div>';
        html+='</div>';
        html+='<div style="display:flex;gap:8px;margin-top:12px">';
        html+='<button class="btn-s" style="flex:1;font-size:11px" onclick="event.stopPropagation();editMenu(\''+m.id+'\')">Edit</button>';
        html+='<button class="btn-s" style="font-size:11px" onclick="event.stopPropagation();window.open(\'/api/menu-editor?id='+m.id+'\',\'_blank\')">Mobile Edit</button>';
        html+='<button class="btn-s" style="font-size:11px" onclick="event.stopPropagation();previewMenu(\''+m.id+'\')">Preview</button>';
        html+='<button style="background:none;border:1px solid var(--red);color:var(--red);padding:6px 10px;border-radius:8px;font-size:11px;cursor:pointer" onclick="event.stopPropagation();deleteMenu(\''+m.id+'\')">Delete</button>';
        html+='</div></div></div>';
      });
      html+='</div>';
    }
    el.innerHTML=html;
  }catch(e){el.innerHTML='<p style="color:var(--red)">'+e.message+'</p>'}
};

function showCreateMenu(){
  var html='<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.8);z-index:100;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)" id="menu-modal">';
  html+='<div style="width:600px;max-height:90vh;overflow-y:auto;background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:32px">';
  html+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px"><h2 style="font-size:20px;font-weight:800">Create New Menu</h2>';
  html+='<button onclick="document.getElementById(\'menu-modal\').remove()" style="background:none;border:none;color:#64748b;font-size:20px;cursor:pointer">✕</button></div>';
  
  html+='<label class="inp-label">Menu Name</label>';
  html+='<input id="new-menu-name" class="inp" placeholder="e.g. Lunch Menu, Drinks Menu" style="margin-bottom:14px">';
  
  html+='<label class="inp-label">Restaurant Name</label>';
  html+='<input id="new-menu-restaurant" class="inp" placeholder="e.g. Casa Bella, Taco House" style="margin-bottom:14px">';
  
  html+='<label class="inp-label">Subtitle (optional)</label>';
  html+='<input id="new-menu-subtitle" class="inp" placeholder="e.g. Fresh ingredients daily" style="margin-bottom:14px">';
  
  html+='<label class="inp-label">Currency Symbol</label>';
  html+='<input id="new-menu-currency" class="inp" value="$" style="margin-bottom:20px;width:80px">';
  
  html+='<label class="inp-label" style="margin-bottom:12px">Select Template</label>';
  html+='<div id="template-grid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:24px"></div>';
  
  html+='<button class="btn-p" style="width:100%;justify-content:center;padding:14px" onclick="createMenu()">Create Menu</button>';
  html+='</div></div>';
  
  document.body.insertAdjacentHTML('beforeend',html);
  
  // Load templates
  api('/menu-templates').then(function(templates){
    var grid=document.getElementById('template-grid');
    var thtml='';
    templates.forEach(function(t,i){
      thtml+='<div class="card card-i" style="padding:12px;cursor:pointer;border:2px solid '+(i===0?'var(--cyan)':'transparent')+'" onclick="selectTemplate(this,\''+t.id+'\')" data-tid="'+t.id+'">';
      thtml+='<div style="height:40px;background:'+t.preview_color+';border-radius:6px;margin-bottom:8px;display:flex;align-items:center;justify-content:center">';
      thtml+='<span style="font-size:11px;font-weight:800;color:'+t.accent_color+'">'+t.name+'</span></div>';
      thtml+='<div style="font-size:12px;font-weight:600">'+t.name+'</div>';
      thtml+='<div style="font-size:10px;color:var(--t-4)">'+t.category+'</div>';
      thtml+='</div>';
    });
    grid.innerHTML=thtml;
  });
}

var selectedTemplate='classic';
function selectTemplate(el,tid){
  selectedTemplate=tid;
  document.querySelectorAll('#template-grid .card').forEach(function(c){c.style.borderColor='transparent'});
  el.style.borderColor='var(--cyan)';
}

async function createMenu(){
  var name=document.getElementById('new-menu-name').value;
  var restaurant=document.getElementById('new-menu-restaurant').value;
  var subtitle=document.getElementById('new-menu-subtitle').value;
  var currency=document.getElementById('new-menu-currency').value;
  if(!name){alert('Enter a menu name');return}
  try{
    var m=await api('/menus',{method:'POST',body:JSON.stringify({name:name,restaurant_name:restaurant,subtitle:subtitle,currency_symbol:currency||'$',template_id:selectedTemplate})});
    window.dispatchEvent(new CustomEvent('mediaview:sources-changed',{detail:{type:'menu',id:m.id}}));
    document.getElementById('menu-modal').remove();
    editMenu(m.id);
  }catch(e){alert(e.message)}
}

async function deleteMenu(id){
  if(!confirm('Delete this menu?'))return;
  try{await api('/menus/'+id,{method:'DELETE'});window.dispatchEvent(new CustomEvent('mediaview:sources-changed',{detail:{type:'menu',id:id}}));loaders.menus()}catch(e){alert(e.message)}
}

function previewMenu(id){
  window.open(API+'/menus/'+id+'/render','_blank');
}

// ============ MENU EDITOR ============

async function editMenu(menuId){
  document.querySelectorAll('.pg').forEach(function(x){x.classList.remove('on')});
  document.getElementById('pg-menu-edit').classList.add('on');
  document.querySelectorAll('.ni').forEach(function(n){n.classList.remove('on')});
  document.querySelector('[data-p="menus"]')?.classList.add('on');
  
  try{
    var menu=await api('/menus/'+menuId);
    currentMenu=menu;
    renderMenuEditor(menu);
  }catch(e){
    document.getElementById('pg-menu-edit').innerHTML='<p style="color:var(--red)">'+e.message+'</p>';
  }
}

function renderMenuEditor(menu){
  var el=document.getElementById('pg-menu-edit');
  var html='';
  
  // Header
  html+='<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px">';
  html+='<div><button style="background:none;border:none;color:var(--cyan);font-size:13px;cursor:pointer;padding:0;margin-bottom:8px" onclick="go(\'menus\')">← Back to Menus</button>';
  html+='<h1 style="font-size:28px;font-weight:800;margin-bottom:4px">'+menu.name+'</h1>';
  html+='<p style="color:var(--t-3);font-size:14px">'+menu.restaurant_name+'</p></div>';
  html+='<div style="display:flex;gap:8px">';
  html+='<button class="btn-s" onclick="previewMenu(\''+menu.id+'\')"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>Preview</button>';
  html+='<button class="btn-p" onclick="publishMenu(\''+menu.id+'\')">Publish</button>';
  html+='</div></div>';
  
  // Two column layout
  html+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">';
  
  // Left: Categories & Items
  html+='<div>';
  html+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
  html+='<h2 style="font-size:16px;font-weight:700">Categories & Items</h2>';
  html+='<button class="btn-s" onclick="addCategory(\''+menu.id+'\')"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14m7-7H5"/></svg>Add Category</button>';
  html+='</div>';
  
  if(!menu.categories||menu.categories.length===0){
    html+='<div class="card" style="padding:40px;text-align:center;color:var(--t-4)">';
    html+='<p>No categories yet. Add your first category!</p>';
    html+='<button class="btn-p" style="margin-top:12px" onclick="addCategory(\''+menu.id+'\')">+ Add Category</button>';
    html+='</div>';
  } else {
    menu.categories.forEach(function(cat){
      html+='<div class="card" style="margin-bottom:12px;overflow:hidden">';
      // Category header
      html+='<div style="display:flex;align-items:center;gap:10px;padding:14px 16px;background:var(--brand-l)10;border-bottom:1px solid #1e293b">';
      html+='<div style="flex:1"><div style="font-size:15px;font-weight:700;color:var(--cyan)">'+cat.name+'</div>';
      if(cat.description)html+='<div style="font-size:11px;color:var(--t-4)">'+cat.description+'</div>';
      html+='</div>';
      html+='<button class="btn-s" style="font-size:10px;padding:4px 10px" onclick="addItem(\''+menu.id+'\',\''+cat.id+'\')">+ Item</button>';
      html+='<button style="background:none;border:none;color:var(--t-4);cursor:pointer;font-size:12px" onclick="editCategory(\''+menu.id+'\',\''+cat.id+'\',\''+cat.name.replace(/'/g,"\\'")+'\')" title="Edit">✏️</button>';
      html+='<button style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px" onclick="deleteCategory(\''+menu.id+'\',\''+cat.id+'\')" title="Delete">🗑️</button>';
      html+='</div>';
      
      // Items
      if(!cat.items||cat.items.length===0){
        html+='<div style="padding:20px;text-align:center;color:var(--t-4);font-size:12px">No items in this category</div>';
      } else {
        cat.items.forEach(function(item){
          html+='<div style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid #1e293b08'+(item.featured?';background:rgba(34,211,238,.03)':'')+'">';
          if(item.image){
            html+='<img src="'+item.image+'" style="width:40px;height:40px;border-radius:8px;object-fit:cover;flex-shrink:0">';
          } else {
            html+='<div style="width:40px;height:40px;border-radius:8px;background:#1e293b;display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="16" height="16" fill="none" stroke="var(--t-4)" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14"/></svg></div>';
          }
          html+='<div style="flex:1;min-width:0">';
          html+='<div style="font-size:13px;font-weight:600">'+item.name+(item.featured?' <span style="color:var(--cyan);font-size:9px">★ FEATURED</span>':'')+'</div>';
          if(item.description)html+='<div style="font-size:10px;color:var(--t-4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+item.description+'</div>';
          html+='</div>';
          html+='<div style="font-size:15px;font-weight:800;color:var(--cyan)">'+(menu.currency_symbol||'$')+parseFloat(item.price||0).toFixed(2)+'</div>';
          html+='<button style="background:none;border:none;color:var(--t-4);cursor:pointer;font-size:12px" onclick="editItem(\''+menu.id+'\',\''+cat.id+'\',\''+item.id+'\')" title="Edit">✏️</button>';
          html+='<button style="background:none;border:none;color:var(--red);cursor:pointer;font-size:12px" onclick="deleteItem(\''+menu.id+'\',\''+cat.id+'\',\''+item.id+'\')" title="Delete">🗑️</button>';
          html+='</div>';
        });
      }
      html+='</div>';
    });
  }
  html+='</div>';
  
  // Right: Menu Settings & Preview
  html+='<div>';
  html+='<h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Menu Settings</h2>';
  html+='<div class="card" style="padding:16px;margin-bottom:16px">';
  html+='<label class="inp-label">Menu Name</label>';
  html+='<input class="inp" value="'+menu.name+'" onchange="updateMenuField(\''+menu.id+'\',\'name\',this.value)" style="margin-bottom:10px">';
  html+='<label class="inp-label">Restaurant Name</label>';
  html+='<input class="inp" value="'+(menu.restaurant_name||'')+'" onchange="updateMenuField(\''+menu.id+'\',\'restaurant_name\',this.value)" style="margin-bottom:10px">';
  html+='<label class="inp-label">Subtitle</label>';
  html+='<input class="inp" value="'+(menu.subtitle||'')+'" onchange="updateMenuField(\''+menu.id+'\',\'subtitle\',this.value)" style="margin-bottom:10px">';
  html+='<label class="inp-label">Currency Symbol</label>';
  html+='<input class="inp" value="'+(menu.currency_symbol||'$')+'" onchange="updateMenuField(\''+menu.id+'\',\'currency_symbol\',this.value)" style="width:80px">';
  var mt=menu.theme||{};
  html+='<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:14px">';
  html+='<label class="inp-label">Background<input type="color" value="'+(mt.bg||'#09090b')+'" onchange="updateMenuTheme(\''+menu.id+'\',\'bg\',this.value)" style="display:block;width:100%;height:38px;margin-top:6px;border:0;background:none"></label>';
  html+='<label class="inp-label">Accent<input type="color" value="'+(mt.accent||'#eab308')+'" onchange="updateMenuTheme(\''+menu.id+'\',\'accent\',this.value)" style="display:block;width:100%;height:38px;margin-top:6px;border:0;background:none"></label>';
  html+='<label class="inp-label">Text<input type="color" value="'+(mt.text||'#ffffff')+'" onchange="updateMenuTheme(\''+menu.id+'\',\'text\',this.value)" style="display:block;width:100%;height:38px;margin-top:6px;border:0;background:none"></label></div>';
  html+='</div>';
  
  html+='<h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Live Preview</h2>';
  html+='<div style="border-radius:12px;overflow:hidden;border:1px solid #1e293b;height:400px">';
  html+='<iframe src="'+API+'/menus/'+menu.id+'/render" style="width:100%;height:100%;border:none;transform:scale(0.5);transform-origin:top left;width:200%;height:200%"></iframe>';
  html+='</div>';
  
  html+='<div style="margin-top:12px;text-align:center">';
  html+='<a href="'+API+'/menus/'+menu.id+'/render" target="_blank" style="font-size:12px;color:var(--cyan);cursor:pointer">Open full preview →</a>';
  html+='</div>';
  
  // Promo Media Section
  html+='<h2 style="font-size:16px;font-weight:700;margin-top:20px;margin-bottom:12px">Promotional Media</h2>';
  html+='<div class="card" style="padding:16px">';
  html+='<p style="font-size:11px;color:var(--t-4);margin-bottom:12px">Add videos or images that scroll at the bottom of your menu display (e.g. food preparation, promotions)</p>';
  html+='<input id="promo-file" type="file" accept="image/*,video/*" onchange="uploadPromoMedia(\''+menu.id+'\',this)" style="font-size:11px;color:var(--t-3);margin-bottom:12px">';
  
  var promos = menu.promo_media || [];
  if(promos.length > 0){
    html+='<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">';
    promos.forEach(function(pm){
      html+='<div style="position:relative;width:100px;height:70px;border-radius:8px;overflow:hidden;border:1px solid #1e293b">';
      if(pm.type==='video'){
        html+='<video src="'+(pm.data||pm.url)+'" style="width:100%;height:100%;object-fit:cover" muted></video>';
      } else {
        html+='<img src="'+(pm.data||pm.url)+'" style="width:100%;height:100%;object-fit:cover">';
      }
      html+='<button onclick="deletePromoMedia(\''+menu.id+'\',\''+pm.id+'\')" style="position:absolute;top:2px;right:2px;background:rgba(0,0,0,.7);color:var(--red);border:none;border-radius:50%;width:18px;height:18px;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center">✕</button>';
      html+='</div>';
    });
    html+='</div>';
  }
  html+='</div>';
  
  html+='</div></div>';
  
  el.innerHTML=html;
}

async function updateMenuField(menuId,field,value){
  try{
    var body={};body[field]=value;
    await api('/menus/'+menuId,{method:'PUT',body:JSON.stringify(body)});
  }catch(e){alert(e.message)}
}

async function updateMenuTheme(menuId,field,value){
  try{var menu=await api('/menus/'+menuId);var theme=menu.theme||{};theme[field]=value;await api('/menus/'+menuId,{method:'PUT',body:JSON.stringify({theme:theme})});editMenu(menuId)}catch(e){alert(e.message)}
}

async function publishMenu(menuId){
  if(typeof window.openMenuPlaylistPublish==='function')return window.openMenuPlaylistPublish(menuId);
  alert('Playlist publishing is still loading. Please try again.');
}

function addCategory(menuId){
  var name=prompt('Category name (e.g. Appetizers, Main Course, Drinks):');
  if(!name)return;
  var desc=prompt('Category description (optional):');
  api('/menus/'+menuId+'/categories',{method:'POST',body:JSON.stringify({name:name,description:desc||''})}).then(function(){editMenu(menuId)}).catch(function(e){alert(e.message)});
}

function editCategory(menuId,catId,currentName){
  var name=prompt('Category name:',currentName);
  if(!name)return;
  api('/menus/'+menuId+'/categories/'+catId,{method:'PUT',body:JSON.stringify({name:name})}).then(function(){editMenu(menuId)}).catch(function(e){alert(e.message)});
}

function deleteCategory(menuId,catId){
  if(!confirm('Delete this category and all its items?'))return;
  api('/menus/'+menuId+'/categories/'+catId,{method:'DELETE'}).then(function(){editMenu(menuId)}).catch(function(e){alert(e.message)});
}

function addItem(menuId,catId){
  var html='<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.8);z-index:100;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)" id="item-modal">';
  html+='<div style="width:500px;background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:28px">';
  html+='<div style="display:flex;justify-content:space-between;margin-bottom:20px"><h2 style="font-size:18px;font-weight:800">Add Menu Item</h2>';
  html+='<button onclick="document.getElementById(\'item-modal\').remove()" style="background:none;border:none;color:#64748b;font-size:20px;cursor:pointer">✕</button></div>';
  
  html+='<label class="inp-label">Item Name *</label>';
  html+='<input id="item-name" class="inp" placeholder="e.g. Caesar Salad" style="margin-bottom:10px">';
  
  html+='<label class="inp-label">Description</label>';
  html+='<input id="item-desc" class="inp" placeholder="e.g. Fresh romaine, parmesan, croutons" style="margin-bottom:10px">';
  
  html+='<label class="inp-label">Price *</label>';
  html+='<input id="item-price" class="inp" type="number" step="0.01" placeholder="12.99" style="margin-bottom:10px;width:150px">';
  
  html+='<label class="inp-label">Image (optional)</label>';
  html+='<input id="item-image-file" type="file" accept="image/*" onchange="previewItemImage(this)" style="margin-bottom:6px;font-size:12px;color:var(--t-3)">';
  html+='<div id="item-image-preview" style="margin-bottom:10px"></div>';
  html+='<input id="item-image-data" type="hidden">';
  
  html+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">';
  html+='<input type="checkbox" id="item-featured" style="width:16px;height:16px">';
  html+='<label for="item-featured" style="font-size:13px;color:var(--t-2)">Featured / Special</label></div>';
  
  html+='<button class="btn-p" style="width:100%;justify-content:center;padding:12px" onclick="saveItem(\''+menuId+'\',\''+catId+'\')">Add Item</button>';
  html+='</div></div>';
  
  document.body.insertAdjacentHTML('beforeend',html);
}

function previewItemImage(input){
  var preview=document.getElementById('item-image-preview');
  if(input.files&&input.files[0]){
    var reader=new FileReader();
    reader.onload=function(e){
      document.getElementById('item-image-data').value=e.target.result;
      preview.innerHTML='<img src="'+e.target.result+'" style="width:80px;height:80px;border-radius:8px;object-fit:cover">';
    };
    reader.readAsDataURL(input.files[0]);
  }
}

async function saveItem(menuId,catId){
  var name=document.getElementById('item-name').value;
  var desc=document.getElementById('item-desc').value;
  var price=parseFloat(document.getElementById('item-price').value)||0;
  var image=document.getElementById('item-image-data').value||'';
  var featured=document.getElementById('item-featured').checked;
  if(!name){alert('Enter item name');return}
  if(price<=0){alert('Enter a valid price');return}
  try{
    await api('/menus/'+menuId+'/categories/'+catId+'/items',{method:'POST',body:JSON.stringify({name:name,description:desc,price:price,image:image,featured:featured})});
    document.getElementById('item-modal').remove();
    editMenu(menuId);
  }catch(e){alert(e.message)}
}

function editItem(menuId,catId,itemId){
  // Find the item data
  var item=null;
  if(currentMenu&&currentMenu.categories){
    currentMenu.categories.forEach(function(c){
      if(c.id===catId)(c.items||[]).forEach(function(it){if(it.id===itemId)item=it});
    });
  }
  if(!item){alert('Item not found');return}
  
  var html='<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.8);z-index:100;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)" id="item-modal">';
  html+='<div style="width:500px;background:#0f172a;border:1px solid #1e293b;border-radius:16px;padding:28px">';
  html+='<div style="display:flex;justify-content:space-between;margin-bottom:20px"><h2 style="font-size:18px;font-weight:800">Edit Menu Item</h2>';
  html+='<button onclick="document.getElementById(\'item-modal\').remove()" style="background:none;border:none;color:#64748b;font-size:20px;cursor:pointer">✕</button></div>';
  
  html+='<label class="inp-label">Item Name *</label>';
  html+='<input id="item-name" class="inp" value="'+item.name+'" style="margin-bottom:10px">';
  
  html+='<label class="inp-label">Description</label>';
  html+='<input id="item-desc" class="inp" value="'+(item.description||'')+'" style="margin-bottom:10px">';
  
  html+='<label class="inp-label">Price *</label>';
  html+='<input id="item-price" class="inp" type="number" step="0.01" value="'+item.price+'" style="margin-bottom:10px;width:150px">';
  
  html+='<label class="inp-label">Image</label>';
  html+='<input id="item-image-file" type="file" accept="image/*" onchange="previewItemImage(this)" style="margin-bottom:6px;font-size:12px;color:var(--t-3)">';
  html+='<div id="item-image-preview" style="margin-bottom:10px">';
  if(item.image)html+='<img src="'+item.image+'" style="width:80px;height:80px;border-radius:8px;object-fit:cover">';
  html+='</div>';
  html+='<input id="item-image-data" type="hidden" value="'+(item.image||'')+'">';
  
  html+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">';
  html+='<input type="checkbox" id="item-featured" style="width:16px;height:16px"'+(item.featured?' checked':'')+'>';
  html+='<label for="item-featured" style="font-size:13px;color:var(--t-2)">Featured / Special</label></div>';
  
  html+='<button class="btn-p" style="width:100%;justify-content:center;padding:12px" onclick="updateItem(\''+menuId+'\',\''+catId+'\',\''+itemId+'\')">Save Changes</button>';
  html+='</div></div>';
  
  document.body.insertAdjacentHTML('beforeend',html);
}

async function updateItem(menuId,catId,itemId){
  var name=document.getElementById('item-name').value;
  var desc=document.getElementById('item-desc').value;
  var price=parseFloat(document.getElementById('item-price').value)||0;
  var image=document.getElementById('item-image-data').value||'';
  var featured=document.getElementById('item-featured').checked;
  if(!name||price<=0){alert('Enter name and valid price');return}
  try{
    await api('/menus/'+menuId+'/categories/'+catId+'/items/'+itemId,{method:'PUT',body:JSON.stringify({name:name,description:desc,price:price,image:image,featured:featured})});
    document.getElementById('item-modal').remove();
    editMenu(menuId);
  }catch(e){alert(e.message)}
}

async function deleteItem(menuId,catId,itemId){
  if(!confirm('Delete this item?'))return;
  try{
    await api('/menus/'+menuId+'/categories/'+catId+'/items/'+itemId,{method:'DELETE'});
    editMenu(menuId);
  }catch(e){alert(e.message)}
}

// Promo media functions
function uploadPromoMedia(menuId,input){
  if(!input.files||!input.files[0])return;
  var file=input.files[0];
  var type=file.type.startsWith('video')?'video':'image';
  var reader=new FileReader();
  reader.onload=async function(e){
    try{
      await api('/menus/'+menuId+'/promo-media',{method:'POST',body:JSON.stringify({type:type,data:e.target.result,title:file.name})});
      editMenu(menuId);
    }catch(err){alert(err.message)}
  };
  reader.readAsDataURL(file);
}

async function deletePromoMedia(menuId,mediaId){
  if(!confirm('Delete this media?'))return;
  try{
    await api('/menus/'+menuId+'/promo-media/'+mediaId,{method:'DELETE'});
    editMenu(menuId);
  }catch(e){alert(e.message)}
}

if(token&&user){enterApp()}

// ============ POWER SCHEDULE ============
async function openPowerSchedule(deviceId,deviceName,e){
  if(e)e.stopPropagation();
  let cur={enabled:false,power_on:'08:00',power_off:'22:00',days:['mon','tue','wed','thu','fri','sat','sun']};
  try{cur=await api('/admin/devices/'+deviceId+'/power-schedule')}catch(err){/* use default schedule */}
  const dayLabels=[['mon','Mon'],['tue','Tue'],['wed','Wed'],['thu','Thu'],['fri','Fri'],['sat','Sat'],['sun','Sun']];
  const html=`<div id="ps-modal" style="position:fixed;inset:0;background:rgba(2,6,18,.85);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);padding:20px">
    <div style="width:100%;max-width:480px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--rl);box-shadow:var(--sh-lg);overflow:hidden">
      <div style="padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-size:17px;font-weight:700">Power Schedule</div>
          <div style="font-size:12px;color:var(--t-4);margin-top:2px">${deviceName}</div>
        </div>
        <button onclick="document.getElementById('ps-modal').remove()" class="btn-icon">✕</button>
      </div>
      <div style="padding:24px">
        <label style="display:flex;align-items:center;gap:12px;padding:14px 16px;background:rgba(99,102,241,.05);border:1px solid rgba(99,102,241,.15);border-radius:var(--rs);cursor:pointer;margin-bottom:20px">
          <input type="checkbox" id="ps-enabled" ${cur.enabled?'checked':''} style="width:18px;height:18px;accent-color:var(--brand)">
          <div style="flex:1">
            <div style="font-size:13px;font-weight:600;color:var(--t-1)">Enable automatic schedule</div>
            <div style="font-size:11px;color:var(--t-4);margin-top:2px">Saves energy by turning the screen off at night</div>
          </div>
        </label>
        <div class="row2" style="margin-bottom:20px">
          <div>
            <label class="inp-label"><svg style="display:inline;vertical-align:-2px;margin-right:4px" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><path stroke-linecap="round" d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>Power On</label>
            <input id="ps-on" type="time" class="inp" value="${cur.power_on||'08:00'}">
          </div>
          <div>
            <label class="inp-label"><svg style="display:inline;vertical-align:-2px;margin-right:4px" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>Power Off</label>
            <input id="ps-off" type="time" class="inp" value="${cur.power_off||'22:00'}">
          </div>
        </div>
        <label class="inp-label">Active Days</label>
        <div style="display:flex;gap:6px;margin-bottom:24px">
          ${dayLabels.map(([k,lbl])=>`<button type="button" data-day="${k}" onclick="this.classList.toggle('ps-on')" class="${(cur.days||[]).includes(k)?'ps-on':''}" style="flex:1;padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--bg-1);color:var(--t-3);font-size:12px;font-weight:600;cursor:pointer;transition:all .15s">${lbl}</button>`).join('')}
        </div>
        <div style="background:rgba(245,158,11,.06);border:1px solid rgba(245,158,11,.15);border-radius:var(--rs);padding:12px;margin-bottom:20px">
          <div style="font-size:11px;color:var(--amber-l);display:flex;gap:8px"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="flex-shrink:0;margin-top:1px"><path stroke-linecap="round" d="M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.74-2.97l-6.93-12a2 2 0 00-3.48 0l-6.93 12A2 2 0 005.07 19z"/></svg><span>Device must support remote control. Some manufacturers require enabling this feature on the TV settings.</span></div>
        </div>
        <div style="display:flex;gap:10px">
          <button onclick="document.getElementById('ps-modal').remove()" class="btn-s" style="flex:1;justify-content:center;padding:12px">Cancel</button>
          <button onclick="savePowerSchedule('${deviceId}')" class="btn-p" style="flex:1;padding:12px">Save Schedule</button>
        </div>
        <p id="ps-msg" style="font-size:12px;text-align:center;margin-top:10px;display:none"></p>
      </div>
    </div>
  </div>
  <style>.ps-on{background:rgba(99,102,241,.15) !important;border-color:var(--brand) !important;color:var(--brand-l) !important}</style>`;
  document.body.insertAdjacentHTML('beforeend',html);
}

async function savePowerSchedule(deviceId){
  const enabled=document.getElementById('ps-enabled').checked;
  const power_on=document.getElementById('ps-on').value;
  const power_off=document.getElementById('ps-off').value;
  const days=Array.from(document.querySelectorAll('[data-day].ps-on')).map(b=>b.dataset.day);
  const msg=document.getElementById('ps-msg');msg.style.display='none';
  try{
    await api('/admin/devices/'+deviceId+'/power-schedule',{method:'PUT',body:JSON.stringify({enabled,power_on,power_off,days})});
    msg.textContent='Schedule saved!';msg.style.color='var(--green-l)';msg.style.display='block';
    setTimeout(()=>{document.getElementById('ps-modal')?.remove();loaders.devices()},700);
  }catch(e){msg.textContent=e.message;msg.style.color='var(--red)';msg.style.display='block'}
}

// ============ PAIRING / COLORLIGHT HELPERS ============
function copyText(btn,text){
  if(!text)return;
  navigator.clipboard.writeText(text).then(()=>{
    const orig=btn.innerHTML;btn.innerHTML='✓';btn.style.background='rgba(34,197,94,.15)';btn.style.color='var(--green-l)';
    setTimeout(()=>{btn.innerHTML=orig;btn.style.background='';btn.style.color=''},1200);
  }).catch(()=>{
    // Fallback for non-secure contexts
    const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}catch(e){/* clipboard fallback unavailable */}ta.remove();
    btn.innerHTML='✓';setTimeout(()=>btn.innerHTML='📋',1000);
  });
}

async function regenPairingSecret(screenId){
  if(!confirm('⚠ Regenerate Device ID + Secret Key?\n\nThis will INVALIDATE the current credentials. Any device currently paired with this screen will need to re-enter the new credentials.\n\nContinue?'))return;
  try{
    const res=await api('/admin/screens/'+screenId+'/regenerate-pairing',{method:'POST'});
    alert('✓ New credentials generated.\n\nDevice ID: '+res.pairing_code+'\nSecret Key: '+res.pairing_secret+'\n\nReloading editor…');
    editAdminScreen(screenId);
  }catch(e){alert('Error: '+e.message)}
}

// ============ COLORLIGHT A40 PROVISIONING (auto-create terminal in cloud) ============
async function openProvisionModal(screenId, screenName){
  // Fetch terminal groups from ColorlightCloud
  let groups=[];
  try{
    const terms=await api('/colorlight/terminals');
    groups=terms.groups||[];
  }catch(e){
    alert('ColorlightCloud not configured or unreachable.\n\nGo to Admin Panel → LED Cloud first and connect your account.\n\nError: '+e.message);
    return;
  }
  const ov=document.createElement('div');ov.id='cl-prov-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.85);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;overflow:auto';
  ov.innerHTML='<div class="card" style="max-width:520px;width:100%;padding:28px;background:var(--bg-2)">'+
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">'+
      '<div style="width:44px;height:44px;border-radius:12px;background:rgba(34,211,238,.12);color:var(--cyan);display:flex;align-items:center;justify-content:center"><svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg></div>'+
      '<div style="flex:1"><h2 style="font-size:18px;font-weight:700;margin:0">Provision A40 in ColorlightCloud</h2><p style="font-size:12px;color:var(--t-4);margin:4px 0 0">Auto-creates the terminal and returns Device ID + Secret Key.</p></div>'+
      '<button onclick="document.getElementById(\'cl-prov-modal\').remove()" style="background:none;border:none;color:var(--t-4);font-size:24px;cursor:pointer;padding:0;line-height:1">×</button>'+
    '</div>'+
    '<div style="margin-bottom:14px"><div class="lbl">Terminal name</div><input class="inp" id="prov-title" value="'+(screenName||'')+'" placeholder="Eg. casa josue A40"></div>'+
    '<div style="margin-bottom:14px"><div class="lbl">Description (optional)</div><input class="inp" id="prov-desc" placeholder="Eg. Columbus OH 30x54 Portrait"></div>'+
    '<div style="margin-bottom:18px"><div class="lbl">Target group in ColorlightCloud</div><select class="inp" id="prov-group"><option value="">— Select a group —</option>'+
      groups.map(g=>'<option value="'+g.group_id+'">'+g.group_name+' ('+g.terminal_count+' terminals)</option>').join('')+
    '</select></div>'+
    '<button class="btn-p" id="prov-btn" onclick="executeProvision(\''+screenId+'\')" style="width:100%;justify-content:center;padding:14px;font-size:14px"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="margin-right:6px"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg> Create Terminal & Get Credentials</button>'+
    '<p id="prov-msg" style="font-size:12px;margin-top:14px;text-align:center;display:none"></p>'+
  '</div>';
  document.body.appendChild(ov);
}

async function executeProvision(screenId){
  const title=document.getElementById('prov-title').value.trim();
  const desc=document.getElementById('prov-desc').value.trim();
  const groupId=parseInt(document.getElementById('prov-group').value);
  const msg=document.getElementById('prov-msg');msg.style.display='none';
  const btn=document.getElementById('prov-btn');
  if(!title){msg.textContent='Enter a name';msg.style.color='var(--red)';msg.style.display='block';return}
  if(!groupId){msg.textContent='Select a group';msg.style.color='var(--red)';msg.style.display='block';return}
  btn.disabled=true;btn.style.opacity='.6';
  msg.textContent='Creating terminal in ColorlightCloud…';msg.style.color='var(--t-4)';msg.style.display='block';
  try{
    const res=await api('/colorlight/provision',{method:'POST',body:JSON.stringify({
      title,description:desc,group_id:groupId,link_screen_id:screenId
    })});
    document.getElementById('cl-prov-modal').remove();
    showColorlightCredentialsModal(res);
    // Refresh the editor to show the new colorlight section
    setTimeout(()=>editAdminScreen(screenId),300);
  }catch(e){msg.textContent='✗ '+e.message;msg.style.color='var(--red)';btn.disabled=false;btn.style.opacity='1'}
}

function showColorlightCredentialsModal(creds){
  const ov=document.createElement('div');ov.id='cl-creds-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.9);backdrop-filter:blur(6px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;overflow:auto';
  ov.innerHTML='<div class="card" style="max-width:580px;width:100%;padding:28px;background:var(--bg-2)">'+
    '<div style="text-align:center;margin-bottom:20px">'+
      '<div style="width:64px;height:64px;border-radius:50%;background:rgba(34,197,94,.15);color:var(--green-l);display:flex;align-items:center;justify-content:center;margin:0 auto 12px"><svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>'+
      '<h2 style="font-size:20px;font-weight:700;margin:0">Terminal Created! 🎉</h2>'+
      '<p style="font-size:13px;color:var(--t-4);margin:6px 0 0">Now enter these 3 values into your A40 device:</p>'+
    '</div>'+
    '<div style="display:flex;flex-direction:column;gap:14px;margin-bottom:20px">'+
      '<div style="padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--bg-1)">'+
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><div style="font-size:11px;color:var(--t-3);font-weight:700;text-transform:uppercase;letter-spacing:.6px">1️⃣ Cloud URL</div><button class="btn-s" onclick="copyText(this,\''+creds.url+'\')" style="font-size:11px;padding:4px 10px">📋 Copy</button></div>'+
        '<div style="font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--cyan);word-break:break-all">'+creds.url+'</div>'+
      '</div>'+
      '<div style="padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--bg-1)">'+
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><div style="font-size:11px;color:var(--t-3);font-weight:700;text-transform:uppercase;letter-spacing:.6px">2️⃣ Device ID</div><button class="btn-s" onclick="copyText(this,\''+creds.device_id+'\')" style="font-size:11px;padding:4px 10px">📋 Copy</button></div>'+
        '<div style="font-family:ui-monospace,Menlo,monospace;font-size:18px;font-weight:700;color:var(--cyan);letter-spacing:1px">'+creds.device_id+'</div>'+
      '</div>'+
      '<div style="padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--bg-1)">'+
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><div style="font-size:11px;color:var(--t-3);font-weight:700;text-transform:uppercase;letter-spacing:.6px">3️⃣ Secret Key</div><button class="btn-s" onclick="copyText(this,\''+creds.secret_key+'\')" style="font-size:11px;padding:4px 10px">📋 Copy</button></div>'+
        '<div style="font-family:ui-monospace,Menlo,monospace;font-size:18px;font-weight:700;color:#22d3ee;letter-spacing:1px;word-break:break-all">'+creds.secret_key+'</div>'+
      '</div>'+
    '</div>'+
    '<div style="padding:14px;border-left:3px solid var(--cyan);background:rgba(34,211,238,.05);border-radius:6px;margin-bottom:18px">'+
      '<div style="font-size:12px;color:var(--t-2);line-height:1.6">'+
        '<b style="color:var(--cyan)">📺 On the A40:</b><br>'+
        '1. Open the device web admin (eg. <code>http://192.168.x.x</code>)<br>'+
        '2. Go to <b>Cloud account</b> tab<br>'+
        '3. Paste the 3 values above<br>'+
        '4. Click <b>Apply</b><br>'+
        '5. Status should change to: <span style="color:var(--green-l)">✓ Network Connected · Login Logged in</span>'+
      '</div>'+
    '</div>'+
    '<div style="display:flex;gap:10px">'+
      '<button class="btn-s" onclick="copyAllColorlightCreds(\''+creds.url+'\',\''+creds.device_id+'\',\''+creds.secret_key+'\')" style="flex:1;justify-content:center;padding:12px">📋 Copy All 3</button>'+
      '<button class="btn-p" onclick="document.getElementById(\'cl-creds-modal\').remove()" style="flex:1;justify-content:center;padding:12px">Done</button>'+
    '</div>'+
  '</div>';
  document.body.appendChild(ov);
}

function copyAllColorlightCreds(url,deviceId,secretKey){
  const text='URL: '+url+'\nDevice ID: '+deviceId+'\nSecret Key: '+secretKey;
  navigator.clipboard.writeText(text).then(()=>{
    alert('✓ All 3 credentials copied to clipboard');
  }).catch(()=>alert('Copy failed. Please copy each value individually.'));
}

function showColorlightInstructions(screenId){
  // Re-open the credentials modal using saved values
  api('/screens/'+screenId).then(s=>{
    if(s.colorlight && s.colorlight.device_id){
      showColorlightCredentialsModal(s.colorlight);
    }else{
      alert('No ColorlightCloud credentials saved for this screen.');
    }
  }).catch(e=>alert('Error: '+e.message));
}

// ============ DIRECT MODE — A40 controlled directly by MediAd View ============

// Auto-load (or auto-create) the Direct Mode credentials for a given screen.
async function autoLoadPairing(screenId, existing, screenName){
  const urlEl=document.getElementById('pair-url-'+screenId);
  const didEl=document.getElementById('pair-did-'+screenId);
  const secEl=document.getElementById('pair-sec-'+screenId);
  const statusEl=document.getElementById('pair-status-'+screenId);
  if(!urlEl) return;
  // Clear any previous polling interval
  if(window._pairPollIv){clearInterval(window._pairPollIv);window._pairPollIv=null}
  let creds=existing;
  if(!creds || !creds.device_id){
    statusEl.innerHTML='⏳ Generating credentials…';
    try{
      const res=await api('/cls/provision-direct',{method:'POST',body:JSON.stringify({
        title: screenName||'A40',
        link_screen_id: screenId,
        url_base: window.location.origin
      })});
      creds={url:res.url, device_id:res.device_id, secret_key:res.secret_key,
             terminal_id:res.terminal_id, provisioned_at:new Date().toISOString()};
    }catch(e){
      statusEl.innerHTML='<span style="color:var(--red)">✗ '+e.message+'</span>';
      return;
    }
  }
  urlEl.value=creds.url||'';
  didEl.value=creds.device_id||'';
  secEl.value=creds.secret_key||'';
  window._pairCurrentDeviceId=creds.device_id;
  window._pairCurrentScreenId=screenId;
  // Show schedule button now that we have a device
  injectScheduleAndControlsButtons(screenId, creds.device_id);
  // Refresh status NOW + then every 8 seconds while the editor is open
  refreshPairStatus(screenId, creds.device_id);
  window._pairPollIv=setInterval(()=>{
    if(document.getElementById('pair-status-'+screenId)){
      refreshPairStatus(screenId, creds.device_id);
    }else{
      clearInterval(window._pairPollIv);window._pairPollIv=null;
    }
  }, 8000);
}

function injectScheduleAndControlsButtons(screenId, deviceId){
  const status=document.getElementById('pair-status-'+screenId);
  if(!status)return;
  const parent=status.parentNode;
  // Don't duplicate
  if(document.getElementById('pair-actions-'+screenId))return;
  const row=document.createElement('div');
  row.id='pair-actions-'+screenId;
  row.style.cssText='display:flex;gap:8px;margin-top:10px;padding-top:10px;border-top:1px dashed var(--border)';
  row.innerHTML=
    '<button class="btn-s" onclick="openDirectPushModal(\''+deviceId+'\',\''+(document.getElementById('es-name')?.value||'A40').replace(/\'/g,'')+'\')" style="flex:1;justify-content:center;padding:8px;font-size:11px">⚡ Push Media</button>'+
    '<button class="btn-s" onclick="openScheduleModal(\''+deviceId+'\',\''+(document.getElementById('es-name')?.value||'A40').replace(/\'/g,'')+'\')" style="flex:1;justify-content:center;padding:8px;font-size:11px">🕐 ON/OFF Schedule</button>'+
    '<button class="btn-s" onclick="openDirectControlsModal(\''+deviceId+'\',\''+(document.getElementById('es-name')?.value||'A40').replace(/\'/g,'')+'\')" style="flex:1;justify-content:center;padding:8px;font-size:11px">🎛 Controls</button>';
  parent.parentNode.appendChild(row);
}

async function refreshPairStatus(screenId, deviceId){
  const statusEl=document.getElementById('pair-status-'+screenId);
  if(!statusEl||!deviceId)return;
  try{
    const s=await api('/cls/devices/'+deviceId+'/status');
    if(s.online){
      const lastSeen=new Date(s.last_seen);
      const ago=Math.floor((Date.now()-lastSeen.getTime())/1000);
      statusEl.innerHTML='<span style="display:inline-flex;align-items:center;gap:6px;color:var(--green-l);font-weight:700">'+
        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#22c55e;box-shadow:0 0 12px #22c55e;animation:pulse 1.5s infinite"></span>'+
        ' ONLINE · Connected '+(ago<10?'just now':ago+'s ago')+' · '+lastSeen.toLocaleTimeString()+'</span>';
    }else if(s.last_seen){
      const lastSeen=new Date(s.last_seen);
      const minAgo=Math.floor((Date.now()-lastSeen.getTime())/60000);
      let reason='No internet or device powered off';
      if(minAgo<5) reason='Reconnecting…';
      statusEl.innerHTML='<span style="display:inline-flex;align-items:center;gap:6px;color:var(--red);font-weight:700">'+
        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ef4444"></span>'+
        ' OFFLINE · '+reason+' · last seen '+(minAgo<60?minAgo+' min ago':lastSeen.toLocaleString())+'</span>';
    }else{
      statusEl.innerHTML='<span style="display:inline-flex;align-items:center;gap:6px;color:var(--t-4)">'+
        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#94a3b8"></span>'+
        ' Waiting for device · paste credentials into the LED and click Apply</span>';
    }
  }catch(e){
    statusEl.innerHTML='<span style="color:var(--t-4)">⚠ Status unavailable</span>';
  }
}

async function openScheduleModal(deviceId, deviceName){
  let sched={};
  try{sched=await api('/cls/schedule/'+deviceId)}catch(e){/* schedule may not exist */}
  const w=sched.wakeup_time||'07:00',sl=sched.sleep_time||'22:00';
  const days=sched.days||[1,1,1,1,1,1,1];
  const dn=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const ov=document.createElement('div');ov.id='sched-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.85);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px';
  ov.innerHTML='<div class="card" style="max-width:480px;width:100%;padding:28px;background:var(--bg-2)">'+
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">'+
      '<div style="width:44px;height:44px;border-radius:12px;background:rgba(34,211,238,.12);color:var(--cyan);display:flex;align-items:center;justify-content:center;font-size:20px">🕐</div>'+
      '<div style="flex:1"><h2 style="font-size:18px;font-weight:700;margin:0">ON/OFF Schedule</h2><p style="font-size:12px;color:var(--t-4);margin:4px 0 0">Device: '+deviceName+'</p></div>'+
      '<button onclick="document.getElementById(\'sched-modal\').remove()" style="background:none;border:none;color:var(--t-4);font-size:24px;cursor:pointer">×</button>'+
    '</div>'+
    '<label style="display:flex;align-items:center;gap:10px;padding:12px;background:var(--bg-1);border-radius:8px;cursor:pointer;margin-bottom:16px"><input type="checkbox" id="sc-enabled" '+(sched.enabled?'checked':'')+'><span style="font-size:13px;font-weight:600">Enable automatic schedule</span></label>'+
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">'+
      '<div><div class="lbl">🌅 Wake up (turn ON)</div><input class="inp" type="time" id="sc-wake" value="'+w+'"></div>'+
      '<div><div class="lbl">🌙 Sleep (turn OFF)</div><input class="inp" type="time" id="sc-sleep" value="'+sl+'"></div>'+
    '</div>'+
    '<div class="lbl" style="margin-bottom:8px">Active days</div>'+
    '<div style="display:flex;gap:6px;margin-bottom:18px">'+
      dn.map((d,i)=>'<label style="flex:1;padding:8px;border:1px solid '+(days[i]?'var(--cyan)':'var(--border)')+';background:'+(days[i]?'rgba(34,211,238,.1)':'var(--bg-1)')+';color:'+(days[i]?'var(--cyan)':'var(--t-4)')+';border-radius:6px;text-align:center;font-size:11px;font-weight:700;cursor:pointer;user-select:none" onclick="this.classList.toggle(\'on\');var on=this.classList.contains(\'on\')||this.style.color==\'var(--cyan)\';if(this.style.color==\'var(--cyan)\'){this.style.color=\'var(--t-4)\';this.style.background=\'var(--bg-1)\';this.style.borderColor=\'var(--border)\';this.dataset.on=0}else{this.style.color=\'var(--cyan)\';this.style.background=\'rgba(34,211,238,.1)\';this.style.borderColor=\'var(--cyan)\';this.dataset.on=1}"><input type="hidden" class="sc-d" data-d="'+i+'" data-on="'+days[i]+'">'+d+'</label>').join('')+
    '</div>'+
    '<div style="padding:10px;background:rgba(99,102,241,.05);border-left:3px solid #818cf8;border-radius:6px;font-size:11px;color:var(--t-3);margin-bottom:18px"><b>💡 What this does:</b> the A40 stays powered ON but the LED panel turns OFF during sleep hours (saves power, extends LED life). It wakes up automatically.</div>'+
    '<div style="display:flex;gap:10px;margin-bottom:14px">'+
      '<button class="btn-s" onclick="manualSleepWake(\''+deviceId+'\',\'sleep\')" style="flex:1;justify-content:center;padding:10px;color:#818cf8">🌙 Sleep NOW</button>'+
      '<button class="btn-s" onclick="manualSleepWake(\''+deviceId+'\',\'wakeup\')" style="flex:1;justify-content:center;padding:10px;color:var(--green-l)">🌅 Wake NOW</button>'+
    '</div>'+
    '<button class="btn-p" onclick="saveSchedule(\''+deviceId+'\')" style="width:100%;justify-content:center;padding:12px">Save Schedule</button>'+
    '<p id="sc-msg" style="font-size:12px;margin-top:12px;text-align:center;display:none"></p>'+
  '</div>';
  document.body.appendChild(ov);
  // initialize day toggle states
  setTimeout(()=>{document.querySelectorAll('.sc-d').forEach(c=>{c.parentElement.dataset.on=c.dataset.on});},10);
}

async function saveSchedule(deviceId){
  const enabled=document.getElementById('sc-enabled').checked;
  const wakeup_time=document.getElementById('sc-wake').value;
  const sleep_time=document.getElementById('sc-sleep').value;
  const days=Array.from(document.querySelectorAll('.sc-d')).map(c=>parseInt(c.parentElement.dataset.on||c.dataset.on||0));
  const msg=document.getElementById('sc-msg');msg.style.display='none';
  try{
    await api('/cls/schedule',{method:'POST',body:JSON.stringify({device_id:deviceId,enabled,wakeup_time,sleep_time,days})});
    msg.textContent='✓ Schedule saved. Will activate at next time match.';
    msg.style.color='var(--green-l)';msg.style.display='block';
    setTimeout(()=>document.getElementById('sched-modal')?.remove(),1500);
  }catch(e){msg.textContent='✗ '+e.message;msg.style.color='var(--red)';msg.style.display='block'}
}

async function manualSleepWake(deviceId, action){
  try{
    await api('/cls/'+action+'/'+deviceId,{method:'POST'});
    const msg=document.getElementById('sc-msg');
    if(msg){msg.textContent='✓ Command sent. Device should react in <5s.';msg.style.color='var(--green-l)';msg.style.display='block'}
  }catch(e){alert('Error: '+e.message)}
}

function copyAllPairing(screenId){
  const url=document.getElementById('pair-url-'+screenId).value;
  const did=document.getElementById('pair-did-'+screenId).value;
  const sec=document.getElementById('pair-sec-'+screenId).value;
  const text='URL: '+url+'\nDevice ID: '+did+'\nSecret Key: '+sec;
  navigator.clipboard.writeText(text).then(()=>alert('✓ All 3 credentials copied'))
    .catch(()=>alert('Copy failed — please copy each one individually'));
}

async function regenDirectCreds(screenId){
  if(!confirm('⚠ Generate BRAND NEW credentials for this screen?\n\nThe LED device currently connected with the old credentials will DISCONNECT.\nYou will need to enter the new credentials into the device.\n\nContinue?'))return;
  try{
    // Unlink the old colorlight credentials so autoLoadPairing creates new ones
    const screen=await api('/screens/'+screenId);
    if(screen.colorlight && screen.colorlight.device_id){
      // Delete old terminal entry
      try{await api('/admin/screens/'+screenId+'/unlink-colorlight',{method:'POST'})}catch(e){/* continue local unlink */}
    }
    // Reload editor — autoLoadPairing will generate new ones
    editAdminScreen(screenId);
  }catch(e){alert('Error: '+e.message)}
}

async function provisionDirect(screenId, screenName){
  if(!confirm('Provision this screen in MediAd View DIRECT MODE?\n\nA Device ID + Secret Key will be generated and saved locally. NO call to ColorlightCloud will be made.\n\nProceed?'))return;
  try{
    const res=await api('/cls/provision-direct',{method:'POST',body:JSON.stringify({
      title: screenName || 'A40 Direct',
      link_screen_id: screenId,
      url_base: window.location.origin
    })});
    showColorlightCredentialsModal({
      url:        res.url,
      device_id:  res.device_id,
      secret_key: res.secret_key,
      terminal_id: res.terminal_id,
      provisioned_at: new Date().toISOString(),
      mode: 'direct'
    });
    setTimeout(()=>editAdminScreen(screenId),400);
  }catch(e){alert('Error: '+e.message)}
}

function openDirectPushModal(deviceId, deviceName){
  const ov=document.createElement('div');ov.id='dir-push-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.85);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;overflow:auto';
  ov.innerHTML='<div class="card" style="max-width:520px;width:100%;padding:28px;background:var(--bg-2)">'+
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">'+
      '<div style="width:44px;height:44px;border-radius:12px;background:rgba(34,211,238,.12);color:var(--cyan);display:flex;align-items:center;justify-content:center;font-size:20px">⚡</div>'+
      '<div style="flex:1"><h2 style="font-size:18px;font-weight:700;margin:0">Push to '+deviceName+'</h2><p style="font-size:12px;color:var(--t-4);margin:4px 0 0">Direct push (no ColorlightCloud) · Device: '+deviceId+'</p></div>'+
      '<button onclick="document.getElementById(\'dir-push-modal\').remove()" style="background:none;border:none;color:var(--t-4);font-size:24px;cursor:pointer">×</button>'+
    '</div>'+
    '<div style="margin-bottom:14px"><div class="lbl">Title</div><input class="inp" id="dp-title" placeholder="Promo Junio 2026"></div>'+
    '<div style="margin-bottom:14px"><div class="lbl">Media file (image/video)</div><input class="inp" id="dp-file" type="file" accept="image/*,video/*"></div>'+
    '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px">'+
      '<div><div class="lbl">Width</div><input class="inp" id="dp-w" type="number" value="192"></div>'+
      '<div><div class="lbl">Height</div><input class="inp" id="dp-h" type="number" value="320"></div>'+
      '<div><div class="lbl">Duration (s)</div><input class="inp" id="dp-dur" type="number" value="8"></div>'+
    '</div>'+
    '<button class="btn-p" id="dp-btn" onclick="executeDirectPush(\''+deviceId+'\')" style="width:100%;justify-content:center;padding:14px;font-size:14px">⚡ Push Now</button>'+
    '<p id="dp-msg" style="font-size:12px;margin-top:12px;text-align:center;display:none"></p>'+
  '</div>';
  document.body.appendChild(ov);
}

async function executeDirectPush(deviceId){
  const title=document.getElementById('dp-title').value.trim()||'Untitled';
  const file=document.getElementById('dp-file').files[0];
  const w=parseInt(document.getElementById('dp-w').value)||192;
  const h=parseInt(document.getElementById('dp-h').value)||320;
  const dur=(parseInt(document.getElementById('dp-dur').value)||8)*1000;
  const msg=document.getElementById('dp-msg');msg.style.display='none';
  const btn=document.getElementById('dp-btn');
  if(!file){msg.textContent='Select a media file';msg.style.color='var(--red)';msg.style.display='block';return}
  const b64=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=rej;r.readAsDataURL(file)});
  btn.disabled=true;btn.style.opacity='.6';
  msg.textContent='Uploading & queueing…';msg.style.color='var(--t-4)';msg.style.display='block';
  try{
    const res=await api('/cls/push',{method:'POST',body:JSON.stringify({
      device_id:deviceId,media_base64:b64,filename:file.name,content_type:file.type||'image/jpeg',
      title:title,width:w,height:h,duration_ms:dur
    })});
    msg.textContent='✓ Pushed! Program #'+res.program_id+' queued. Device will pick it up within 5s.';
    msg.style.color='var(--green-l)';
    setTimeout(()=>document.getElementById('dir-push-modal')?.remove(),2200);
  }catch(e){msg.textContent='✗ '+e.message;msg.style.color='var(--red)';btn.disabled=false;btn.style.opacity='1'}
}

function openDirectControlsModal(deviceId, deviceName){
  const ov=document.createElement('div');ov.id='dir-ctl-modal';
  ov.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.85);backdrop-filter:blur(4px);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;overflow:auto';
  ov.innerHTML='<div class="card" style="max-width:480px;width:100%;padding:28px;background:var(--bg-2)">'+
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">'+
      '<div style="width:44px;height:44px;border-radius:12px;background:rgba(99,102,241,.12);color:#818cf8;display:flex;align-items:center;justify-content:center;font-size:20px">🎛</div>'+
      '<div style="flex:1"><h2 style="font-size:18px;font-weight:700;margin:0">Controls — '+deviceName+'</h2><p style="font-size:12px;color:var(--t-4);margin:4px 0 0">'+deviceId+'</p></div>'+
      '<button onclick="document.getElementById(\'dir-ctl-modal\').remove()" style="background:none;border:none;color:var(--t-4);font-size:24px;cursor:pointer">×</button>'+
    '</div>'+
    '<div style="margin-bottom:16px"><label style="font-size:12px;color:var(--t-3);font-weight:600">Brightness</label><div style="display:flex;align-items:center;gap:10px;margin-top:6px"><input type="range" id="ctl-bri" min="0" max="255" value="200" oninput="document.getElementById(\'ctl-bri-v\').textContent=this.value" style="flex:1"><span id="ctl-bri-v" style="min-width:40px;text-align:right;font-family:ui-monospace,monospace;font-weight:700;color:var(--cyan)">200</span><button class="btn-s" onclick="sendDirectCommand(\''+deviceId+'\',\'brightness\',document.getElementById(\'ctl-bri\').value)" style="padding:6px 12px">Set</button></div></div>'+
    '<div style="margin-bottom:16px"><label style="font-size:12px;color:var(--t-3);font-weight:600">Volume (0-15)</label><div style="display:flex;align-items:center;gap:10px;margin-top:6px"><input type="range" id="ctl-vol" min="0" max="15" value="10" oninput="document.getElementById(\'ctl-vol-v\').textContent=this.value" style="flex:1"><span id="ctl-vol-v" style="min-width:40px;text-align:right;font-family:ui-monospace,monospace;font-weight:700;color:var(--cyan)">10</span><button class="btn-s" onclick="sendDirectCommand(\''+deviceId+'\',\'volume\',document.getElementById(\'ctl-vol\').value)" style="padding:6px 12px">Set</button></div></div>'+
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:18px">'+
      '<button class="btn-s" onclick="sendDirectCommand(\''+deviceId+'\',\'reboot\')" style="justify-content:center;padding:12px">🔁 Reboot</button>'+
      '<button class="btn-s" onclick="sendDirectCommand(\''+deviceId+'\',\'screenshot\')" style="justify-content:center;padding:12px">📷 Screenshot</button>'+
      '<button class="btn-s" onclick="sendDirectCommand(\''+deviceId+'\',\'clear\')" style="justify-content:center;padding:12px;color:var(--red)">🗑 Clear Programs</button>'+
      '<button class="btn-s" onclick="showRecentCommands(\''+deviceId+'\')" style="justify-content:center;padding:12px">📜 Recent Commands</button>'+
    '</div>'+
    '<p id="ctl-msg" style="font-size:12px;margin-top:14px;text-align:center;display:none"></p>'+
  '</div>';
  document.body.appendChild(ov);
}

async function sendDirectCommand(deviceId, kind, value){
  const msg=document.getElementById('ctl-msg');if(msg)msg.style.display='none';
  try{
    let res;
    if(kind==='brightness')      res=await api('/cls/brightness',{method:'POST',body:JSON.stringify({device_id:deviceId,value:parseInt(value)})});
    else if(kind==='volume')     res=await api('/cls/volume',{method:'POST',body:JSON.stringify({device_id:deviceId,value:parseInt(value)})});
    else if(kind==='reboot')     res=await api('/cls/reboot/'+deviceId,{method:'POST'});
    else if(kind==='screenshot') res=await api('/cls/screenshot/'+deviceId,{method:'POST'});
    else if(kind==='clear')      res=await api('/cls/clear-program/'+deviceId,{method:'POST'});
    if(msg){msg.textContent='✓ Command #'+res.cmd_id+' queued. Device will pick it up within 5s.';msg.style.color='var(--green-l)';msg.style.display='block'}
  }catch(e){if(msg){msg.textContent='✗ '+e.message;msg.style.color='var(--red)';msg.style.display='block'}}
}

async function showRecentCommands(deviceId){
  try{
    const res=await api('/cls/commands/'+deviceId);
    const lines=res.commands.map(c=>{
      const t=new Date(c.created_at).toLocaleTimeString();
      return '['+t+'] '+c.author_url+' · '+c.status+(c.device_response?' ('+c.device_response+')':'');
    }).join('\n');
    alert('Recent commands for '+deviceId+':\n\n'+(lines||'(none)'));
  }catch(e){alert('Error: '+e.message)}
}


// ============ COLORLIGHT CLOUD ============
async function loadColorlightPanel(){
  const panel=document.getElementById('cl-panel');if(!panel)return;
  // Load BOTH: ColorlightCloud bridge status + Direct Mode devices
  let status, direct=null;
  try{status=await api('/colorlight/status')}catch(e){panel.innerHTML='<div class="card" style="padding:24px;color:var(--red)">'+e.message+'</div>';return}
  try{direct=await api('/cls/devices')}catch(e){direct={devices:[],total:0}}
  // ===== Render Direct Mode banner first (the new pro flow) =====
  let directHtml='<div class="card" style="padding:20px;margin-bottom:18px;border:1px solid rgba(34,211,238,.3);background:linear-gradient(135deg,rgba(34,211,238,.08),rgba(99,102,241,.04))">'+
    '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">'+
      '<div style="width:42px;height:42px;border-radius:10px;background:rgba(34,211,238,.15);color:var(--cyan);display:flex;align-items:center;justify-content:center;font-size:20px">⚡</div>'+
      '<div style="flex:1"><div style="font-size:15px;font-weight:700;color:var(--cyan)">Direct Mode — A40 ↔ MediAd View (no ColorlightCloud)</div>'+
        '<div style="font-size:11px;color:var(--t-4)">Devices configured to talk directly to YOUR server. Full control, zero dependency.</div></div>'+
      '<a href="/api/web/apk-install-guide.html" target="_blank" style="font-size:11px;padding:7px 13px;border-radius:14px;background:linear-gradient(135deg,#22d3ee,#6366f1);color:#0b1220;font-weight:700;text-decoration:none;margin-right:6px">📖 Cómo instalar APK</a>'+
      '<span style="font-size:11px;padding:6px 12px;border-radius:14px;background:rgba(34,211,238,.15);color:var(--cyan);font-weight:600">'+direct.total+' direct device(s)</span>'+
    '</div>'+
    (direct.total===0
      ? '<div style="padding:16px;background:var(--bg-1);border-radius:8px;font-size:12px;color:var(--t-4);line-height:1.6"><b style="color:var(--t-2)">📺 How to add a device in Direct Mode:</b><br>1. Click <b>Provision in ColorlightCloud</b> on any screen (Edit Screen → Colorlight section)<br>2. After provisioning, in the A40 Settings → Cloud account → put:<br>&nbsp;&nbsp;&nbsp;<code style="color:var(--cyan)">URL = '+window.location.origin+'/api</code><br>&nbsp;&nbsp;&nbsp;<code style="color:var(--cyan)">Device ID = (from MediAd View)</code><br>&nbsp;&nbsp;&nbsp;<code style="color:var(--cyan)">Secret Key = (from MediAd View)</code><br>3. Click Apply on the A40 → device appears here within 30s</div>'
      : '<div style="display:flex;flex-direction:column;gap:8px">'+
          direct.devices.map(d=>'<div style="padding:12px;background:var(--bg-1);border-radius:8px;display:flex;align-items:center;gap:12px">'+
            '<span style="width:10px;height:10px;border-radius:50%;background:'+(d.online?'var(--green-l)':'var(--t-4)')+';box-shadow:'+(d.online?'0 0 8px var(--green-l)':'none')+'"></span>'+
            '<div style="flex:1"><div style="font-size:13px;font-weight:700">'+(d.title||d.device_id)+' <span style="font-size:10px;color:var(--t-4);font-weight:500">#'+d.device_id+'</span></div>'+
              '<div style="font-size:10px;color:var(--t-4)">'+(d.model||'A40')+' · fw '+(d.firmware||'?')+' · S/N '+(d.serial||'?')+' · last seen '+(d.last_seen?new Date(d.last_seen).toLocaleTimeString():'never')+'</div></div>'+
            '<button class="btn-p" onclick="openDirectPushModal(\''+d.device_id+'\',\''+(d.title||d.device_id).replace(/\'/g,'')+'\')" style="font-size:11px;padding:6px 14px">⚡ Push</button>'+
            '<button class="btn-s" onclick="openDirectControlsModal(\''+d.device_id+'\',\''+(d.title||d.device_id).replace(/\'/g,'')+'\')" style="font-size:11px;padding:6px 10px" title="Controls (brightness, volume, reboot)">🎛</button>'+
          '</div>').join('')+
        '</div>')+
  '</div>';
  // ===== ColorlightCloud Bridge section (legacy) =====
  if(!status.configured){
    panel.innerHTML=directHtml+'<div class="card" style="padding:24px;max-width:560px"><h3 style="font-size:16px;font-weight:700;margin-bottom:6px">Connect ColorlightCloud Bridge (legacy)</h3><p style="font-size:13px;color:var(--t-4);margin-bottom:18px">Optional. Lets you also manage screens that are still on ColorlightCloud.</p>'+
      '<div style="margin-bottom:12px"><div class="lbl">Server</div><input class="inp" id="cl-server" value="us33.colorlightcloud.com"></div>'+
      '<div style="margin-bottom:12px"><div class="lbl">Username</div><input class="inp" id="cl-user" placeholder="josue"></div>'+
      '<div style="margin-bottom:16px"><div class="lbl">Password</div><input class="inp" id="cl-pwd" type="password"></div>'+
      '<button class="btn-p" onclick="saveColorlightSettings()" style="width:100%;justify-content:center">Test & Save</button>'+
      '<p id="cl-msg" style="font-size:12px;margin-top:12px;text-align:center;display:none"></p></div>';
    return;
  }
  let terms;
  try{terms=await api('/colorlight/terminals')}catch(e){panel.innerHTML=directHtml+'<div class="card" style="padding:24px;color:var(--red)"><b>Bridge error:</b> '+e.message+'<div style="margin-top:14px"><button class="btn-s" onclick="resetColorlightSettings()">Reconfigure</button></div></div>';return}
  const groups=terms.groups||[];
  panel.innerHTML=directHtml+'<div style="display:grid;grid-template-columns:1.2fr 1fr;gap:18px;align-items:start">'+
    // LEFT — Status + Push form
    '<div>'+
      '<div class="card" style="padding:18px;margin-bottom:14px;display:flex;align-items:center;gap:14px">'+
        '<div style="width:42px;height:42px;border-radius:10px;background:rgba(34,197,94,.12);color:var(--green-l);display:flex;align-items:center;justify-content:center"><svg width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg></div>'+
        '<div style="flex:1"><div style="font-size:14px;font-weight:700">Connected to '+status.server+'</div><div style="font-size:11px;color:var(--t-4)">User: '+status.username+' · Auth: '+(status.method||'form')+' · '+terms.total_terminals+' terminal(s) in '+terms.total_groups+' group(s)</div></div>'+
        '<button class="btn-s" onclick="resetColorlightSettings()" style="font-size:11px;padding:6px 12px">Reconfigure</button>'+
      '</div>'+
      '<div class="card" style="padding:20px">'+
        '<h3 style="font-size:15px;font-weight:700;margin-bottom:4px">Push Media to LED Screen</h3>'+
        '<p style="font-size:12px;color:var(--t-4);margin-bottom:18px">Upload an image/video and publish it directly to the selected ColorlightCloud terminal.</p>'+
        '<div style="margin-bottom:12px"><div class="lbl">Title (program name)</div><input class="inp" id="cl-title" placeholder="Promo June 2025"></div>'+
        '<div style="margin-bottom:12px"><div class="lbl">Media file</div><input class="inp" id="cl-file" type="file" accept="image/*,video/*"></div>'+
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">'+
          '<div><div class="lbl">Width (px)</div><input class="inp" id="cl-w" type="number" value="192"></div>'+
          '<div><div class="lbl">Height (px)</div><input class="inp" id="cl-h" type="number" value="320"></div>'+
        '</div>'+
        '<div style="margin-bottom:12px"><div class="lbl">Duration per image (sec)</div><input class="inp" id="cl-dur" type="number" value="8"></div>'+
        '<div style="margin-bottom:14px"><div class="lbl">Target group</div><select class="inp" id="cl-group" onchange="updateColorlightTerminals()">'+
          '<option value="">— Select a group —</option>'+
          groups.map(g=>'<option value="'+g.group_id+'">'+(g.group_name||'(unnamed)')+' ('+g.terminal_count+' terminals)</option>').join('')+
        '</select></div>'+
        '<div style="margin-bottom:14px"><div class="lbl">Target terminal(s)</div><div id="cl-terms-list" style="padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--bg-1);min-height:60px;font-size:12px;color:var(--t-4)">Select a group first…</div></div>'+
        '<button class="btn-p" id="cl-push-btn" onclick="pushToColorlight()" style="width:100%;justify-content:center;padding:14px;font-size:14px">⚡ Push to LED Screens</button>'+
        '<p id="cl-push-msg" style="font-size:12px;margin-top:12px;text-align:center;display:none"></p>'+
      '</div>'+
    '</div>'+
    // RIGHT — Terminal listing
    '<div>'+
      '<h3 style="font-size:13px;font-weight:700;margin-bottom:10px;color:var(--t-3);text-transform:uppercase;letter-spacing:.6px">Available Terminals</h3>'+
      (groups.length===0?'<div class="card" style="padding:24px;color:var(--t-4);text-align:center">No groups found in your ColorlightCloud account.</div>':
        '<div style="display:flex;flex-direction:column;gap:10px">'+groups.map(g=>
          '<div class="card" style="padding:14px">'+
            '<div style="font-size:13px;font-weight:700;margin-bottom:8px">'+(g.group_name||'(unnamed)')+' <span style="font-size:10px;color:var(--t-4);font-weight:500">#'+g.group_id+'</span></div>'+
            (g.terminals.length===0?'<div style="font-size:11px;color:var(--t-4)">No terminals</div>':
              '<div style="display:flex;flex-direction:column;gap:6px">'+g.terminals.map(t=>
                '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg-1);border-radius:6px">'+
                  '<span style="width:6px;height:6px;border-radius:50%;background:'+(t.online?'var(--green-l)':'var(--t-4)')+'"></span>'+
                  '<span style="font-size:12px;font-weight:600;flex:1">'+(t.name||'Terminal '+t.id)+'</span>'+
                  '<span style="font-size:10px;color:var(--t-4)">#'+t.id+'</span>'+
                '</div>').join('')+'</div>')+
          '</div>').join('')+'</div>')+
    '</div>'+
  '</div>';
  // cache groups for use in updateColorlightTerminals
  window._clGroups=groups;
}

async function saveColorlightSettings(){
  const server=document.getElementById('cl-server').value.trim();
  const username=document.getElementById('cl-user').value.trim();
  const password=document.getElementById('cl-pwd').value;
  const msg=document.getElementById('cl-msg');msg.style.display='none';
  if(!server||!username||!password){msg.textContent='All fields are required';msg.style.color='var(--red)';msg.style.display='block';return}
  try{
    msg.textContent='Testing connection…';msg.style.color='var(--t-4)';msg.style.display='block';
    const res=await api('/colorlight/settings',{method:'POST',body:JSON.stringify({server,username,password})});
    msg.textContent='✓ Connected ('+res.method+'). Loading…';msg.style.color='var(--green-l)';
    setTimeout(()=>loadColorlightPanel(),600);
  }catch(e){msg.textContent='✗ '+e.message;msg.style.color='var(--red)'}
}

async function resetColorlightSettings(){
  if(!confirm('Reset ColorlightCloud connection? You will need to re-enter credentials.'))return;
  try{await api('/colorlight/settings',{method:'POST',body:JSON.stringify({server:'',username:'',password:''})})}catch(e){/* local disconnect still applies */}
  // Just re-render setup form by treating as not configured
  document.getElementById('cl-panel').innerHTML='<div style="padding:24px;text-align:center;color:var(--t-4)">Resetting…</div>';
  setTimeout(async()=>{
    // Quick hack: directly render setup form
    const panel=document.getElementById('cl-panel');
    panel.innerHTML='<div class="card" style="padding:24px;max-width:560px"><h3 style="font-size:16px;font-weight:700;margin-bottom:6px">Reconnect to ColorlightCloud</h3>'+
      '<div style="margin-bottom:12px"><div class="lbl">Server</div><input class="inp" id="cl-server" value="us33.colorlightcloud.com"></div>'+
      '<div style="margin-bottom:12px"><div class="lbl">Username</div><input class="inp" id="cl-user" placeholder="josue"></div>'+
      '<div style="margin-bottom:16px"><div class="lbl">Password</div><input class="inp" id="cl-pwd" type="password"></div>'+
      '<button class="btn-p" onclick="saveColorlightSettings()" style="width:100%;justify-content:center">Test & Save</button>'+
      '<p id="cl-msg" style="font-size:12px;margin-top:12px;text-align:center;display:none"></p></div>';
  },300);
}

function updateColorlightTerminals(){
  const gid=parseInt(document.getElementById('cl-group').value);
  const box=document.getElementById('cl-terms-list');
  const g=(window._clGroups||[]).find(x=>x.group_id===gid);
  if(!g||!g.terminals.length){box.innerHTML='<span style="color:var(--t-4)">No terminals in this group</span>';return}
  box.innerHTML='<div style="display:flex;flex-direction:column;gap:6px">'+
    '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px;font-weight:600;color:var(--t-2);margin-bottom:4px"><input type="checkbox" id="cl-t-all" onchange="document.querySelectorAll(\'.cl-t-chk\').forEach(c=>c.checked=this.checked)"> Select all</label>'+
    g.terminals.map(t=>'<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:12px"><input type="checkbox" class="cl-t-chk" value="'+t.id+'"> <span style="width:6px;height:6px;border-radius:50%;background:'+(t.online?'var(--green-l)':'var(--t-4)')+'"></span> '+(t.name||'Terminal '+t.id)+' <span style="color:var(--t-4)">#'+t.id+'</span></label>').join('')+'</div>';
}

async function pushToColorlight(){
  const title=document.getElementById('cl-title').value.trim();
  const file=document.getElementById('cl-file').files[0];
  const gid=parseInt(document.getElementById('cl-group').value);
  const w=parseInt(document.getElementById('cl-w').value)||192;
  const h=parseInt(document.getElementById('cl-h').value)||320;
  const dur=(parseInt(document.getElementById('cl-dur').value)||8)*1000;
  const termIds=Array.from(document.querySelectorAll('.cl-t-chk:checked')).map(c=>parseInt(c.value));
  const msg=document.getElementById('cl-push-msg');msg.style.display='none';
  const btn=document.getElementById('cl-push-btn');
  if(!title){msg.textContent='Enter a title';msg.style.color='var(--red)';msg.style.display='block';return}
  if(!file){msg.textContent='Select a media file';msg.style.color='var(--red)';msg.style.display='block';return}
  if(!gid){msg.textContent='Select a target group';msg.style.color='var(--red)';msg.style.display='block';return}
  if(!termIds.length){msg.textContent='Select at least one terminal';msg.style.color='var(--red)';msg.style.display='block';return}
  // Convert file to base64
  const b64=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=rej;r.readAsDataURL(file)});
  btn.disabled=true;btn.style.opacity='.6';
  msg.textContent='Uploading & publishing… (this may take 10-30s)';msg.style.color='var(--t-4)';msg.style.display='block';
  try{
    const res=await api('/colorlight/push',{method:'POST',body:JSON.stringify({
      title,media_base64:b64,filename:file.name,content_type:file.type||'image/jpeg',
      group_id:gid,terminal_ids:termIds,mode:'single',width:w,height:h,duration_ms:dur
    })});
    msg.textContent='✓ Published successfully! Program #'+res.program_id+' sent to '+termIds.length+' terminal(s).';
    msg.style.color='var(--green-l)';
    document.getElementById('cl-title').value='';
    document.getElementById('cl-file').value='';
  }catch(e){msg.textContent='✗ '+e.message;msg.style.color='var(--red)'}
  finally{btn.disabled=false;btn.style.opacity='1'}
}

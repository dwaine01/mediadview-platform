// MediaView Dashboard v2 — Complete SPA
const API='/api';let token=localStorage.getItem('mv_t'),user=JSON.parse(localStorage.getItem('mv_u')||'null');
let wizardData={step:0,screen:null,name:'',startDate:'',endDate:'',startTime:'08:00',endTime:'22:00',duration:15,mediaId:null,pricing:null};

async function api(p,o={}){const h={'Content-Type':'application/json',...(o.headers||{})};if(token)h['Authorization']='Bearer '+token;const r=await fetch(API+p,{...o,headers:h});if(r.status===401){doLogout();throw new Error('Session expired')}if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Error')}return r.json()}
async function doLogin(){const e=document.getElementById('in-email').value,p=document.getElementById('in-pwd').value,err=document.getElementById('login-err');err.style.display='none';try{const d=await api('/auth/login',{method:'POST',body:JSON.stringify({email:e,password:p})});token=d.access_token;user=d.user;localStorage.setItem('mv_t',token);localStorage.setItem('mv_u',JSON.stringify(user));enterApp()}catch(x){err.textContent=x.message;err.style.display='block'}}
function doLogout(){token=null;user=null;localStorage.removeItem('mv_t');localStorage.removeItem('mv_u');document.getElementById('view-login').classList.remove('off');document.getElementById('view-app').classList.remove('on')}
function enterApp(){document.getElementById('view-login').classList.add('off');document.getElementById('view-app').classList.add('on');document.getElementById('sb-name').textContent=user?.name||'User';document.getElementById('sb-email').textContent=user?.email||'';document.getElementById('sb-av').textContent=(user?.name||'U')[0].toUpperCase();go('dashboard')}
document.getElementById('in-pwd')?.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin()});
function go(p){document.querySelectorAll('.pg').forEach(x=>x.classList.remove('on'));document.getElementById('pg-'+p)?.classList.add('on');document.querySelectorAll('.ni').forEach(n=>n.classList.remove('on'));document.querySelector(`[data-p="${p}"]`)?.classList.add('on');loaders[p]?.()}
function badge(s){return`<span class="badge badge-${s}">${s}</span>`}
function dot(s){const m={active:'#34d399',pending:'#fbbf24',approved:'#60a5fa',rejected:'#f87171',draft:'#94a3b8',completed:'#a78bfa'};return m[s]||'#94a3b8'}
const SG=['linear-gradient(135deg,#2563eb,#1e40af)','linear-gradient(135deg,#ea580c,#c2410c)','linear-gradient(135deg,#0d9488,#0f766e)','linear-gradient(135deg,#7c3aed,#6d28d9)','linear-gradient(135deg,#d97706,#b45309)','linear-gradient(135deg,#db2777,#be185d)','linear-gradient(135deg,#059669,#047857)','linear-gradient(135deg,#4f46e5,#4338ca)','linear-gradient(135deg,#0891b2,#0e7490)','linear-gradient(135deg,#e11d48,#be123c)'];
function stat(l,v,s,cv,ic){return`<div class="stat-card" style="border-left-color:var(${cv})"><div style="display:flex;align-items:center;gap:8px"><div style="width:32px;height:32px;border-radius:8px;background:color-mix(in srgb,var(${cv}) 12%,transparent);display:flex;align-items:center;justify-content:center"><svg width="16" height="16" fill="none" stroke="var(${cv})" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg></div><span style="font-size:11px;font-weight:600;color:var(--t-3)">${l}</span></div><div class="stat-value" style="color:var(${cv})">${v}</div><div class="stat-sub">${s}</div></div>`}
function actCard(l,d,c,ic,p){return`<div class="card card-interactive" style="display:flex;align-items:center;gap:12px;padding:14px;cursor:pointer" onclick="go('${p}')"><div style="width:36px;height:36px;border-radius:10px;background:${c}15;border:1px solid ${c}25;display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="16" height="16" fill="none" stroke="${c}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg></div><div style="flex:1"><div style="font-size:13px;font-weight:600">${l}</div><div style="font-size:10px;color:var(--t-4)">${d}</div></div><svg width="14" height="14" fill="none" stroke="var(--t-4)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></div>`}

const loaders={
  async dashboard(){
    const el=document.getElementById('pg-dashboard');
    try{
      const d=await api('/analytics/dashboard');let a=null;if(user?.role==='admin')try{a=await api('/admin/analytics')}catch(e){}
      const rev=a?.total_revenue||d.total_spent||0,scr=a?.active_screens||d.active_campaigns||0,camp=d.total_campaigns||0,pend=d.pending_campaigns||0;
      const screens=await api('/screens');
      el.innerHTML=`
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px">
          <div><p style="font-size:11px;font-weight:700;color:var(--brand-l);text-transform:uppercase;letter-spacing:3px;margin-bottom:6px">Welcome back</p><h1 style="font-size:32px;font-weight:800;letter-spacing:-.5px">${user?.name}</h1><p style="color:var(--t-3);font-size:14px;margin-top:4px">Your digital signage network overview</p></div>
          <button class="btn-primary" onclick="go('create')"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14m7-7H5"/></svg>New Campaign</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:32px">
          ${stat('Revenue','$'+rev.toLocaleString(),'All time','--cyan','M13 7h8m0 0v8m0-8l-8 8-4-4-6 6')}
          ${stat('Screens',scr,'Online now','--green','M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z')}
          ${stat('Campaigns',camp,'Total created','--brand-l','M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2')}
          ${stat('Pending',pend,'Awaiting review','--amber','M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z')}
        </div>
        <div style="display:grid;grid-template-columns:5fr 4fr 3fr;gap:20px">
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h2 style="font-size:16px;font-weight:700">Recent Campaigns</h2><a onclick="go('campaigns')" style="font-size:12px;color:var(--brand-l);cursor:pointer;font-weight:600">View All →</a></div>
            <div class="card">${(d.recent_campaigns||[]).length===0?'<div style="padding:40px;text-align:center;color:var(--t-4)">No campaigns yet</div>':(d.recent_campaigns||[]).map((c,i)=>`<div class="list-row" onclick="go('campaigns')"><div class="list-dot" style="background:${dot(c.status)}"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.name}</div><div style="font-size:11px;color:var(--t-4)">${c.screen_name||''} · ${c.schedule?.start_date||''}</div></div>${badge(c.status)}</div>`).join('')}</div>
          </div>
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h2 style="font-size:16px;font-weight:700">Active Screens</h2><a onclick="go('screens')" style="font-size:12px;color:var(--brand-l);cursor:pointer;font-weight:600">Browse →</a></div>
            <div class="card">${screens.slice(0,6).map((s,i)=>`<div class="list-row" onclick="go('screens')"><div class="list-dot" style="background:#34d399"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.name}</div><div style="font-size:11px;color:var(--t-4)">${s.location?.city}, ${s.location?.state}</div></div><div style="font-size:14px;font-weight:700;color:var(--cyan)">$${s.pricing?.per_hour}<span style="font-size:10px;color:var(--t-4);font-weight:400">/hr</span></div></div>`).join('')}</div>
          </div>
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Quick Actions</h2>
            <div style="display:flex;flex-direction:column;gap:8px">
              ${actCard('Create Campaign','Launch new ad','#6366f1','M12 5v14m7-7H5','create')}
              ${actCard('Browse Screens','Explore displays','#22d3ee','M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z','screens')}
              ${actCard('Analytics','View reports','#a78bfa','M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10','analytics')}
              ${user?.role==='admin'?actCard('Admin Panel','Manage platform','#fbbf24','M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z','admin'):''}
            </div>
          </div>
        </div>`;
    }catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}
  },

  async screens(){const el=document.getElementById('pg-screens');try{const d=await api('/screens');el.innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Screens</h1><p style="color:var(--t-3);font-size:14px;margin-bottom:24px">${d.length} LED displays available</p><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">${d.map((s,i)=>`<div class="screen-card card-interactive"><div class="header" style="background:${SG[i%SG.length]}"><div class="city">${s.location?.city}, ${s.location?.state}</div></div><div class="body"><div class="name">${s.name}</div><div class="addr">${s.location?.address}</div><div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11px;color:var(--t-3)">${s.specs?.size||''} · ${s.specs?.resolution||''}</span><div class="price">$${s.pricing?.per_hour}<span>/hr</span></div></div></div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  async campaigns(){const el=document.getElementById('pg-campaigns');try{const d=await api('/campaigns');el.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px"><div><h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Campaigns</h1><p style="color:var(--t-3);font-size:14px">${d.length} campaigns</p></div><button class="btn-primary" onclick="go('create')">+ New Campaign</button></div><div style="display:flex;flex-direction:column;gap:8px">${d.length===0?'<div class="card" style="padding:48px;text-align:center;color:var(--t-4)">No campaigns yet</div>':d.map(c=>`<div class="card card-interactive" style="display:flex;align-items:center;gap:12px;padding:16px;cursor:pointer"><div style="width:3px;height:40px;border-radius:2px;background:${dot(c.status)};flex-shrink:0"></div><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700">${c.name}</div><div style="font-size:12px;color:var(--t-4);margin-top:2px">${c.screen?.name||''} · ${c.schedule?.start_date||''} → ${c.schedule?.end_date||''}</div></div>${badge(c.status)}<div style="font-size:20px;font-weight:800;color:var(--cyan);min-width:100px;text-align:right">$${(c.pricing?.total||0).toLocaleString()}</div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  async payments(){const el=document.getElementById('pg-payments');try{const d=await api('/payments');el.innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Payments</h1><p style="color:var(--t-3);font-size:14px;margin-bottom:24px">${d.length} transactions</p><div style="display:flex;flex-direction:column;gap:8px">${d.length===0?'<div class="card" style="padding:48px;text-align:center;color:var(--t-4)">No payments</div>':d.map(p=>`<div class="card" style="display:flex;align-items:center;gap:14px;padding:16px"><div style="width:40px;height:40px;border-radius:10px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="18" height="18" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700">${p.campaign_name||'Campaign'}</div><div style="font-size:12px;color:var(--t-4)">${p.invoice_number} · ${p.screen_name||''}</div></div><span class="badge badge-${p.status==='completed'?'active':'pending'}">${p.status}</span><div style="font-size:22px;font-weight:800;min-width:110px;text-align:right">$${(p.amount||0).toLocaleString()}</div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  // Campaign Creation Wizard
  async create(){
    const el=document.getElementById('pg-create');
    if(wizardData.step===0){
      const screens=await api('/screens');
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Create Campaign</h1>
        <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">Launch a new advertising campaign</p>
        <div class="wizard-steps">
          <div class="wizard-step active"><div class="num">1</div>Screen</div><div class="wizard-conn"></div>
          <div class="wizard-step"><div class="num">2</div>Schedule</div><div class="wizard-conn"></div>
          <div class="wizard-step"><div class="num">3</div>Media</div><div class="wizard-conn"></div>
          <div class="wizard-step"><div class="num">4</div>Review</div>
        </div>
        <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Select a Screen</h2>
        <div class="screen-select">${screens.map((s,i)=>`
          <div class="screen-opt ${wizardData.screen?.id===s.id?'selected':''}" onclick="selectScreen(${JSON.stringify(s).replace(/"/g,'&quot;')})">
            <div style="display:flex;gap:12px;align-items:center">
              <div style="width:48px;height:48px;border-radius:12px;background:${SG[i%SG.length]};flex-shrink:0"></div>
              <div><div style="font-size:14px;font-weight:700">${s.name}</div><div style="font-size:11px;color:var(--t-4)">${s.location?.city} · $${s.pricing?.per_hour}/hr</div></div>
            </div>
          </div>`).join('')}</div>
        <div style="display:flex;justify-content:flex-end;margin-top:24px">
          <button class="btn-primary" onclick="wizardNext()" ${!wizardData.screen?'disabled style="opacity:.4"':''}>Next: Schedule →</button>
        </div>`;
    } else if(wizardData.step===1){
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Create Campaign</h1>
        <div class="wizard-steps">
          <div class="wizard-step done"><div class="num">✓</div>Screen</div><div class="wizard-conn done"></div>
          <div class="wizard-step active"><div class="num">2</div>Schedule</div><div class="wizard-conn"></div>
          <div class="wizard-step"><div class="num">3</div>Media</div><div class="wizard-conn"></div>
          <div class="wizard-step"><div class="num">4</div>Review</div>
        </div>
        <div style="max-width:600px">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Campaign Details</h2>
          <div style="margin-bottom:16px"><label class="input-label">Campaign Name</label><input class="input" id="wz-name" value="${wizardData.name}" placeholder="e.g. Summer Sale Promo"></div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label class="input-label">Start Date</label><input class="input" id="wz-sd" type="date" value="${wizardData.startDate}"></div>
            <div><label class="input-label">End Date</label><input class="input" id="wz-ed" type="date" value="${wizardData.endDate}"></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
            <div><label class="input-label">Start Time</label><select class="input" id="wz-st">${['06:00','08:00','10:00','12:00','14:00','16:00','18:00','20:00','22:00'].map(t=>`<option value="${t}" ${wizardData.startTime===t?'selected':''}>${t}</option>`).join('')}</select></div>
            <div><label class="input-label">End Time</label><select class="input" id="wz-et">${['06:00','08:00','10:00','12:00','14:00','16:00','18:00','20:00','22:00'].map(t=>`<option value="${t}" ${wizardData.endTime===t?'selected':''}>${t}</option>`).join('')}</select></div>
          </div>
          <label class="input-label">Slot Duration</label>
          <div style="display:flex;gap:8px;margin-bottom:20px">${[10,15,30].map(d=>`<button onclick="wizardData.duration=${d};loaders.create()" style="flex:1;padding:12px;border-radius:var(--radius-sm);border:2px solid ${wizardData.duration===d?'var(--brand)':'var(--border)'};background:${wizardData.duration===d?'rgba(99,102,241,.08)':'var(--bg-2)'};color:${wizardData.duration===d?'var(--brand-l)':'var(--t-3)'};font-size:16px;font-weight:700;cursor:pointer">${d}s</button>`).join('')}</div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=0;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button class="btn-primary" onclick="wizardNext()">Next: Media →</button>
          </div>
        </div>`;
    } else if(wizardData.step===2){
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Create Campaign</h1>
        <div class="wizard-steps">
          <div class="wizard-step done"><div class="num">✓</div>Screen</div><div class="wizard-conn done"></div>
          <div class="wizard-step done"><div class="num">✓</div>Schedule</div><div class="wizard-conn done"></div>
          <div class="wizard-step active"><div class="num">3</div>Media</div><div class="wizard-conn"></div>
          <div class="wizard-step"><div class="num">4</div>Review</div>
        </div>
        <div style="max-width:600px">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Upload Media</h2>
          <div id="wz-media-area" style="border:2px dashed var(--border);border-radius:var(--radius);padding:48px;text-align:center;cursor:pointer" onclick="document.getElementById('wz-file').click()">
            <svg width="48" height="48" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
            <p style="color:var(--t-2);font-weight:600">Click to upload image</p>
            <p style="color:var(--t-4);font-size:12px;margin-top:4px">JPG, PNG — Optimized for 1920×1080</p>
          </div>
          <input type="file" id="wz-file" accept="image/*" style="display:none" onchange="uploadMedia(this)">
          <div id="wz-media-status" style="margin-top:12px"></div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=1;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button class="btn-primary" onclick="wizardNext()" ${!wizardData.mediaId?'disabled style="opacity:.4"':''}>Next: Review →</button>
          </div>
        </div>`;
    } else if(wizardData.step===3){
      let pricing=null;
      try{pricing=await api('/screens/'+wizardData.screen.id+'/calculate-price',{method:'POST',body:JSON.stringify({start_date:wizardData.startDate,end_date:wizardData.endDate,start_time:wizardData.startTime,end_time:wizardData.endTime,slot_duration:wizardData.duration,frequency:5})});wizardData.pricing=pricing}catch(e){}
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Create Campaign</h1>
        <div class="wizard-steps">
          <div class="wizard-step done"><div class="num">✓</div>Screen</div><div class="wizard-conn done"></div>
          <div class="wizard-step done"><div class="num">✓</div>Schedule</div><div class="wizard-conn done"></div>
          <div class="wizard-step done"><div class="num">✓</div>Media</div><div class="wizard-conn done"></div>
          <div class="wizard-step active"><div class="num">4</div>Review</div>
        </div>
        <div style="max-width:600px">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:16px">Review & Confirm</h2>
          <div class="card" style="padding:20px;margin-bottom:12px"><div style="font-size:12px;color:var(--t-3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Campaign</div><div style="font-size:16px;font-weight:700">${wizardData.name}</div></div>
          <div class="card" style="padding:20px;margin-bottom:12px"><div style="font-size:12px;color:var(--t-3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Screen</div><div style="font-size:16px;font-weight:700">${wizardData.screen?.name}</div><div style="font-size:12px;color:var(--t-4)">${wizardData.screen?.location?.city}</div></div>
          <div class="card" style="padding:20px;margin-bottom:12px"><div style="font-size:12px;color:var(--t-3);text-transform:uppercase;font-weight:600;margin-bottom:6px">Schedule</div><div style="font-size:14px">${wizardData.startDate} → ${wizardData.endDate}</div><div style="font-size:12px;color:var(--t-4)">${wizardData.startTime} - ${wizardData.endTime} · ${wizardData.duration}s slots</div></div>
          ${pricing?`<div class="price-box"><div class="price-row"><span style="color:var(--t-3)">${pricing.total_hours} hours × $${pricing.per_hour}/hr</span><span>$${pricing.subtotal?.toLocaleString()}</span></div><div class="price-row"><span style="color:var(--t-3)">Tax (8%)</span><span>$${pricing.tax?.toLocaleString()}</span></div><div class="price-total"><span>Total</span><span style="color:var(--cyan)">$${pricing.total?.toLocaleString()}</span></div></div>`:''}
          <div style="background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.15);border-radius:var(--radius-sm);padding:12px;margin-top:16px;font-size:12px;color:var(--amber)">Payment: **** **** **** 4242 (Simulated)</div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=2;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button class="btn-primary" onclick="submitCampaign()" style="background:linear-gradient(135deg,#10b981,#059669);box-shadow:0 4px 14px rgba(16,185,129,.3)">✓ Pay & Submit Campaign</button>
          </div>
        </div>`;
    }
  },

  // Analytics
  async analytics(){
    const el=document.getElementById('pg-analytics');
    try{
      const d=await api('/analytics/dashboard');let a=null;if(user?.role==='admin')try{a=await api('/admin/analytics')}catch(e){}
      const rev=a?.total_revenue||d.total_spent||0;const monthly=a?.monthly_revenue||{};
      const months=Object.keys(monthly).sort().slice(-6);const maxVal=Math.max(...Object.values(monthly).map(Number),1);
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Analytics</h1>
        <p style="color:var(--t-3);font-size:14px;margin-bottom:24px">Platform performance overview</p>
        <div style="display:grid;grid-template-columns:2fr 1fr;gap:20px">
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:16px">Monthly Revenue</h2>
            <div class="card" style="padding:24px">
              ${months.length===0?'<p style="color:var(--t-4);text-align:center;padding:24px">No revenue data yet</p>':months.map(m=>{const v=monthly[m]||0;const pct=Math.round(v/maxVal*100);return`<div class="chart-bar-row"><div class="chart-bar-label">${m.substring(5)}</div><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${pct}%;background:linear-gradient(90deg,var(--brand),var(--cyan))">$${v.toLocaleString()}</div></div></div>`}).join('')}
            </div>
          </div>
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:16px">Campaign Status</h2>
            <div class="card" style="padding:24px">
              ${[{l:'Active',v:d.active_campaigns||0,c:'var(--green)'},{l:'Pending',v:d.pending_campaigns||0,c:'var(--amber)'},{l:'Total',v:d.total_campaigns||0,c:'var(--brand-l)'}].map(s=>`
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
    if(user?.role!=='admin'){el.innerHTML='<p style="color:var(--red)">Admin access required</p>';return}
    try{
      const [users,campaigns,analyticsData]=await Promise.all([api('/admin/users'),api('/admin/campaigns'),api('/admin/analytics')]);
      el.innerHTML=`
        <h1 style="font-size:28px;font-weight:800;margin-bottom:24px">Admin Panel</h1>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Users (${users.length})</h2>
            <div class="card">
              <div class="table-header" style="grid-template-columns:1fr 1fr auto""><span>Name</span><span>Email</span><span>Status</span></div>
              ${users.map(u=>`<div class="table-row" style="grid-template-columns:1fr 1fr auto"><span style="font-size:13px;font-weight:600">${u.name}</span><span style="font-size:12px;color:var(--t-3)">${u.email}</span><span class="${u.active!==false?'tag-online':'tag-offline'}">${u.active!==false?'Active':'Disabled'}</span></div>`).join('')}
            </div>
          </div>
          <div>
            <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Campaigns (${campaigns.length})</h2>
            <div class="card">
              ${campaigns.slice(0,8).map(c=>`<div class="list-row"><div class="list-dot" style="background:${dot(c.status)}"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600">${c.name}</div><div style="font-size:11px;color:var(--t-4)">${c.user?.name||''} · $${(c.pricing?.total||0).toLocaleString()}</div></div>${badge(c.status)}${c.status==='pending'?`<button onclick="approveCamp('${c.id}')" style="padding:4px 12px;border-radius:6px;background:rgba(52,211,153,.12);color:var(--green);font-size:11px;font-weight:700;border:none;cursor:pointer">Approve</button>`:''}</div>`).join('')}
            </div>
          </div>
        </div>`;
    }catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}
  },

  devices(){document.getElementById('pg-devices').innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Devices</h1><p style="color:var(--t-3);font-size:14px;margin-bottom:24px">Connected players</p><div class="card" style="padding:48px;text-align:center"><svg width="48" height="48" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px"><path d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg><p style="font-size:16px;font-weight:600;color:var(--t-2)">Device Management</p><p style="font-size:13px;color:var(--t-4)">Install MediaView Player on a TV to see devices here</p></div>`},

  settings(){document.getElementById('pg-settings').innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:28px">Settings</h1><div style="max-width:560px"><div style="display:flex;align-items:center;gap:16px;margin-bottom:32px"><div style="width:64px;height:64px;border-radius:16px;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:900;color:#fff;box-shadow:0 4px 15px rgba(99,102,241,.25)">${(user?.name||'U')[0]}</div><div><div style="font-size:20px;font-weight:700">${user?.name}</div><div style="font-size:13px;color:var(--t-3)">${user?.email}</div><span class="badge" style="margin-top:6px;background:${user?.role==='admin'?'rgba(99,102,241,.12)':'rgba(52,211,153,.12)'};color:${user?.role==='admin'?'var(--brand-l)':'var(--green)'}">${user?.role==='admin'?'Administrator':'Customer'}</span></div></div><div class="card" style="margin-bottom:20px"><div style="padding:14px 20px;border-bottom:1px solid var(--border);font-size:10px;font-weight:700;color:var(--t-2);text-transform:uppercase;letter-spacing:1.5px">Account</div>${[['Name',user?.name],['Email',user?.email],['Company',user?.company_name||'—'],['Role',user?.role]].map(([l,v])=>`<div style="padding:14px 20px;display:flex;justify-content:space-between;border-bottom:1px solid rgba(30,41,59,.2)"><span style="font-size:13px;color:var(--t-3)">${l}</span><span style="font-size:13px;font-weight:600">${v}</span></div>`).join('')}</div><button onclick="doLogout()" style="width:100%;padding:12px;border-radius:var(--radius-sm);background:none;border:1px solid var(--bg-3);color:var(--t-3);font-size:13px;cursor:pointer">Sign Out</button></div>`}
};

// Wizard helpers
function selectScreen(s){wizardData.screen=s;loaders.create()}
function wizardNext(){
  if(wizardData.step===1){wizardData.name=document.getElementById('wz-name')?.value||'';wizardData.startDate=document.getElementById('wz-sd')?.value||'';wizardData.endDate=document.getElementById('wz-ed')?.value||'';wizardData.startTime=document.getElementById('wz-st')?.value||'08:00';wizardData.endTime=document.getElementById('wz-et')?.value||'22:00'}
  wizardData.step++;loaders.create()
}
async function uploadMedia(input){
  const file=input.files[0];if(!file)return;
  const st=document.getElementById('wz-media-status');st.innerHTML='<p style="color:var(--brand-l)">Uploading...</p>';
  const reader=new FileReader();reader.onload=async function(){
    const b64=reader.result.split(',')[1];
    try{const r=await api('/media/upload',{method:'POST',body:JSON.stringify({filename:file.name,content_type:file.type,data:b64})});wizardData.mediaId=r.id;
      st.innerHTML=`<div class="card" style="padding:12px;display:flex;align-items:center;gap:10px"><svg width="20" height="20" fill="none" stroke="var(--green)" stroke-width="2" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg><span style="font-size:13px;font-weight:600;color:var(--green)">${file.name} uploaded</span></div>`;
      loaders.create()
    }catch(e){st.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}
  };reader.readAsDataURL(file)
}
async function submitCampaign(){
  try{
    const r=await api('/campaigns',{method:'POST',body:JSON.stringify({name:wizardData.name,screen_id:wizardData.screen.id,schedule:{start_date:wizardData.startDate,end_date:wizardData.endDate,start_time:wizardData.startTime,end_time:wizardData.endTime,slot_duration:wizardData.duration,frequency:5},media_ids:wizardData.mediaId?[wizardData.mediaId]:[]})});
    await api('/payments',{method:'POST',body:JSON.stringify({campaign_id:r.id,method:'card',card_last4:'4242'})});
    wizardData={step:0,screen:null,name:'',startDate:'',endDate:'',startTime:'08:00',endTime:'22:00',duration:15,mediaId:null,pricing:null};
    alert('Campaign submitted for review!');go('campaigns')
  }catch(e){alert('Error: '+e.message)}
}
async function approveCamp(id){try{await api('/admin/campaigns/'+id+'/approve',{method:'PUT'});loaders.admin()}catch(e){alert(e.message)}}

if(token&&user){enterApp()}

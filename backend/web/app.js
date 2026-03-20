// MediAd View Dashboard v2 — Complete SPA
const API='/api';let token=localStorage.getItem('mv_t'),user=JSON.parse(localStorage.getItem('mv_u')||'null');
let wizardData={step:0,screen:null,name:'',startDate:'',endDate:'',startTime:'08:00',endTime:'22:00',duration:15,mediaId:null,pricing:null};

async function api(p,o={}){const h={'Content-Type':'application/json',...(o.headers||{})};if(token)h['Authorization']='Bearer '+token;const r=await fetch(API+p,{...o,headers:h});if(r.status===401){doLogout();throw new Error('Session expired')}if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||'Error')}return r.json()}
async function doLogin(){const e=document.getElementById('in-email').value,p=document.getElementById('in-pwd').value,err=document.getElementById('login-err');err.style.display='none';try{const d=await api('/auth/login',{method:'POST',body:JSON.stringify({email:e,password:p})});token=d.access_token;user=d.user;localStorage.setItem('mv_t',token);localStorage.setItem('mv_u',JSON.stringify(user));enterApp()}catch(x){err.textContent=x.message;err.style.display='block'}}
function doLogout(){token=null;user=null;localStorage.removeItem('mv_t');localStorage.removeItem('mv_u');document.getElementById('view-login').classList.remove('off');document.getElementById('view-app').classList.remove('on')}
function enterApp(){
  document.getElementById('view-login').classList.add('off');document.getElementById('view-app').classList.add('on');
  document.getElementById('sb-name').textContent=user?.name||'User';document.getElementById('sb-email').textContent=user?.email||'';
  document.getElementById('sb-av').textContent=(user?.name||'U')[0].toUpperCase();
  // Show/hide role-specific nav items
  document.querySelectorAll('[data-p="admin"]').forEach(e=>e.style.display=user?.role==='admin'||user?.role==='superadmin'?'':'none');
  document.querySelectorAll('[data-p="superadmin"]').forEach(e=>e.style.display=user?.role==='superadmin'?'':'none');
  go('dashboard');
}
document.getElementById('in-pwd')?.addEventListener('keydown',e=>{if(e.key==='Enter')doLogin()});
function go(p){document.querySelectorAll('.pg').forEach(x=>x.classList.remove('on'));document.getElementById('pg-'+p)?.classList.add('on');document.querySelectorAll('.ni').forEach(n=>n.classList.remove('on'));document.querySelector(`[data-p="${p}"]`)?.classList.add('on');loaders[p]?.()}
function badge(s){return`<span class="bdg bdg-${s}">${s}</span>`}
function dot(s){const m={active:'#34d399',pending:'#fbbf24',approved:'#60a5fa',rejected:'#f87171',draft:'#94a3b8',completed:'#a78bfa'};return m[s]||'#94a3b8'}
const SG=['linear-gradient(135deg,#2563eb,#1e40af)','linear-gradient(135deg,#ea580c,#c2410c)','linear-gradient(135deg,#0d9488,#0f766e)','linear-gradient(135deg,#7c3aed,#6d28d9)','linear-gradient(135deg,#d97706,#b45309)','linear-gradient(135deg,#db2777,#be185d)','linear-gradient(135deg,#059669,#047857)','linear-gradient(135deg,#4f46e5,#4338ca)','linear-gradient(135deg,#0891b2,#0e7490)','linear-gradient(135deg,#e11d48,#be123c)'];
function stat(l,v,s,cv,ic){return`<div class="st-card" style="border-left-color:var(${cv})"><div style="display:flex;align-items:center;gap:8px"><div class="st-ico" style="background:color-mix(in srgb,var(${cv}) 12%,transparent)"><svg width="16" height="16" fill="none" stroke="var(${cv})" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg></div><span style="font-size:11px;font-weight:600;color:var(--t-3)">${l}</span></div><div class="st-val" style="color:var(${cv})">${v}</div><div class="st-sub">${s}</div></div>`}
function actCard(l,d,c,ic,p){return`<div class="card card-i" style="display:flex;align-items:center;gap:12px;padding:14px" onclick="go('${p}')"><div style="width:36px;height:36px;border-radius:10px;background:${c}15;border:1px solid ${c}25;display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="16" height="16" fill="none" stroke="${c}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${ic}"/></svg></div><div style="flex:1"><div style="font-size:13px;font-weight:600">${l}</div><div style="font-size:10px;color:var(--t-4)">${d}</div></div><svg width="14" height="14" fill="none" stroke="var(--t-4)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></div>`}

const loaders={
  async dashboard(){
    const el=document.getElementById('pg-dashboard');
    try{
      const d=await api('/analytics/dashboard');let a=null;if(user?.role==='admin')try{a=await api('/admin/analytics')}catch(e){}
      const rev=a?.total_revenue||d.total_spent||0,scr=a?.active_screens||d.active_campaigns||0,camp=a?.total_campaigns||d.total_campaigns||0,pend=a?.pending_campaigns||d.pending_campaigns||0;
      const screens=await api('/screens');
      const recentCamps=a?.recent_campaigns||d.recent_campaigns||[];
      el.innerHTML=`
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px">
          <div><p style="font-size:11px;font-weight:700;color:var(--brand-l);text-transform:uppercase;letter-spacing:3px;margin-bottom:6px">Welcome back</p><h1 style="font-size:32px;font-weight:800;letter-spacing:-.5px">${user?.name}</h1><p style="color:var(--t-3);font-size:14px;margin-top:4px">Your digital signage network overview</p></div>
          <button class="btn-p" onclick="go('create')"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 5v14m7-7H5"/></svg>New Campaign</button>
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
            <div class="card">${(recentCamps).length===0?'<div style="padding:40px;text-align:center;color:var(--t-4)">No campaigns yet</div>':(recentCamps).map((c,i)=>`<div class="lr" onclick="go('campaigns')"><div class="dot" style="background:${dot(c.status)}"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.name}</div><div style="font-size:11px;color:var(--t-4)">${c.user_name||c.screen_name||''} · ${c.schedule?.start_date||''}</div></div>${badge(c.status)}</div>`).join('')}</div>
          </div>
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h2 style="font-size:16px;font-weight:700">Active Screens</h2><a onclick="go('screens')" style="font-size:12px;color:var(--brand-l);cursor:pointer;font-weight:600">Browse →</a></div>
            <div class="card">${screens.slice(0,6).map((s,i)=>`<div class="lr" onclick="go('screens')"><div class="dot" style="background:#34d399"></div><div style="flex:1;min-width:0"><div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${s.name}</div><div style="font-size:11px;color:var(--t-4)">${s.location?.city}, ${s.location?.state}</div></div><div style="font-size:14px;font-weight:700;color:var(--cyan)">$${s.pricing?.per_hour}<span style="font-size:10px;color:var(--t-4);font-weight:400">/hr</span></div></div>`).join('')}</div>
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
        </div>
        <div style="margin-top:24px">
          <h2 style="font-size:16px;font-weight:700;margin-bottom:12px">Proof of Play (Last 7 Days)</h2>
          <div id="proof-of-play" class="card" style="padding:20px"><p style="color:var(--t-4)">Loading...</p></div>
        </div>`;
      // Load proof of play
      loadProofOfPlay();
    }catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}
  },

  async screens(){const el=document.getElementById('pg-screens');try{const d=await api('/screens');el.innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Screens</h1><p style="color:var(--t-3);font-size:14px;margin-bottom:24px">${d.length} LED displays available</p><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">${d.map((s,i)=>`<div class="sc card-i"><div class="hd" style="background:${SG[i%SG.length]}"><div class="city">${s.location?.city}, ${s.location?.state}</div></div><div class="ct"><div class="nm">${s.name}</div><div class="ad">${s.location?.address}</div><div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:11px;color:var(--t-3)">${s.specs?.size||''} · ${s.specs?.resolution||''}</span><div class="pr">$${s.pricing?.per_hour}<span>/hr</span></div></div></div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  async campaigns(){const el=document.getElementById('pg-campaigns');try{const d=user?.role==='admin'?await api('/admin/campaigns'):await api('/campaigns');el.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:24px"><div><h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Campaigns</h1><p style="color:var(--t-3);font-size:14px">${d.length} campaigns</p></div><button class="btn-p" onclick="go('create')">+ New Campaign</button></div><div style="display:flex;flex-direction:column;gap:8px">${d.length===0?'<div class="card" style="padding:48px;text-align:center;color:var(--t-4)">No campaigns yet</div>':d.map(c=>`<div class="card card-i" style="display:flex;align-items:center;gap:12px;padding:16px;cursor:pointer"><div style="width:3px;height:40px;border-radius:2px;background:${dot(c.status)};flex-shrink:0"></div><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700">${c.name}</div><div style="font-size:12px;color:var(--t-4);margin-top:2px">${c.user?.name||c.screen?.name||''} · ${c.schedule?.start_date||''} → ${c.schedule?.end_date||''}</div></div>${badge(c.status)}<div style="font-size:20px;font-weight:800;color:var(--cyan);min-width:100px;text-align:right">$${(c.pricing?.total||0).toLocaleString()}</div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

  async payments(){const el=document.getElementById('pg-payments');try{const d=user?.role==='admin'?await api('/admin/payments'):await api('/payments');el.innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:4px">Payments</h1><p style="color:var(--t-3);font-size:14px;margin-bottom:24px">${d.length} transactions</p><div style="display:flex;flex-direction:column;gap:8px">${d.length===0?'<div class="card" style="padding:48px;text-align:center;color:var(--t-4)">No payments</div>':d.map(p=>`<div class="card" style="display:flex;align-items:center;gap:14px;padding:16px"><div style="width:40px;height:40px;border-radius:10px;background:rgba(99,102,241,.1);display:flex;align-items:center;justify-content:center;flex-shrink:0"><svg width="18" height="18" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg></div><div style="flex:1;min-width:0"><div style="font-size:14px;font-weight:700">${p.campaign_name||'Campaign'}</div><div style="font-size:12px;color:var(--t-4)">${p.user_name?p.user_name+' · ':''}${p.invoice_number} · ${p.screen_name||''}</div></div><span class="bdg bdg-${p.status==='completed'?'active':'pending'}">${p.status}</span><div style="font-size:22px;font-weight:800;min-width:110px;text-align:right">$${(p.amount||0).toLocaleString()}</div></div>`).join('')}</div>`}catch(e){el.innerHTML=`<p style="color:var(--red)">${e.message}</p>`}},

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
          <div id="wz-media-area" style="border:2px dashed var(--border);border-radius:var(--radius);padding:48px;text-align:center;cursor:pointer" onclick="document.getElementById('wz-file').click()">
            <svg width="48" height="48" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
            <p style="color:var(--t-2);font-weight:600">Click to upload image</p>
            <p style="color:var(--t-4);font-size:12px;margin-top:4px">JPG, PNG — Optimized for 1920×1080</p>
          </div>
          <input type="file" id="wz-file" accept="image/*" style="display:none" onchange="uploadMedia(this)">
          <div id="wz-media-status" style="margin-top:12px"></div>
          <div style="display:flex;justify-content:space-between;margin-top:24px">
            <button onclick="wizardData.step=1;loaders.create()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">← Back</button>
            <button class="btn-p" onclick="wizardNext()" ${!wizardData.mediaId?'disabled style="opacity:.4"':''}>Next: Review →</button>
          </div>
        </div>`;
    } else if(wizardData.step===3){
      let pricing=null;
      try{pricing=await api('/screens/'+wizardData.screen.id+'/calculate-price',{method:'POST',body:JSON.stringify({start_date:wizardData.startDate,end_date:wizardData.endDate,start_time:wizardData.startTime,end_time:wizardData.endTime,slot_duration:wizardData.duration,frequency:5})});wizardData.pricing=pricing}catch(e){}
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
              ${months.length===0?'<p style="color:var(--t-4);text-align:center;padding:24px">No revenue data yet</p>':months.map(m=>{const v=monthly[m]||0;const pct=Math.round(v/maxVal*100);return`<div class="bar-r"><div class="bar-l">${m.substring(5)}</div><div class="bar-t"><div class="bar-f" style="width:${pct}%;background:linear-gradient(90deg,var(--brand),var(--cyan))">$${v.toLocaleString()}</div></div></div>`}).join('')}
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
    if(user?.role!=='admin'&&user?.role!=='superadmin'){el.innerHTML='<p style="color:var(--red)">Admin access required</p>';return}
    if(!window._adminTab)window._adminTab='screens';
    try{
      const screens=await api('/screens');

      // Tabs
      var tabs=[
        {id:'screens',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/></svg>',name:'Screens'},
        {id:'pending',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',name:'Pending'},
        {id:'users',icon:'<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2m22 0v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',name:'Users'}
      ];

      var tabHtml='<div style="display:flex;gap:6px;margin-bottom:24px">'+tabs.map(t=>
        '<button onclick="window._adminTab=\''+t.id+'\';loaders.admin()" style="display:flex;align-items:center;gap:8px;padding:10px 20px;border-radius:10px;font-size:13px;font-weight:600;border:none;cursor:pointer;font-family:inherit;transition:all .15s;'+(window._adminTab===t.id?'background:rgba(99,102,241,.12);color:#818cf8;border:1px solid rgba(99,102,241,.2)':'background:#0f172a;color:#64748b;border:1px solid #1e293b')+'">'+t.icon+t.name+'</button>').join('')+'</div>';

      // ===== SCREENS TAB =====
      if(window._adminTab==='screens'){
        el.innerHTML='<div class="ph"><div><h1>Screens</h1><p>Manage your screens and playlists</p></div><button class="btn-p" onclick="document.getElementById(\'add-screen-form\').style.display=document.getElementById(\'add-screen-form\').style.display===\'none\'?\'block\':\'none\'">+ Add Screen</button></div>'+tabHtml+
        '<div id="add-screen-form" style="display:none;margin-bottom:16px"><div class="card" style="padding:20px"><div style="font-size:15px;font-weight:700;margin-bottom:14px">Add New Screen</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px"><div><div class="lbl">Screen Name</div><input class="inp" id="ns-name" placeholder="Downtown LED Display"></div><div><div class="lbl">City</div><input class="inp" id="ns-city" placeholder="New York"></div></div><div style="display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px;margin-bottom:10px"><div><div class="lbl">Address</div><input class="inp" id="ns-addr" placeholder="123 Main St"></div><div><div class="lbl">State</div><input class="inp" id="ns-state" placeholder="NY"></div><div><div class="lbl">Size</div><input class="inp" id="ns-size" placeholder="20ft x 10ft"></div></div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px"><div><div class="lbl">Price/Month ($)</div><input class="inp" id="ns-pm" type="number" placeholder="5000"></div><div><div class="lbl">Resolution</div><input class="inp" id="ns-res" value="1920x1080"></div><div><div class="lbl">Orientation</div><select class="inp" id="ns-orient"><option value="landscape">Landscape</option><option value="portrait">Portrait</option></select></div></div><div style="display:flex;gap:8px"><button class="btn-p" onclick="addScreen()">Create</button><button class="btn-s" onclick="document.getElementById(\'add-screen-form\').style.display=\'none\'">Cancel</button></div><p id="ns-msg" style="font-size:12px;margin-top:10px;display:none"></p></div></div>'+
        '<div style="display:flex;flex-direction:column;gap:8px">'+screens.map(s=>
          '<div class="card card-i" style="padding:16px;display:flex;align-items:center;gap:14px" onclick="showScreenPlaylist(\''+s.id+'\')">'+
            '<div style="width:56px;height:36px;border-radius:8px;background:'+(s._g||'linear-gradient(135deg,#4338ca,#818cf8)')+';flex-shrink:0"></div>'+
            '<div style="flex:1">'+
              '<div style="font-size:15px;font-weight:700">'+s.name+'</div>'+
              '<div style="font-size:11px;color:#475569">'+(s.location_code||'')+' · '+s.location?.city+' · $'+(s.pricing?.per_month||0).toLocaleString()+'/mo · '+(s.specs?.orientation==='portrait'?'↕ Portrait':'↔ Landscape')+'</div>'+
            '</div>'+
            '<div style="display:flex;gap:6px" onclick="event.stopPropagation()">'+
              '<button onclick="editScreen(\''+s.id+'\')" style="padding:5px 14px;border-radius:6px;background:rgba(99,102,241,.1);color:#818cf8;font-size:11px;font-weight:600;border:none;cursor:pointer">Edit</button>'+
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
              <div style="margin-bottom:12px"><label class="inp-label">Name</label><input class="inp" id="sa-name" placeholder="Admin name"></div>
              <div style="margin-bottom:12px"><label class="inp-label">Email</label><input class="inp" id="sa-email" placeholder="admin@company.com"></div>
              <div style="margin-bottom:12px"><label class="inp-label">Password</label><input class="inp" id="sa-pwd" type="password" placeholder="Min 6 characters"></div>
              <div style="margin-bottom:16px"><label class="inp-label">Company</label><input class="inp" id="sa-company" placeholder="Company name (optional)"></div>
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
                <div style="display:flex;gap:8px;margin-bottom:8px">${d.screen_id?'<button onclick="unlinkDev(\''+d.id+'\',event)" style="padding:3px 10px;border-radius:5px;background:rgba(251,191,36,.1);color:var(--amber);font-size:10px;font-weight:600;border:none;cursor:pointer">Unlink</button>':''}<button onclick="removeDev(\''+d.id+'\',event)" style="padding:3px 10px;border-radius:5px;background:rgba(248,113,113,.1);color:var(--red);font-size:10px;font-weight:600;border:none;cursor:pointer">Remove</button></div><div style="display:flex;gap:20px;flex-wrap:wrap">
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">Screen:</span> ${d.screen_name||screenMap[d.screen_id]||'Not assigned'}</div>
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">IP:</span> ${d.diagnostics?.ip_address||'—'}</div>
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">Uptime:</span> ${upD>0?upD+'d ':''}${upH%24}h</div>
                  <div style="font-size:11px;color:var(--t-4)"><span style="color:var(--t-2);font-weight:600">Sync:</span> ${syncAgo!==null?(syncAgo<1?'Just now':syncAgo+'m ago'):'Never'}</div>
                </div>
              </div>
            </div>
          </div>`}).join('')}</div>`}`;
    }catch(e){el.innerHTML=`<div class="ph"><div><h1>Devices</h1><p>Connected players</p></div></div><div class="card" style="padding:48px;text-align:center;color:var(--t-4)">Sign in as admin to manage devices</div>`}
  },

  settings(){document.getElementById('pg-settings').innerHTML=`<h1 style="font-size:28px;font-weight:800;margin-bottom:28px">Settings</h1><div style="max-width:560px"><div style="display:flex;align-items:center;gap:16px;margin-bottom:32px"><div style="width:64px;height:64px;border-radius:16px;background:linear-gradient(135deg,#6366f1,#4338ca);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:900;color:#fff;box-shadow:0 4px 15px rgba(99,102,241,.25)">${(user?.name||'U')[0]}</div><div><div style="font-size:20px;font-weight:700">${user?.name}</div><div style="font-size:13px;color:var(--t-3)">${user?.email}</div><span class="bdg" style="margin-top:6px;background:${user?.role==='admin'?'rgba(99,102,241,.12)':'rgba(52,211,153,.12)'};color:${user?.role==='admin'?'var(--brand-l)':'var(--green)'}">${user?.role==='admin'?'Administrator':'Customer'}</span></div></div><div class="card" style="margin-bottom:20px"><div style="padding:14px 20px;border-bottom:1px solid var(--border);font-size:10px;font-weight:700;color:var(--t-2);text-transform:uppercase;letter-spacing:1.5px">Account</div>${[['Name',user?.name],['Email',user?.email],['Company',user?.company_name||'—'],['Role',user?.role]].map(([l,v])=>`<div style="padding:14px 20px;display:flex;justify-content:space-between;border-bottom:1px solid rgba(30,41,59,.2)"><span style="font-size:13px;color:var(--t-3)">${l}</span><span style="font-size:13px;font-weight:600">${v}</span></div>`).join('')}</div><button onclick="doLogout()" style="width:100%;padding:12px;border-radius:var(--radius-sm);background:none;border:1px solid var(--bg-3);color:var(--t-3);font-size:13px;cursor:pointer">Sign Out</button></div>`}
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
async function addScreen(){
  var name=document.getElementById('ns-name')?.value,city=document.getElementById('ns-city')?.value,addr=document.getElementById('ns-addr')?.value,state=document.getElementById('ns-state')?.value,size=document.getElementById('ns-size')?.value,pm=document.getElementById('ns-pm')?.value,res=document.getElementById('ns-res')?.value;
  var msg=document.getElementById('ns-msg');msg.style.display='none';
  if(!name||!city||!pm){msg.textContent='Name, city and monthly price are required';msg.style.color='var(--red)';msg.style.display='block';return}
  try{
    await api('/admin/screens',{method:'POST',body:JSON.stringify({name:name,description:name+' in '+city,location:{city:city,address:addr||city,state:state||'',country:'US'},pricing:{per_month:parseFloat(pm)||5000,per_day:Math.round((parseFloat(pm)||5000)/30),per_hour:Math.round((parseFloat(pm)||5000)/30/14),per_slot:Math.round((parseFloat(pm)||5000)/30/14/10),currency:'USD'},specs:{size:size||'20ft x 10ft',type:'LED',resolution:res||'1920x1080',orientation:document.getElementById('ns-orient')?.value||'landscape'},status:'active'})});
    msg.textContent='Screen created!';msg.style.color='var(--green)';msg.style.display='block';
    setTimeout(()=>loaders.admin(),800);
  }catch(e){msg.textContent=e.message;msg.style.color='var(--red)';msg.style.display='block'}}
async function editScreen(id){
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
  '<button class="btn-p" style="width:100%;justify-content:center;padding:14px;font-size:15px" onclick="saveScreen(\''+id+'\')">Save Changes</button></div>';
  window._editOrient=orient}
async function removeScreen(id){if(!confirm('Remove this screen?'))return;try{await api('/admin/screens/'+id,{method:'DELETE'});loaders.admin()}catch(e){alert(e.message)}}
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
    var widgets=[];try{widgets=await api('/admin/widgets?screen_id='+screenId)}catch(e){}
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

if(token&&user){enterApp()}

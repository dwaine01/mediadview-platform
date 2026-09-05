/**
 * workspace.js — Tenant-Scoped Customer Workspace
 * Phase 2C P1: Page loaders for the /workspace/* experience.
 *
 * All data calls go to /api/workspace/* which enforces org_id scoping.
 * SELF_SERVICE_OWNER and SELF_SERVICE_MANAGER only.
 */

/* ── Shared helpers ──────────────────────────────────────────────────────── */
function _wsFmt(val){return val??'—'}
function _wsDate(d){if(!d)return'—';try{return new Date(d).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}catch(_){return d}}
function _wsStatus(s){
  const map={
    active:{bg:'#064e3b',cl:'#34d399',label:'Active'},
    trial:{bg:'#1e3a5f',cl:'#60a5fa',label:'Trial'},
    suspended:{bg:'#422006',cl:'#f59e0b',label:'Suspended'},
    cancelled:{bg:'#450a0a',cl:'#f87171',label:'Cancelled'},
    pending:{bg:'#1c1917',cl:'#9ca3af',label:'Pending'},
    online:{bg:'#064e3b',cl:'#34d399',label:'Online'},
    offline:{bg:'#1c1917',cl:'#9ca3af',label:'Offline'},
    published:{bg:'#064e3b',cl:'#34d399',label:'Published'},
    draft:{bg:'#1c1917',cl:'#9ca3af',label:'Draft'},
  };
  const m=map[s?.toLowerCase()]||{bg:'#1c1917',cl:'#9ca3af',label:s||'—'};
  return`<span style="background:${m.bg};color:${m.cl};border-radius:20px;padding:3px 10px;font-size:11px;font-weight:700;letter-spacing:.04em">${m.label}</span>`;
}
function _wsEmpty(msg,icon){
  const i=icon||'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2';
  return`<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 24px;gap:12px">
    <div style="width:52px;height:52px;border-radius:14px;background:#1f2937;display:flex;align-items:center;justify-content:center">
      <svg width="24" height="24" fill="none" stroke="#6b7280" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${i}"/></svg>
    </div>
    <p style="color:#9ca3af;font-size:14px;font-weight:500;text-align:center">${msg}</p>
  </div>`;
}
function _wsCard(content){
  return`<div style="background:#111827;border:1px solid #1f2937;border-radius:12px;overflow:hidden">${content}</div>`;
}
function _wsRow(cells){
  return`<div style="display:grid;grid-template-columns:${cells.map(c=>c.w||'1fr').join(' ')};gap:12px;align-items:center;padding:14px 18px;border-bottom:1px solid #1a2234">${cells.map(c=>`<div style="font-size:13px;color:${c.dim?'#6b7280':'#d1d5db'};${c.style||''}">${c.v}</div>`).join('')}</div>`;
}
function _wsTableHead(cols){
  return`<div style="display:grid;grid-template-columns:${cols.map(c=>c.w||'1fr').join(' ')};gap:12px;padding:10px 18px;background:#0d1420;border-bottom:1px solid #1f2937">${cols.map(c=>`<div style="font-size:11px;font-weight:700;color:#6b7280;letter-spacing:.06em;text-transform:uppercase">${c.label}</div>`).join('')}</div>`;
}
function _wsStat(label,value,sub,iconPath,color){
  return`<div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:20px 22px">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
      <span style="font-size:12px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em">${label}</span>
      <div style="width:32px;height:32px;border-radius:9px;background:${color}22;border:1px solid ${color}33;display:flex;align-items:center;justify-content:center">
        <svg width="15" height="15" fill="none" stroke="${color}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${iconPath}"/></svg>
      </div>
    </div>
    <div style="font-size:26px;font-weight:800;color:#f3f4f6;font-variant-numeric:tabular-nums">${value}</div>
    <div style="font-size:12px;color:#6b7280;margin-top:4px">${sub}</div>
  </div>`;
}

/* ── ws-dashboard ────────────────────────────────────────────────────────── */
loaders['ws-dashboard']=async function(){
  const el=document.getElementById('pg-ws-dashboard');
  if(!el)return;
  try{
    const ctx=await api('/workspace/context');
    const u=ctx.current_user||{};
    const org=ctx.organization||{};
    const sub=ctx.subscription||{};
    const plan=ctx.plan_config||{};
    const st=ctx.stats||{};
    const now=new Date();
    const hour=now.getHours();
    const greet=hour<12?'Good morning':hour<18?'Good afternoon':'Good evening';

    el.innerHTML=`
    <div style="max-width:1100px">
      <!-- Welcome -->
      <div style="background:linear-gradient(135deg,#1e1b4b,#1e3a5f);border:1px solid #312e81;border-radius:16px;padding:28px 32px;margin-bottom:28px;display:flex;align-items:center;gap:24px">
        <div style="flex:1">
          <div style="font-size:13px;color:#818cf8;font-weight:600;margin-bottom:4px">${greet}</div>
          <h1 style="font-size:26px;font-weight:800;color:#f3f4f6;margin-bottom:8px">${org.name||'Your Workspace'}</h1>
          <p style="font-size:14px;color:#94a3b8">${sub.status?'Subscription: '+sub.status+' plan':'Start by adding your first screen to broadcast content.'}</p>
        </div>
        ${plan.plan_id?`<div style="background:#0f172a;border:1px solid #1f2937;border-radius:12px;padding:16px 22px;text-align:center;flex-shrink:0">
          <div style="font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px">Current Plan</div>
          <div style="font-size:20px;font-weight:800;color:#6366f1">${plan.display_name}</div>
          <div style="font-size:12px;color:#9ca3af;margin-top:2px">${plan.monthly_price===0?'Free':'$'+plan.monthly_price+'/mo'}</div>
        </div>`:''}
      </div>

      <!-- Stats -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:28px">
        ${_wsStat('Screens',st.screens??0,'Active display locations','M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z','#6366f1')}
        ${_wsStat('Players',st.devices??0,'Connected media players','M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z','#22d3ee')}
        ${_wsStat('Team Members',st.users??0,'Active workspace users','M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z','#10b981')}
        ${_wsStat('Plan Screens',plan.screens_included??'—',plan.screens_limit?'Max: '+plan.screens_limit:'Unlimited add-ons','M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z','#f59e0b')}
      </div>

      <!-- Quick actions -->
      <div style="margin-bottom:28px">
        <h2 style="font-size:16px;font-weight:700;color:#f3f4f6;margin-bottom:14px">Quick Actions</h2>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px">
          ${[
            ['Add Screen','Connect a new display','M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14 2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z','ws-screens','#6366f1'],
            ['Upload Media','Add images, videos','M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12','ws-content','#22d3ee'],
            ['Create Playlist','Organise your content','M5 4h14a2 2 0 012 2v3H3V6a2 2 0 012-2zm-2 9h18v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5z','ws-playlists','#10b981'],
            ['Schedule Content','Set broadcast times','M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z','ws-schedules','#f59e0b'],
          ].map(([title,desc,icon,page,color])=>`<div onclick="go('${page}')" style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:18px;cursor:pointer;transition:border-color .2s" onmouseover="this.style.borderColor='${color}66'" onmouseout="this.style.borderColor='#1f2937'">
            <div style="width:36px;height:36px;border-radius:10px;background:${color}22;display:flex;align-items:center;justify-content:center;margin-bottom:12px">
              <svg width="16" height="16" fill="none" stroke="${color}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${icon}"/></svg>
            </div>
            <div style="font-size:13px;font-weight:700;color:#f3f4f6;margin-bottom:4px">${title}</div>
            <div style="font-size:11px;color:#6b7280">${desc}</div>
          </div>`).join('')}
        </div>
      </div>

      ${sub.trial_ends_at?`<div style="background:#1e3a5f;border:1px solid #1e40af;border-radius:12px;padding:16px 22px;display:flex;align-items:center;gap:16px">
        <svg width="20" height="20" fill="none" stroke="#60a5fa" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        <div>
          <div style="font-size:14px;font-weight:600;color:#93c5fd">Your free trial ends on ${_wsDate(sub.trial_ends_at)}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:2px">Upgrade your plan to keep full access to all features.</div>
        </div>
        <button onclick="go('ws-billing')" style="margin-left:auto;padding:8px 16px;background:#1d4ed8;border:none;border-radius:8px;color:#fff;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap">View Billing</button>
      </div>`:''}
    </div>`;
  }catch(e){
    el.innerHTML=`<div style="padding:48px;text-align:center"><p style="color:#f87171">${e.message}</p><button onclick="loaders['ws-dashboard']()" style="margin-top:12px;padding:8px 16px;background:#1f2937;border:none;border-radius:8px;color:#d1d5db;cursor:pointer">Retry</button></div>`;
  }
};

/* ── ws-screens ──────────────────────────────────────────────────────────── */
loaders['ws-screens']=async function(){
  const el=document.getElementById('pg-ws-screens');
  if(!el)return;
  try{
    const screens=await api('/workspace/screens');
    el.innerHTML=`
    <div style="max-width:1000px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <div><h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:4px">Screens</h1>
        <p style="font-size:13px;color:#9ca3af">${screens.length} display location${screens.length!==1?'s':''} in your workspace</p></div>
      </div>
      ${screens.length===0?_wsEmpty('No screens yet. Add your first screen to start broadcasting.','M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z'):
      _wsCard(`
        ${_wsTableHead([{label:'Name',w:'2fr'},{label:'Status',w:'120px'},{label:'Location'},{label:'Created',w:'130px'}])}
        ${screens.map(s=>_wsRow([
          {v:`<div style="font-weight:600;color:#f3f4f6">${s.name||'Unnamed Screen'}</div><div style="font-size:11px;color:#6b7280;margin-top:2px">${s.code||''}</div>`,w:'2fr'},
          {v:_wsStatus(s.status||'active'),w:'120px'},
          {v:s.location?.city?`${s.location.city}${s.location.state?', '+s.location.state:''}`:s.location?.address||'—'},
          {v:_wsDate(s.created_at),w:'130px',dim:true}
        ])).join('')}
      `)}
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

/* ── ws-content ──────────────────────────────────────────────────────────── */
loaders['ws-content']=async function(){
  const el=document.getElementById('pg-ws-content');
  if(!el)return;
  try{
    const media=await api('/workspace/media');
    const formatSize=b=>{if(!b)return'';if(b<1024)return b+'B';if(b<1048576)return(b/1024).toFixed(1)+'KB';return(b/1048576).toFixed(1)+'MB'};
    el.innerHTML=`
    <div style="max-width:1000px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <div><h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:4px">Content / Media</h1>
        <p style="font-size:13px;color:#9ca3af">${media.length} file${media.length!==1?'s':''} in your media library</p></div>
      </div>
      ${media.length===0?_wsEmpty('Your media library is empty. Upload images or videos to start creating playlists.','M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z'):
      _wsCard(`
        ${_wsTableHead([{label:'Name',w:'3fr'},{label:'Type',w:'90px'},{label:'Size',w:'90px'},{label:'Uploaded',w:'130px'}])}
        ${media.map(m=>_wsRow([
          {v:`<div style="font-weight:600;color:#f3f4f6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${m.filename||m.name||'File'}</div>`,w:'3fr'},
          {v:`<span style="font-size:11px;color:#9ca3af;background:#1f2937;padding:2px 8px;border-radius:6px">${(m.content_type||m.mime_type||'—').split('/').pop().toUpperCase()}</span>`,w:'90px'},
          {v:formatSize(m.size_bytes||m.file_size),w:'90px',dim:true},
          {v:_wsDate(m.created_at||m.uploaded_at),w:'130px',dim:true}
        ])).join('')}
      `)}
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

/* ── ws-playlists ────────────────────────────────────────────────────────── */
loaders['ws-playlists']=async function(){
  const el=document.getElementById('pg-ws-playlists');
  if(!el)return;
  try{
    const playlists=await api('/workspace/playlists');
    el.innerHTML=`
    <div style="max-width:1000px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <div><h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:4px">Playlists</h1>
        <p style="font-size:13px;color:#9ca3af">${playlists.length} playlist${playlists.length!==1?'s':''}</p></div>
      </div>
      ${playlists.length===0?_wsEmpty('No playlists yet. Create a playlist to organise and schedule your content.','M5 4h14a2 2 0 012 2v3H3V6a2 2 0 012-2zm-2 9h18v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5zm5-6h8M8 16h5'):
      _wsCard(`
        ${_wsTableHead([{label:'Name',w:'3fr'},{label:'Status',w:'120px'},{label:'Screens',w:'100px'},{label:'Created',w:'130px'}])}
        ${playlists.map(p=>_wsRow([
          {v:`<div style="font-weight:600;color:#f3f4f6">${p.name||'Unnamed Playlist'}</div>`,w:'3fr'},
          {v:_wsStatus(p.status||'draft'),w:'120px'},
          {v:(p.screen_ids||[]).length,w:'100px',dim:true},
          {v:_wsDate(p.created_at),w:'130px',dim:true}
        ])).join('')}
      `)}
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

/* ── ws-schedules ────────────────────────────────────────────────────────── */
loaders['ws-schedules']=async function(){
  const el=document.getElementById('pg-ws-schedules');
  if(!el)return;
  try{
    const schedules=await api('/workspace/schedules');
    el.innerHTML=`
    <div style="max-width:1000px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <div><h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:4px">Schedules</h1>
        <p style="font-size:13px;color:#9ca3af">${schedules.length} schedule${schedules.length!==1?'s':''}</p></div>
      </div>
      ${schedules.length===0?_wsEmpty('No schedules yet. Create a schedule to control when your content plays.','M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z'):
      _wsCard(`
        ${_wsTableHead([{label:'Name',w:'3fr'},{label:'Status',w:'120px'},{label:'Dates'},{label:'Created',w:'130px'}])}
        ${schedules.map(c=>_wsRow([
          {v:`<div style="font-weight:600;color:#f3f4f6">${c.name||'Unnamed'}</div>`,w:'3fr'},
          {v:_wsStatus(c.status),w:'120px'},
          {v:c.schedule?.start_date?`${c.schedule.start_date} → ${c.schedule.end_date||''}`:_wsDate(c.starts_at)},
          {v:_wsDate(c.created_at),w:'130px',dim:true}
        ])).join('')}
      `)}
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

/* ── ws-users ────────────────────────────────────────────────────────────── */
loaders['ws-users']=async function(){
  const el=document.getElementById('pg-ws-users');
  if(!el)return;
  try{
    const users=await api('/workspace/users');
    el.innerHTML=`
    <div style="max-width:800px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <div><h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:4px">Team</h1>
        <p style="font-size:13px;color:#9ca3af">${users.length} team member${users.length!==1?'s':''}</p></div>
      </div>
      ${users.length===0?_wsEmpty('No team members found.'):
      _wsCard(`
        ${_wsTableHead([{label:'Member'},{label:'Role',w:'160px'},{label:'Joined',w:'130px'}])}
        ${users.map(u=>{
          const initial=(u.name||u.email||'U')[0].toUpperCase();
          return _wsRow([
            {v:`<div style="display:flex;align-items:center;gap:12px"><div style="width:34px;height:34px;border-radius:50%;background:#312e81;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#818cf8;flex-shrink:0">${initial}</div><div><div style="font-weight:600;color:#f3f4f6">${u.name||'—'}</div><div style="font-size:11px;color:#6b7280">${u.email}</div></div></div>`},
            {v:`<span style="font-size:11px;font-weight:600;color:#9ca3af;background:#1f2937;padding:3px 10px;border-radius:20px">${u.rbac_role?.replace('_',' ')||u.role||'—'}</span>`,w:'160px'},
            {v:_wsDate(u.created_at),w:'130px',dim:true}
          ]);
        }).join('')}
      `)}
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

/* ── ws-billing ──────────────────────────────────────────────────────────── */
loaders['ws-billing']=async function(){
  const el=document.getElementById('pg-ws-billing');
  if(!el)return;
  try{
    const data=await api('/workspace/billing');
    const sub=data.subscription;
    const pa=data.current_pricing_agreement;
    const plan=data.plan_config;
    el.innerHTML=`
    <div style="max-width:760px">
      <h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:24px">Billing & Plan</h1>
      ${!sub?_wsEmpty('No subscription found. Contact support if you believe this is an error.'):
      `<!-- Subscription Card -->
      <div style="background:#111827;border:1px solid #1f2937;border-radius:14px;padding:24px;margin-bottom:20px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <h2 style="font-size:15px;font-weight:700;color:#f3f4f6">Subscription</h2>
          ${_wsStatus(sub.status)}
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          ${[
            ['Plan',plan?.display_name||pa?.plan_id||sub.plan||'—'],
            ['Status',sub.status||'—'],
            ['Billing Cycle',pa?.billing_cycle||'monthly'],
            ['Monthly Price',pa?.agreed_monthly_price!=null?'$'+pa.agreed_monthly_price.toLocaleString():sub.monthly_price?'$'+sub.monthly_price:'—'],
            ['Screens Included',pa?.screens_included!=null?pa.screens_included:plan?.screens_included||'—'],
            ['Trial Ends',sub.trial_ends_at?_wsDate(sub.trial_ends_at):'N/A'],
            ['Period Start',_wsDate(sub.current_period_start)],
            ['Period End',_wsDate(sub.current_period_end)],
          ].map(([k,v])=>`<div><div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px">${k}</div><div style="font-size:14px;color:#d1d5db;font-weight:500">${v}</div></div>`).join('')}
        </div>
      </div>
      <!-- Pricing Agreement -->
      ${pa?`<div style="background:#111827;border:1px solid #1f2937;border-radius:14px;padding:24px;margin-bottom:20px">
        <h2 style="font-size:15px;font-weight:700;color:#f3f4f6;margin-bottom:16px">Pricing Agreement</h2>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          ${[
            ['Pricing Model',pa.pricing_model||'standard'],
            ['Monthly Price','$'+(pa.agreed_monthly_price||0).toLocaleString()],
            ['Screens Included',pa.screens_included??'—'],
            ['Screens Limit',pa.screens_limit||'Unlimited'],
            ['Extra Screen Price',pa.overage_price_per_screen!=null?'$'+pa.overage_price_per_screen+'/screen':'—'],
            ['Discount',pa.discount_percent!=null?pa.discount_percent+'%':'None'],
            ['Effective From',_wsDate(pa.effective_from)],
            ['Effective To',pa.effective_to?_wsDate(pa.effective_to):'Open-ended'],
          ].map(([k,v])=>`<div><div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px">${k}</div><div style="font-size:14px;color:#d1d5db;font-weight:500">${v}</div></div>`).join('')}
        </div>
        ${pa.notes?`<div style="margin-top:14px;padding:12px;background:#0d1420;border-radius:8px;font-size:12px;color:#9ca3af"><span style="font-weight:600;color:#6b7280">Notes:</span> ${pa.notes}</div>`:''}
      </div>`:''}
      <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px 20px">
        <p style="font-size:13px;color:#9ca3af">Billing is currently managed manually by the MediAd View team. For changes to your plan or pricing, please contact <a href="mailto:billing@mediadview.com" style="color:#6366f1">billing@mediadview.com</a>.</p>
      </div>`}
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

/* ── ws-settings ─────────────────────────────────────────────────────────── */
loaders['ws-settings']=async function(){
  const el=document.getElementById('pg-ws-settings');
  if(!el)return;
  try{
    const ctx=await api('/workspace/context');
    const u=ctx.current_user||{};
    const org=ctx.organization||{};
    el.innerHTML=`
    <div style="max-width:640px">
      <h1 style="font-size:22px;font-weight:800;color:#f3f4f6;margin-bottom:24px">Settings</h1>
      <!-- Org Info -->
      <div style="background:#111827;border:1px solid #1f2937;border-radius:14px;padding:24px;margin-bottom:20px">
        <h2 style="font-size:15px;font-weight:700;color:#f3f4f6;margin-bottom:16px">Organization</h2>
        <div style="display:flex;flex-direction:column;gap:12px">
          ${[['Name',org.name],['Slug',org.slug],['Status',org.status],['Created',_wsDate(org.created_at)]].map(([k,v])=>`<div style="display:flex;align-items:center;gap:0;border-bottom:1px solid #1a2234;padding-bottom:12px">
            <span style="font-size:12px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;min-width:120px">${k}</span>
            <span style="font-size:14px;color:#d1d5db">${v||'—'}</span>
          </div>`).join('')}
        </div>
      </div>
      <!-- Profile -->
      <div style="background:#111827;border:1px solid #1f2937;border-radius:14px;padding:24px;margin-bottom:20px">
        <h2 style="font-size:15px;font-weight:700;color:#f3f4f6;margin-bottom:16px">Your Profile</h2>
        <div style="display:flex;flex-direction:column;gap:12px">
          ${[['Name',u.name],['Email',u.email],['Role',u.rbac_role]].map(([k,v])=>`<div style="display:flex;align-items:center;gap:0;border-bottom:1px solid #1a2234;padding-bottom:12px">
            <span style="font-size:12px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.04em;min-width:120px">${k}</span>
            <span style="font-size:14px;color:#d1d5db">${v||'—'}</span>
          </div>`).join('')}
        </div>
      </div>
      <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px 20px">
        <p style="font-size:13px;color:#9ca3af">To update organization details or change your password, please contact <a href="mailto:support@mediadview.com" style="color:#6366f1">support@mediadview.com</a>.</p>
      </div>
    </div>`;
  }catch(e){el.innerHTML=`<p style="color:#f87171;padding:40px">${e.message}</p>`;}
};

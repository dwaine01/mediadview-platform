/* Admin — Sign Permit Requests
 * Loads at #pg-signpermits via loaders.signpermits.
 * Backend: /api/sign-permits/list, /{id}, /{id} (PUT), /{id}/pdf
 */
(function(){
  'use strict';

  if(!document.getElementById('sp-css')){
    const st=document.createElement('style'); st.id='sp-css';
    st.textContent=`
      .sp-hd{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px;margin-bottom:18px}
      .sp-hd h1{font-size:22px;font-weight:900;color:var(--t-1)}
      .sp-hd p{color:var(--t-4);font-size:12px;margin-top:2px}
      .sp-fbtns{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
      .sp-fbtn{padding:7px 13px;border-radius:8px;font-size:12px;font-weight:600;border:1px solid var(--border);background:transparent;color:var(--t-3);cursor:pointer;font-family:inherit}
      .sp-fbtn.on{background:var(--brand-l);color:#fff;border-color:var(--brand-l)}
      .sp-fbtn .n{margin-left:5px;background:rgba(0,0,0,.18);padding:1px 6px;border-radius:8px;font-size:10px;font-weight:700}
      .sp-tbl{width:100%;border-collapse:collapse;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;overflow:hidden}
      .sp-tbl th,.sp-tbl td{padding:11px 13px;text-align:left;font-size:12.5px;border-bottom:1px solid var(--border)}
      .sp-tbl th{background:rgba(2,6,23,.04);font-size:10px;font-weight:800;color:var(--t-4);text-transform:uppercase;letter-spacing:1px}
      .sp-tbl tbody tr{cursor:pointer;transition:background .1s}
      .sp-tbl tbody tr:hover{background:rgba(99,102,241,.04)}
      .sp-mono{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--t-4)}
      .sp-badge{display:inline-block;padding:3px 8px;border-radius:6px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
      .sp-b-new{background:rgba(99,102,241,.12);color:#4f46e5}
      .sp-b-in_review{background:rgba(251,191,36,.15);color:#d97706}
      .sp-b-missing_info{background:rgba(239,68,68,.12);color:#dc2626}
      .sp-b-ready_for_permit{background:rgba(34,211,238,.12);color:#0891b2}
      .sp-b-submitted{background:rgba(147,51,234,.12);color:#7c3aed}
      .sp-b-approved{background:rgba(16,185,129,.12);color:#059669}
      .sp-b-closed{background:rgba(148,163,184,.15);color:#64748b}
      .sp-empty{padding:60px 20px;text-align:center;color:var(--t-4);font-size:13px}
      .sp-dr-ov{position:fixed;inset:0;background:rgba(2,6,23,.6);backdrop-filter:blur(6px);z-index:200;display:flex;justify-content:flex-end}
      .sp-dr{background:var(--bg-card);width:min(760px,100vw);height:100vh;overflow:auto;padding:24px 26px;box-shadow:-12px 0 40px rgba(0,0,0,.15)}
      .sp-dr .close{position:absolute;top:20px;right:22px;background:transparent;border:1px solid var(--border);color:var(--t-4);padding:6px 10px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:12px}
      .sp-dr h2{font-size:19px;font-weight:900;color:var(--t-1);margin:0}
      .sp-dr .ref{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--t-4);margin:2px 0 6px}
      .sp-sec{margin-top:20px}
      .sp-sec h3{font-size:10px;font-weight:800;color:var(--t-4);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px}
      .sp-kv{display:grid;grid-template-columns:1fr 1fr;gap:4px 20px}
      .sp-kv div{padding:5px 0;border-bottom:1px dashed var(--border);font-size:13px;display:flex;justify-content:space-between;gap:8px}
      .sp-kv div span:first-child{color:var(--t-4);font-size:11.5px}
      .sp-kv div span:last-child{color:var(--t-1);font-weight:500;text-align:right;word-break:break-word}
      .sp-sig{background:#fafafa;border:1px solid var(--border);border-radius:10px;padding:10px;text-align:center}
      .sp-sig img{max-width:100%;max-height:180px;background:#fff;border-radius:6px}
      .sp-act{background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;border:none;padding:9px 14px;border-radius:8px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit;margin-right:6px}
      .sp-act.pdf{background:linear-gradient(135deg,#22d3ee,#0891b2)}
      .sp-note{width:100%;background:var(--bg-card);border:1px solid var(--border);color:var(--t-1);padding:10px 12px;border-radius:8px;font-family:inherit;font-size:13px;resize:vertical;min-height:60px}
    `;
    document.head.appendChild(st);
  }

  const STATUSES = ['new','in_review','missing_info','ready_for_permit','submitted','approved','closed'];
  const state = {filter:'all', items:[]};

  const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  const dt = s => { try{ const d=new Date(s); return isNaN(d)?'—':d.toLocaleString('en-US',{month:'short',day:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});}catch(e){return '—'}};
  const stLabel = s => String(s||'').replace(/_/g,' ');

  function counts(){
    const c={all:state.items.length};
    STATUSES.forEach(s=>c[s]=state.items.filter(x=>x.status===s).length);
    return c;
  }

  function renderTable(){
    const list = state.filter==='all' ? state.items : state.items.filter(x=>x.status===state.filter);
    if(!list.length) return `<div class="sp-empty">No submissions in this view.<br><span style="font-size:11.5px;color:var(--t-5)">Public form at mediadview.com/sign-permit-information</span></div>`;
    return `<table class="sp-tbl">
      <thead><tr>
        <th>Ref</th><th>Date</th><th>Business</th><th>Contact</th><th>Sign Address</th><th>Landlord</th><th>Status</th>
      </tr></thead><tbody>
      ${list.map(o=>`<tr onclick="window.spOpen('${o.id}')">
        <td class="sp-mono">${esc(o.ref)}</td>
        <td class="sp-mono">${esc(dt(o.submitted_at))}</td>
        <td><div style="font-weight:600;color:var(--t-1)">${esc(o.business_name)}</div>
            <div style="font-size:11px;color:var(--t-4)">${esc(o.business_owner||'')}</div></td>
        <td><div>${esc(o.business_phone||'')}</div>
            <div style="font-size:11px;color:var(--t-4)">${esc(o.business_email||'')}</div></td>
        <td>${esc(o.sign_address||o.business_address||'')}</td>
        <td>${esc(o.landlord_company||o.landlord_name||'')}</td>
        <td><span class="sp-badge sp-b-${o.status}">${esc(stLabel(o.status))}</span></td>
      </tr>`).join('')}
      </tbody></table>`;
  }

  function render(el){
    const c = counts();
    const chip = (k,label)=>`<button class="sp-fbtn ${state.filter===k?'on':''}" onclick="window.spFilter('${k}')">${label}<span class="n">${c[k]||0}</span></button>`;
    el.innerHTML = `
      <div class="sp-hd">
        <div><h1>Sign Permit Requests</h1>
             <p>Requests submitted through mediadview.com/sign-permit-information</p></div>
        <button class="sp-fbtn" onclick="loaders.signpermits()">↻ Refresh</button>
      </div>
      <div class="sp-fbtns">
        ${chip('all','All')}
        ${STATUSES.map(s=>chip(s,stLabel(s).replace(/^./,c=>c.toUpperCase()))).join('')}
      </div>
      <div id="sp-list">${renderTable()}</div>`;
  }

  if(typeof loaders !== 'undefined'){
    loaders.signpermits = async function(){
      const el = document.getElementById('pg-signpermits'); if(!el) return;
      el.innerHTML = `<div class="sp-empty">Loading…</div>`;
      try{
        const data = await api('/sign-permits/list');
        state.items = Array.isArray(data)?data:[];
        render(el);
      }catch(e){
        el.innerHTML = `<div class="sp-empty" style="color:#dc2626">Failed to load: ${esc(e.message||'error')}</div>`;
      }
    };
  }

  window.spFilter = k => { state.filter=k; document.getElementById('sp-list').innerHTML = renderTable();
    document.querySelectorAll('.sp-fbtn').forEach(b=>b.classList.remove('on'));
    const btns = document.querySelectorAll('.sp-fbtn');
    const idx = ['all',...STATUSES].indexOf(k);
    if(btns[idx]) btns[idx].classList.add('on');
  };

  window.spOpen = async id => {
    document.querySelectorAll('.sp-dr-ov').forEach(x=>x.remove());
    const ov=document.createElement('div'); ov.className='sp-dr-ov';
    ov.innerHTML=`<div class="sp-dr"><div class="sp-empty">Loading…</div></div>`;
    ov.addEventListener('click', e=>{if(e.target===ov)ov.remove()});
    document.body.appendChild(ov);
    try{
      const o = await api('/sign-permits/'+encodeURIComponent(id));
      renderDrawer(ov.querySelector('.sp-dr'), o);
    }catch(e){
      ov.querySelector('.sp-dr').innerHTML=`<button class="close" onclick="this.closest('.sp-dr-ov').remove()">Close</button><div class="sp-empty" style="color:#dc2626">${esc(e.message||'error')}</div>`;
    }
  };

  function renderDrawer(root, o){
    const kv = (rows)=>`<div class="sp-kv">${rows.map(([l,v])=>`<div><span>${esc(l)}</span><span>${esc(v||'—')}</span></div>`).join('')}</div>`;
    const stOpts = STATUSES.map(s=>`<option value="${s}"${o.status===s?' selected':''}>${esc(stLabel(s))}</option>`).join('');
    root.innerHTML = `
      <button class="close" onclick="this.closest('.sp-dr-ov').remove()">Close</button>
      <h2>${esc(o.business_name)}</h2>
      <div class="ref">${esc(o.ref)} · Submitted ${esc(dt(o.submitted_at))}</div>
      <div style="margin-top:8px"><span class="sp-badge sp-b-${o.status}">${esc(stLabel(o.status))}</span></div>

      <div style="margin-top:16px;display:flex;flex-wrap:wrap;gap:8px;align-items:center">
        <select id="sp-status" onchange="window.spSave('${o.id}')" style="border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-family:inherit;font-size:12.5px;background:var(--bg-card);color:var(--t-1)">${stOpts}</select>
        <button class="sp-act pdf" onclick="window.spPdf('${o.id}','${esc(o.ref)}')">↓ Download PDF</button>
        <button class="sp-act" onclick="window.spPrint('${o.id}','${esc(o.ref)}')">🖨 Print</button>
      </div>

      <div class="sp-sec"><h3>Business / Tenant</h3>${kv([
        ['Business',o.business_name],['Legal Company',o.legal_company],
        ['Owner',o.business_owner],['Phone',o.business_phone],
        ['Email',o.business_email],
        ['Address',`${o.business_address||''}, ${o.business_city||''} ${o.business_state||''} ${o.business_zip||''}`],
      ])}</div>

      <div class="sp-sec"><h3>Landlord / Property Owner</h3>${kv([
        ['Company',o.landlord_company],['Landlord',o.landlord_name],
        ['Contact',o.landlord_contact],['Phone',o.landlord_phone],
        ['Email',o.landlord_email],
        ['Mailing',`${o.landlord_mailing||''}, ${o.landlord_city||''} ${o.landlord_state||''} ${o.landlord_zip||''}`],
      ])}</div>

      <div class="sp-sec"><h3>Sign Project</h3>${kv([
        ['Business on Sign',o.sign_business_name],
        ['Sign Address',o.sign_address],
        ['Type',o.sign_type + (o.sign_type_other?` — ${o.sign_type_other}`:'')],
      ])}${o.sign_description?`<div style="margin-top:8px;padding:10px 12px;background:rgba(99,102,241,.04);border-radius:8px;font-size:13px"><b>Description:</b><br>${esc(o.sign_description)}</div>`:''}${o.sign_additional?`<div style="margin-top:8px;padding:10px 12px;background:rgba(99,102,241,.04);border-radius:8px;font-size:13px"><b>Additional:</b><br>${esc(o.sign_additional)}</div>`:''}</div>

      <div class="sp-sec"><h3>Authorization</h3>${kv([
        ['Certified by',o.cert_full_name],['Date',o.cert_date],['Agreed',o.cert_agreed?'Yes':'No'],
      ])}<div class="sp-sig" style="margin-top:8px">${o.cert_signature_data?`<img src="${o.cert_signature_data}" alt="Signature">`:'<span style="color:var(--t-4);font-size:12px">No signature captured</span>'}</div></div>

      <div class="sp-sec"><h3>Admin note</h3>
        <textarea class="sp-note" id="sp-note" placeholder="Internal notes visible only to admins">${esc(o.admin_notes||'')}</textarea>
        <div style="margin-top:8px"><button class="sp-act" onclick="window.spSave('${o.id}',true)">Save note</button></div>
      </div>
    `;
  }

  window.spSave = async (id, includeNote)=>{
    const st = document.getElementById('sp-status')?.value;
    const payload = {};
    if(st) payload.status = st;
    if(includeNote){
      const nt = document.getElementById('sp-note');
      if(nt) payload.admin_notes = nt.value;
    }
    try{
      await api('/sign-permits/'+encodeURIComponent(id), {method:'PUT', body:JSON.stringify(payload)});
      if(typeof loaders!=='undefined' && loaders.signpermits) await loaders.signpermits();
    }catch(e){ alert('Failed to save: '+e.message); }
  };

  window.spPdf = async (id, ref)=>{
    try{
      const r = await window.Auth.api.raw('/sign-permits/'+encodeURIComponent(id)+'/pdf',{credentials:'include'});
      if(!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href=url; a.download=ref+'.pdf'; a.click();
      setTimeout(()=>URL.revokeObjectURL(url), 4000);
    }catch(e){ alert('Failed to download PDF: '+e.message); }
  };
  window.spPrint = async (id, ref)=>{
    try{
      const r = await window.Auth.api.raw('/sign-permits/'+encodeURIComponent(id)+'/pdf',{credentials:'include'});
      if(!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const w = window.open(url,'_blank');
      if(w) w.addEventListener('load', ()=>{ try{w.print()}catch(_){} });
    }catch(e){ alert('Failed to print: '+e.message); }
  };
})();

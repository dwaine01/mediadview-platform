// MediaView — Bandeja de entrada de WhatsApp (Finanzas → 💬 Bandeja)
// Lo que escriben los clientes se lee y se contesta acá. Meta no guarda un
// historial recuperable: si esto no existe, migrar el número significa perder
// las respuestas.
//
// Reglas de Meta que la pantalla respeta:
//  · Texto libre SÓLO dentro de las 24 h desde el último mensaje del cliente.
//  · Fuera de esa ventana hay que usar plantilla aprobada (se avisa y se ofrece
//    mandar la factura, que sí es plantilla).
// Las fotos y archivos no se muestran con el link de Meta (necesita el token):
// se bajan por el servidor con la sesión del panel.
(function(){
  if (typeof loaders === 'undefined') return;
  const FAPI = '/finance';
  const POLL_MS = 10000;

  const esc = s => String(s||'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt$ = v => '$' + Number(v||0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  const asDate = s => s ? new Date(/Z|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z') : null;
  const fmtHora = s => { const d = asDate(s); return d && !isNaN(d) ? d.toLocaleTimeString('es-US',{hour:'2-digit',minute:'2-digit'}) : ''; };
  const fmtDia  = s => { const d = asDate(s); if (!d || isNaN(d)) return ''; const hoy = new Date();
    if (d.toDateString() === hoy.toDateString()) return 'Hoy';
    return d.toLocaleDateString('es-US',{day:'2-digit',month:'short',year:'numeric'}); };
  const relativo = s => {
    const d = asDate(s); if (!d || isNaN(d)) return '';
    const min = Math.floor((Date.now() - d.getTime())/60000);
    if (min < 1) return 'ahora';
    if (min < 60) return min + ' min';
    if (min < 1440) return Math.floor(min/60) + ' h';
    return fmtDia(s);
  };
  const telLindo = t => {
    const d = String(t||'').replace(/\D/g,'');
    if (d.length === 11 && d[0] === '1') return `+1 (${d.slice(1,4)}) ${d.slice(4,7)}-${d.slice(7)}`;
    return '+' + d;
  };

  const mediaCache = {};
  async function mediaUrl(id){
    if (mediaCache[id]) return mediaCache[id];
    const r = await window.Auth.api.raw('/finance/whatsapp/media/' + encodeURIComponent(id));
    if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.detail || 'No se pudo abrir el archivo'); }
    return mediaCache[id] = URL.createObjectURL(await r.blob());
  }

  // ---------------------------------------------------------------- pantalla
  window.renderWhatsAppInbox = async function(){
    const el = document.getElementById('pg-finance');
    if (!el) return;
    const tabs = window._finTabsBar ? window._finTabsBar(window._fTab) : '';
    el.innerHTML = `<div class="ph"><div><h1>Bandeja de entrada</h1>
      <p>Mensajes de WhatsApp de los clientes — leer, responder y vincular con su ficha</p></div></div>
      ${tabs}
      <div id="wa-banner"></div>
      <div id="wa-wrap" style="display:flex;gap:14px;align-items:stretch;flex-wrap:wrap">
        <div class="card" id="wa-list" style="width:330px;min-width:280px;flex:1 1 300px;max-height:640px;overflow-y:auto;padding:0">
          <div style="padding:40px;text-align:center;color:var(--t-4);font-size:13px">Cargando…</div>
        </div>
        <div class="card" id="wa-chat" style="flex:2 1 460px;min-width:320px;display:flex;flex-direction:column;height:640px;padding:0">
          <div style="margin:auto;text-align:center;color:var(--t-4);font-size:13px;padding:24px">Elegí una conversación</div>
        </div>
      </div>`;
    await cargarLista();
    if (window._waPhone) await abrirHilo(window._waPhone, true);
    arrancarPoll();
  };

  function arrancarPoll(){
    if (window._waPoll) clearInterval(window._waPoll);
    window._waPoll = setInterval(async ()=>{
      if (window._fTab !== 'inbox' || !document.getElementById('wa-list')) {
        clearInterval(window._waPoll); window._waPoll = null; return;
      }
      try {
        await cargarLista();
        if (window._waPhone) await abrirHilo(window._waPhone, false);
      } catch(e){}
    }, POLL_MS);
  }

  let ultimaLista = '';
  async function cargarLista(){
    const cont = document.getElementById('wa-list');
    if (!cont) return;
    const data = await api(FAPI + '/whatsapp/inbox');
    const banner = document.getElementById('wa-banner');
    if (banner) banner.innerHTML = data.connected ? '' :
      `<div class="card" style="padding:14px 18px;margin-bottom:14px;border-left:4px solid #b45309">
         <div style="font-size:13.5px;font-weight:700;color:#b45309;margin-bottom:3px">WhatsApp todavía no está conectado</div>
         <div style="font-size:12.5px;color:var(--t-3);line-height:1.6">${esc(data.reason||'')}
           Cuando se conecte el número oficial, los mensajes de los clientes van a aparecer acá automáticamente.</div></div>`;
    const rows = data.rows || [];
    const firma = JSON.stringify(rows.map(r=>[r.phone,r.last_at,r.unread,r.client_id]));
    if (firma === ultimaLista) return;
    ultimaLista = firma;
    cont.innerHTML = rows.length === 0
      ? `<div style="padding:40px 24px;text-align:center"><div style="font-size:30px;margin-bottom:8px">💬</div>
         <div style="font-size:14px;font-weight:700;color:var(--t-2)">Sin conversaciones</div>
         <div style="font-size:12.5px;color:var(--t-4);margin-top:6px;line-height:1.6">Acá van a aparecer los mensajes que manden los clientes al WhatsApp de MediaView.</div></div>`
      : rows.map(r=>{
          const activo = window._waPhone === r.phone;
          const nombre = r.client_name || telLindo(r.phone);
          return `<div onclick="waOpen('${r.phone}')" style="padding:13px 16px;border-bottom:1px solid var(--border);cursor:pointer;background:${activo?'var(--brand-tint)':'transparent'};display:flex;gap:11px;align-items:flex-start">
            <div style="width:36px;height:36px;border-radius:50%;background:${r.client_id?'#04785722':'#64748b22'};color:${r.client_id?'#047857':'#475569'};display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0">${esc(nombre.trim().charAt(0).toUpperCase()||'?')}</div>
            <div style="flex:1;min-width:0">
              <div style="display:flex;justify-content:space-between;gap:8px">
                <span style="font-size:13.5px;font-weight:700;color:var(--t-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(nombre)}</span>
                <span style="font-size:11px;color:var(--t-4);flex-shrink:0">${relativo(r.last_at)}</span>
              </div>
              <div style="font-size:12px;color:var(--t-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px">
                ${r.last_direction==='out'?'<span style="color:var(--t-4)">Vos: </span>':''}${esc(r.last_message||'—')}</div>
              <div style="display:flex;gap:6px;align-items:center;margin-top:4px">
                ${r.client_id?'':'<span style="font-size:10.5px;font-weight:700;color:#b45309;background:#b4530914;padding:1px 6px;border-radius:5px">DESCONOCIDO</span>'}
                ${r.unread>0?`<span style="font-size:10.5px;font-weight:800;color:#fff;background:#047857;padding:1px 7px;border-radius:9px">${r.unread}</span>`:''}
              </div>
            </div></div>`;
        }).join('');
  }

  window.waOpen = async function(phone){
    window._waPhone = phone;
    ultimaLista = '';
    await abrirHilo(phone, true);
    await cargarLista();
    try { await api(FAPI + '/whatsapp/inbox/' + phone + '/read', {method:'POST'}); } catch(e){}
  };

  let ultimoHilo = '';
  async function abrirHilo(phone, forzar){
    const cont = document.getElementById('wa-chat');
    if (!cont) return;
    const d = await api(FAPI + '/whatsapp/inbox/' + phone);
    const firma = JSON.stringify([phone, (d.messages||[]).map(m=>[m.id,m.status]), d.window_open, d.client && d.client.id]);
    if (!forzar && firma === ultimoHilo) return;
    ultimoHilo = firma;
    const borrador = (document.getElementById('wa-reply')||{}).value || '';
    const cl = d.client;
    const nombre = cl ? (cl.business_name || cl.representative) : telLindo(phone);

    cont.innerHTML = `
      <div style="padding:13px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap">
        <div style="min-width:0">
          <div style="font-size:14.5px;font-weight:800;color:var(--t-1)">${esc(nombre)}</div>
          <div style="font-size:11.5px;color:var(--t-4)">${telLindo(phone)}${cl&&cl.representative&&cl.business_name?' · '+esc(cl.representative):''}</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          ${cl
            ? `<button class="btn-s" style="padding:6px 11px;font-size:11.5px" onclick="viewClient('${cl.id}')">Ver ficha</button>`
            : `<button class="btn-p" style="padding:6px 11px;font-size:11.5px" onclick="waLinkModal('${phone}')">+ Registrar cliente</button>`}
          ${cl ? `<button class="btn-s" style="padding:6px 11px;font-size:11.5px" onclick="waLinkModal('${phone}')">Cambiar cliente</button>` : ''}
        </div>
      </div>
      ${cl ? `<div style="padding:9px 16px;background:var(--bg-1);border-bottom:1px solid var(--border);display:flex;gap:14px;align-items:center;flex-wrap:wrap;font-size:12px">
          <span style="color:var(--t-3)">Saldo pendiente: <b style="color:${cl.balance>0?'#b45309':'#047857'}">${fmt$(cl.balance)}</b></span>
          <span style="color:var(--t-3)">Facturas abiertas: <b style="color:var(--t-1)">${cl.open_count}</b></span>
          ${(cl.invoices||[]).slice(0,3).map(i=>`<button class="btn-s" style="padding:3px 9px;font-size:11px" onclick="waSendInvoice('${i.id}')" title="Reenviar por WhatsApp">📄 ${esc(i.invoice_number)} · ${fmt$(i.balance)}</button>`).join('')}
        </div>` : ''}
      <div id="wa-msgs" style="flex:1;overflow-y:auto;padding:16px;background:var(--bg-1);display:flex;flex-direction:column;gap:8px"></div>
      <div style="padding:12px 16px;border-top:1px solid var(--border)">
        ${d.window_open
          ? `<div style="display:flex;gap:8px;align-items:flex-end">
              <textarea id="wa-reply" class="inp" rows="2" placeholder="Escribí tu respuesta…" style="flex:1;resize:vertical;min-height:44px"></textarea>
              <button class="btn-p" id="wa-send" style="min-height:44px" onclick="waSend('${phone}')">Enviar</button>
            </div>
            <div style="font-size:11px;color:var(--t-4);margin-top:6px">Se puede responder libremente hasta 24 h después del último mensaje del cliente.</div>`
          : `<div style="background:#b4530910;border:1px solid #b4530933;border-radius:10px;padding:12px 14px">
              <div style="font-size:12.5px;font-weight:700;color:#b45309;margin-bottom:3px">Ventana de 24 h cerrada</div>
              <div style="font-size:12px;color:var(--t-3);line-height:1.6">WhatsApp no permite escribir libremente si el cliente no escribió en las últimas 24 h. Se le puede mandar una plantilla aprobada${cl&&cl.open_count?' — por ejemplo, reenviar su factura con los botones de arriba.':'.'}</div>
            </div>`}
      </div>`;

    const caja = document.getElementById('wa-msgs');
    let diaPrevio = '';
    caja.innerHTML = (d.messages||[]).map(m=>{
      const salida = m.direction === 'out';
      const dia = fmtDia(m.sent_at);
      const sep = dia && dia !== diaPrevio
        ? `<div style="text-align:center;font-size:11px;color:var(--t-4);font-weight:700;margin:6px 0">${esc(dia)}</div>` : '';
      diaPrevio = dia || diaPrevio;
      return sep + `<div style="display:flex;justify-content:${salida?'flex-end':'flex-start'}">
        <div style="max-width:78%;background:${salida?'#dcf8c6':'var(--bg-card)'};border:1px solid ${salida?'#bbe8a0':'var(--border)'};border-radius:12px;padding:9px 12px">
          ${m.template && salida ? `<div style="font-size:10.5px;font-weight:800;color:#047857;margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em">Plantilla · ${esc(kindLindo(m.kind))}</div>` : ''}
          ${mediaHtml(m)}
          ${textoVisible(m) ? `<div style="font-size:13px;color:#0f172a;white-space:pre-wrap;word-break:break-word">${esc(m.text)}</div>` : ''}
          ${!m.ok && m.error ? `<div style="font-size:11px;color:#b91c1c;margin-top:4px">No se pudo enviar: ${esc(m.error)}</div>` : ''}
          <div style="font-size:10.5px;color:#64748b;text-align:right;margin-top:3px">${fmtHora(m.sent_at)} ${salida?estadoIcono(m):''}</div>
        </div></div>`;
    }).join('') || `<div style="margin:auto;text-align:center;color:var(--t-4);font-size:13px">Sin mensajes todavía</div>`;
    caja.scrollTop = caja.scrollHeight;

    caja.querySelectorAll('img[data-media]').forEach(async img=>{
      try { img.src = await mediaUrl(img.dataset.media); }
      catch(e){ img.replaceWith(Object.assign(document.createElement('div'),
        {style:'font-size:11.5px;color:#b45309', textContent:'No se pudo cargar la imagen'})); }
    });

    const ta = document.getElementById('wa-reply');
    if (ta) {
      ta.value = borrador;
      ta.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); window.waSend(phone); } };
      if (forzar) ta.focus();
    }
  }

  const KINDS = {invoice_created:'Factura', invoice_due:'Aviso de vencimiento',
                 invoice_overdue:'Atraso', payment_received:'Pago recibido', test:'Prueba'};
  const kindLindo = k => KINDS[k] || (String(k||'').startsWith('reminder') ? 'Recordatorio' : (k||''));

  function estadoIcono(m){
    if (!m.ok) return '<span style="color:#b91c1c">⚠</span>';
    if (m.read_at) return '<span style="color:#0ea5e9" title="Leído">✓✓</span>';
    if (m.delivered_at) return '<span title="Entregado">✓✓</span>';
    return '<span title="Enviado">✓</span>';
  }

  // Una foto sin pie de foto llega con el texto «[image]» (para que la lista
  // muestre algo): en la burbuja no se repite, ahí ya se ve el archivo.
  const textoVisible = m => !!m.text && !(m.media && /^\[\w+\]$/.test(m.text));

  function mediaHtml(m){
    const md = m.media;
    if (!md || !md.media_id) return '';
    if (md.kind === 'image' || md.kind === 'sticker')
      return `<img data-media="${esc(md.media_id)}" alt="Foto" style="max-width:100%;width:230px;border-radius:9px;margin-bottom:6px;display:block;background:#e2e8f0;min-height:80px">`;
    const ico = md.kind === 'audio' || md.kind === 'voice' ? '🎤' : (md.kind === 'video' ? '🎬' : '📎');
    const nom = md.filename || (md.kind === 'audio' || md.kind === 'voice' ? 'Nota de voz' : 'Archivo');
    return `<button class="btn-s" style="padding:7px 11px;font-size:12px;margin-bottom:6px" onclick="waDownload('${esc(md.media_id)}','${esc(nom)}')">${ico} ${esc(nom)}</button>`;
  }

  window.waDownload = async function(id, nombre){
    try {
      const url = await mediaUrl(id);
      const a = document.createElement('a');
      a.href = url; a.download = nombre || 'archivo'; a.click();
    } catch(e){ alert(e.message); }
  };

  window.waSend = async function(phone){
    const ta = document.getElementById('wa-reply');
    const btn = document.getElementById('wa-send');
    if (!ta || !ta.value.trim()) return;
    const texto = ta.value.trim();
    if (btn) { btn.disabled = true; btn.textContent = 'Enviando…'; }
    try {
      await api(FAPI + '/whatsapp/inbox/' + phone + '/reply', {method:'POST', body:JSON.stringify({text:texto})});
      ta.value = '';
      await abrirHilo(phone, true);
      ultimaLista = ''; await cargarLista();
    } catch(e){
      alert(e.message);
      if (btn) { btn.disabled = false; btn.textContent = 'Enviar'; }
    }
  };

  window.waSendInvoice = async function(invoiceId){
    if (!confirm('¿Reenviar esta factura por WhatsApp (con el PDF adjunto)?')) return;
    try {
      await api(FAPI + '/invoices/' + invoiceId + '/whatsapp', {method:'POST'});
      alert('Factura enviada por WhatsApp.');
      if (window._waPhone) await abrirHilo(window._waPhone, true);
    } catch(e){ alert(e.message); }
  };

  // -------------------------------------------- vincular / dar de alta cliente
  window.waLinkModal = async function(phone){
    if (window.closeFinModal) closeFinModal();
    const clientes = await api(FAPI + '/clients').catch(()=>[]);
    const opciones = clientes.map(c=>`<option value="${c.id}">${esc(c.business_name)}${c.representative?' — '+esc(c.representative):''}</option>`).join('');
    document.body.insertAdjacentHTML('beforeend', `
      <div id="fin-modal" style="position:fixed;inset:0;background:rgba(2,6,18,.85);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);padding:20px;overflow-y:auto">
        <div style="width:100%;max-width:520px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--rl);box-shadow:var(--sh-lg);overflow:hidden;max-height:90vh;display:flex;flex-direction:column">
          <div style="padding:18px 22px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
            <div><div style="font-size:16px;font-weight:800">Vincular ${telLindo(phone)}</div>
              <div style="font-size:12px;color:var(--t-4);margin-top:2px">Asociá el número a un cliente o dalo de alta</div></div>
            <button onclick="closeFinModal()" class="btn-icon">✕</button>
          </div>
          <div style="padding:20px 22px;overflow-y:auto">
            <label class="inp-label">Cliente que ya existe</label>
            <select class="inp" id="wa-link-client"><option value="">— Elegir cliente —</option>${opciones}</select>
            <button class="btn-p" style="margin-top:10px;width:100%" onclick="waLinkExisting('${phone}')">Vincular con este cliente</button>
            <div style="display:flex;align-items:center;gap:10px;margin:18px 0 14px">
              <div style="flex:1;height:1px;background:var(--border)"></div>
              <span style="font-size:11px;font-weight:800;color:var(--t-4)">O DAR DE ALTA UNO NUEVO</span>
              <div style="flex:1;height:1px;background:var(--border)"></div>
            </div>
            <label class="inp-label">Nombre del negocio *</label>
            <input class="inp" id="wa-new-biz" placeholder="Taquería La Esquina">
            <div class="row2" style="margin-top:10px">
              <div><label class="inp-label">Persona de contacto</label><input class="inp" id="wa-new-rep" placeholder="Juan Pérez"></div>
              <div><label class="inp-label">Correo</label><input class="inp" id="wa-new-email" placeholder="juan@negocio.com"></div>
            </div>
            <label class="inp-label" style="margin-top:10px">Dirección</label>
            <input class="inp" id="wa-new-addr" placeholder="Opcional — se puede completar después">
            <div style="font-size:11.5px;color:var(--t-4);margin-top:8px;line-height:1.6">Se crea con este número como WhatsApp y teléfono. Los contratos y pantallas se cargan después desde su ficha.</div>
            <button class="btn-p" style="margin-top:14px;width:100%" onclick="waLinkNew('${phone}')">Crear cliente y vincular</button>
          </div>
        </div>
      </div>`);
  };

  window.waLinkExisting = async function(phone){
    const id = (document.getElementById('wa-link-client')||{}).value;
    if (!id) { alert('Elegí un cliente de la lista.'); return; }
    try {
      await api(FAPI + '/whatsapp/inbox/' + phone + '/link', {method:'POST', body:JSON.stringify({client_id:id})});
      closeFinModal();
      ultimaLista = ''; await cargarLista(); await abrirHilo(phone, true);
    } catch(e){ alert(e.message); }
  };

  window.waLinkNew = async function(phone){
    const biz = (document.getElementById('wa-new-biz')||{}).value || '';
    if (!biz.trim()) { alert('Escribí el nombre del negocio.'); return; }
    try {
      await api(FAPI + '/whatsapp/inbox/' + phone + '/link', {method:'POST', body:JSON.stringify({
        business_name: biz,
        representative: (document.getElementById('wa-new-rep')||{}).value || '',
        email: (document.getElementById('wa-new-email')||{}).value || '',
        address_line1: (document.getElementById('wa-new-addr')||{}).value || '',
      })});
      closeFinModal();
      ultimaLista = ''; await cargarLista(); await abrirHilo(phone, true);
    } catch(e){ alert(e.message); }
  };
})();

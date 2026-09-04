/**
 * managed-portal.js — MediaView Fase 4: Managed Client Portal
 * ─────────────────────────────────────────────────────────────
 * View-only portal for MANAGED_VIEWER accounts.
 * Registers loaders: managed-dashboard | managed-screens | managed-requests
 */

// ── Colour helpers ────────────────────────────────────────────────────────────
const MV_STATUS_COLOR = {
  online:  '#34d399',
  offline: '#f87171',
  unpaired:'#94a3b8',
  PENDING:    '#fbbf24',
  IN_PROGRESS:'#60a5fa',
  COMPLETED:  '#34d399',
  CANCELLED:  '#94a3b8',
};

const MV_TYPE_LABEL = {
  CONTENT_UPDATE: 'Actualización de Contenido',
  SCHEDULE_CHANGE:'Cambio de Horario',
  TECHNICAL_ISSUE:'Problema Técnico',
  ADD_SCREEN:     'Agregar Pantalla',
  REMOVE_SCREEN:  'Eliminar Pantalla',
  OTHER:          'Otro',
};

const MV_STATUS_LABEL = {
  PENDING:    'Pendiente',
  IN_PROGRESS:'En Proceso',
  COMPLETED:  'Completado',
  CANCELLED:  'Cancelado',
};

const MV_PRIORITY_LABEL = {
  LOW:    'Baja',
  NORMAL: 'Normal',
  HIGH:   'Alta',
  URGENT: 'Urgente',
};

function mvBadge(key, label){
  const c = MV_STATUS_COLOR[key] || '#94a3b8';
  return `<span style="display:inline-flex;align-items:center;font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;background:${c}22;color:${c};border:1px solid ${c}44">${label||key}</span>`;
}

function fmtDt(iso){
  if(!iso) return '—';
  try { return new Date(iso).toLocaleDateString('es-US',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}); }
  catch { return iso; }
}

// ── Shared KPI Card ───────────────────────────────────────────────────────────
function mvKpi(label, value, color, icon){
  return `
    <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--rl);padding:22px 24px;display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:12px;font-weight:600;color:var(--t-4);text-transform:uppercase;letter-spacing:.5px">${label}</span>
        <div style="width:36px;height:36px;border-radius:10px;background:${color}18;display:flex;align-items:center;justify-content:center">
          <svg width="18" height="18" fill="none" stroke="${color}" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="${icon}"/></svg>
        </div>
      </div>
      <div style="font-size:32px;font-weight:800;color:var(--t-1);font-variant-numeric:tabular-nums">${value}</div>
    </div>`;
}

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Managed Dashboard
// ══════════════════════════════════════════════════════════════════════════════
loaders['managed-dashboard'] = async function(){
  const el = document.getElementById('pg-managed-dashboard');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Cargando panel…</div>';
  try {
    const d = await api('/managed/dashboard');
    const usr = window._user ? window._user() : {};
    const now = new Date();
    const hour = now.getHours();
    const greet = hour < 12 ? 'Buenos días' : hour < 18 ? 'Buenas tardes' : 'Buenas noches';

    el.innerHTML = `
      <div class="welcome-banner fade" style="border-left:4px solid #6366f1;padding-left:20px;margin-bottom:28px">
        <div class="greeting" style="font-size:12px;color:var(--t-4);font-weight:600;text-transform:uppercase;letter-spacing:.5px">${greet} · Portal de Cliente Gestionado</div>
        <h1 style="font-size:28px;font-weight:800;margin:6px 0 6px">Bienvenido, ${(usr.name||'').split(' ')[0]||'Cliente'}</h1>
        <p style="color:var(--t-3);font-size:14px">Tu equipo de MediaView gestiona el contenido de tus pantallas. Aquí puedes monitorear el estado y solicitar cambios.</p>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:28px">
        ${mvKpi('Total Pantallas', d.total_screens, '#6366f1', 'M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z')}
        ${mvKpi('En Línea', d.online_screens, '#34d399', 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z')}
        ${mvKpi('Ubicaciones', d.total_locations, '#22d3ee', 'M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z')}
        ${mvKpi('Contenido Activo', d.active_content, '#a78bfa', 'M5 4h14a2 2 0 012 2v3H3V6a2 2 0 012-2zm-2 9h18v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5z')}
        ${mvKpi('Solicitudes Pendientes', d.pending_requests, '#fbbf24', 'M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z')}
      </div>

      <div>
        <div class="sh" style="margin-bottom:14px"><h2 style="font-size:16px;font-weight:700">Estado de Pantallas</h2>
          <a class="sh-link" onclick="go('managed-screens')">Ver todas <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" d="M9 5l7 7-7 7"/></svg></a>
        </div>
        <div class="card" style="overflow:hidden">
          ${d.screens_status.length === 0
            ? '<div style="padding:48px;text-align:center;color:var(--t-4);font-size:13px">No hay pantallas asignadas a tu organización todavía.</div>'
            : `<table style="width:100%;border-collapse:collapse;font-size:13px">
                <thead>
                  <tr style="border-bottom:1px solid var(--border)">
                    <th style="padding:12px 16px;text-align:left;font-weight:600;color:var(--t-3);font-size:11px;text-transform:uppercase">Nombre</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:600;color:var(--t-3);font-size:11px;text-transform:uppercase">Ubicación</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:600;color:var(--t-3);font-size:11px;text-transform:uppercase">Estado</th>
                    <th style="padding:12px 16px;text-align:left;font-weight:600;color:var(--t-3);font-size:11px;text-transform:uppercase">Último Heartbeat</th>
                  </tr>
                </thead>
                <tbody>
                  ${d.screens_status.map(s=>`
                    <tr style="border-bottom:1px solid var(--border);cursor:pointer" onclick="go('managed-screens')">
                      <td style="padding:14px 16px;font-weight:600;color:var(--t-1)">${escapeHtml(s.name||'')}</td>
                      <td style="padding:14px 16px;color:var(--t-3)">${escapeHtml((s.location?.city||'')+( s.location?.state?', '+s.location.state:''))}</td>
                      <td style="padding:14px 16px">${mvBadge(s.status, s.status==='online'?'En Línea':'Sin Conexión')}</td>
                      <td style="padding:14px 16px;color:var(--t-4);font-size:12px">${fmtDt(s.last_heartbeat)}</td>
                    </tr>`).join('')}
                </tbody>
              </table>`
          }
        </div>
      </div>

      <div style="margin-top:28px">
        <div class="sh" style="margin-bottom:14px"><h2 style="font-size:16px;font-weight:700">¿Necesitas un cambio?</h2></div>
        <div class="card" style="padding:24px;display:flex;align-items:center;gap:20px">
          <div style="width:48px;height:48px;border-radius:14px;background:rgba(99,102,241,.12);display:flex;align-items:center;justify-content:center;flex-shrink:0">
            <svg width="22" height="22" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z"/></svg>
          </div>
          <div style="flex:1">
            <div style="font-size:15px;font-weight:700;color:var(--t-1);margin-bottom:4px">Solicitar un Cambio</div>
            <div style="font-size:13px;color:var(--t-3)">¿Quieres actualizar el contenido, cambiar horarios o reportar un problema? Envía una solicitud a tu gestor de cuenta.</div>
          </div>
          <button class="btn-p" onclick="go('managed-requests')" style="flex-shrink:0;white-space:nowrap">+ Nueva Solicitud</button>
        </div>
      </div>`;
  } catch(e){
    el.innerHTML = `<div style="padding:48px;text-align:center"><p style="color:var(--red);font-size:13px">${e.message}</p></div>`;
  }
};

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Managed Screens
// ══════════════════════════════════════════════════════════════════════════════
loaders['managed-screens'] = async function(){
  const el = document.getElementById('pg-managed-screens');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Cargando pantallas…</div>';
  try {
    const screens = await api('/managed/screens');
    el.innerHTML = `
      <div class="ph">
        <div>
          <h1>Mis Pantallas</h1>
          <p>${screens.length} pantalla${screens.length!==1?'s':''} gestionada${screens.length!==1?'s':''} por MediaView</p>
        </div>
      </div>
      ${screens.length === 0
        ? `<div class="card" style="padding:48px;text-align:center">
             <svg width="40" height="40" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;display:block"><rect x="2" y="3" width="20" height="14" rx="2"/><path stroke-linecap="round" d="M8 21h8m-4-4v4"/></svg>
             <h3 style="font-size:15px;font-weight:700;margin-bottom:6px">No hay pantallas asignadas</h3>
             <p style="color:var(--t-4);font-size:13px">Tu equipo de MediaView aún no ha asignado pantallas a tu organización.</p>
           </div>`
        : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px">
            ${screens.map(s=>{
              const statusColor = MV_STATUS_COLOR[s.device_status] || '#94a3b8';
              const statusLabel = s.device_status==='online'?'En Línea':s.device_status==='offline'?'Sin Conexión':'Sin Dispositivo';
              return `
              <div class="card" style="overflow:hidden">
                <div style="padding:18px 18px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
                  <div style="min-width:0">
                    <div style="font-size:15px;font-weight:700;color:var(--t-1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(s.name||'')}</div>
                    <div style="font-size:12px;color:var(--t-4);margin-top:3px">${escapeHtml((s.location?.city||'')+( s.location?.state?', '+s.location.state:''))}</div>
                  </div>
                  ${mvBadge(s.device_status, statusLabel)}
                </div>
                <div style="padding:14px 18px">
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px;margin-bottom:10px">
                    <div>
                      <div style="color:var(--t-4);margin-bottom:2px">Tipo</div>
                      <div style="font-weight:600;color:var(--t-2)">${s.specs?.type||'LCD'}</div>
                    </div>
                    <div>
                      <div style="color:var(--t-4);margin-bottom:2px">Resolución</div>
                      <div style="font-weight:600;color:var(--t-2)">${s.specs?.resolution||'1920×1080'}</div>
                    </div>
                    <div>
                      <div style="color:var(--t-4);margin-bottom:2px">Contenido Activo</div>
                      <div style="font-weight:600;color:var(--t-2)">${s.active_playlists||0} playlist${s.active_playlists!==1?'s':''}</div>
                    </div>
                    <div>
                      <div style="color:var(--t-4);margin-bottom:2px">Último Heartbeat</div>
                      <div style="font-weight:600;color:var(--t-2);font-size:11px">${s.last_heartbeat?new Date(s.last_heartbeat).toLocaleTimeString('es-US',{hour:'2-digit',minute:'2-digit'}):'—'}</div>
                    </div>
                  </div>
                  <div style="font-size:11px;color:var(--t-5);padding-top:8px;border-top:1px solid var(--border)">
                    <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="vertical-align:middle;margin-right:3px"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/></svg>
                    ${escapeHtml(s.location?.address||'')}
                  </div>
                </div>
              </div>`;
            }).join('')}
          </div>`
      }
      <div style="margin-top:24px;padding:16px;background:rgba(99,102,241,.05);border:1px solid rgba(99,102,241,.15);border-radius:var(--radius-sm);font-size:13px;color:var(--t-3);display:flex;align-items:center;gap:10px">
        <svg width="16" height="16" fill="none" stroke="var(--brand-l)" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path stroke-linecap="round" d="M12 8v4m0 4h.01"/></svg>
        <span>Estas pantallas son <strong>administradas por MediaView</strong>. Para solicitar cambios de contenido o configuración, usa la sección <a onclick="go('managed-requests')" style="color:var(--brand-l);cursor:pointer;text-decoration:underline">Solicitar Cambio</a>.</span>
      </div>`;
  } catch(e){
    el.innerHTML = `<div style="padding:48px;text-align:center"><p style="color:var(--red);font-size:13px">${e.message}</p></div>`;
  }
};

// ══════════════════════════════════════════════════════════════════════════════
//  PAGE: Managed Requests
// ══════════════════════════════════════════════════════════════════════════════

// Show the "New Request" form inside the requests page
window._mvShowRequestForm = function(){
  const formEl = document.getElementById('mv-request-form');
  const listEl = document.getElementById('mv-request-list');
  if(formEl){
    formEl.style.display = '';
    listEl && (listEl.style.display = 'none');
    formEl.scrollIntoView({behavior:'smooth'});
  }
};

window._mvHideRequestForm = function(){
  const formEl = document.getElementById('mv-request-form');
  const listEl = document.getElementById('mv-request-list');
  if(formEl){
    formEl.style.display = 'none';
    listEl && (listEl.style.display = '');
  }
};

window._mvSubmitRequest = async function(){
  const btn = document.getElementById('mv-req-submit-btn');
  const errEl = document.getElementById('mv-req-err');
  const title = document.getElementById('mv-req-title').value.trim();
  const type  = document.getElementById('mv-req-type').value;
  const prio  = document.getElementById('mv-req-priority').value;
  const desc  = document.getElementById('mv-req-desc').value.trim();
  errEl.style.display = 'none';
  if(!title){ errEl.textContent = 'El título es obligatorio.'; errEl.style.display = ''; return; }
  if(!desc){  errEl.textContent = 'La descripción es obligatoria.'; errEl.style.display = ''; return; }
  btn.disabled = true;
  btn.textContent = 'Enviando…';
  try {
    await api('/managed/requests', {
      method:'POST',
      body: JSON.stringify({ title, request_type: type, description: desc, priority: prio }),
    });
    // Reload the requests page
    loaders['managed-requests']();
  } catch(e){
    errEl.textContent = e.message || 'Error al enviar la solicitud.';
    errEl.style.display = '';
    btn.disabled = false;
    btn.textContent = 'Enviar Solicitud';
  }
};

loaders['managed-requests'] = async function(){
  const el = document.getElementById('pg-managed-requests');
  el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--t-4)">Cargando solicitudes…</div>';
  try {
    const reqs = await api('/managed/requests');

    el.innerHTML = `
      <div class="ph">
        <div>
          <h1>Solicitudes de Cambio</h1>
          <p>${reqs.length} solicitud${reqs.length!==1?'es':''} enviada${reqs.length!==1?'s':''}</p>
        </div>
        <button class="btn-p" onclick="window._mvShowRequestForm()">+ Nueva Solicitud</button>
      </div>

      <!-- New Request Form (hidden by default) -->
      <div id="mv-request-form" style="display:none;margin-bottom:28px">
        <div class="card" style="padding:28px;max-width:680px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:22px">
            <h2 style="font-size:17px;font-weight:700">Nueva Solicitud de Cambio</h2>
            <button onclick="window._mvHideRequestForm()" style="width:28px;height:28px;border-radius:8px;background:var(--bg-2);border:1px solid var(--border);color:var(--t-3);cursor:pointer;font-size:16px">✕</button>
          </div>
          <div style="display:flex;flex-direction:column;gap:16px">
            <div>
              <label class="inp-label">Título *</label>
              <input id="mv-req-title" class="inp" placeholder="Ej. Actualizar imagen de fondo en Pantalla Lobby">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div>
                <label class="inp-label">Tipo de Solicitud</label>
                <select id="mv-req-type" class="inp">
                  <option value="CONTENT_UPDATE">Actualización de Contenido</option>
                  <option value="SCHEDULE_CHANGE">Cambio de Horario</option>
                  <option value="TECHNICAL_ISSUE">Problema Técnico</option>
                  <option value="ADD_SCREEN">Agregar Pantalla</option>
                  <option value="REMOVE_SCREEN">Eliminar Pantalla</option>
                  <option value="OTHER">Otro</option>
                </select>
              </div>
              <div>
                <label class="inp-label">Prioridad</label>
                <select id="mv-req-priority" class="inp">
                  <option value="LOW">Baja</option>
                  <option value="NORMAL" selected>Normal</option>
                  <option value="HIGH">Alta</option>
                  <option value="URGENT">Urgente</option>
                </select>
              </div>
            </div>
            <div>
              <label class="inp-label">Descripción *</label>
              <textarea id="mv-req-desc" class="inp" rows="4" placeholder="Describe el cambio que necesitas con el mayor detalle posible…" style="resize:vertical;min-height:100px"></textarea>
            </div>
            <p id="mv-req-err" style="color:var(--red);font-size:12px;display:none"></p>
            <div style="display:flex;gap:10px;justify-content:flex-end">
              <button onclick="window._mvHideRequestForm()" style="padding:10px 20px;border-radius:var(--radius-sm);background:var(--bg-2);border:1px solid var(--border);color:var(--t-2);font-weight:600;font-size:13px;cursor:pointer">Cancelar</button>
              <button id="mv-req-submit-btn" class="btn-p" onclick="window._mvSubmitRequest()">Enviar Solicitud</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Requests List -->
      <div id="mv-request-list">
        ${reqs.length === 0
          ? `<div class="card" style="padding:56px;text-align:center">
               <svg width="40" height="40" fill="none" stroke="var(--t-4)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 14px;display:block"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-4 4v-4z"/></svg>
               <h3 style="font-size:15px;font-weight:700;margin-bottom:6px">Sin solicitudes todavía</h3>
               <p style="color:var(--t-4);font-size:13px;margin-bottom:18px">¿Necesitas un cambio en tu contenido o pantallas? Envía tu primera solicitud.</p>
               <button class="btn-p" onclick="window._mvShowRequestForm()">+ Crear Primera Solicitud</button>
             </div>`
          : reqs.map(r=>{
              const statusColor = MV_STATUS_COLOR[r.status] || '#94a3b8';
              const prioColor = r.priority==='URGENT'?'#ef4444':r.priority==='HIGH'?'#f97316':r.priority==='LOW'?'#94a3b8':'var(--t-3)';
              return `
              <div class="card" style="padding:20px;margin-bottom:10px">
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px">
                  <div style="min-width:0">
                    <div style="font-size:15px;font-weight:700;color:var(--t-1);margin-bottom:4px">${escapeHtml(r.title||'')}</div>
                    <div style="font-size:12px;color:var(--t-4)">
                      ${MV_TYPE_LABEL[r.request_type]||r.request_type} ·
                      <span style="color:${prioColor};font-weight:600">${MV_PRIORITY_LABEL[r.priority]||r.priority}</span> ·
                      ${fmtDt(r.created_at)}
                    </div>
                  </div>
                  ${mvBadge(r.status, MV_STATUS_LABEL[r.status]||r.status)}
                </div>
                <p style="font-size:13px;color:var(--t-3);margin:0 0 ${r.admin_notes?'10px':'0'};line-height:1.6">${escapeHtml(r.description||'')}</p>
                ${r.admin_notes
                  ? `<div style="padding:10px 14px;background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.15);border-radius:8px;margin-top:8px">
                       <div style="font-size:11px;font-weight:700;color:var(--brand-l);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Nota del Equipo MediaView</div>
                       <div style="font-size:13px;color:var(--t-2)">${escapeHtml(r.admin_notes)}</div>
                     </div>`
                  : ''}
              </div>`;
            }).join('')}
      </div>`;
  } catch(e){
    el.innerHTML = `<div style="padding:48px;text-align:center"><p style="color:var(--red);font-size:13px">${e.message}</p></div>`;
  }
};

// ══════════════════════════════════════════════════════════════════════════════
//  ADMIN: Managed Requests section in the admin panel
//  (adds to the existing admin loaders - ONLY executed if user is Admin)
// ══════════════════════════════════════════════════════════════════════════════
window._mvAdminLoadRequests = async function(containerId){
  const el = document.getElementById(containerId);
  if(!el) return;
  el.innerHTML = '<p style="padding:20px;color:var(--t-4);font-size:13px">Cargando solicitudes…</p>';
  try {
    const reqs = await api('/admin/managed/requests');
    if(reqs.length === 0){
      el.innerHTML = '<p style="padding:20px;color:var(--t-4);font-size:13px">No hay solicitudes de clientes gestionados todavía.</p>';
      return;
    }
    el.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px;padding:4px 0">` +
      reqs.map(r=>{
        const statusColor = MV_STATUS_COLOR[r.status] || '#94a3b8';
        return `
        <div style="padding:16px;background:var(--bg-2);border-radius:10px;border:1px solid var(--border)">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px">
            <div>
              <div style="font-size:14px;font-weight:700;color:var(--t-1)">${escapeHtml(r.title||'')}</div>
              <div style="font-size:11px;color:var(--t-4);margin-top:2px">${escapeHtml(r.created_by_email||'')} · ${MV_TYPE_LABEL[r.request_type]||r.request_type} · ${fmtDt(r.created_at)}</div>
            </div>
            <div style="display:flex;gap:6px;align-items:center;flex-shrink:0">
              ${mvBadge(r.status, MV_STATUS_LABEL[r.status]||r.status)}
              <select onchange="window._mvAdminSetStatus('${r.id}', this.value, '${containerId}')"
                style="font-size:11px;padding:4px 8px;border-radius:6px;background:var(--bg-3);border:1px solid var(--border);color:var(--t-2);cursor:pointer">
                <option value="">Cambiar estado…</option>
                <option value="PENDING">Pendiente</option>
                <option value="IN_PROGRESS">En Proceso</option>
                <option value="COMPLETED">Completado</option>
                <option value="CANCELLED">Cancelado</option>
              </select>
            </div>
          </div>
          <p style="font-size:12px;color:var(--t-3);margin:0 0 6px">${escapeHtml(r.description||'')}</p>
          ${r.admin_notes ? `<p style="font-size:11px;color:var(--brand-l);margin:0"><strong>Nota:</strong> ${escapeHtml(r.admin_notes)}</p>` : ''}
        </div>`;
      }).join('') + '</div>';
  } catch(e){
    el.innerHTML = `<p style="color:var(--red);font-size:12px;padding:16px">${e.message}</p>`;
  }
};

window._mvAdminSetStatus = async function(reqId, newStatus, containerId){
  if(!newStatus) return;
  const note = newStatus === 'COMPLETED'
    ? (prompt('Nota para el cliente (opcional):')||'')
    : '';
  try {
    await api(`/admin/managed/requests/${reqId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: newStatus, admin_notes: note||null }),
    });
    window._mvAdminLoadRequests(containerId);
  } catch(e){
    alert('Error al actualizar: '+e.message);
  }
};

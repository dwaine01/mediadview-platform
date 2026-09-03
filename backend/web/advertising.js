// advertising.js — MediaView Fase 3: Marketplace de Publicidad Pública
// Handles: Advertiser portal, Admin Approval Center, Screen QR, Waitlist
// v20260903-fase3-v1

/* global api, user, go, token */

// ── Estado global ──────────────────────────────────────────────────────────────
let _adTab = 'marketplace';
let _approvalTab = 'pending';

// ── Badge de estado para campañas ad ────────────────────────────────────────────
function adStatusBadge(status) {
  const map = {
    DRAFT:          { cls: 'bdg-pending', label: 'Borrador' },
    PENDING_REVIEW: { cls: 'bdg-pending', label: '⏳ En revisión' },
    APPROVED:       { cls: 'bdg-active',  label: '✅ Aprobada' },
    ACTIVE:         { cls: 'bdg-active',  label: '🟢 Activa' },
    REJECTED:       { cls: 'bdg-rej',     label: '❌ Rechazada' },
    CANCELLED:      { cls: 'bdg-rej',     label: 'Cancelada' },
    EXPIRED:        { cls: 'bdg-pending', label: 'Expirada' },
  };
  const b = map[status] || { cls: 'bdg-pending', label: status };
  return `<span class="bdg ${b.cls}">${b.label}</span>`;
}

// ── Formatear precio ──────────────────────────────────────────────────────────
function fmtPrice(v, cur = 'USD') {
  if (v == null) return '—';
  return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' ' + cur;
}

function periodLabel(p) {
  const map = { weekly: 'Semanal', monthly: 'Mensual', yearly: 'Anual' };
  return map[p] || p;
}

// ── ADVERTISER PORTAL ──────────────────────────────────────────────────────────

window._adCampaignForm = {};   // state for create form
window._selectedScreens = {};  // selected screens for new campaign

async function renderAdvertiserPortal() {
  const el = document.getElementById('pg-advertiser');
  if (!el) return;

  const tabs = [
    { id: 'marketplace',    label: '🗺 Marketplace' },
    { id: 'my-campaigns',   label: '📋 Mis Campañas' },
    { id: 'create-ad',      label: '➕ Nueva Campaña' },
    { id: 'waitlist',       label: '⏳ Lista de Espera' },
  ];

  el.innerHTML = `
    <div class="ph"><div><h1>Portal del Anunciante</h1><p>Gestiona tus campañas en pantallas públicas</p></div></div>
    <div class="tabs-row">
      ${tabs.map(t => `<button class="tab-btn ${_adTab === t.id ? 'on' : ''}" onclick="switchAdTab('${t.id}')">${t.label}</button>`).join('')}
    </div>
    <div id="ad-tab-content" style="margin-top:16px"></div>`;

  await loadAdTabContent();
}

async function switchAdTab(tab) {
  _adTab = tab;
  // Update tab buttons
  document.querySelectorAll('#pg-advertiser .tab-btn').forEach(b => {
    b.classList.toggle('on', b.textContent.includes(tab) || b.getAttribute('onclick').includes(`'${tab}'`));
  });
  await loadAdTabContent();
}

async function loadAdTabContent() {
  const el = document.getElementById('ad-tab-content');
  if (!el) return;
  el.innerHTML = '<div style="padding:40px;text-align:center;color:#64748b"><div class="spinner2"></div></div>';
  try {
    if (_adTab === 'marketplace')  await renderMarketplace(el);
    else if (_adTab === 'my-campaigns') await renderMyCampaigns(el);
    else if (_adTab === 'create-ad')  await renderCreateAdForm(el);
    else if (_adTab === 'waitlist')    await renderMyWaitlist(el);
  } catch (e) {
    el.innerHTML = `<div class="alert-err">Error: ${e.message}</div>`;
  }
}

// ── Marketplace ──────────────────────────────────────────────────────────────
async function renderMarketplace(el) {
  let screens = [];
  let cities = [];
  try {
    [screens, cities] = await Promise.all([
      api('/marketplace/screens'),
      api('/marketplace/cities'),
    ]);
  } catch (e) {
    el.innerHTML = `<div style="color:var(--red);padding:20px">${e.message}</div>`;
    return;
  }

  const cityFilter = document.getElementById('mkt-city-filter')?.value || '';

  el.innerHTML = `
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center">
      <select id="mkt-city-filter" class="inp" style="max-width:200px" onchange="switchAdTab('marketplace')">
        <option value="">Todas las ciudades</option>
        ${cities.map(c => `<option value="${c}" ${c === cityFilter ? 'selected' : ''}>${c}</option>`).join('')}
      </select>
      <span style="font-size:13px;color:#64748b">${screens.length} pantalla${screens.length !== 1 ? 's' : ''} disponible${screens.length !== 1 ? 's' : ''}</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px">
      ${screens.length === 0 ? '<div class="empty"><h3>Sin pantallas disponibles</h3><p>No hay pantallas de publicidad activas por el momento</p></div>' : screens.map(s => renderScreenCard(s)).join('')}
    </div>`;
}

function renderScreenCard(s) {
  const ap = s.pricing || {};
  const prices = [
    ap.price_per_week ? `<span>Sem: ${fmtPrice(ap.price_per_week)}</span>` : '',
    ap.price_per_month ? `<span>Mes: ${fmtPrice(ap.price_per_month)}</span>` : '',
    ap.price_per_year ? `<span>Año: ${fmtPrice(ap.price_per_year)}</span>` : '',
  ].filter(Boolean).join(' · ');

  const slotsColor = s.is_full ? '#ef4444' : s.available_slots <= 1 ? '#f59e0b' : '#10b981';
  const slotsText = s.is_full ? '🔴 Lleno' : `🟢 ${s.available_slots} libre${s.available_slots !== 1 ? 's' : ''}`;

  return `
    <div class="card card-i" style="padding:20px;cursor:pointer" onclick="selectScreenForCampaign('${s.id}','${(s.name || '').replace(/'/g, "\\'")}')">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
        <div>
          <div style="font-size:15px;font-weight:700;color:#e2e8f0;margin-bottom:4px">${s.name}</div>
          <div style="font-size:12px;color:#64748b">${s.location?.city || ''}, ${s.location?.state || ''}</div>
        </div>
        <span style="font-size:11px;font-weight:600;color:${slotsColor};background:${slotsColor}22;padding:3px 8px;border-radius:6px;border:1px solid ${slotsColor}44">${slotsText}</span>
      </div>
      <div style="font-size:12px;color:#94a3b8;margin-bottom:12px;line-height:1.5">${(s.description || '').substring(0, 80)}${(s.description || '').length > 80 ? '…' : ''}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
        ${s.specs?.type ? `<span class="tag">${s.specs.type}</span>` : ''}
        ${s.specs?.resolution ? `<span class="tag">${s.specs.resolution}</span>` : ''}
        ${s.specs?.size ? `<span class="tag">${s.specs.size}</span>` : ''}
      </div>
      <div style="font-size:12px;color:#6366f1;font-weight:600;border-top:1px solid rgba(255,255,255,.06);padding-top:10px">${prices || 'Consultar precio'}</div>
      <div style="display:flex;gap:8px;margin-top:10px">
        ${s.is_full
          ? `<button class="btn-s" style="flex:1;font-size:12px;color:var(--amber);border-color:rgba(245,158,11,.3)" onclick="event.stopPropagation();joinWaitlist('${s.id}','${(s.name||'').replace(/'/g,"\\'")}')">📋 Lista de espera</button>`
          : `<button class="btn-p" style="flex:1;font-size:12px;padding:8px" onclick="event.stopPropagation();selectScreenForCampaign('${s.id}','${(s.name||'').replace(/'/g,"\\'")}')">✨ Anunciarme aquí</button>`}
      </div>
    </div>`;
}

function selectScreenForCampaign(screenId, screenName) {
  if (!window._selectedScreens) window._selectedScreens = {};
  if (window._selectedScreens[screenId]) {
    delete window._selectedScreens[screenId];
  } else {
    window._selectedScreens[screenId] = screenName;
  }
  _adTab = 'create-ad';
  // Update tabs
  document.querySelectorAll('#pg-advertiser .tab-btn').forEach(b => {
    b.classList.toggle('on', b.getAttribute('onclick').includes("'create-ad'"));
  });
  loadAdTabContent();
}

// ── Crear Campaña ─────────────────────────────────────────────────────────────
async function renderCreateAdForm(el) {
  const selected = window._selectedScreens || {};
  const selectedIds = Object.keys(selected);

  el.innerHTML = `
    <div style="max-width:680px">
      <h2 style="font-size:18px;font-weight:700;margin-bottom:4px">Crear Nueva Campaña Publicitaria</h2>
      <p style="font-size:13px;color:#64748b;margin-bottom:20px">Configura tu campaña para pantallas públicas MediaView</p>

      <div class="card" style="padding:20px;margin-bottom:16px">
        <div class="card-section-title">1. Pantallas Seleccionadas</div>
        ${selectedIds.length === 0
          ? '<div style="font-size:13px;color:#64748b;margin-bottom:10px">Ninguna pantalla seleccionada. Ve al Marketplace para seleccionar.</div>'
          : `<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px">${selectedIds.map(id => `<span class="tag" style="color:#6366f1;border-color:rgba(99,102,241,.3);padding:6px 12px">${selected[id]} <span onclick="removeSelectedScreen('${id}')" style="cursor:pointer;color:#ef4444;margin-left:4px">✕</span></span>`).join('')}</div>`}
        <button class="btn-s" style="font-size:12px" onclick="_adTab='marketplace';loadAdTabContent()">
          ${selectedIds.length === 0 ? '🗺 Ir al Marketplace' : '+ Agregar más pantallas'}
        </button>
      </div>

      <div class="card" style="padding:20px;margin-bottom:16px">
        <div class="card-section-title">2. Detalles de la Campaña</div>
        <div style="margin-bottom:12px">
          <div class="lbl">Nombre de la campaña</div>
          <input class="inp" id="ad-name" placeholder="Ej: Oferta Verano 2026" value="${window._adCampaignForm.name || ''}">
        </div>
        <div style="margin-bottom:12px">
          <div class="lbl">URL del material publicitario (video o imagen)</div>
          <input class="inp" id="ad-creative-url" type="url" placeholder="https://cdn.tudominio.com/anuncio.mp4" value="${window._adCampaignForm.creative_url || ''}">
          <div style="font-size:11px;color:#64748b;margin-top:4px">Acepta .mp4, .mov, .jpg, .png, etc.</div>
        </div>
        <div style="margin-bottom:12px">
          <div class="lbl">Notas adicionales (opcional)</div>
          <input class="inp" id="ad-notes" placeholder="Cualquier instrucción especial..." value="${window._adCampaignForm.notes || ''}">
        </div>
      </div>

      <div class="card" style="padding:20px;margin-bottom:16px">
        <div class="card-section-title">3. Período y Duración</div>
        <div class="row2" style="gap:12px">
          <div>
            <div class="lbl">Período de facturación</div>
            <select class="inp" id="ad-period" onchange="updateAdQuote()">
              <option value="weekly" ${(window._adCampaignForm.pricing_period||'monthly') === 'weekly' ? 'selected' : ''}>Semanal</option>
              <option value="monthly" ${(window._adCampaignForm.pricing_period||'monthly') === 'monthly' ? 'selected' : ''}>Mensual</option>
              <option value="yearly" ${(window._adCampaignForm.pricing_period||'monthly') === 'yearly' ? 'selected' : ''}>Anual</option>
            </select>
          </div>
          <div>
            <div class="lbl">Duración (número de períodos)</div>
            <input class="inp" id="ad-duration" type="number" min="1" max="24" value="${window._adCampaignForm.duration || 1}" onchange="updateAdQuote()">
          </div>
        </div>
        <div style="margin-top:12px">
          <div class="lbl">Fecha de inicio</div>
          <input class="inp" id="ad-start-date" type="date" value="${window._adCampaignForm.start_date || new Date().toISOString().split('T')[0]}" onchange="updateAdQuote()">
        </div>
        <div id="ad-duration-lbl" style="font-size:12px;color:#64748b;margin-top:6px"></div>
      </div>

      <!-- Cotización en tiempo real -->
      <div class="card" id="ad-quote-card" style="padding:20px;margin-bottom:16px;background:rgba(99,102,241,.06);border-color:rgba(99,102,241,.2)">
        <div class="card-section-title">💰 Cotización (calculada en backend)</div>
        <div id="ad-quote-content" style="color:#64748b;font-size:13px">Selecciona pantallas, período y duración para ver el precio</div>
      </div>

      <div id="ad-form-msg" style="display:none;padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:12px"></div>
      <div style="display:flex;gap:10px">
        <button class="btn-p" onclick="submitAdCampaign()" style="flex:1;padding:14px;font-size:15px">Guardar como Borrador</button>
        <button class="btn-s" onclick="clearAdForm()" style="padding:14px 20px">Limpiar</button>
      </div>
    </div>`;

  updateAdQuote();
}

function removeSelectedScreen(id) {
  delete window._selectedScreens[id];
  loadAdTabContent();
}

function clearAdForm() {
  window._selectedScreens = {};
  window._adCampaignForm = {};
  loadAdTabContent();
}

let _quoteDebounce = null;
function updateAdQuote() {
  clearTimeout(_quoteDebounce);
  _quoteDebounce = setTimeout(async () => {
    const screenIds = Object.keys(window._selectedScreens || {});
    const period = document.getElementById('ad-period')?.value;
    const duration = parseInt(document.getElementById('ad-duration')?.value) || 1;
    const startDate = document.getElementById('ad-start-date')?.value;

    const lbl = document.getElementById('ad-duration-lbl');
    if (lbl && period && startDate) {
      const days = { weekly: 7, monthly: 30, yearly: 365 }[period] || 30;
      const start = new Date(startDate);
      const end = new Date(start.getTime() + days * duration * 86400000 - 86400000);
      lbl.textContent = `Tu campaña duraría del ${startDate} al ${end.toISOString().split('T')[0]}`;
    }

    if (screenIds.length === 0) return;
    const qEl = document.getElementById('ad-quote-content');
    if (!qEl) return;
    qEl.innerHTML = '<span style="color:#64748b">Calculando…</span>';
    try {
      const q = await api('/ad-campaigns/checkout', {
        method: 'POST',
        body: JSON.stringify({ screen_ids: screenIds, pricing_period: period, duration, start_date: startDate }),
      });
      const lines = q.lines || [];
      qEl.innerHTML = `
        ${lines.map(l => `
          <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05)">
            <div>
              <div style="font-size:13px;font-weight:600;color:#e2e8f0">${l.screen_name}</div>
              <div style="font-size:11px;color:#64748b">${l.screen_city} · ${l.duration}× ${periodLabel(l.pricing_period)} @ ${fmtPrice(l.unit_price)}</div>
            </div>
            <div style="font-size:14px;font-weight:700;color:#6366f1">${fmtPrice(l.line_total)}</div>
          </div>`).join('')}
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
          <div style="font-size:14px;font-weight:700;color:#e2e8f0">TOTAL</div>
          <div style="font-size:24px;font-weight:800;color:#6366f1">${fmtPrice(q.grand_total)}</div>
        </div>
        <div style="font-size:11px;color:#64748b;margin-top:4px">Del ${q.start_date} al ${q.end_date} · Pago SIMULADO</div>`;
    } catch (e) {
      qEl.innerHTML = `<span style="color:var(--red)">${e.message}</span>`;
    }
  }, 600);
}

async function submitAdCampaign() {
  const screenIds = Object.keys(window._selectedScreens || {});
  const name = document.getElementById('ad-name')?.value?.trim();
  const creativeUrl = document.getElementById('ad-creative-url')?.value?.trim();
  const period = document.getElementById('ad-period')?.value;
  const duration = parseInt(document.getElementById('ad-duration')?.value) || 1;
  const startDate = document.getElementById('ad-start-date')?.value;
  const notes = document.getElementById('ad-notes')?.value?.trim();
  const msgEl = document.getElementById('ad-form-msg');

  if (!name) { showAdMsg('El nombre de la campaña es requerido', 'error'); return; }
  if (!creativeUrl) { showAdMsg('La URL del material publicitario es requerida', 'error'); return; }
  if (!creativeUrl.startsWith('http')) { showAdMsg('La URL debe empezar con http:// o https://', 'error'); return; }
  if (screenIds.length === 0) { showAdMsg('Selecciona al menos una pantalla en el Marketplace', 'error'); return; }

  showAdMsg('Creando campaña…', 'info');
  try {
    const c = await api('/ad-campaigns', {
      method: 'POST',
      body: JSON.stringify({
        name, screen_ids: screenIds, creative_url: creativeUrl,
        pricing_period: period, duration, start_date: startDate, notes,
      }),
    });
    window._adCampaignForm = {};
    window._selectedScreens = {};
    showAdMsg(`✅ Campaña "${c.name}" creada en estado BORRADOR. Ve a "Mis Campañas" para pagar y enviar a revisión.`, 'success');
    setTimeout(() => { _adTab = 'my-campaigns'; loadAdTabContent(); }, 2500);
  } catch (e) {
    const detail = e.detail || e.message;
    if (typeof detail === 'object' && detail.waitlist_available) {
      showAdMsg(`🔴 ${detail.message}`, 'error');
    } else {
      showAdMsg(detail || e.message, 'error');
    }
  }
}

function showAdMsg(msg, type) {
  const el = document.getElementById('ad-form-msg');
  if (!el) return;
  const colors = { error: '#ef4444', success: '#10b981', info: '#6366f1' };
  const bgs = { error: 'rgba(239,68,68,.08)', success: 'rgba(16,185,129,.08)', info: 'rgba(99,102,241,.08)' };
  el.style.display = 'block';
  el.style.color = colors[type] || '#e2e8f0';
  el.style.background = bgs[type] || 'rgba(255,255,255,.05)';
  el.style.border = `1px solid ${colors[type] || '#64748b'}44`;
  el.textContent = msg;
}

// ── Mis Campañas ──────────────────────────────────────────────────────────────
async function renderMyCampaigns(el) {
  const camps = await api('/ad-campaigns');
  if (camps.length === 0) {
    el.innerHTML = `<div class="empty">
      <div class="empty-ico">📢</div>
      <h3>Sin campañas aún</h3>
      <p>Crea tu primera campaña publicitaria en una pantalla pública</p>
      <button class="btn-p" onclick="_adTab='create-ad';switchAdTab('create-ad')">+ Nueva Campaña</button>
    </div>`;
    return;
  }

  el.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:12px">
      ${camps.map(c => {
        const screens = (c.screens_info || []).map(s => s.name).join(', ');
        const canPay = c.status === 'DRAFT';
        const hasRejection = c.status === 'DRAFT' && c.rejection_reason;
        return `
          <div class="card" style="padding:18px">
            <div style="display:flex;align-items:flex-start;gap:12px">
              <div style="flex:1;min-width:0">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                  <div style="font-size:15px;font-weight:700;color:#e2e8f0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.name}</div>
                  ${adStatusBadge(c.status)}
                </div>
                <div style="font-size:12px;color:#64748b;margin-bottom:6px">
                  ${screens || 'Sin pantallas'} · ${periodLabel(c.pricing_period)} × ${c.duration} · ${c.start_date || ''} → ${c.end_date || ''}
                </div>
                ${hasRejection ? `<div style="font-size:12px;color:#ef4444;background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.2);border-radius:6px;padding:8px;margin-bottom:8px">❌ Motivo de rechazo: ${c.rejection_reason}</div>` : ''}
                <div style="font-size:12px;color:#94a3b8;margin-top:2px">
                  🔗 <a href="${c.creative_url}" target="_blank" style="color:#6366f1;text-decoration:none">${c.creative_url.substring(0,60)}${c.creative_url.length>60?'…':''}</a>
                </div>
              </div>
              <div style="text-align:right;flex-shrink:0">
                <div style="font-size:20px;font-weight:800;color:#6366f1">${fmtPrice(c.total_price)}</div>
                ${c.payment_ref ? `<div style="font-size:10px;color:#64748b;margin-top:2px">${c.payment_ref}</div>` : ''}
              </div>
            </div>
            ${canPay ? `<div style="display:flex;gap:8px;margin-top:12px;border-top:1px solid rgba(255,255,255,.06);padding-top:12px">
              <button class="btn-p" style="flex:1;padding:10px;font-size:13px" onclick="payAdCampaign('${c.id}','${(c.name||'').replace(/'/g,"\\'")}')">💳 Pagar y enviar a revisión (MOCK)</button>
            </div>` : ''}
          </div>`;
      }).join('')}
    </div>`;
}

async function payAdCampaign(id, name) {
  if (!confirm(`¿Proceder con el pago SIMULADO de la campaña "${name}"?\n\nEsto la enviará a revisión del equipo MediaView.`)) return;
  try {
    const r = await api(`/ad-campaigns/${id}/pay`, { method: 'POST' });
    alert(`✅ ${r.message}\n\nRef: ${r.payment_ref}`);
    await loadAdTabContent();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ── Lista de Espera ───────────────────────────────────────────────────────────
async function renderMyWaitlist(el) {
  const entries = await api('/ad-campaigns/waitlist/mine');
  if (entries.length === 0) {
    el.innerHTML = `<div class="empty"><div class="empty-ico">⏳</div><h3>Sin entradas en espera</h3><p>Cuando una pantalla esté llena puedes unirte a su lista de espera</p></div>`;
    return;
  }
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:12px">
    ${entries.map(e => `
      <div class="card" style="padding:16px">
        <div style="display:flex;align-items:center;gap:12px">
          <div style="flex:1">
            <div style="font-size:14px;font-weight:700;color:#e2e8f0">${e.screen_name}</div>
            <div style="font-size:12px;color:#64748b">${e.screen_city || ''} · En espera desde ${new Date(e.created_at).toLocaleDateString()}</div>
          </div>
          <span class="bdg bdg-pending">${e.status}</span>
        </div>
      </div>`).join('')}
  </div>`;
}

async function joinWaitlist(screenId, screenName) {
  const notes = prompt(`Únete a la lista de espera para "${screenName}".\n\nNotas (opcional):`);
  if (notes === null) return; // cancelado
  try {
    await api('/marketplace/screens/' + screenId + '/waitlist', {
      method: 'POST',
      body: JSON.stringify({ screen_id: screenId, notes }),
    });
    alert(`✅ Añadido a la lista de espera para "${screenName}". Te notificaremos cuando haya disponibilidad.`);
    await loadAdTabContent();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ── ADMIN APPROVAL CENTER ──────────────────────────────────────────────────────

async function renderApprovalCenter() {
  const el = document.getElementById('pg-approval');
  if (!el) return;

  let stats = { total_campaigns: 0, pending_review: 0, active: 0, rejected: 0, waitlist_entries: 0, total_mock_revenue: 0 };
  try { stats = await api('/admin/ad-campaigns/stats'); } catch {}

  const tabs = [
    { id: 'pending',  label: `⏳ Pendientes (${stats.pending_review})` },
    { id: 'all',      label: '📋 Todas las Campañas' },
    { id: 'waitlist', label: `📋 Lista de Espera (${stats.waitlist_entries})` },
  ];

  el.innerHTML = `
    <div class="ph">
      <div><h1>Centro de Aprobación</h1><p>Revisión de campañas publicitarias públicas</p></div>
    </div>

    <!-- KPI Cards -->
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:20px">
      ${[
        { label: 'Pendientes', v: stats.pending_review, c: '--amber' },
        { label: 'Activas', v: stats.active, c: '--green' },
        { label: 'Total', v: stats.total_campaigns, c: '--brand-l' },
        { label: 'Revenue (MOCK)', v: fmtPrice(stats.total_mock_revenue), c: '--cyan' },
        { label: 'En espera', v: stats.waitlist_entries, c: '--violet' },
      ].map(s => `<div class="card" style="padding:16px;text-align:center">
        <div style="font-size:22px;font-weight:800;color:var(${s.c})">${s.v}</div>
        <div style="font-size:11px;color:#64748b;font-weight:600;margin-top:2px">${s.label}</div>
      </div>`).join('')}
    </div>

    <div class="tabs-row">
      ${tabs.map(t => `<button class="tab-btn ${_approvalTab === t.id ? 'on' : ''}" onclick="switchApprovalTab('${t.id}')">${t.label}</button>`).join('')}
    </div>
    <div id="approval-tab-content" style="margin-top:16px"></div>`;

  await loadApprovalTabContent();
}

async function switchApprovalTab(tab) {
  _approvalTab = tab;
  document.querySelectorAll('#pg-approval .tab-btn').forEach(b => {
    b.classList.toggle('on', b.getAttribute('onclick').includes(`'${tab}'`));
  });
  await loadApprovalTabContent();
}

async function loadApprovalTabContent() {
  const el = document.getElementById('approval-tab-content');
  if (!el) return;
  el.innerHTML = '<div style="padding:40px;text-align:center;color:#64748b"></div>';
  try {
    if (_approvalTab === 'pending') await renderPendingCampaigns(el);
    else if (_approvalTab === 'all') await renderAllAdCampaigns(el);
    else if (_approvalTab === 'waitlist') await renderAdminWaitlist(el);
  } catch (e) {
    el.innerHTML = `<div style="color:var(--red);padding:20px">${e.message}</div>`;
  }
}

async function renderPendingCampaigns(el) {
  const camps = await api('/admin/ad-campaigns/pending');
  if (camps.length === 0) {
    el.innerHTML = `<div class="empty"><div class="empty-ico">✅</div><h3>Sin campañas pendientes</h3><p>Todas las campañas han sido procesadas</p></div>`;
    return;
  }
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:16px">
    ${camps.map(c => renderApprovalCard(c, true)).join('')}
  </div>`;
}

async function renderAllAdCampaigns(el) {
  const camps = await api('/admin/ad-campaigns');
  if (camps.length === 0) {
    el.innerHTML = `<div class="empty"><h3>Sin campañas</h3></div>`;
    return;
  }
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:12px">
    ${camps.map(c => renderApprovalCard(c, false)).join('')}
  </div>`;
}

function renderApprovalCard(c, showActions) {
  const adv = c.advertiser || {};
  const screens = (c.screens_info || []).map(s => s.name).join(', ');
  const isPending = c.status === 'PENDING_REVIEW';

  return `
    <div class="card" style="padding:20px;border-left:4px solid ${isPending ? 'var(--amber)' : 'var(--border)'}">
      <div style="display:flex;align-items:flex-start;gap:14px;margin-bottom:12px">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
            <span style="font-size:15px;font-weight:700;color:#e2e8f0">${c.name}</span>
            ${adStatusBadge(c.status)}
          </div>
          <div style="font-size:12px;color:#64748b">
            👤 ${adv.name || 'Anunciante'} (${adv.email || ''}) ·
            📺 ${screens || 'Sin pantallas'} ·
            📅 ${c.start_date || ''} → ${c.end_date || ''}
          </div>
          <div style="font-size:12px;color:#64748b;margin-top:3px">
            💳 ${periodLabel(c.pricing_period)} × ${c.duration} · Ref: ${c.payment_ref || '—'}
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:22px;font-weight:800;color:#6366f1">${fmtPrice(c.total_price)}</div>
          <div style="font-size:10px;color:#64748b">${c.payment_status === 'mocked_paid' ? '✅ Pago recibido' : '⏳ Sin pago'}</div>
        </div>
      </div>
      <div style="margin-bottom:12px;padding:10px;background:rgba(255,255,255,.03);border-radius:8px">
        <div style="font-size:11px;font-weight:600;color:#64748b;margin-bottom:4px">MATERIAL PUBLICITARIO</div>
        <a href="${c.creative_url}" target="_blank" style="font-size:12px;color:#6366f1;word-break:break-all">${c.creative_url}</a>
      </div>
      ${showActions && isPending ? `
        <div style="display:flex;gap:8px">
          <button class="btn-p" style="flex:1;padding:10px;font-size:13px;background:linear-gradient(135deg,#10b981,#059669)" onclick="approveAdCampaign('${c.id}','${(c.name||'').replace(/'/g,"\\'")}')">
            ✅ Aprobar
          </button>
          <div style="flex:2;display:flex;gap:6px">
            <input class="inp" id="reject-reason-${c.id}" placeholder="Motivo del rechazo (requerido)…" style="flex:1;font-size:12px">
            <button class="btn-s" style="padding:10px 14px;color:var(--red);border-color:rgba(239,68,68,.3);font-size:12px" onclick="rejectAdCampaign('${c.id}','${(c.name||'').replace(/'/g,"\\'")}')">
              ❌ Rechazar
            </button>
          </div>
        </div>` : ''}
      ${c.rejection_reason ? `<div style="font-size:12px;color:#ef4444;margin-top:8px">Motivo: ${c.rejection_reason}</div>` : ''}
      ${c.admin_notes ? `<div style="font-size:11px;color:#64748b;margin-top:4px">${c.admin_notes}</div>` : ''}
    </div>`;
}

async function approveAdCampaign(id, name) {
  if (!confirm(`¿Aprobar la campaña "${name}"?\n\nSe añadirá a las playlists de las pantallas seleccionadas.`)) return;
  try {
    const r = await api('/admin/ad-campaigns/' + id + '/approve', { method: 'POST' });
    alert(`✅ ${r.message}`);
    await loadApprovalTabContent();
    await renderApprovalCenter(); // refresh stats
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function rejectAdCampaign(id, name) {
  const reason = document.getElementById('reject-reason-' + id)?.value?.trim();
  if (!reason) { alert('Por favor indica el motivo del rechazo'); return; }
  if (!confirm(`¿Rechazar la campaña "${name}" con el motivo:\n"${reason}"?`)) return;
  try {
    await api('/admin/ad-campaigns/' + id + '/reject', {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
    alert('Campaña rechazada. El anunciante podrá editarla y volver a enviar.');
    await loadApprovalTabContent();
    await renderApprovalCenter();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function renderAdminWaitlist(el) {
  const entries = await api('/admin/ad-waitlist');
  if (entries.length === 0) {
    el.innerHTML = `<div class="empty"><h3>Lista de espera vacía</h3></div>`;
    return;
  }
  el.innerHTML = `<div style="display:flex;flex-direction:column;gap:10px">
    ${entries.map(e => `
      <div class="card" style="padding:14px;display:flex;align-items:center;gap:12px">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600">${e.advertiser_name} <span style="color:#64748b;font-weight:400">(${e.advertiser_email})</span></div>
          <div style="font-size:12px;color:#64748b">${e.screen_name} · ${e.screen_city} · ${new Date(e.created_at).toLocaleDateString()}</div>
          ${e.notes ? `<div style="font-size:11px;color:#94a3b8;margin-top:2px">${e.notes}</div>` : ''}
        </div>
        <span class="bdg bdg-pending">${e.status}</span>
      </div>`).join('')}
  </div>`;
}

// ── QR Code para Pantallas PUBLIC_ADVERTISING ─────────────────────────────────
async function showScreenQR(screenId, screenName) {
  try {
    const baseUrl = window.location.origin;
    const data = await api(`/admin/screens/${screenId}/qr?base_url=${encodeURIComponent(baseUrl)}`);

    const modalHtml = `
      <div id="qr-modal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(2,6,18,.9);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px)">
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:20px;padding:32px;max-width:400px;width:90%;text-align:center">
          <h2 style="font-size:18px;font-weight:700;margin-bottom:4px">${screenName}</h2>
          <p style="font-size:12px;color:#64748b;margin-bottom:20px">QR de Publicidad Pública</p>

          <div style="background:#fff;padding:16px;border-radius:16px;display:inline-block;margin-bottom:16px">
            <img src="${data.qr_image_url}" alt="QR Code" style="width:220px;height:220px" onerror="this.src='data:image/svg+xml,<svg/>'" crossorigin="anonymous">
          </div>

          <div style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:12px;margin-bottom:16px">
            <div style="font-size:11px;color:#64748b;margin-bottom:4px">URL de la Landing</div>
            <div style="font-size:13px;color:#6366f1;word-break:break-all;font-weight:600">${data.advertise_url}</div>
            <div style="font-size:11px;color:#64748b;margin-top:6px">Código: <strong style="color:#22d3ee">${data.public_screen_code}</strong></div>
          </div>

          <div style="display:flex;gap:8px;justify-content:center">
            <button class="btn-p" style="padding:10px 20px;font-size:13px" onclick="printQR()">🖨 Imprimir QR</button>
            <button class="btn-s" style="padding:10px 16px;font-size:13px" onclick="copyQRUrl('${data.advertise_url}')">📋 Copiar URL</button>
            <button class="btn-s" style="padding:10px 16px;font-size:13px" onclick="document.getElementById('qr-modal').remove()">✕ Cerrar</button>
          </div>
        </div>
      </div>`;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
  } catch (e) {
    alert('Error generando QR: ' + e.message);
  }
}

function printQR() {
  const qrImg = document.querySelector('#qr-modal img');
  if (!qrImg) return;
  const url = qrImg.src;
  const win = window.open('', '_blank');
  win.document.write(`<!DOCTYPE html><html><head><title>QR Publicitario</title>
    <style>body{margin:0;padding:20px;text-align:center;font-family:Inter,sans-serif}
    img{width:300px;height:300px}
    p{font-size:14px;color:#334155;margin-top:8px}</style></head>
    <body><img src="${url}"><p>Escanea para anunciarte en esta pantalla</p>
    <script>window.onload=()=>window.print()<\/script></body></html>`);
  win.document.close();
}

function copyQRUrl(url) {
  navigator.clipboard.writeText(url).then(() => alert('URL copiada al portapapeles'));
}

// Registrar loaders en el objeto global loaders
if (typeof loaders !== 'undefined') {
  loaders['advertiser'] = () => renderAdvertiserPortal();
  loaders['approval']   = () => renderApprovalCenter();
}

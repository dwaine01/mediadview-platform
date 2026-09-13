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
// La pantalla desde la que el anunciante escaneó el QR. Viene en la URL
// (?screen=MV-ADV-XXXX) o en la sesión que dejó la landing del QR. Se marca en
// el listado porque es la pantalla que tiene delante y la razón por la que entró.
function hereScreenCode() {
  const fromUrl = new URLSearchParams(window.location.search).get('screen');
  return (fromUrl || sessionStorage.getItem('advertise_screen_code') || '').trim();
}

async function renderMarketplace(el) {
  let screens = [];
  let cities = [];
  const here = hereScreenCode();
  try {
    [screens, cities] = await Promise.all([
      api('/marketplace/screens' + (here ? '?here=' + encodeURIComponent(here) : '')),
      api('/marketplace/cities'),
    ]);
  } catch (e) {
    el.innerHTML = `<div style="color:var(--red);padding:20px">${e.message}</div>`;
    return;
  }

  const cityFilter = document.getElementById('mkt-city-filter')?.value || '';
  const hereScreen = screens.find(s => s.is_here);

  el.innerHTML = `
    ${hereScreen ? `
      <div style="display:flex;align-items:center;gap:10px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);border-radius:12px;padding:12px 14px;margin-bottom:16px">
        <span style="font-size:18px">📍</span>
        <div style="font-size:13px;color:#34d399;font-weight:600">Esta es la pantalla donde estás ahora:
          <span style="color:var(--t-1)">${hereScreen.venue.establishment_name}</span>
        </div>
      </div>` : ''}
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center">
      <select id="mkt-city-filter" class="inp" style="max-width:200px" onchange="switchAdTab('marketplace')">
        <option value="">Todas las ciudades</option>
        ${cities.map(c => `<option value="${c}" ${c === cityFilter ? 'selected' : ''}>${c}</option>`).join('')}
      </select>
      <span style="font-size:13px;color:var(--t-4)">${screens.length} pantalla${screens.length !== 1 ? 's' : ''} disponible${screens.length !== 1 ? 's' : ''}</span>
      <span style="font-size:12px;color:var(--t-5);margin-left:auto">Toca una pantalla para ver la ubicación antes de comprar</span>
      <div style="display:flex;gap:0;border:1px solid var(--border);border-radius:10px;overflow:hidden">
        <button class="tab-btn" id="mkt-view-list" onclick="switchMktView('list')"
          style="padding:8px 14px;font-size:12px;border:0;border-radius:0;${_mktView === 'list' ? 'background:var(--brand-l);color:#fff' : ''}">☰ Listado</button>
        <button class="tab-btn" id="mkt-view-map" onclick="switchMktView('map')"
          style="padding:8px 14px;font-size:12px;border:0;border-radius:0;${_mktView === 'map' ? 'background:var(--brand-l);color:#fff' : ''}">🗺 Mapa</button>
      </div>
    </div>
    <div id="mkt-map-wrap" style="display:${_mktView === 'map' ? 'block' : 'none'}">
      <div id="mkt-map" style="height:520px;border-radius:14px;overflow:hidden;border:1px solid var(--border)"></div>
      <div id="mkt-map-note" style="font-size:12px;color:var(--t-4);margin-top:8px"></div>
    </div>
    <div id="mkt-grid" style="display:${_mktView === 'map' ? 'none' : 'grid'};grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px">
      ${screens.length === 0 ? '<div class="empty"><h3>Sin pantallas disponibles</h3><p>No hay pantallas de publicidad activas por el momento</p></div>' : screens.map(s => renderScreenCard(s)).join('')}
    </div>`;
  window._mktScreens = screens;
  if (_mktView === 'map') renderMktMap();
}

// ── Mapa: el anunciante elige por zona, no leyendo direcciones ──────────────
var _mktView = 'list';

function switchMktView(view) {
  _mktView = view;
  const grid = document.getElementById('mkt-grid');
  const map = document.getElementById('mkt-map-wrap');
  if (!grid || !map) return;
  grid.style.display = view === 'map' ? 'none' : 'grid';
  map.style.display = view === 'map' ? 'block' : 'none';
  document.getElementById('mkt-view-list').style.cssText +=
    view === 'list' ? ';background:var(--brand-l);color:#fff' : ';background:transparent;color:var(--t-3)';
  document.getElementById('mkt-view-map').style.cssText +=
    view === 'map' ? ';background:var(--brand-l);color:#fff' : ';background:transparent;color:var(--t-3)';
  if (view === 'map') renderMktMap();
}

// Leaflet + OpenStreetMap: sin llave de API y sin costo por vista.
function ensureLeaflet() {
  if (window.L) return Promise.resolve();
  if (window._leafletLoading) return window._leafletLoading;
  window._leafletLoading = new Promise((resolve, reject) => {
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = resolve;
    script.onerror = () => reject(new Error('No se pudo cargar el mapa'));
    document.head.appendChild(script);
  });
  return window._leafletLoading;
}

async function renderMktMap() {
  const box = document.getElementById('mkt-map');
  const note = document.getElementById('mkt-map-note');
  const screens = window._mktScreens || [];
  try {
    await ensureLeaflet();
  } catch (e) {
    note.textContent = 'No se pudo cargar el mapa. Usá el listado.';
    return;
  }
  const located = screens.filter(s => s.venue?.lat != null && s.venue?.lng != null);
  const missing = screens.length - located.length;
  note.textContent = missing
    ? `${missing} pantalla${missing !== 1 ? 's' : ''} todavía sin ubicación en el mapa: están en el listado.`
    : 'Toca un punto para ver la ficha de esa ubicación.';
  if (!located.length) {
    box.innerHTML = '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:var(--t-4);font-size:13px">Ninguna pantalla tiene ubicación cargada todavía</div>';
    return;
  }

  if (window._mktMap) { window._mktMap.remove(); window._mktMap = null; }
  box.innerHTML = '';
  const map = L.map(box).setView([located[0].venue.lat, located[0].venue.lng], 12);
  window._mktMap = map;
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '© OpenStreetMap',
  }).addTo(map);

  located.forEach(s => {
    const v = s.venue;
    const color = s.is_here ? '#10b981' : s.is_full ? '#ef4444' : '#6366f1';
    const marker = L.marker([v.lat, v.lng], {
      icon: L.divIcon({
        className: '',
        html: `<div style="width:30px;height:30px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid #fff;box-shadow:0 3px 8px rgba(2,6,18,.4)"></div>`,
        iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -28],
      }),
    }).addTo(map);
    marker.bindPopup(`
      <div style="min-width:200px;font-family:inherit">
        ${v.photo_url ? `<img src="${v.photo_url}" style="width:100%;height:96px;object-fit:cover;border-radius:8px;margin-bottom:8px">` : ''}
        <div style="font-size:13px;font-weight:700;color:#0f172a">${v.establishment_name}</div>
        <div style="font-size:11px;color:#64748b;margin-top:2px">${[v.city, v.reference].filter(Boolean).join(' · ')}</div>
        ${v.audience?.label ? `<div style="font-size:11px;color:#4f46e5;font-weight:600;margin-top:6px">👥 ${v.audience.label}</div>` : ''}
        <div style="font-size:11px;color:${s.is_full ? '#ef4444' : '#059669'};font-weight:600;margin-top:4px">${s.is_full ? 'Lleno' : s.available_slots + ' espacios libres'}</div>
        <button onclick="openVenueSheet('${s.id}')" style="width:100%;margin-top:8px;padding:8px;border:0;border-radius:8px;background:#4f46e5;color:#fff;font-size:12px;font-weight:700;cursor:pointer">Ver esta ubicación</button>
      </div>`);
    if (s.is_here) marker.openPopup();
  });

  const bounds = L.latLngBounds(located.map(s => [s.venue.lat, s.venue.lng]));
  const here = located.find(s => s.is_here);
  if (here) {
    // Si escaneó un QR, el mapa abre donde está parado: lo demás lo explora él.
    map.setView([here.venue.lat, here.venue.lng], 13);
  } else {
    map.fitBounds(bounds.pad(0.25), { maxZoom: 15 });
  }
  setTimeout(() => map.invalidateSize(), 120);
}

function venuePhoto(s, height) {
  if (s.venue?.photo_url) {
    return `<img src="${s.venue.photo_url}" alt="Pantalla instalada en ${(s.venue.establishment_name || '').replace(/"/g, '')}"
      style="width:100%;height:${height}px;object-fit:cover;display:block">`;
  }
  return `<div style="width:100%;height:${height}px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;background:var(--bg-1);color:var(--t-5)">
      <span style="font-size:26px">📺</span>
      <span style="font-size:11px">Foto en camino</span>
    </div>`;
}

function renderScreenCard(s) {
  const v = s.venue || {};
  const ap = s.pricing || {};
  const prices = [
    ap.price_per_week ? `Sem: ${fmtPrice(ap.price_per_week)}` : '',
    ap.price_per_month ? `Mes: ${fmtPrice(ap.price_per_month)}` : '',
    ap.price_per_year ? `Año: ${fmtPrice(ap.price_per_year)}` : '',
  ].filter(Boolean).join(' · ');

  const slotsColor = s.is_full ? '#ef4444' : s.available_slots <= 1 ? '#f59e0b' : '#10b981';
  const slotsText = s.is_full ? '🔴 Lleno' : `🟢 ${s.available_slots} libre${s.available_slots !== 1 ? 's' : ''}`;
  const selected = !!(window._selectedScreens || {})[s.id];

  return `
    <div class="card card-i" style="padding:0;overflow:hidden;cursor:pointer;${s.is_here ? 'border:1.5px solid rgba(16,185,129,.55);box-shadow:0 0 0 3px rgba(16,185,129,.10)' : ''}"
         onclick="openVenueSheet('${s.id}')">
      <div style="position:relative">
        ${venuePhoto(s, 168)}
        ${s.is_here ? '<span style="position:absolute;top:10px;left:10px;background:#10b981;color:#04140f;font-size:11px;font-weight:800;padding:4px 10px;border-radius:999px;white-space:nowrap">📍&#8202;Estás acá</span>' : ''}
        <span style="position:absolute;top:10px;right:10px;font-size:11px;font-weight:600;color:${slotsColor};background:rgba(2,6,18,.78);padding:4px 9px;border-radius:999px;border:1px solid ${slotsColor}55">${slotsText}</span>
        ${selected ? '<span style="position:absolute;bottom:10px;right:10px;background:#6366f1;color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px">✓ Elegida</span>' : ''}
      </div>
      <div style="padding:16px">
        <div style="font-size:15px;font-weight:700;color:var(--t-1)">${v.establishment_name || s.name}</div>
        <div style="font-size:12px;color:var(--t-4);margin-top:3px">${[v.city, v.state].filter(Boolean).join(', ')}</div>
        ${v.reference ? `<div style="font-size:12px;color:var(--t-3);margin-top:6px">📍 ${v.reference}</div>` : ''}
        ${v.audience?.label ? `<div style="display:inline-flex;align-items:center;gap:5px;margin-top:10px;background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.25);color:#a5b4fc;font-size:11px;font-weight:600;padding:4px 10px;border-radius:999px">👥 ${v.audience.label}</div>` : ''}
        <div style="font-size:12px;color:#6366f1;font-weight:600;border-top:1px solid var(--border);padding-top:10px;margin-top:12px">${prices || 'Consultar precio'}</div>
        <button class="btn-s" style="width:100%;margin-top:10px;padding:9px;font-size:12px" onclick="event.stopPropagation();openVenueSheet('${s.id}')">👁 Ver esta ubicación</button>
      </div>
    </div>`;
}

// ── Ficha detallada de la ubicación (antes de cualquier pago) ────────────────
// Nadie compra publicidad a ciegas: primero ve el negocio, la calle, la
// referencia, cuánta gente pasa y cómo se ve la pantalla instalada.
async function openVenueSheet(screenId) {
  document.getElementById('venue-sheet')?.remove();
  document.body.insertAdjacentHTML('beforeend', `
    <div id="venue-sheet" style="position:fixed;inset:0;background:rgba(2,6,18,.92);z-index:200;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(10px);padding:20px">
      <div style="color:var(--t-4);font-size:13px">Cargando la ubicación…</div>
    </div>`);
  let s;
  try {
    const here = hereScreenCode();
    s = await api('/marketplace/screens/' + screenId + (here ? '?here=' + encodeURIComponent(here) : ''));
  } catch (e) {
    document.getElementById('venue-sheet').innerHTML =
      `<div class="card" style="padding:24px;max-width:420px;text-align:center">
         <div style="color:var(--red);font-size:13px;margin-bottom:14px">${e.message}</div>
         <button class="btn-s" onclick="closeVenueSheet()">Volver al listado</button>
       </div>`;
    return;
  }

  const v = s.venue || {};
  const p = s.pricing || {};
  const specs = s.specs || {};
  const selected = !!(window._selectedScreens || {})[s.id];
  const rows = [
    ['Establecimiento', v.establishment_name || s.name],
    ['Dirección', v.address],
    ['Ciudad', [v.city, v.state].filter(Boolean).join(', ')],
    ['Cómo llegar', v.reference],
    ['Gente que pasa', v.audience?.label],
    ['Mejor horario', v.audience?.note],
  ].filter(r => r[1]);
  const priceItems = [
    { label: 'Semana', amount: p.price_per_week },
    { label: 'Mes', amount: p.price_per_month },
    { label: 'Año', amount: p.price_per_year },
  ].filter(i => i.amount);

  document.getElementById('venue-sheet').innerHTML = `
    <div class="card" style="padding:0;max-width:620px;width:100%;max-height:92vh;overflow:auto;border-radius:20px">
      <div style="position:relative">
        ${venuePhoto(s, 260)}
        ${s.is_here ? '<span style="position:absolute;top:14px;left:14px;background:#10b981;color:#04140f;font-size:12px;font-weight:800;padding:5px 12px;border-radius:999px;white-space:nowrap">📍&#8202;Estás acá ahora</span>' : ''}
        <button class="btn-s" style="position:absolute;top:12px;right:12px;padding:6px 12px;font-size:14px;background:rgba(2,6,18,.82);color:#fff;border-color:rgba(255,255,255,.25)" onclick="closeVenueSheet()">✕</button>
      </div>
      <div style="padding:22px">
        <div style="font-size:20px;font-weight:800;color:var(--t-1)">${v.establishment_name || s.name}</div>
        <div style="font-size:13px;color:var(--t-4);margin-top:4px">${[v.address, v.city].filter(Boolean).join(' · ') || 'Ubicación a confirmar'}</div>
        ${s.description ? `<div style="font-size:13px;color:var(--t-3);line-height:1.6;margin-top:12px">${s.description}</div>` : ''}

        <div style="margin-top:18px;border:1px solid var(--border);border-radius:14px;overflow:hidden">
          ${rows.map((r, i) => `
            <div style="display:flex;gap:12px;padding:11px 14px;${i ? 'border-top:1px solid var(--border-l)' : ''}">
              <div style="font-size:12px;color:var(--t-4);width:130px;flex-shrink:0">${r[0]}</div>
              <div style="font-size:13px;color:var(--t-1);font-weight:500">${r[1]}</div>
            </div>`).join('')}
        </div>

        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
          ${specs.type ? `<span class="tag">📺 ${specs.type}</span>` : ''}
          ${specs.resolution ? `<span class="tag">🖥 ${specs.resolution}</span>` : ''}
          ${specs.size ? `<span class="tag">📐 ${specs.size}</span>` : ''}
          ${specs.orientation ? `<span class="tag">${specs.orientation === 'portrait' ? '↕ Vertical' : '↔ Horizontal'}</span>` : ''}
        </div>

        <div style="margin-top:16px;font-size:12px;color:${s.is_full ? '#f87171' : '#34d399'};font-weight:600">
          ${s.is_full
            ? '🔴 Esta pantalla está a capacidad máxima'
            : `🟢 ${s.available_slots} de ${s.max_ad_slots} espacios publicitarios libres`}
        </div>

        ${priceItems.length ? `
          <div style="display:grid;grid-template-columns:repeat(${priceItems.length},1fr);gap:10px;margin-top:14px">
            ${priceItems.map(i => `
              <div style="background:rgba(8,145,178,.07);border:1px solid rgba(8,145,178,.18);border-radius:12px;padding:12px;text-align:center">
                <div style="font-size:11px;color:var(--t-4);font-weight:600;text-transform:uppercase;letter-spacing:.5px">${i.label}</div>
                <div style="font-size:19px;font-weight:800;color:#22d3ee;margin-top:2px">${fmtPrice(i.amount)}</div>
              </div>`).join('')}
          </div>` : '<div style="font-size:12px;color:var(--t-4);margin-top:14px">Consultá el precio con el equipo MediaView</div>'}

        ${reachBlock(s)}

        <div style="display:flex;flex-direction:column;gap:8px;margin-top:20px">
          ${s.is_full
            ? `<button class="btn-s" style="padding:13px;font-size:14px;color:var(--amber);border-color:rgba(245,158,11,.35)" onclick="closeVenueSheet();joinWaitlist('${s.id}','${(v.establishment_name || s.name || '').replace(/'/g, "\\'")}')">📋 Avisarme cuando se libere un espacio</button>`
            : `<button class="btn-p" style="padding:14px;font-size:14px;justify-content:center" onclick="chooseVenue('${s.id}','${(v.establishment_name || s.name || '').replace(/'/g, "\\'")}')">${selected ? '✓ Ya la elegí — quitarla de mi selección' : '✨ Quiero anunciarme en esta pantalla'}</button>`}
          <div style="display:flex;gap:8px">
            <button class="btn-s" style="flex:1;padding:11px;font-size:13px" onclick="closeVenueSheet()">Seguir eligiendo pantallas</button>
            <button class="btn-s" style="flex:1;padding:11px;font-size:13px" onclick="closeVenueSheet()">Volver al listado</button>
          </div>
        </div>
      </div>
    </div>`;
  if (document.getElementById('reach-result')) recalcReach(s.id);
}

// ── Alcance estimado: a cuánta gente le llega según días y horario ──────────
// El anunciante no compara pantallas por el precio, las compara por la gente
// que va a ver su anuncio. La cuenta se muestra completa para que pueda
// rehacerla: tráfico del local × la parte del día que eligió × días.
function reachBlock(s) {
  const v = s.venue || {};
  if (!v.audience?.label) return '';
  const openFrom = parseInt((v.open_from || '08:00').split(':')[0], 10);
  const openTo = parseInt((v.open_to || '20:00').split(':')[0], 10);
  const hours = [];
  for (let h = openFrom; h <= openTo; h++) hours.push(String(h).padStart(2, '0') + ':00');
  const opt = (list, value) => list.map(o =>
    `<option value="${o.v !== undefined ? o.v : o}" ${String(o.v !== undefined ? o.v : o) === String(value) ? 'selected' : ''}>${o.t || o}</option>`).join('');

  return `
    <div style="margin-top:18px;border:1px solid var(--border);border-radius:14px;padding:16px">
      <div style="font-size:13px;font-weight:700;color:var(--t-1)">¿A cuánta gente le va a llegar?</div>
      <div style="font-size:11px;color:var(--t-4);margin-top:2px">El local atiende de ${v.hours_label}${v.hours_are_default ? ' (horario estimado)' : ''}.</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-top:12px">
        <div><div style="font-size:11px;color:var(--t-4);margin-bottom:4px">Días</div>
          <select class="inp" id="reach-days" onchange="recalcReach('${s.id}')" style="padding:8px;font-size:12px">
            ${opt([{ v: 7, t: 'Todos los días' }, { v: 5, t: 'Lunes a viernes' }, { v: 2, t: 'Fin de semana' }], 7)}
          </select></div>
        <div><div style="font-size:11px;color:var(--t-4);margin-bottom:4px">Desde</div>
          <select class="inp" id="reach-from" onchange="recalcReach('${s.id}')" style="padding:8px;font-size:12px">${opt(hours, v.open_from)}</select></div>
        <div><div style="font-size:11px;color:var(--t-4);margin-bottom:4px">Hasta</div>
          <select class="inp" id="reach-to" onchange="recalcReach('${s.id}')" style="padding:8px;font-size:12px">${opt(hours, v.open_to)}</select></div>
        <div><div style="font-size:11px;color:var(--t-4);margin-bottom:4px">Duración</div>
          <select class="inp" id="reach-weeks" onchange="recalcReach('${s.id}')" style="padding:8px;font-size:12px">
            ${opt([{ v: 1, t: '1 semana' }, { v: 4, t: '1 mes' }, { v: 12, t: '3 meses' }, { v: 52, t: '1 año' }], 4)}
          </select></div>
      </div>
      <div id="reach-result" style="margin-top:14px"></div>
    </div>`;
}

async function recalcReach(screenId) {
  const box = document.getElementById('reach-result');
  if (!box) return;
  box.innerHTML = '<div style="font-size:12px;color:var(--t-4)">Calculando…</div>';
  try {
    const r = await api('/marketplace/screens/' + screenId + '/reach', {
      method: 'POST',
      body: JSON.stringify({
        start_time: document.getElementById('reach-from').value,
        end_time: document.getElementById('reach-to').value,
        days_per_week: parseInt(document.getElementById('reach-days').value, 10),
        weeks: parseInt(document.getElementById('reach-weeks').value, 10),
        slot_seconds: 30,
      }),
    });
    if (r.hours_selected <= 0) {
      box.innerHTML = '<div style="font-size:12px;color:var(--amber)">Elegí una franja dentro del horario del local.</div>';
      return;
    }
    const n = x => Number(x).toLocaleString('es-HN');
    box.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.22);border-radius:12px;padding:12px">
          <div style="font-size:11px;color:var(--t-4);font-weight:600">POR DÍA</div>
          <div style="font-size:22px;font-weight:800;color:#059669">${n(r.reach_per_day)}</div>
          <div style="font-size:11px;color:var(--t-4)">personas frente a la pantalla</div>
        </div>
        <div style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.22);border-radius:12px;padding:12px">
          <div style="font-size:11px;color:var(--t-4);font-weight:600">EN TODA LA CAMPAÑA</div>
          <div style="font-size:22px;font-weight:800;color:#4f46e5">${n(r.reach_total)}</div>
          <div style="font-size:11px;color:var(--t-4)">${r.days_total} días al aire</div>
        </div>
      </div>
      <div style="font-size:12px;color:var(--t-3);margin-top:10px;line-height:1.6">
        Tu anuncio sale <strong>${n(r.plays_per_hour)} veces por hora</strong>
        (${n(r.plays_per_day)} por día, ${n(r.plays_total)} en total), compartiendo el bucle con
        ${r.ads_in_loop - 1 === 0 ? 'ningún otro anuncio' : (r.ads_in_loop - 1) + ' anuncio' + (r.ads_in_loop - 1 !== 1 ? 's' : '')}.<br>
        Cuenta: ${n(r.people_per_day_venue)} personas/día × ${r.hours_selected} h de las ${r.hours_open} h que abre el local × ${r.days_total} días.
      </div>
      <div style="font-size:11px;color:var(--t-5);margin-top:8px">${r.note}</div>`;
  } catch (e) {
    box.innerHTML = `<div style="font-size:12px;color:var(--red)">${e.message}</div>`;
  }
}

function closeVenueSheet() {
  document.getElementById('venue-sheet')?.remove();
  if (_adTab === 'marketplace') loadAdTabContent();  // refresca el estado «Elegida»
}

// Elegir la pantalla NO es pagar: queda guardada en la selección y el
// anunciante decide si sigue eligiendo o pasa a armar la campaña.
function chooseVenue(screenId, screenName) {
  if (!window._selectedScreens) window._selectedScreens = {};
  const already = !!window._selectedScreens[screenId];
  if (already) delete window._selectedScreens[screenId];
  else window._selectedScreens[screenId] = screenName;
  document.getElementById('venue-sheet')?.remove();
  if (already) {
    loadAdTabContent();
    return;
  }
  _adTab = 'create-ad';
  document.querySelectorAll('#pg-advertiser .tab-btn').forEach(b => {
    b.classList.toggle('on', b.getAttribute('onclick').includes("'create-ad'"));
  });
  loadAdTabContent();
}

function selectScreenForCampaign(screenId, screenName) {
  chooseVenue(screenId, screenName);
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

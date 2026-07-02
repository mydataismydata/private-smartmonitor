/* Private SmartMonitor dashboard — vanilla JS, no framework (same choice as SolarPi).
   Fetches the fleet from /api/devices, renders a room grid of device cards with
   optimistic toggles, and opens a thermostat-style control sheet per device. */

'use strict';

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

/* ---- icons (feather-style, uniform stroke) -------------------------------- */
const ICONS = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  home: '<path d="M3 10.2 12 3l9 7.2V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  bolt: '<polygon points="13 2 4 14 11 14 10 22 20 10 13 10 13 2"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  info: '<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/>',
  bulb: '<path d="M9 18h6M10 21.5h4"/><path d="M12 2.5a6.5 6.5 0 0 0-4 11.7c.6.5 1 1.3 1 2.1V17h6v-.7c0-.8.4-1.6 1-2.1A6.5 6.5 0 0 0 12 2.5z"/>',
  plug: '<path d="M9 2.5v5M15 2.5v5"/><path d="M7 7.5h10v3.5a5 5 0 0 1-10 0z"/><path d="M12 16v5.5"/>',
  power: '<path d="M18.4 6.6a9 9 0 1 1-12.8 0"/><line x1="12" y1="2.5" x2="12" y2="12"/>',
  thermo: '<path d="M14 14.8V4.5a2 2 0 0 0-4 0v10.3a4 4 0 1 0 4 0z"/><circle cx="12" cy="18" r="1.2" fill="currentColor" stroke="none"/>',
  snow: '<path d="M12 2v20M4.2 7l15.6 10M19.8 7 4.2 17"/><path d="M12 6 9.5 3.5M12 6l2.5-2.5M12 18l-2.5 2.5M12 18l2.5 2.5M4.2 7l.3 3.4M4.2 7l3.4-.3M19.8 17l-.3-3.4M19.8 17l-3.4.3M19.8 7l-3.4.3M19.8 7l-.3 3.4M4.2 17l3.4.3M4.2 17l.3-3.4"/>',
  flame: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1.1-2.1-.2-4 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2 2.5z"/>',
  droplet: '<path d="M12 2.7 6.3 9a8 8 0 1 0 11.4 0z"/>',
  wind: '<path d="M4 8h11a3 3 0 1 0-3-3M2 12h17a3 3 0 1 1-3 3M4 16h9a3 3 0 1 1-3 3"/>',
  auto: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  away: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  minus: '<line x1="5" y1="12" x2="19" y2="12"/>',
  close: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
  pin: '<path d="M21 10c0 6-9 12-9 12s-9-6-9-12a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  offline: '<line x1="2" y1="2" x2="22" y2="22"/><path d="M16.7 11.3A6 6 0 0 1 20 12M5 12a11 11 0 0 1 6.5-3.1M9 16a4 4 0 0 1 5 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
};
const icon = (name, cls) =>
  `<svg${cls ? ` class="${cls}"` : ''} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ''}</svg>`;

const TYPE_ICON = { light: 'bulb', plug: 'plug', switch: 'power', climate: 'thermo' };
const MODES = [
  { m: 'cool', ic: 'snow', label: 'Cool' },
  { m: 'heat', ic: 'flame', label: 'Heat' },
  { m: 'auto', ic: 'auto', label: 'Auto' },
  { m: 'dry', ic: 'droplet', label: 'Dry' },
  { m: 'fan', ic: 'wind', label: 'Fan' },
];

/* ---- state ---------------------------------------------------------------- */
const state = {
  data: { devices: [], rooms: [], summary: {}, demo: false },
  automations: [],
  view: 'home',
  open: null,     // { id, type, setpoint, brightness }
  settings: loadSettings(),
  timer: null,
};

function loadSettings() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem('smartmon') || '{}'); } catch (_) {}
  return {
    theme: s.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    fahrenheit: !!s.fahrenheit,
    autoRefresh: s.autoRefresh !== false,
  };
}
function saveSettings() { localStorage.setItem('smartmon', JSON.stringify(state.settings)); }

/* ---- api ------------------------------------------------------------------ */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

function deviceById(id) { return state.data.devices.find((d) => d.id === id); }

/* ---- helpers -------------------------------------------------------------- */
function tempDisplay(c) {
  if (c == null) return { v: '—', u: '' };
  return state.settings.fahrenheit ? { v: Math.round(c * 9 / 5 + 32), u: '°F' } : { v: Math.round(c), u: '°C' };
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
function toast(msg, isErr) {
  const t = $('#toast');
  t.textContent = msg; t.classList.toggle('err', !!isErr); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
}

/* ---- dial geometry (270° arc, gap at the bottom) -------------------------- */
const DIAL = { cx: 116, cy: 116, r: 92, start: 225, sweep: 270 };
function polar(cx, cy, r, deg) { const a = (deg - 90) * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
function arcPath(frac) {
  const { cx, cy, r, start, sweep } = DIAL;
  const f = Math.max(0.0001, Math.min(1, frac));
  const end = start + sweep * f;
  const [x1, y1] = polar(cx, cy, r, start), [x2, y2] = polar(cx, cy, r, end);
  const large = sweep * f > 180 ? 1 : 0;
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}
function knobXY(frac) { const { cx, cy, r, start, sweep } = DIAL; return polar(cx, cy, r, start + sweep * Math.max(0, Math.min(1, frac))); }
function dialHTML(frac, color, centerHTML) {
  const [kx, ky] = knobXY(frac);
  return `<div class="dial-wrap"><svg class="dial-svg" viewBox="0 0 232 232">
    <path class="dial-track" d="${arcPath(1)}"/>
    <path class="dial-fill" id="dialFill" d="${arcPath(frac)}" stroke="${color}"/>
    <circle class="dial-knob" id="dialKnob" cx="${kx.toFixed(1)}" cy="${ky.toFixed(1)}" r="11" stroke="${color}"/>
  </svg><div class="dial-center">${centerHTML}</div></div>`;
}
function setDial(frac, color, valHTML) {
  const f = $('#dialFill'), k = $('#dialKnob'), v = $('#dialVal');
  if (f) { f.setAttribute('d', arcPath(frac)); if (color) f.setAttribute('stroke', color); }
  if (k) { const [kx, ky] = knobXY(frac); k.setAttribute('cx', kx.toFixed(1)); k.setAttribute('cy', ky.toFixed(1)); if (color) k.setAttribute('stroke', color); }
  if (v && valHTML != null) v.innerHTML = valHTML;
}

/* ---- greeting / clock ----------------------------------------------------- */
function greet() {
  const h = new Date().getHours();
  return h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : h < 22 ? 'Good evening' : 'Good night';
}
function tickClock() {
  $('#clock').textContent = new Date().toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
}

/* ---- render: shell -------------------------------------------------------- */
function paintIcons() {
  $('#brandMark').innerHTML = icon('grid');
  $$('.nav-ic').forEach((el) => (el.innerHTML = icon(el.dataset.ic)));
  $('#themeBtn').firstElementChild.outerHTML = icon(state.settings.theme === 'dark' ? 'sun' : 'moon');
}
function applyTheme() {
  document.documentElement.setAttribute('data-theme', state.settings.theme);
  const btn = $('#themeBtn'); if (btn) btn.innerHTML = icon(state.settings.theme === 'dark' ? 'sun' : 'moon');
}

/* ---- render: home --------------------------------------------------------- */
function renderStats() {
  const s = state.data.summary || {};
  const cards = [
    { ic: 'on', name: 'on', val: s.on ?? 0, lbl: 'Devices on' },
    { ic: 'count', name: 'grid', val: s.total ?? 0, lbl: 'Total devices' },
    { ic: 'power', name: 'bolt', val: s.offline ?? 0, lbl: 'Offline' },
  ];
  $('#statRow').innerHTML = cards.map((c) =>
    `<div class="stat"><span class="stat-ic ${c.ic}">${icon(c.name)}</span>
      <span class="stat-txt"><span class="stat-val">${c.val}</span><span class="stat-lbl">${c.lbl}</span></span></div>`).join('');
}

function deviceBody(d) {
  const st = d.state || {};
  if (!d.online) return `<span class="offline-tag">${icon('offline')}&nbsp; Offline</span>`;
  if (!st.power && d.type !== 'plug') return `<span class="device-state-txt">Off</span>`;
  switch (d.type) {
    case 'light': {
      const b = st.brightness ?? 0;
      return st.power
        ? `<div class="mini-bar"><i style="width:${b}%"></i></div><span class="device-state-txt">${b}%</span>`
        : `<span class="device-state-txt">Off</span>`;
    }
    case 'plug': {
      const w = st.power ? (st.power_w ?? 0) : 0;
      return `<div class="device-metric">${Math.round(w)}<small>W</small></div>`;
    }
    case 'climate': {
      const t = tempDisplay(st.current_temp_c);
      const cls = st.mode === 'cool' ? 'cool' : st.mode === 'heat' ? 'heat' : 'on';
      const mi = st.mode === 'cool' ? 'snow' : st.mode === 'heat' ? 'flame' : 'wind';
      return `<div class="device-metric">${t.v}<small>${t.u}</small></div>
        <span class="chip ${cls}">${icon(mi)}${cap(st.mode || '')}</span>`;
    }
    default:
      return `<span class="device-state-txt">${st.power ? 'On' : 'Off'}</span>`;
  }
}

function deviceCard(d) {
  const st = d.state || {};
  const on = d.online && st.power;
  const disabled = !d.online ? 'disabled' : '';
  return `<div class="card device ${on ? 'on' : 'off'}" data-id="${d.id}">
    <div class="device-top">
      <span class="device-ic">${icon(TYPE_ICON[d.type] || 'power')}</span>
      <span class="device-id"><div class="device-name">${d.name}</div><div class="device-room">${d.room}</div></span>
      <label class="switch device-switch" data-toggle>
        <input type="checkbox" ${st.power ? 'checked' : ''} ${disabled} /><i></i>
      </label>
    </div>
    <div class="device-body">${deviceBody(d)}</div>
  </div>`;
}

function renderRooms() {
  const { devices, rooms } = state.data;
  $('#homeEmpty').hidden = devices.length > 0;
  $('#rooms').innerHTML = rooms.map((room) => {
    const inRoom = devices.filter((d) => d.room === room);
    if (!inRoom.length) return '';
    const onCount = inRoom.filter((d) => d.online && d.state && d.state.power).length;
    return `<section class="room">
      <div class="room-head"><h2>${room}</h2><span class="count">${onCount}/${inRoom.length} on</span></div>
      <div class="grid">${inRoom.map(deviceCard).join('')}</div>
    </section>`;
  }).join('');
}

/* ---- render: automation --------------------------------------------------- */
function renderAutomations() {
  const list = state.automations;
  $('#autoNote').textContent =
    'Routines are a scaffold in this build: toggles persist in memory. The scheduler that fires them on a timer arrives in a later phase.';
  $('#automations').innerHTML = list.map((a) => {
    const names = a.device_names || [];
    const shown = names.slice(0, 2);
    const extra = names.length - shown.length;
    const chips = shown.map((n) => `<span class="meta-chip">${icon('plug')}${n}</span>`).join('');
    const more = extra > 0 ? `<span class="meta-chip more">+${extra} more device${extra > 1 ? 's' : ''} connected</span>` : '';
    const time = a.time_range ? `<span class="meta-chip">${icon('clock')}${a.time_range}</span>` : '';
    return `<div class="card auto" data-auto="${a.id}">
      <div class="auto-top">
        <span class="auto-ic ${a.icon}">${icon(a.icon === 'sun' ? 'sun' : a.icon === 'moon' ? 'moon' : a.icon === 'away' ? 'away' : 'clock')}</span>
        <span class="auto-titles"><div class="auto-name">${a.name}</div><div class="auto-sub">${a.subtitle}</div></span>
        <label class="switch" data-auto-toggle><input type="checkbox" ${a.enabled ? 'checked' : ''} /><i></i></label>
      </div>
      <div class="auto-meta">
        <span class="meta-chip">${icon('pin')}${a.scope}</span>${time}${chips}${more}
      </div>
    </div>`;
  }).join('');
}

/* ---- render: about -------------------------------------------------------- */
function renderAbout() {
  const d = state.data;
  $('#aboutCard').innerHTML = `
    <h3>Private SmartMonitor</h3>
    <p class="muted">A self-hosted controller for smart plugs, lights, switches, and climate devices — a sibling of the Solar Tracking Dashboard, running headless on the same Raspberry Pi.</p>
    <div class="kv"><b>Mode</b><span>${d.demo ? 'Demo (simulated fleet)' : 'Live'}</span></div>
    <div class="kv"><b>Devices</b><span>${d.devices.length}</span></div>
    <div class="kv"><b>API</b><span><code>/api/devices</code>, <code>/api/devices/{id}/command</code>, <code>/api/automations</code></span></div>
    <div class="kv"><b>Discovery</b><span><code>_smartmon._tcp</code> over mDNS</span></div>`;
}

/* ---- render: dispatch ----------------------------------------------------- */
function renderAll() {
  const d = state.data;
  $('#greeting').textContent = greet() + '!';
  const s = d.summary || {};
  $('#subgreeting').textContent = d.devices.length
    ? `You have ${s.on ?? 0} of ${s.total ?? 0} device${s.total === 1 ? '' : 's'} currently on.`
    : 'No devices configured yet.';
  $('#demoBadge').hidden = !d.demo;
  renderStats();
  renderRooms();
  renderAbout();
  if (state.open) refreshSheetLive();
}

function setConn(ok) {
  $('#liveDot').classList.toggle('live', ok);
  $('#liveDot').classList.toggle('down', !ok);
  $('#connState').textContent = ok ? 'connected' : 'offline';
}

/* ---- device control ------------------------------------------------------- */
async function sendCommand(id, command, revert) {
  try {
    const res = await post(`/api/devices/${id}/command`, command);
    if (!res.ok) {
      if (res.cooldown) toast(`Cooling down — try again in ${res.retry_after}s`, true);
      else toast('Command failed', true);
      if (revert) revert();
      return res;
    }
    await refresh();
    return res;
  } catch (e) {
    toast('Command failed', true);
    if (revert) revert();
  }
}

async function toggleDevice(id, on, inputEl) {
  const d = deviceById(id);
  if (d && d.state) d.state.power = on;          // optimistic
  if (d) renderRoomsIfVisible();
  await sendCommand(id, { power: on }, () => {
    if (d && d.state) d.state.power = !on;
    if (inputEl) inputEl.checked = !on;
    renderRoomsIfVisible();
  });
}

function renderRoomsIfVisible() { if (state.view === 'home') { renderStats(); renderRooms(); } }

/* ---- device sheet --------------------------------------------------------- */
function openSheet(id) {
  const d = deviceById(id);
  if (!d) return;
  const st = d.state || {};
  state.open = {
    id, type: d.type,
    setpoint: st.setpoint_c != null ? Math.round(st.setpoint_c) : 21,
    brightness: st.brightness != null ? st.brightness : 100,
    colorTemp: st.color_temp != null ? st.color_temp : 50,
  };
  $('#modal').hidden = false;
  renderSheet();
}
function closeSheet() { $('#modal').hidden = true; state.open = null; }

function powerRow(d, st) {
  return `<div class="sheet-power">
    <span><b>Power</b><div class="muted">${st.power ? 'On' : 'Off'}</div></span>
    <label class="switch" data-sheet-power><input type="checkbox" ${st.power ? 'checked' : ''} ${d.online ? '' : 'disabled'} /><i></i></label>
  </div>`;
}

function renderSheet() {
  const o = state.open; if (!o) return;
  const d = deviceById(o.id); if (!d) return closeSheet();
  const st = d.state || {};
  let body = '';

  if (d.type === 'climate') {
    const frac = (o.setpoint - 16) / (30 - 16);
    const color = st.mode === 'heat' ? 'var(--amber)' : st.mode === 'cool' ? 'var(--sky)' : 'var(--accent)';
    const t = tempDisplay(o.setpoint);
    const room = tempDisplay(st.current_temp_c);
    const cd = d.power_cooldown || d.mode_cooldown || 0;
    body = `
      ${dialHTML(frac, color, `<div class="dial-ic">${icon('thermo')}</div><div class="dial-val" id="dialVal">${t.v}<small>${t.u}</small></div><div class="dial-cap">Setpoint</div>`)}
      <div class="stepper">
        <button class="step-btn" data-step="-1" ${st.power ? '' : 'disabled'}>${icon('minus')}</button>
        <button class="step-btn" data-step="1" ${st.power ? '' : 'disabled'}>${icon('plus')}</button>
      </div>
      ${cd ? `<div class="cooldown-note">Compressor cooldown — ${cd}s left</div>` : ''}
      <div class="modes">
        ${MODES.map((m) => `<button class="mode-btn ${st.power && st.mode === m.m ? 'active' : ''}" data-mode="${m.m}">${icon(m.ic)}<span>${m.label}</span></button>`).join('')}
        <button class="mode-btn ${!st.power ? 'active' : ''}" data-mode="off" style="${!st.power ? 'background:var(--ink-3);border-color:var(--ink-3);color:#fff' : ''}">${icon('power')}<span>Off</span></button>
      </div>
      <div class="sheet-foot">
        <div><span class="fi">${icon('thermo')}</span><span><span class="fv">${room.v}${room.u}</span><div class="fl">Room temp</div></span></div>
        <div><span class="fi">${icon('wind')}</span><span><span class="fv">${cap(st.mode || '—')}</span><div class="fl">Mode</div></span></div>
      </div>`;
  } else if (d.type === 'light') {
    const frac = o.brightness / 100;
    const hasCT = (d.capabilities || []).includes('color_temp');
    body = `
      ${dialHTML(st.power ? frac : 0, 'var(--accent)', `<div class="dial-ic">${icon('bulb')}</div><div class="dial-val" id="dialVal">${st.power ? o.brightness : 0}<small>%</small></div><div class="dial-cap">Brightness</div>`)}
      ${powerRow(d, st)}
      <div class="slider-row">
        <label>Brightness <b id="brightLbl">${o.brightness}%</b></label>
        <input type="range" class="slider" id="brightSlider" min="1" max="100" value="${o.brightness}" ${st.power ? '' : 'disabled'} />
      </div>
      ${hasCT ? `<div class="slider-row"><label>Warm <b>Cool</b></label><input type="range" class="slider" id="ctSlider" min="0" max="100" value="${o.colorTemp}" ${st.power ? '' : 'disabled'} /></div>` : ''}`;
  } else if (d.type === 'plug') {
    const w = st.power ? (st.power_w ?? 0) : 0;
    const softMax = Math.max(100, Math.ceil(((st.power_w ?? 0) + 1) / 100) * 100);
    body = `
      ${dialHTML(st.power ? Math.min(1, w / softMax) : 0, 'var(--blue)', `<div class="dial-ic">${icon('bolt')}</div><div class="dial-val" id="dialVal">${Math.round(w)}<small>W</small></div><div class="dial-cap">Power draw</div>`)}
      ${powerRow(d, st)}
      <div class="sheet-foot">
        <div><span class="fi">${icon('bolt')}</span><span><span class="fv">${Math.round(w)} W</span><div class="fl">Now</div></span></div>
        <div><span class="fi">${icon('power')}</span><span><span class="fv">${st.power ? 'On' : 'Off'}</span><div class="fl">State</div></span></div>
      </div>`;
  } else {
    body = `
      <div class="dial-wrap"><div class="dial-center"><div class="dial-ic" style="color:${st.power ? 'var(--accent)' : 'var(--ink-3)'}">${icon('power')}</div><div class="dial-val">${st.power ? 'On' : 'Off'}</div></div>
        <svg class="dial-svg" viewBox="0 0 232 232"><path class="dial-track" d="${arcPath(1)}"/><path class="dial-fill" d="${arcPath(st.power ? 1 : 0.0001)}" stroke="var(--accent)"/></svg></div>
      ${powerRow(d, st)}`;
  }

  $('#sheet').innerHTML = `
    <div class="sheet-head">
      <div><div class="sheet-title">${d.name}</div><div class="sheet-sub">${d.room}${d.online ? '' : ' · offline'}</div></div>
      <button class="sheet-close" data-close>${icon('close')}</button>
    </div>${body}`;
}

/* live-value refresh for an open sheet without clobbering user edits */
function refreshSheetLive() {
  const o = state.open; if (!o) return;
  const d = deviceById(o.id); if (!d) return;
  const st = d.state || {};
  if (d.type === 'plug' && st.power) {
    const w = st.power_w ?? 0;
    const softMax = Math.max(100, Math.ceil((w + 1) / 100) * 100);
    setDial(Math.min(1, w / softMax), 'var(--blue)', `${Math.round(w)}<small>W</small>`);
  }
}

/* ---- sheet interactions --------------------------------------------------- */
function sheetStep(delta) {
  const o = state.open; if (!o || o.type !== 'climate') return;
  o.setpoint = Math.max(16, Math.min(30, o.setpoint + delta));
  const d = deviceById(o.id); const st = d.state || {};
  const color = st.mode === 'heat' ? 'var(--amber)' : st.mode === 'cool' ? 'var(--sky)' : 'var(--accent)';
  const t = tempDisplay(o.setpoint);
  setDial((o.setpoint - 16) / 14, color, `${t.v}<small>${t.u}</small>`);
  clearTimeout(sheetStep._t);
  sheetStep._t = setTimeout(() => sendCommand(o.id, { setpoint: o.setpoint }), 500);
}

async function sheetMode(mode) {
  const o = state.open; if (!o) return;
  if (mode === 'off') return sendCommand(o.id, { power: false }).then(renderSheet);
  await sendCommand(o.id, { power: true, mode });
  renderSheet();
}

function bindSheetEvents() {
  const sheet = $('#sheet');
  sheet.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) return closeSheet();
    const step = e.target.closest('[data-step]');
    if (step) return sheetStep(Number(step.dataset.step));
    const mode = e.target.closest('[data-mode]');
    if (mode) return sheetMode(mode.dataset.mode);
  });
  sheet.addEventListener('change', (e) => {
    const o = state.open; if (!o) return;
    if (e.target.closest('[data-sheet-power]')) {
      sendCommand(o.id, { power: e.target.checked }).then(renderSheet);
    } else if (e.target.id === 'brightSlider') {
      o.brightness = Number(e.target.value);
      sendCommand(o.id, { brightness: o.brightness });
    } else if (e.target.id === 'ctSlider') {
      o.colorTemp = Number(e.target.value);
      sendCommand(o.id, { color_temp: o.colorTemp });
    }
  });
  sheet.addEventListener('input', (e) => {
    const o = state.open; if (!o) return;
    if (e.target.id === 'brightSlider') {
      o.brightness = Number(e.target.value);
      $('#brightLbl').textContent = o.brightness + '%';
      setDial(o.brightness / 100, 'var(--accent)', `${o.brightness}<small>%</small>`);
    }
  });
  $('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') closeSheet(); });
}

/* ---- automation toggle ---------------------------------------------------- */
async function toggleAutomation(id, enabled, inputEl) {
  const a = state.automations.find((x) => x.id === id);
  if (a) a.enabled = enabled;
  try {
    const res = await post(`/api/automations/${id}/toggle`, { enabled });
    if (!res.ok) throw new Error();
    toast(`${a ? a.name : 'Routine'} ${enabled ? 'enabled' : 'disabled'}`);
  } catch (_) {
    if (a) a.enabled = !enabled;
    if (inputEl) inputEl.checked = !enabled;
    toast('Could not update routine', true);
  }
}

/* ---- views ---------------------------------------------------------------- */
function switchView(view) {
  state.view = view;
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
  $$('.view').forEach((v) => (v.hidden = v.id !== 'view-' + view));
}

/* ---- data refresh --------------------------------------------------------- */
async function refresh() {
  try {
    state.data = await api('/api/devices');
    setConn(true);
    renderAll();
  } catch (e) {
    setConn(false);
  }
}
async function refreshAutomations() {
  try { state.automations = (await api('/api/automations')).automations || []; renderAutomations(); } catch (_) {}
}

function startPolling() {
  clearInterval(state.timer);
  if (state.settings.autoRefresh) state.timer = setInterval(refresh, 5000);
}

/* ---- events --------------------------------------------------------------- */
function bindEvents() {
  $('#nav').addEventListener('click', (e) => {
    const b = e.target.closest('.nav-item'); if (b) switchView(b.dataset.view);
  });

  $('#rooms').addEventListener('change', (e) => {
    const label = e.target.closest('[data-toggle]');
    if (label) {
      const card = e.target.closest('.device');
      toggleDevice(card.dataset.id, e.target.checked, e.target);
    }
  });
  $('#rooms').addEventListener('click', (e) => {
    if (e.target.closest('[data-toggle]')) return;      // toggles handled above
    const card = e.target.closest('.device');
    if (card) openSheet(card.dataset.id);
  });

  $('#automations').addEventListener('change', (e) => {
    const t = e.target.closest('[data-auto-toggle]');
    if (t) { const card = e.target.closest('[data-auto]'); toggleAutomation(card.dataset.auto, e.target.checked, e.target); }
  });

  $('#themeBtn').addEventListener('click', () => {
    state.settings.theme = state.settings.theme === 'dark' ? 'light' : 'dark';
    saveSettings(); applyTheme();
    $('#setDark').checked = state.settings.theme === 'dark';
  });

  // settings
  $('#setDark').checked = state.settings.theme === 'dark';
  $('#setFahrenheit').checked = state.settings.fahrenheit;
  $('#setAutoRefresh').checked = state.settings.autoRefresh;
  $('#setDark').addEventListener('change', (e) => { state.settings.theme = e.target.checked ? 'dark' : 'light'; saveSettings(); applyTheme(); });
  $('#setFahrenheit').addEventListener('change', (e) => { state.settings.fahrenheit = e.target.checked; saveSettings(); renderAll(); if (state.open) renderSheet(); });
  $('#setAutoRefresh').addEventListener('change', (e) => { state.settings.autoRefresh = e.target.checked; saveSettings(); startPolling(); });

  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.open) closeSheet(); });

  bindSheetEvents();
}

/* ---- boot ----------------------------------------------------------------- */
async function boot() {
  applyTheme();
  paintIcons();
  bindEvents();
  tickClock(); setInterval(tickClock, 30000);
  await Promise.all([refresh(), refreshAutomations()]);
  startPolling();
}
boot();

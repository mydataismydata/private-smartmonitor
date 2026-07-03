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
  pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  trash: '<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  ac: '<rect x="2" y="4" width="20" height="9" rx="2"/><line x1="5.5" y1="9.5" x2="14" y2="9.5"/><path d="M6 17.5c1.6 0 1.6-1.5 3.2-1.5M12 18.5c1.6 0 1.6-1.5 3.2-1.5M16 16.5c1.6 0 1.6-1.5 3.2-1.5"/>',
};
const icon = (name, cls) =>
  `<svg${cls ? ` class="${cls}"` : ''} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ''}</svg>`;

const TYPE_ICON = { light: 'bulb', plug: 'plug', switch: 'power', ac: 'ac', solar_ac: 'sun' };
const TYPES = [
  { t: 'plug', label: 'Plug', ic: 'plug' },
  { t: 'light', label: 'Light', ic: 'bulb' },
  { t: 'switch', label: 'Switch', ic: 'power' },
  { t: 'ac', label: 'A/C', ic: 'ac' },
  { t: 'solar_ac', label: 'Solar A/C', ic: 'sun' },
];
const MODES = [
  { m: 'cool', ic: 'snow', label: 'Cool' },
  { m: 'heat', ic: 'flame', label: 'Heat' },
  { m: 'auto', ic: 'auto', label: 'Auto' },
  { m: 'dry', ic: 'droplet', label: 'Dry' },
  { m: 'fan', ic: 'wind', label: 'Fan' },
];

/* ---- state ---------------------------------------------------------------- */
const SETTINGS_V = 2;  // bumped when defaults change; pre-v2 saves are re-defaulted (F is now default)

const state = {
  data: { devices: [], rooms: [], summary: {}, demo: false },
  automations: [],
  view: 'home',
  open: null,     // { id, type, setpoint, brightness, mode, power }
  settings: loadSettings(),
  timer: null,
  cdTimer: null,      // 1s ticker for the compressor cooldown countdown
  cdDeadline: 0,      // wall-clock ms when the current cooldown ends
};

function loadSettings() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem('smartmon') || '{}'); } catch (_) {}
  const current = s.v === SETTINGS_V;
  return {
    theme: s.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    // Fahrenheit is the default. Honor an explicit choice only from a current-version save;
    // anything older (when Celsius was the default) resets to F.
    fahrenheit: current ? !!s.fahrenheit : true,
    autoRefresh: s.autoRefresh !== false,
  };
}
function saveSettings() { localStorage.setItem('smartmon', JSON.stringify({ v: SETTINGS_V, ...state.settings })); }

/* ---- api ------------------------------------------------------------------ */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
const post = (path, body) =>
  api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const put = (path, body) =>
  api(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const del = (path) => api(path, { method: 'DELETE' });

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
    case 'solar_ac':
    case 'ac': {
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

// The PV / grid power row shown under a solar mini-split's card.
function solarExtra(d) {
  const st = d.state || {};
  if (d.type !== 'solar_ac' || !d.online || !st.power) return '';
  return `<div class="device-extra">
    <span class="ex solar">${icon('sun')}<b>${Math.round(st.solar_power_w || 0)}</b> W<small>solar</small></span>
    <span class="ex grid">${icon('bolt')}<b>${Math.round(st.grid_power_w || 0)}</b> W<small>AC</small></span>
  </div>`;
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
    ${solarExtra(d)}
  </div>`;
}

function renderRooms() {
  const { devices, rooms } = state.data;
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
    <p class="muted">A self-hosted controller for smart plugs, lights, switches, and A/C units — a sibling of the Solar Tracking Dashboard, running headless on the same Raspberry Pi.</p>
    <div class="kv"><b>Build</b><span>v${(d.build || {}).version || '?'}${(d.build || {}).commit ? ' · ' + d.build.commit : ''}</span></div>
    <div class="kv"><b>Mode</b><span>${d.demo ? 'Demo (simulated fleet)' : 'Live'}</span></div>
    <div class="kv"><b>Devices</b><span>${d.devices.length}</span></div>
    <div class="kv"><b>API</b><span><code>/api/devices</code>, <code>/api/devices/{id}/command</code>, <code>/api/automations</code></span></div>
    <div class="kv"><b>Discovery</b><span><code>_smartmon._tcp</code> over mDNS</span></div>`;
}

/* ---- render: banner + onboarding ------------------------------------------ */
function renderBanner() {
  const b = $('#demoBanner');
  if (!state.data.demo) { b.hidden = true; return; }
  b.hidden = false;
  b.innerHTML = `
    <span class="b-ic">${icon('chip')}</span>
    <span class="b-txt"><b>Demo mode</b><div>The devices below are simulated. Add one of your real devices to get started.</div></span>
    <span class="b-actions">
      <button class="btn" data-scan>${icon('search')}<span>Scan network</span></button>
      <button class="btn-primary" data-add-manual>${icon('plus')}<span>Add device</span></button>
    </span>`;
}

function renderOnboard() {
  const o = $('#homeEmpty');
  const show = !state.data.demo && state.data.devices.length === 0;
  o.hidden = !show;
  if (!show) return;
  o.innerHTML = `
    <div class="o-ic">${icon('chip')}</div>
    <h2>No devices yet</h2>
    <p>Scan your network to find smart devices automatically, or add one by hand. You'll paste each device's local key once (from <code>tinytuya&nbsp;wizard</code>).</p>
    <div class="o-actions">
      <button class="btn-primary" data-scan>${icon('search')}<span>Scan network</span></button>
      <button class="btn" data-add-manual>${icon('plus')}<span>Add manually</span></button>
    </div>`;
}

/* ---- render: dispatch ----------------------------------------------------- */
function renderAll() {
  const d = state.data;
  $('#greeting').textContent = greet() + '!';
  const s = d.summary || {};
  $('#subgreeting').textContent = d.devices.length
    ? `You have ${s.on ?? 0} of ${s.total ?? 0} device${s.total === 1 ? '' : 's'} currently on.`
    : (d.demo ? 'Exploring the demo fleet.' : 'No devices yet — add your first one.');
  $('#demoBadge').hidden = !d.demo;
  const b = d.build || {};
  $('#verLabel').textContent = b.version ? (b.commit ? `v${b.version} · ${b.commit}` : `v${b.version}`) : '';
  renderBanner();
  renderStats();
  renderRooms();
  renderOnboard();
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
    mode: st.mode || 'cool',   // local UI intent — the device's own report can lag a few seconds
    power: !!st.power,
    fan: st.fan_speed || '',
  };
  $('#modal').hidden = false;
  renderSheet();
}
function closeSheet() { $('#modal').hidden = true; state.open = null; clearInterval(state.cdTimer); state.cdTimer = null; state.cdDeadline = 0; }

function fmtCooldown(sec) {
  sec = Math.max(0, Math.round(sec));
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
}
// Live 1-second countdown for the compressor cooldown note. Anchored to a wall-clock deadline so
// a re-render mid-cooldown (e.g. tapping another mode) keeps counting smoothly instead of jumping.
// The server's remaining-seconds are stale between 5s polls, so only adopt a new deadline when it's
// meaningfully later (a genuinely fresh cooldown), not on every re-render.
function startCooldown(total) {
  const now = Date.now();
  const candidate = now + Math.round(total) * 1000;
  if (!state.cdDeadline || state.cdDeadline <= now || candidate > state.cdDeadline + 10000) {
    state.cdDeadline = candidate;
  }
  clearInterval(state.cdTimer);
  const tick = () => {
    const el = document.getElementById('cdLeft');
    if (!el) { clearInterval(state.cdTimer); state.cdTimer = null; return; }
    const left = Math.round((state.cdDeadline - Date.now()) / 1000);
    if (left <= 0) {
      clearInterval(state.cdTimer); state.cdTimer = null; state.cdDeadline = 0;
      const note = el.closest('.cooldown-note'); if (note) note.remove();
      return;
    }
    el.textContent = fmtCooldown(left);
  };
  tick();
  state.cdTimer = setInterval(tick, 1000);
}

function powerRow(d, st) {
  return `<div class="sheet-power">
    <span><b>Power</b><div class="muted">${st.power ? 'On' : 'Off'}</div></span>
    <label class="switch" data-sheet-power><input type="checkbox" ${st.power ? 'checked' : ''} ${d.online ? '' : 'disabled'} /><i></i></label>
  </div>`;
}

const FAN_LABELS = { auto: 'Auto', low: 'Low', medium: 'Med', mid: 'Med', high: 'High' };
const fanLabel = (f) => FAN_LABELS[f] || cap(f);

// The fan-speed selector for the A/C sheet. Speeds come from the device (options.fan_speeds).
function fanRow(d, o, on) {
  const speeds = d.fan_speeds && d.fan_speeds.length ? d.fan_speeds : ['auto', 'low', 'medium', 'high'];
  return `<div class="fan-row">
    <label>Fan speed</label>
    <div class="fan-speeds">
      ${speeds.map((f) => `<button class="fan-btn ${on && o.fan === f ? 'active' : ''}" data-fan="${f}" ${on ? '' : 'disabled'}>${fanLabel(f)}</button>`).join('')}
    </div>
  </div>`;
}

function renderSheet() {
  const o = state.open; if (!o) return;
  const d = deviceById(o.id); if (!d) return closeSheet();
  const st = d.state || {};
  let body = '';

  if (d.type === 'ac' || d.type === 'solar_ac') {
    const isSolar = d.type === 'solar_ac';
    const on = o.power;                              // local intent, so the UI updates instantly
    const frac = (o.setpoint - 16) / (30 - 16);
    const color = o.mode === 'heat' ? 'var(--amber)' : o.mode === 'cool' ? 'var(--sky)' : 'var(--accent)';
    const t = tempDisplay(o.setpoint);
    const room = tempDisplay(st.current_temp_c);
    const cd = d.power_cooldown || d.mode_cooldown || 0;
    const foot = isSolar
      ? `<div class="sheet-foot">
          <div><span class="fi">${icon('sun')}</span><span><span class="fv" id="saSolar">${Math.round(st.solar_power_w || 0)} W</span><div class="fl">Solar</div></span></div>
          <div><span class="fi">${icon('bolt')}</span><span><span class="fv" id="saGrid">${Math.round(st.grid_power_w || 0)} W</span><div class="fl">AC / grid</div></span></div>
          <div><span class="fi">${icon('thermo')}</span><span><span class="fv" id="saRoom">${room.v}${room.u}</span><div class="fl">Room</div></span></div>
        </div>
        ${st.solar_percent != null ? `<div class="solar-split"><span id="saBar" style="width:${st.solar_percent}%"></span></div><div class="solar-split-lbl" id="saPct">${st.solar_percent}% of load from solar</div>` : ''}`
      : `<div class="sheet-foot">
          <div><span class="fi">${icon('thermo')}</span><span><span class="fv">${room.v}${room.u}</span><div class="fl">Room temp</div></span></div>
          <div><span class="fi">${icon('wind')}</span><span><span class="fv">${on ? cap(o.mode) : 'Off'}</span><div class="fl">Mode</div></span></div>
        </div>`;
    body = `
      ${dialHTML(frac, color, `<div class="dial-ic">${icon('thermo')}</div><div class="dial-val" id="dialVal">${t.v}<small>${t.u}</small></div><div class="dial-cap">Setpoint</div>`)}
      <div class="stepper">
        <button class="step-btn" data-step="-1" ${on ? '' : 'disabled'}>${icon('minus')}</button>
        <button class="step-btn" data-step="1" ${on ? '' : 'disabled'}>${icon('plus')}</button>
      </div>
      ${cd ? `<div class="cooldown-note">Compressor cooldown — <span id="cdLeft">${fmtCooldown(cd)}</span> left</div>` : ''}
      <div class="modes">
        ${MODES.map((m) => `<button class="mode-btn ${on && o.mode === m.m ? 'active' : ''}" data-mode="${m.m}">${icon(m.ic)}<span>${m.label}</span></button>`).join('')}
        <button class="mode-btn ${!on ? 'active' : ''}" data-mode="off" style="${!on ? 'background:var(--ink-3);border-color:var(--ink-3);color:#fff' : ''}">${icon('power')}<span>Off</span></button>
      </div>
      ${fanRow(d, o, on)}
      ${foot}`;
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

  const editable = !state.data.demo;
  $('#sheet').innerHTML = `
    <div class="sheet-head">
      <div><div class="sheet-title">${d.name}</div><div class="sheet-sub">${d.room}${d.online ? '' : ' · offline'}</div></div>
      <div class="sheet-actions">
        ${editable ? `<button class="sheet-icon" data-edit-device="${d.id}" title="Edit device">${icon('pencil')}</button>` : ''}
        <button class="sheet-close" data-close>${icon('close')}</button>
      </div>
    </div>${body}`;

  // (Re)start the live compressor-cooldown countdown, if any.
  const cd = (d.type === 'ac' || d.type === 'solar_ac') ? (d.power_cooldown || d.mode_cooldown || 0) : 0;
  if (cd > 0) startCooldown(cd);
  else { clearInterval(state.cdTimer); state.cdTimer = null; }
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
  if (d.type === 'solar_ac') {
    const set = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
    set('saSolar', `${Math.round(st.solar_power_w || 0)} W`);
    set('saGrid', `${Math.round(st.grid_power_w || 0)} W`);
    const room = tempDisplay(st.current_temp_c); set('saRoom', `${room.v}${room.u}`);
    if (st.solar_percent != null) {
      const bar = document.getElementById('saBar'); if (bar) bar.style.width = st.solar_percent + '%';
      set('saPct', `${st.solar_percent}% of load from solar`);
    }
  }
}

/* ---- add / edit device form ----------------------------------------------- */
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

function showModal(html) {
  state.open = null;              // not a control sheet — pauses live refresh
  clearInterval(state.cdTimer); state.cdTimer = null;
  $('#sheet').innerHTML = html;
  $('#modal').hidden = false;
}

function slugify(s) {
  return (s || '').toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'device';
}
function uniqueId(base) {
  const ids = new Set(state.data.devices.map((d) => d.id));
  if (!ids.has(base)) return base;
  let n = 2; while (ids.has(`${base}-${n}`)) n++;
  return `${base}-${n}`;
}

function openAddForm(prefill) { renderDeviceForm({ mode: 'add', data: prefill || {} }); }

async function openEditForm(id) {
  try {
    const cfg = await api(`/api/devices/${id}/config`);
    if (!cfg.available) return toast('Device not found', true);
    renderDeviceForm({ mode: 'edit', id, data: cfg });
  } catch (_) { toast('Could not load device', true); }
}

function renderDeviceForm({ mode, id, data }) {
  data = data || {};
  const type = data.type || 'plug';
  const rooms = (state.data.rooms || []).filter((r) => r && r !== 'Unassigned');
  const keyHint = (mode === 'edit' && data.has_local_key) ? 'leave blank to keep current key' : '16-character local key';
  showModal(`
    <div class="sheet-head">
      <div><div class="sheet-title">${mode === 'edit' ? 'Edit device' : 'Add device'}</div>
        <div class="sheet-sub">${mode === 'edit' ? esc(data.id) : 'Tuya-local (LAN) device'}</div></div>
      <button class="sheet-close" data-close>${icon('close')}</button>
    </div>
    <div class="form">
      <div class="form-row">
        <label>Type</label>
        <div class="type-pick" id="typePick">
          ${TYPES.map((t) => `<button type="button" data-type="${t.t}" class="${t.t === type ? 'active' : ''}">${icon(t.ic)}<span>${t.label}</span></button>`).join('')}
        </div>
        <input type="hidden" id="f_type" value="${type}" />
      </div>
      <div class="form-row">
        <label>Name <span class="req">*</span></label>
        <input id="f_name" value="${esc(data.name)}" placeholder="e.g. Living Room Lamp" />
      </div>
      <div class="form-row">
        <label>Room</label>
        <input id="f_room" value="${esc(data.room)}" placeholder="e.g. Living Room" list="roomList" />
        <datalist id="roomList">${rooms.map((r) => `<option value="${esc(r)}"></option>`).join('')}</datalist>
      </div>
      <div class="form-row split">
        <div class="form-row"><label>IP address <span class="req">*</span></label><input id="f_ip" value="${esc(data.ip)}" placeholder="192.168.1.50" /></div>
        <div class="form-row"><label>Version</label><input id="f_version" value="${esc(data.version || 3.3)}" placeholder="3.3" /></div>
      </div>
      <div class="form-row">
        <label>Device ID <span class="req">*</span></label>
        <input id="f_device_id" value="${esc(data.device_id)}" placeholder="Tuya device id (gwId)" />
      </div>
      <div class="form-row">
        <label>Local key ${mode === 'edit' ? '' : '<span class="req">*</span>'}</label>
        <input id="f_local_key" type="password" placeholder="${keyHint}" autocomplete="off" />
        <span class="hint">From <code>tinytuya wizard</code> — stored only on this server.</span>
      </div>
      <button class="adv-toggle" data-adv>Advanced · DP / option overrides</button>
      <div class="adv" id="advBox" hidden>
        <div class="form-row"><label>DP overrides (JSON)</label><textarea id="f_dps" placeholder='{"power":"1","brightness":"2"}'>${esc(data.dps ? JSON.stringify(data.dps) : '')}</textarea></div>
        <div class="form-row"><label>Options (JSON)</label><textarea id="f_options" placeholder='{"bright_scale":255}'>${esc(data.options ? JSON.stringify(data.options) : '')}</textarea></div>
      </div>
      <div class="form-error" id="formError"></div>
      <div class="form-actions">
        ${mode === 'edit'
          ? `<button class="btn-danger" data-remove="${esc(data.id)}">${icon('trash')}<span>Remove</span></button>`
          : `<button class="btn" data-scan>${icon('search')}<span>Scan</span></button>`}
        <span class="spacer"></span>
        <button class="btn-ghost" data-close>Cancel</button>
        <button class="btn-primary" data-save="${mode}" ${mode === 'edit' ? `data-id="${esc(data.id)}"` : ''}>${mode === 'edit' ? 'Save' : 'Add device'}</button>
      </div>
    </div>`);
}

function collectForm() {
  const val = (id) => { const el = $('#' + id); return el ? el.value.trim() : ''; };
  const body = {
    type: val('f_type'),
    name: val('f_name'),
    room: val('f_room'),
    protocol: 'tuya',
    ip: val('f_ip'),
    device_id: val('f_device_id'),
    version: parseFloat(val('f_version')) || 3.3,
  };
  const key = val('f_local_key');
  if (key) body.local_key = key;
  const dps = val('f_dps'), opt = val('f_options');
  if (dps) body.dps = JSON.parse(dps);       // may throw -> caught by caller
  if (opt) body.options = JSON.parse(opt);
  return body;
}

async function submitDeviceForm(mode, id) {
  const err = $('#formError'); err.textContent = '';
  let body;
  try { body = collectForm(); }
  catch (_) { err.textContent = 'Advanced fields must be valid JSON.'; return; }
  if (!body.name) { err.textContent = 'Give the device a name.'; return; }
  if (!body.ip || !body.device_id || (mode === 'add' && !body.local_key)) {
    err.textContent = 'IP, device ID, and local key are required.'; return;
  }
  let res;
  try {
    if (mode === 'add') { body.id = uniqueId(slugify(body.name)); res = await post('/api/devices', body); }
    else { res = await put(`/api/devices/${id}`, body); }
  } catch (_) { err.textContent = 'Request failed.'; return; }
  if (res && res.ok) {
    closeSheet(); await refresh();
    toast(mode === 'add' ? 'Device added' : 'Device saved');
  } else {
    err.textContent = (res && res.error) || 'Could not save the device.';
  }
}

async function removeDevice(id) {
  if (!confirm('Remove this device? This only deletes it from SmartMonitor, not the device itself.')) return;
  try {
    const res = await del(`/api/devices/${id}`);
    if (res && res.ok) { closeSheet(); await refresh(); toast('Device removed'); }
    else toast((res && res.error) || 'Could not remove device', true);
  } catch (_) { toast('Could not remove device', true); }
}

/* ---- discovery ------------------------------------------------------------ */
async function openDiscovery() {
  showModal(`
    <div class="sheet-head">
      <div><div class="sheet-title">Scan for devices</div><div class="sheet-sub">Tuya devices on your network</div></div>
      <button class="sheet-close" data-close>${icon('close')}</button>
    </div>
    <div class="disco-status"><span class="disco-spin"></span> Scanning your local network…</div>
    <div class="disco-list" id="discoList"></div>`);
  try { renderDiscovery(await api('/api/discover')); }
  catch (_) { renderDiscovery({ available: false, error: 'scan failed' }); }
}

function renderDiscovery(res) {
  const status = $('.disco-status'), list = $('#discoList');
  if (!status) return;  // modal was closed while scanning
  if (!res.available) {
    status.innerHTML = `${icon('offline')} Discovery unavailable — ${esc(res.error || 'tinytuya not installed on the server')}.`;
    list.innerHTML = `<button class="btn-primary" data-add-manual>${icon('plus')}<span>Add manually instead</span></button>`;
    return;
  }
  const devs = res.devices || [];
  status.textContent = devs.length ? `Found ${devs.length} device${devs.length > 1 ? 's' : ''} on the network.` : 'No Tuya devices found on the network.';
  list.innerHTML = devs.map((d) => {
    const payload = encodeURIComponent(JSON.stringify({ ip: d.ip, device_id: d.device_id, version: d.version }));
    return `<div class="disco-item ${d.configured ? 'configured' : ''}">
      <span class="d-ic">${icon('plug')}</span>
      <span class="d-meta"><div class="d-ip">${esc(d.ip)}</div><div class="d-id">${esc(d.device_id || 'unknown id')}</div></span>
      ${d.configured
        ? `<span class="tag-added">${icon('power')} Added</span>`
        : `<button class="btn" data-disco-use="${payload}">Use</button>`}
    </div>`;
  }).join('') + `<button class="btn-ghost" data-add-manual style="align-self:center;margin-top:6px">Add manually instead</button>`;
}

/* ---- sheet interactions --------------------------------------------------- */
function sheetStep(delta) {
  const o = state.open; if (!o || (o.type !== 'ac' && o.type !== 'solar_ac')) return;
  o.setpoint = Math.max(16, Math.min(30, o.setpoint + delta));
  const color = o.mode === 'heat' ? 'var(--amber)' : o.mode === 'cool' ? 'var(--sky)' : 'var(--accent)';
  const t = tempDisplay(o.setpoint);
  setDial((o.setpoint - 16) / 14, color, `${t.v}<small>${t.u}</small>`);
  clearTimeout(sheetStep._t);
  sheetStep._t = setTimeout(() => sendCommand(o.id, { setpoint: o.setpoint }), 500);
}

async function sheetMode(mode) {
  const o = state.open; if (!o) return;
  const prevMode = o.mode, prevPower = o.power;
  // Reflect the selection immediately — the device's own status() can lag a few seconds.
  if (mode === 'off') o.power = false;
  else { o.power = true; o.mode = mode; }
  renderSheet();
  // Only send a power write when we're actually turning the unit on from off. Switching modes on
  // an already-on unit sends just the mode, so it isn't caught by the compressor power cooldown.
  let cmd;
  if (mode === 'off') cmd = { power: false };
  else if (!prevPower) cmd = { power: true, mode };
  else cmd = { mode };
  const res = await sendCommand(o.id, cmd);
  if (!res || !res.ok) { o.mode = prevMode; o.power = prevPower; }  // rejected (e.g. cooldown) -> revert
  renderSheet();
}

async function sheetFan(fan) {
  const o = state.open; if (!o) return;
  const prev = o.fan;
  o.fan = fan;                    // optimistic — highlight immediately
  renderSheet();
  const res = await sendCommand(o.id, { fan });
  if (!res || !res.ok) { o.fan = prev; renderSheet(); }
}

function bindSheetEvents() {
  const sheet = $('#sheet');
  sheet.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) return closeSheet();
    const step = e.target.closest('[data-step]');
    if (step) return sheetStep(Number(step.dataset.step));
    const mode = e.target.closest('[data-mode]');
    if (mode) return sheetMode(mode.dataset.mode);
    const fan = e.target.closest('[data-fan]');
    if (fan) return sheetFan(fan.dataset.fan);
    // management actions
    const edit = e.target.closest('[data-edit-device]');
    if (edit) return openEditForm(edit.dataset.editDevice);
    const typeBtn = e.target.closest('[data-type]');
    if (typeBtn) {
      $$('#typePick [data-type]').forEach((b) => b.classList.toggle('active', b === typeBtn));
      $('#f_type').value = typeBtn.dataset.type;
      return;
    }
    if (e.target.closest('[data-adv]')) { const a = $('#advBox'); if (a) a.hidden = !a.hidden; return; }
    const save = e.target.closest('[data-save]');
    if (save) return submitDeviceForm(save.dataset.save, save.dataset.id);
    const rm = e.target.closest('[data-remove]');
    if (rm) return removeDevice(rm.dataset.remove);
    const use = e.target.closest('[data-disco-use]');
    if (use) return openAddForm(JSON.parse(decodeURIComponent(use.dataset.discoUse)));
    if (e.target.closest('[data-scan]')) return openDiscovery();
    if (e.target.closest('[data-add-manual]')) return openAddForm({});
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

  // add-device button + the banner / onboarding calls-to-action
  $('#addBtn').addEventListener('click', () => openAddForm({}));
  $('#view-home').addEventListener('click', (e) => {
    if (e.target.closest('[data-scan]')) return openDiscovery();
    if (e.target.closest('[data-add-manual]')) return openAddForm({});
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

  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#modal').hidden) closeSheet(); });

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

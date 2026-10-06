"use strict";
const TZ = "America/New_York";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const fmtTime = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const fmtHour = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric" });
const fmtDay = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", month: "short", day: "numeric" });
const tm = (iso) => fmtTime.format(new Date(iso)).replace(" AM", "a").replace(" PM", "p");
const hr = (iso) => fmtHour.format(new Date(iso)).replace(" AM", "a").replace(" PM", "p");
const dayKey = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d);
const compass = (d) => ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"][Math.round(((d % 360) / 22.5)) % 16];

// "Label: value" reasons from the engine -> labeled rows
const facts = (rs) => `<dl class="facts">${(rs || []).map((r) => {
  const i = r.indexOf(": ");
  return i > 0 ? `<dt>${esc(r.slice(0, i))}</dt><dd>${esc(r.slice(i + 2))}</dd>` : `<dd class="full">${esc(r)}</dd>`;
}).join("")}</dl>`;
const rating = (s) => s == null ? "" : s >= 80 ? "Excellent" : s >= 65 ? "Good" : s >= 45 ? "Fair" : "Poor";

let PLAN = null;
const state = { tab: "now", day: null, slot: null, mode: "all", followNow: true, owl: false };
try { state.owl = localStorage.getItem("owl") === "1"; } catch {}
const hourOf = (iso) => +new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", hourCycle: "h23" }).format(new Date(iso));

/* ---------------------------------------------------------------- data */
async function load() {
  try {
    const r = await fetch("/api/plan", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    PLAN = await r.json();
    try { localStorage.setItem("plan", JSON.stringify(PLAN)); } catch {}
  } catch (e) {
    try { PLAN = JSON.parse(localStorage.getItem("plan")); } catch {}
  }
  if (!PLAN) { $("#status").textContent = "No data yet — open once with signal to download the plan."; return; }
  init();
}

function statusLine() {
  const gen = new Date(PLAN.generated);
  const mins = Math.round((Date.now() - gen) / 60000);
  const age = mins < 60 ? `${mins} min ago` : mins < 1440 ? `${Math.round(mins / 60)} h ago` : `${Math.round(mins / 1440)} d ago`;
  const fb = Object.entries(PLAN.sources || {}).filter(([, v]) => v.source && /fallback|cached/.test(v.source));
  const off = navigator.onLine ? "" : "Offline · ";
  const el = $("#status");
  el.textContent = `${off}Updated ${age}${fb.length ? ` · ${fb.length} source${fb.length > 1 ? "s" : ""} on backup data` : ""}`;
  el.classList.toggle("stale", mins > 90 || fb.length > 0);
}

/* ---------------------------------------------------------------- time selection */
function nowSlot() {
  const now = new Date();
  const key = dayKey(now);
  const day = PLAN.days.find((d) => d.date === key);
  if (!day) return null;
  let best = 0, bestd = Infinity;
  day.slots.forEach((s, i) => { const d = Math.abs(new Date(s.t) - now); if (d < bestd) { bestd = d; best = i; } });
  return { day: day.date, slot: best };
}

function defaultSelection() {
  const n = nowSlot();
  if (n) return { ...n, live: true };
  // Before the trip: preview Saturday dawn (or the first day) so the page is useful now.
  const d = PLAN.days.find((x) => x.special) || PLAN.days[0];
  const i = Math.max(0, d.slots.findIndex((s) => s.t.slice(11, 16) === "07:00"));
  return { day: d.date, slot: i, live: false };
}

function curDay() { return PLAN.days.find((d) => d.date === state.day) || PLAN.days[0]; }

/* ---------------------------------------------------------------- current station state */
function stationAt(evs, t) {
  const slacks = evs.filter((e) => e.type === "slack");
  let a = null, b = null;
  for (const s of slacks) { if (new Date(s.t) <= t) a = s; else { b = s; break; } }
  if (!a || !b) return null;
  const ta = new Date(a.t), tb = new Date(b.t);
  const mx = evs.find((e) => e.type !== "slack" && new Date(e.t) >= ta && new Date(e.t) <= tb);
  const frac = (t - ta) / (tb - ta);
  return { phase: a.begins || mx?.type || "slack", flow: Math.sin(Math.PI * frac), next: b.t,
           maxT: mx ? mx.t : new Date(+ta + (tb - ta) / 2).toISOString(), maxV: mx?.v };
}

/* ---------------------------------------------------------------- NOW tab */
function fillWhen() {
  const ds = $("#nowDay"), ts = $("#nowTime");
  ds.innerHTML = PLAN.days.map((d) => `<option value="${d.date}">${esc(d.label)}</option>`).join("");
  ds.value = state.day;
  ts.innerHTML = curDay().slots.map((s, i) => `<option value="${i}">${tm(s.t)}</option>`).join("");
  ts.value = state.slot;
}

function renderNow() {
  fillWhen();
  const day = curDay(), slot = day.slots[state.slot];
  const t = new Date(slot.t);
  $("#special").hidden = !day.special;
  $("#special").textContent = day.special || "";

  // water + wind strip
  const rows = [];
  const w = slot.wind;
  if (w) rows.push(`<div class="row"><span class="stn">Wind</span><span class="ph">${w.c} ${w.kn} kn</span>
     <span class="sub">gusts ${w.g} kn${w.kn >= 15 ? " — think about the lee" : ""}</span></div>`);
  for (const [, st] of Object.entries(PLAN.stations)) {
    const s = stationAt(st.events, t);
    if (!s) continue;
    const v = s.maxV ? `${s.maxV.toFixed(1)} kn max` : "max";
    rows.push(`<div class="row"><span class="stn">${esc(st.label)}</span>
      <span class="ph ${s.phase}">${s.phase} ${Math.round(s.flow * 100)}%</span>
      <div class="flowbar"><i style="width:${Math.round(s.flow * 100)}%"></i></div>
      <span class="sub">${v} at ${tm(s.maxT)} · turns ${tm(s.next)}</span></div>`);
  }
  $("#water").innerHTML = rows.join("");

  // ranked spots
  const spots = PLAN.spots.filter((s) => state.mode === "all" || s.mode === state.mode);
  const ranked = spots.map((s) => ({ s, c: slot.cells[s.id] })).filter((x) => x.c && x.c.s != null)
    .sort((a, b) => b.c.s - a.c.s);
  $("#ranked").innerHTML = ranked.map(({ s, c }, i) => `
    <li class="${i === 0 ? "best" : ""}" data-spot="${s.id}">
      <div class="score">${c.s}<small>/100</small><small class="rate">${rating(c.s)}</small></div>
      <div><h3>${esc(s.name)}<span class="mode">${s.mode}</span></h3>
        <div class="why">${facts(c.r)}</div>
        ${c.w.map((x) => `<p class="warnline">${esc(x)}</p>`).join("")}
        ${i < 3 ? nextWindowText(s.id) : ""}
      </div></li>`).join("") || `<li><div></div><div>No data for this time.</div></li>`;
  $$("#ranked li[data-spot]").forEach((li) => li.onclick = () => openSpot(li.dataset.spot, state.day, state.slot));
}

function nextWindowText(spotId) {
  const day = curDay(); const t = new Date(day.slots[state.slot].t);
  const w = day.windows.find((x) => x.spot === spotId && new Date(x.end) > t);
  return w ? `<dl class="facts lure"><dt>Best window</dt><dd>${tm(w.start)}–${tm(w.end)}</dd><dt>Lure</dt><dd>${esc(w.lure)}</dd></dl>` : "";
}

/* ---------------------------------------------------------------- PLAN tab */
function dayChips(el, onPick) {
  el.innerHTML = PLAN.days.map((d) => `<button class="chip ${d.date === state.day ? "on" : ""}" data-d="${d.date}" role="tab">${esc(d.label)}</button>`).join("");
  $$("button", el).forEach((b) => b.onclick = () => { state.day = b.dataset.d; state.followNow = false; onPick(); });
}

function heat(s) { return s == null ? "" : s >= 80 ? "h4" : s >= 65 ? "h3" : s >= 50 ? "h2" : s >= 35 ? "h1" : "h0"; }

function renderPlan() {
  dayChips($("#planDays"), renderPlan);
  const day = curDay();
  $("#special").hidden = !day.special; $("#special").textContent = day.special || "";
  const name = Object.fromEntries(PLAN.spots.map((s) => [s.id, s]));
  $("#nightOwl").classList.toggle("on", state.owl); $("#nightOwl").setAttribute("aria-pressed", state.owl);
  $("#owlHint").hidden = !state.owl;
  let wins = day.windows;
  if (state.owl) {
    // tonight = this evening onward + the next calendar day's small hours
    const next = PLAN.days[PLAN.days.indexOf(day) + 1];
    const nw = (d) => d.night_windows || d.windows;  // older cached plans lack night_windows
    wins = [...nw(day).filter((w) => hourOf(w.start) >= 16),
            ...(next ? nw(next).filter((w) => hourOf(w.start) < 3) : [])];
  }
  $("#windows").innerHTML = (wins.map((w) => `
    <li data-spot="${w.spot}"><div class="head"><span>${esc(name[w.spot].name)} <span class="mode">${name[w.spot].mode} · score ${w.peak} (${rating(w.peak)})</span></span>
      <span class="time">${state.owl && hourOf(w.start) < 3 ? "after midnight · " : ""}${tm(w.start)}–${tm(w.end)}</span></div>
      ${facts(w.why)}<dl class="facts"><dt>Lure</dt><dd>${esc(w.lure)}</dd></dl>
      ${w.warn.map((x) => `<p class="warnline">${esc(x)}</p>`).join("")}</li>`).join(""))
    || `<li><p class="hint">No strong ${state.owl ? "evening or night " : ""}windows this day.</p></li>`;
  const now = nowSlot();
  const head = `<thead><tr><th></th>${day.slots.map((s) => `<th>${s.t.slice(14, 16) === "00" ? hr(s.t) : ""}</th>`).join("")}</tr></thead>`;
  const body = PLAN.spots.map((sp) => `<tr><th>${esc(sp.short || sp.name)}</th>${day.slots.map((s, i) => {
    const c = s.cells[sp.id]; const isNow = now && now.day === day.date && now.slot === i;
    return `<td class="${heat(c?.s)} ${isNow ? "nowc" : ""} ${c?.w?.length ? "warn" : ""}" data-spot="${sp.id}" data-i="${i}" title="${c?.s ?? ""}"></td>`;
  }).join("")}</tr>`).join("");
  $("#grid").innerHTML = head + `<tbody>${body}</tbody>`;
  $$("#grid td").forEach((td) => td.onclick = () => openSpot(td.dataset.spot, day.date, +td.dataset.i));
  const wrap = $(".gridwrap"); const firstTd = $("#grid tbody td");
  if (wrap && firstTd && !wrap.dataset.scrolled) { wrap.scrollLeft = firstTd.offsetWidth * (state.owl ? 32 : 10); /* open at 4p or 5a */ wrap.dataset.scrolled = 1; }
}

function openSpot(id, dayDate, i) {
  const sp = PLAN.spots.find((s) => s.id === id);
  const day = PLAN.days.find((d) => d.date === dayDate); const slot = day.slots[i]; const c = slot.cells[id];
  $("#detailBody").innerHTML = `<h3>${esc(sp.name)} <span class="mode">${sp.mode}</span></h3>
    <p><b>Score ${c?.s ?? "—"}/100</b> ${rating(c?.s) ? `(${rating(c.s)})` : ""} at ${tm(slot.t)}, ${esc(day.label)}</p>
    ${facts(c?.r)}
    ${(c?.w || []).map((x) => `<p class="warnline">${esc(x)}</p>`).join("")}
    <p>${esc(sp.notes)}</p>
    <p class="hint">Flow from ${esc(sp.flow_ref)} · targets: ${esc(sp.targets.join(", "))}</p>
    <p><a class="chip" href="${mapsLink(sp)}">Directions</a></p>`;
  $("#detail").showModal();
}

function mapsLink(sp) {
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent);
  return ios ? `maps://?q=${sp.lat},${sp.lon}` : `https://www.google.com/maps/search/?api=1&query=${sp.lat},${sp.lon}`;
}

/* ---------------------------------------------------------------- TIDES tab */
function renderTides() {
  dayChips($("#tideDays"), renderTides);
  const day = curDay();
  const src = (k) => PLAN.sources?.[k]?.source || "";
  const badge = (k) => { const s = src(k); return s ? `<small class="${/fallback|cached/.test(s) ? "fallback" : ""}">${esc(s)}</small>` : ""; };
  const tides = PLAN.tides.filter((e) => e.t.startsWith(day.date));
  let html = `<table class="tbl"><caption>Edgartown tide ${badge("tides")}</caption>
    <tr><th>Time</th><th>Tide</th><th>Height</th></tr>
    ${tides.map((e) => `<tr><td>${tm(e.t)}</td><td>${e.type === "H" ? "High" : "Low"}</td><td>${e.v != null ? e.v.toFixed(1) + " ft" : "—"}</td></tr>`).join("")}</table>`;
  for (const [k, st] of Object.entries(PLAN.stations)) {
    const evs = st.events.filter((e) => e.t.startsWith(day.date));
    html += `<table class="tbl"><caption>${esc(st.label)} ${badge("cur_" + k)}</caption>
      <tr><th>Time</th><th>Event</th><th>Speed</th></tr>
      ${evs.map((e) => `<tr><td>${tm(e.t)}</td><td>${e.type === "slack" ? `Slack, ${e.begins || "?"} begins` : `Max ${e.type}`}</td><td>${e.type !== "slack" && e.v ? e.v.toFixed(1) + " kn" : ""}</td></tr>`).join("")}</table>`;
  }
  html += `<p class="hint">Current lags tide at the Gut and the ponds — the bay keeps draining past posted low. Slack is dead water; flow beats direction.</p>`;
  $("#tideTables").innerHTML = html;
}

/* ---------------------------------------------------------------- WIND tab */
function renderWind() {
  dayChips($("#windDays"), renderWind);
  const day = curDay();
  const hours = PLAN.wind.filter((h) => h.t.startsWith(day.date) && +h.t.slice(11, 13) >= 4 && +h.t.slice(11, 13) <= 20);
  $("#windTable").innerHTML = hours.length ? `<table class="tbl"><caption>Wind, Edgartown <small>${esc(PLAN.sources?.wind?.source || "")}</small></caption>
    <tr><th>Time</th><th>From</th><th>Wind</th><th>Gust</th><th>Cloud</th></tr>
    ${hours.map((h) => `<tr><td>${hr(h.t)}</td><td><span class="arrow" style="transform:rotate(${h.dir + 180}deg)" aria-hidden="true">↑</span> ${h.c}</td>
      <td>${Math.round(h.kn)} kn</td><td>${Math.round(h.gust)}</td><td>${h.cloud ?? "—"}%</td></tr>`).join("")}</table>`
    : `<p class="hint">No wind forecast for this day yet — it fills in about 16 days out.</p>`;
  const m = PLAN.marine || {};
  $("#marine").innerHTML = Object.values(m).map((z) => `<div class="marine"><h3>${esc(z.label)}</h3>
      <p class="hint">${esc(z.issued || "")}</p>
      ${(z.advisories || []).map((a) => `<p class="adv">${esc(a)}</p>`).join("")}
      ${(z.periods || []).slice(0, 6).map((p) => `<p><b>${esc(p.name)}</b> ${esc(p.text)}</p>`).join("")}</div>`).join("");
  if (navigator.onLine && !$("#windy iframe")) {
    $("#windy").innerHTML = `<iframe loading="lazy" title="Windy wind forecast" src="https://embed.windy.com/embed2.html?lat=41.40&lon=-70.52&detailLat=41.39&detailLon=-70.51&zoom=10&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=true&calendar=now&type=map&location=coordinates&metricWind=kt&metricTemp=%C2%B0F"></iframe>`;
  }
}

/* ---------------------------------------------------------------- CHART tab */
const chart = { meta: null, s: 0.3, x: 0, y: 0, built: false };
const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2));
function llToPx(lat, lon) {
  const m = chart.meta;
  const x = (lon - m.west) / (m.east - m.west) * m.width;
  const y = (merc(m.north) - merc(lat)) / (merc(m.north) - merc(m.south)) * m.height;
  return [x, y];
}
function applyChart(anim) {
  const inner = $("#chartInner"); inner.classList.toggle("anim", !!anim);
  inner.style.transform = `translate(${chart.x}px, ${chart.y}px) scale(${chart.s})`;
  $$(".mk", inner).forEach((m) => m.style.transform = `translate(-50%,-50%) scale(${1 / chart.s})`);
}
function zoomAt(f, cx, cy) {
  const ns = Math.min(3, Math.max(0.12, chart.s * f));
  chart.x = cx - (cx - chart.x) * (ns / chart.s); chart.y = cy - (cy - chart.y) * (ns / chart.s); chart.s = ns; applyChart();
}
async function buildChart() {
  if (chart.built) return;
  chart.meta = await (await fetch("/chart.json")).json();
  const box = $("#chartBox");
  const slot = curDay().slots[state.slot];
  $("#markers").innerHTML = PLAN.spots.map((sp) => {
    const [x, y] = llToPx(sp.lat, sp.lon); const sc = slot.cells[sp.id]?.s;
    return `<button class="mk ${sp.mode}" style="left:${x}px;top:${y}px" data-spot="${sp.id}" aria-label="${esc(sp.name)}">${sc ?? ""}</button>`;
  }).join("");
  $$(".mk").forEach((b) => b.onclick = (e) => { e.stopPropagation(); spotCard(b.dataset.spot); });
  const fit = () => { box.style.height = Math.max(300, innerHeight - box.getBoundingClientRect().top - 130) + "px"; };
  fit(); addEventListener("resize", fit);
  // start centred on Edgartown / Chappy
  const [ex, ey] = llToPx(41.40, -70.52); chart.s = 0.4;
  chart.x = box.clientWidth / 2 - ex * chart.s; chart.y = box.clientHeight / 2 - ey * chart.s; applyChart();

  const ptrs = new Map(); let last = null;
  box.addEventListener("pointerdown", (e) => { box.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, e); last = null; });
  box.addEventListener("pointermove", (e) => {
    if (!ptrs.has(e.pointerId)) return;
    const prev = ptrs.get(e.pointerId); ptrs.set(e.pointerId, e);
    if (ptrs.size === 1) { chart.x += e.clientX - prev.clientX; chart.y += e.clientY - prev.clientY; applyChart(); }
    else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()]; const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      const r = box.getBoundingClientRect();
      if (last) zoomAt(d / last, (a.clientX + b.clientX) / 2 - r.left, (a.clientY + b.clientY) / 2 - r.top);
      last = d;
    }
  });
  const up = (e) => { ptrs.delete(e.pointerId); last = null; };
  box.addEventListener("pointerup", up); box.addEventListener("pointercancel", up);
  box.addEventListener("wheel", (e) => { e.preventDefault(); const r = box.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top); }, { passive: false });
  const mid = () => [box.clientWidth / 2, box.clientHeight / 2];
  $("#zoomIn").onclick = () => zoomAt(1.4, ...mid());
  $("#zoomOut").onclick = () => zoomAt(1 / 1.4, ...mid());
  $("#locate").onclick = locate;
  chart.built = true;
}
function refreshMarkers() {
  if (!chart.built) return;
  const slot = curDay().slots[state.slot];
  $$(".mk[data-spot]").forEach((b) => b.textContent = slot.cells[b.dataset.spot]?.s ?? "");
}
function spotCard(id) {
  const sp = PLAN.spots.find((s) => s.id === id); const slot = curDay().slots[state.slot]; const c = slot.cells[id];
  const card = $("#spotCard"); card.hidden = false;
  card.innerHTML = `<h3>${esc(sp.name)} <span class="mode">${sp.mode} · score ${c?.s ?? "—"} ${rating(c?.s) ? `(${rating(c.s)})` : ""} at ${tm(slot.t)}</span></h3>
    ${facts(c?.r)}${(c?.w || []).map((x) => `<p class="warnline">${esc(x)}</p>`).join("")}
    <p>${esc(sp.notes)}</p><p><a class="chip" href="${mapsLink(sp)}">Directions</a></p>`;
}
function locate() {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition((p) => {
    const [x, y] = llToPx(p.coords.latitude, p.coords.longitude);
    let me = $(".mk.me"); if (!me) { me = document.createElement("div"); me.className = "mk me"; $("#markers").append(me); }
    me.style.left = x + "px"; me.style.top = y + "px";
    const box = $("#chartBox"); chart.x = box.clientWidth / 2 - x * chart.s; chart.y = box.clientHeight / 2 - y * chart.s; applyChart(true);
  }, () => { $("#locate").textContent = "Location unavailable"; }, { enableHighAccuracy: true, timeout: 10000 });
}

/* ---------------------------------------------------------------- shell */
function render() {
  statusLine();
  if (state.tab === "now") renderNow();
  if (state.tab === "plan") renderPlan();
  if (state.tab === "tides") renderTides();
  if (state.tab === "wind") renderWind();
  if (state.tab === "chart") buildChart().then(refreshMarkers);
}

function showTab(name) {
  state.tab = name;
  $$(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.hidden = t.id !== "tab-" + name);
  render();
}

function autoTheme() {
  const pref = localStorage.getItem("theme");
  if (pref) return pref;
  const d = PLAN?.days.find((x) => x.date === dayKey(new Date()));
  if (!d) return "day";
  const now = Date.now();
  return now < +new Date(d.sun.rise) - 600000 || now > +new Date(d.sun.set) + 900000 ? "night" : "day";
}
function setTheme(t) { document.documentElement.dataset.theme = t; }

function init() {
  const sel = defaultSelection(); state.day = sel.day; state.slot = sel.slot; state.followNow = sel.live;
  setTheme(autoTheme());
  $$(".tabs button").forEach((b) => b.onclick = () => showTab(b.dataset.tab));
  $("#nowDay").onchange = (e) => { state.day = e.target.value; state.slot = Math.min(state.slot, curDay().slots.length - 1); state.followNow = false; render(); };
  $("#nowTime").onchange = (e) => { state.slot = +e.target.value; state.followNow = false; render(); };
  $("#nowReset").onclick = () => { const n = nowSlot() || defaultSelection(); state.day = n.day; state.slot = n.slot; state.followNow = !!nowSlot(); render(); };
  $("#nightOwl").onclick = () => {
    state.owl = !state.owl; try { localStorage.setItem("owl", state.owl ? "1" : "0"); } catch {}
    const w = $(".gridwrap"); if (w) delete w.dataset.scrolled;
    renderPlan();
  };
  $$(".filters .chip").forEach((b) => b.onclick = () => { state.mode = b.dataset.mode; $$(".filters .chip").forEach((x) => x.classList.toggle("on", x === b)); renderNow(); });
  $("#themeBtn").onclick = () => { const t = document.documentElement.dataset.theme === "night" ? "day" : "night"; localStorage.setItem("theme", t); setTheme(t); };
  render();
  // keep "now" current while the phone sits open on the beach
  setInterval(() => { if (state.followNow) { const n = nowSlot(); if (n) { state.day = n.day; state.slot = n.slot; } } render(); }, 60000);
  setInterval(async () => { if (navigator.onLine) { const old = PLAN.generated; await load.quiet(); if (PLAN.generated !== old) render(); } }, 10 * 60000);
}
load.quiet = async () => { try { const r = await fetch("/api/plan", { cache: "no-store" }); if (r.ok) { PLAN = await r.json(); localStorage.setItem("plan", JSON.stringify(PLAN)); } } catch {} };
window.addEventListener("online", () => PLAN && statusLine());
window.addEventListener("offline", () => PLAN && statusLine());

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
load();

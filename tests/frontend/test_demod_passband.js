'use strict';

const D = require('../../python-processor/static/demod-passband.js');

let passed = 0;
function assert(condition, message) {
  if (!condition) throw new Error(message);
  passed += 1;
}
function approx(a, b, eps = 1e-6) { return Math.abs(a - b) <= eps; }

// Determinisztikus, kézzel léptetett scheduler (debounce + sequence tesztekhez).
class FakeScheduler {
  constructor() { this.now = 0; this.nextId = 1; this.tasks = new Map(); }
  setTimeout(callback, delay) {
    const id = this.nextId++;
    this.tasks.set(id, { at: this.now + delay, callback });
    return id;
  }
  clearTimeout(id) { this.tasks.delete(id); }
  tick(ms) {
    this.now += ms;
    const due = [...this.tasks.entries()].filter(([, t]) => t.at <= this.now);
    due.sort((a, b) => a[1].at - b[1].at);
    for (const [id, task] of due) { this.tasks.delete(id); task.callback(); }
  }
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const frame = { startFrequencyHz: 145_000_000, stepFrequencyHz: 1000, numPoints: 2001 };
// 1 px = 1000 Hz lineáris térkép a 145.0 MHz origóhoz (teszt-segéd).
const freqHzToX = (hz) => (hz - 145_000_000) / 1000;

// --- FRONTEND: állapot- és geometriatesztek ---------------------------------

// 1. Spectrum click frissíti a demod frekvenciát (a snap után az állapotba kerül).
(() => {
  const state = D.createDemodState();
  const snapped = D.snapFrequencyToSpectrumBin(145_500_400, frame);
  state.frequencyHz = snapped;
  state.requestedFrequencyHz = snapped;
  assert(state.frequencyHz === 145_500_000, '1: click sets snapped demod freq');
})();

// 2-3. Panel frekvencia/bandwidth és passband mindig azonos forrásból jön.
(() => {
  const state = D.createDemodState({ frequencyHz: 145_500_000, bandwidthHz: 12500, mode: 'NFM' });
  const edges = D.computePassbandEdges(state.mode, state.frequencyHz, state.bandwidthHz);
  assert(edges.centerHz === state.frequencyHz, '2: passband center == panel freq');
  assert(approx(edges.stopHz - edges.startHz, state.bandwidthHz), '3: passband width == panel bandwidth');
})();

// 4-7. Módváltás geometriája: NFM szimmetrikus, USB jobbra, LSB balra.
(() => {
  const f = 7_100_000;
  const nfm = D.computePassbandEdges('NFM', f, 12500);
  assert(approx(nfm.startHz, f - 6250) && approx(nfm.stopHz, f + 6250), '5: NFM symmetric');
  const usb = D.computePassbandEdges('USB', f, 2700);
  assert(approx(usb.startHz, f) && approx(usb.stopHz, f + 2700), '6: USB right-sided');
  const lsb = D.computePassbandEdges('LSB', f, 2700);
  assert(approx(lsb.startHz, f - 2700) && approx(lsb.stopHz, f), '7: LSB left-sided');
  assert(D.defaultBandwidthFor('WFM') === 75000, '4: mode default bandwidth lookup');
})();

// 8-9. Bal/jobb fogantyú módosítja a bandwidth-et (mód geometriájával).
(() => {
  const f = 100_000_000;
  // NFM: jobb fogantyút +5 kHz-re húzva a teljes BW 10 kHz lesz.
  const bwRight = D.bandwidthFromEdge('NFM', f, 'right', f + 5000);
  assert(approx(bwRight, 10000), '9: right handle sets symmetric bandwidth');
  const bwLeft = D.bandwidthFromEdge('NFM', f, 'left', f - 3000);
  assert(approx(bwLeft, 6000), '8: left handle sets symmetric bandwidth');
  // USB: csak a jobb él mozog, a bal a centeren marad.
  const bwUsb = D.bandwidthFromEdge('USB', f, 'right', f + 3100);
  assert(approx(bwUsb, 3100), '8b: USB right handle sets bandwidth');
})();

// 10. Body drag mozgatja a centert (a hívó a delta-t adja, az állapot követi).
(() => {
  const state = D.createDemodState({ frequencyHz: 100_000_000, bandwidthHz: 12500, mode: 'NFM' });
  const before = D.computePassbandEdges(state.mode, state.frequencyHz, state.bandwidthHz);
  state.frequencyHz += 25000; // body drag
  const after = D.computePassbandEdges(state.mode, state.frequencyHz, state.bandwidthHz);
  assert(approx(after.centerHz - before.centerHz, 25000), '10: body drag moves center');
  assert(approx(after.stopHz - after.startHz, before.stopHz - before.startHz), '10b: width preserved on move');
})();

// 11. A frekvencia binre igazodik; durva felbontás jelzése.
(() => {
  assert(D.snapFrequencyToSpectrumBin(145_500_499, frame) === 145_500_000, '11: snap to nearest bin');
  assert(D.snapFrequencyToSpectrumBin(145_500_501, frame) === 145_501_000, '11b: snap rounds up');
  const coarse = { startFrequencyHz: 0, stepFrequencyHz: 25000, numPoints: 100 };
  assert(D.isResolutionTooCoarse(12500, coarse) === true, '11c: coarse resolution flagged');
  assert(D.isResolutionTooCoarse(12500, frame) === false, '11d: fine resolution not flagged');
})();

// Hitbox-prioritás (bal > jobb > közép > body) keskeny sávnál is.
(() => {
  // Keskeny (500 Hz = 0.5 px) sáv: a fogantyúk átfednek, prioritás szerint a bal
  // nyer, de a sáv egyáltalán kezelhető marad (nem tűnik el a hitbox).
  const state = D.createDemodState({ frequencyHz: 145_500_000, bandwidthHz: 500, mode: 'CW' });
  const geo = D.computePixelGeometry(state, freqHzToX);
  assert(D.hitTestPassband(geo, geo.leftX, 10) === 'leftHandle', 'hit: narrow band still grabbable');
  // Tág sáv: minden hitbox jól elkülönül.
  const wide = D.createDemodState({ frequencyHz: 145_500_000, bandwidthHz: 40000, mode: 'NFM' });
  const wgeo = D.computePixelGeometry(wide, freqHzToX);
  assert(D.hitTestPassband(wgeo, wgeo.leftX) === 'leftHandle', 'hit: left handle priority');
  assert(D.hitTestPassband(wgeo, wgeo.rightX) === 'rightHandle', 'hit: right handle');
  assert(D.hitTestPassband(wgeo, wgeo.centerX) === 'centerLine', 'hit: center line');
  assert(D.hitTestPassband(wgeo, wgeo.leftX + 10) === 'body', 'hit: body interior');
  assert(D.hitTestPassband(wgeo, wgeo.leftX - 50) === null, 'hit: outside -> null');
})();

// Sávszélesség-korlátozás (negatív/nulla/min/max/capture).
(() => {
  assert(D.clampBandwidth(-5).reason === 'invalid', 'clamp: negative invalid');
  assert(D.clampBandwidth(0).reason === 'invalid', 'clamp: zero invalid');
  assert(D.clampBandwidth(50).value === D.ABSOLUTE_MIN_BANDWIDTH_HZ, 'clamp: below absolute min');
  assert(D.clampBandwidth(99_000_000).value === D.ABSOLUTE_MAX_BANDWIDTH_HZ, 'clamp: above absolute max');
  const cap = D.clampBandwidth(5_000_000, { captureBandwidthHz: 2_000_000 });
  assert(cap.value === 2_000_000 && cap.clamped, 'clamp: capped to capture bandwidth');
})();

// Device center vs channel offset terv.
(() => {
  // Belül -> csak offset.
  const inside = D.planChannelTuning(145_500_000, 145_000_000, 10_000_000);
  assert(inside.action === 'offset' && inside.offsetHz === 500_000, 'plan: inside -> offset');
  // Kívül -> retune, offset 0.
  const outside = D.planChannelTuning(160_000_000, 145_000_000, 10_000_000);
  assert(outside.action === 'retune' && outside.offsetHz === 0 && outside.retuneToHz === 160_000_000,
    'plan: outside -> retune');
  // Bizonytalan capture -> konzervatív retune.
  const fallback = D.planChannelTuning(145_500_000, null, null);
  assert(fallback.action === 'retune' && fallback.conservative === true, 'plan: unknown -> conservative retune');
})();

// --- API: debounce + sequence ----------------------------------------------

// A1. Sok mousemove (sok schedule) a debounce ablakban -> egyetlen küldés.
(async () => {
  const sched = new FakeScheduler();
  let sends = 0;
  const s = D.createUpdateScheduler({
    scheduler: sched, debounceMs: 150,
    send: async () => { sends += 1; return { ok: true }; },
  });
  for (let i = 0; i < 50; i += 1) s.schedule({ frequency_hz: 145_500_000 + i });
  sched.tick(50); assert(sends === 0, 'A3a: no send before debounce elapses');
  sched.tick(150);
  await Promise.resolve();
  assert(sends === 1, 'A3: 50 mousemoves -> single debounced send');
})();

// A4. Régi (lassú) válasz nem írja felül az újabbat.
(async () => {
  const sched = new FakeScheduler();
  const d1 = deferred();
  const d2 = deferred();
  const calls = [d1, d2];
  let appliedSeq = null;
  const s = D.createUpdateScheduler({
    scheduler: sched, debounceMs: 100,
    send: (payload, seq) => calls[seq - 1].promise.then((v) => ({ ...v, seq })),
    onApplied: (result, payload, seq) => { appliedSeq = seq; },
  });

  s.schedule({ bandwidth_hz: 12500 });
  sched.tick(100);              // 1. kérés kiküldve (lassú)
  s.schedule({ bandwidth_hz: 25000 });
  sched.tick(100);              // 2. kérés kiküldve (gyors)

  d2.resolve({ applied: 25000 }); // a friss válasz előbb ér be
  await Promise.resolve(); await Promise.resolve();
  assert(appliedSeq === 2, 'A4a: newest response applied');

  d1.resolve({ applied: 12500 }); // a régi válasz későn ér be
  await Promise.resolve(); await Promise.resolve();
  assert(appliedSeq === 2, 'A4: stale response does not overwrite newer state');
})();

// A1(inaktív)/A2(aktív): a hívó dönti el, küld-e. A scheduler nem hív, amíg nincs schedule.
(() => {
  const sched = new FakeScheduler();
  let sends = 0;
  const s = D.createUpdateScheduler({ scheduler: sched, debounceMs: 100, send: async () => { sends += 1; } });
  sched.tick(1000);
  assert(sends === 0, 'A1: no schedule -> no request (inactive drag sends nothing)');
})();

// Késleltetett összegzés (az async blokkok után).
setTimeout(() => {
  console.log(`demod passband module: PASS (${passed} assertions)`);
}, 50);

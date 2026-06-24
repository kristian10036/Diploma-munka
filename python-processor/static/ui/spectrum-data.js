// spectrum-data.js
// -----------------------------------------------------------------------------
// Tiszta / önálló spektrum-sweep adat-segédfüggvények: payload-alak kinyerés,
// tömb-csúcskeresés és a demo-mód szintetikus sweep generátora. Az index.html
// inline scriptjéből emelve, a függvénytestek szó szerint változatlanok
// (script-alapú verbatim kiemelés). Nem olvasnak app-szintű mutable state-et;
// a skála-konstansokat/transzformációkat a spectrum-scale.js-ből importálják.
// (generateDemoSweep szándékosan nem-determinisztikus: performance.now +
// Math.random – de önálló, nincs külső állapotfüggősége.)
//
// extractSpectrumPayload: már a kiemelés előtt is használaton kívüli (holt) kód
// volt az index.html-ben (csak definíció, 0 hívási hely); változatlanul
// megőrizve és exportálva (a tesztben lefedve), de az index.html nem importálja.
// -----------------------------------------------------------------------------

import { NUM_BINS, binToFreq, clamp, DBM_MIN } from './spectrum-scale.js';

export function extractSpectrumPayload(payload){
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === 'object') {
    return payload.reference ?? payload.spectrum ?? payload.sweep ?? payload.points ?? payload.data ?? payload.values ?? payload.samples ?? [];
  }
  return [];
}

export function peakOfArray(arr, start=0, end=NUM_BINS-1){
  if (!arr) return {freq:null, dbm:null};
  let best = -Infinity;
  let bestIdx = -1;
  for (let i=start; i<=end; i++) {
    const v = arr[i];
    if (Number.isFinite(v) && v > best) { best = v; bestIdx = i; }
  }
  return bestIdx >= 0 ? {freq:binToFreq(bestIdx), dbm:best} : {freq:null, dbm:null};
}

export function generateDemoSweep(){
  const out = new Float32Array(NUM_BINS);
  const now = performance.now() / 1000;
  const bands = [
    {mn: 86, mx: 108, amp: 15, wiggle: .15},
    {mn: 420, mx: 470, amp: 12, wiggle: .18},
    {mn: 700, mx: 900, amp: 22, wiggle: .20},
    {mn: 880, mx: 960, amp: 30, wiggle: .32},
    {mn: 1710, mx: 1880, amp: 26, wiggle: .25},
    {mn: 1920, mx: 2170, amp: 22, wiggle: .20},
    {mn: 2401, mx: 2484, amp: 40, wiggle: .45},
    {mn: 3400, mx: 3800, amp: 24, wiggle: .28},
    {mn: 5150, mx: 5850, amp: 34, wiggle: .38},
    {mn: 5900, mx: 6200, amp: 20, wiggle: .22},
    {mn: 7600, mx: 7900, amp: 16, wiggle: .18},
    {mn: 12200, mx: 12400, amp: 13, wiggle: .12},
  ];
  const carriers = [
    {f: 433.92, amp: 38, w: .25},
    {f: 868.3, amp: 32, w: .50},
    {f: 1575.42, amp: 18, w: .80},
    {f: 2412 + 8*Math.sin(now*.7), amp: 28, w: 3.2},
    {f: 2462, amp: 24, w: 2.5},
    {f: 5805, amp: 21, w: 4.0},
  ];
  for (let i=0;i<NUM_BINS;i++){
    const f = binToFreq(i);
    let dbm = -96 + Math.sin(i*.017 + now*.8) * 1.1 + (Math.random()-.5) * 3.4;
    for (const b of bands) {
      if (f >= b.mn && f <= b.mx) {
        const c = (b.mn + b.mx)/2;
        const hw = (b.mx - b.mn)/2;
        const env = Math.exp(-0.5 * Math.pow((f-c)/hw, 2));
        dbm += env * b.amp * (1 + b.wiggle * Math.sin(now*1.7 + f*.012));
      }
    }
    for (const c of carriers) {
      const env = Math.exp(-0.5 * Math.pow((f-c.f)/c.w, 2));
      dbm += env * c.amp;
    }
    out[i] = clamp(dbm, DBM_MIN, -6);
  }
  return Array.from(out, (y,i)=>({x:binToFreq(i), y}));
}

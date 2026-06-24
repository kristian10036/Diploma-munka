// spectrum-scale.js
// -----------------------------------------------------------------------------
// A spektrum-megjelenítés rögzített konstansai (teljes tartomány, felbontás,
// dBm-skála) és a TISZTA, az aktuális nézet-ablaktól (viewMin/viewMax) FÜGGETLEN
// koordináta-/skála-átváltó és formázó segédfüggvények. Az index.html inline
// scriptjéből emelve, viselkedésmegőrző módon (a definíciók szó szerint
// változatlanok), named importtal visszakötve (a hívási helyek bájtra azonosak).
//
// A viewMin/viewMax-FÜGGŐ transzformációk (freqToX/xToFreq/span/center/
// formatAxisFreq) szándékosan az index.html-ben maradtak: azok a mutábilis
// nézet-ablak állapotra épülnek, amelynek egyetlen írója a setView, és amely a
// rajzolás/readout/fetch orchestrationhöz kötött – ennek store-ba mozgatása
// külön, magasabb kockázatú lépés (lásd MAJOR_REFACTOR_REPORT.md).
// -----------------------------------------------------------------------------

export const FULL_MIN = 0;        // MHz; a rendszer globális megjelenítési tartománya
export const FULL_MAX = 24000;    // MHz; DC–24 GHz
export const NUM_BINS = 24576;    // belső teljes spektrum felbontás, kb. 1 MHz/bin 24 GHz-ig
export const DBM_MIN = -110;
export const DBM_MAX = 0;
export const MIN_SPAN = 0.05;     // MHz, nehogy végtelenbe zoomoljon

export function clamp(v, min, max){ return Math.max(min, Math.min(max, v)); }

export function freqToBin(freq){ return clamp(Math.round((freq - FULL_MIN) / (FULL_MAX - FULL_MIN) * (NUM_BINS - 1)), 0, NUM_BINS - 1); }
export function binToFreq(bin){ return FULL_MIN + (bin / (NUM_BINS - 1)) * (FULL_MAX - FULL_MIN); }
export function dbmToY(dbm, plot){ return plot.top + (DBM_MAX - dbm) / (DBM_MAX - DBM_MIN) * plot.height; }
export function yToDbm(y, plot){ return DBM_MAX - ((y - plot.top) / plot.height) * (DBM_MAX - DBM_MIN); }
export function fullFreqToX(freq, plot){ return plot.left + (freq - FULL_MIN) / (FULL_MAX - FULL_MIN) * plot.width; }
export function fullXToFreq(x, plot){ return FULL_MIN + (x - plot.left) / plot.width * (FULL_MAX - FULL_MIN); }

export function formatFreq(mhz, fixed){
  if (!Number.isFinite(mhz)) return '--';
  if (mhz >= 1000) {
    const ghz = mhz / 1000;
    const digits = fixed ?? (ghz >= 10 ? 3 : 4);
    return ghz.toFixed(digits) + ' GHz';
  }
  const digits = fixed ?? (mhz >= 100 ? 2 : 3);
  return mhz.toFixed(digits) + ' MHz';
}
export function formatSpan(mhz){
  if (!Number.isFinite(mhz)) return '--';
  if (mhz >= 1000) return (mhz/1000).toFixed(4) + ' GHz';
  if (mhz >= 1) return mhz.toFixed(3) + ' MHz';
  return (mhz * 1000).toFixed(1) + ' kHz';
}
export function niceStep(raw){
  const exp = Math.floor(Math.log10(raw));
  const f = raw / Math.pow(10, exp);
  let nice;
  if (f <= 1) nice = 1;
  else if (f <= 2) nice = 2;
  else if (f <= 5) nice = 5;
  else nice = 10;
  return nice * Math.pow(10, exp);
}
export function fmtHz(hz){
  if (!Number.isFinite(hz)) return '--';
  return hz >= 1e6 ? `${(hz / 1e6).toFixed(6)} MHz` : `${(hz / 1e3).toFixed(3)} kHz`;
}

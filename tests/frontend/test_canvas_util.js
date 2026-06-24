'use strict';

// Egységtesztek a python-processor/static/ui/canvas-util.js tiszta canvas-/
// geometria-segédfüggvényeihez. ESM modul (tranzitív import spectrum-scale.js),
// Node 24 require()-zel betöltve. A roundRect a megadott 2D-context metódusait
// hívja, ezért egy minimális fake-context rögzíti a hívássorrendet.

const U = require('../../python-processor/static/ui/canvas-util.js');

let passed = 0;
function assert(c, m) { if (!c) throw new Error(m); passed += 1; }
function eq(a, b, m) { assert(a === b, `${m} (várt: ${JSON.stringify(b)}, kapott: ${JSON.stringify(a)})`); }
function deq(a, b, m) { assert(JSON.stringify(a) === JSON.stringify(b), `${m} (várt: ${JSON.stringify(b)}, kapott: ${JSON.stringify(a)})`); }

// --- inPlot (hit-teszt) ---
const plot = { left: 10, top: 20, width: 100, height: 50 };
eq(U.inPlot(10, 20, plot), true, 'inPlot bal-felső sarok (inkluzív)');
eq(U.inPlot(110, 70, plot), true, 'inPlot jobb-alsó sarok (inkluzív)');
eq(U.inPlot(60, 45, plot), true, 'inPlot belül');
eq(U.inPlot(9, 45, plot), false, 'inPlot balra kívül');
eq(U.inPlot(60, 71, plot), false, 'inPlot alul kívül');

// --- dbmToColor (szín-leképezés) ---
deq(U.dbmToColor(NaN), [0, 0, 0, 0], 'dbmToColor NaN -> átlátszó');
deq(U.dbmToColor(Infinity), [0, 0, 0, 0], 'dbmToColor Infinity -> átlátszó');
{
  // alsó vég (t<=0): -100 dBm -> t=0 -> első ág, b=70
  deq(U.dbmToColor(-100), [0, 0, 70], 'dbmToColor -100 (t=0)');
  // erős jel (t>=1): -28 dBm -> t=1 -> utolsó ág, r=255
  const hi = U.dbmToColor(-20);
  assert(hi[0] === 255 && hi[2] === 0, 'dbmToColor erős jel -> vörös tartomány');
  // minden komponens 0..255 egész
  for (const dbm of [-95, -70, -55, -40, -30]) {
    const c = U.dbmToColor(dbm);
    assert(c.length === 3 && c.every(v => Number.isInteger(v) && v >= 0 && v <= 255), `dbmToColor(${dbm}) érvényes RGB`);
  }
}

// --- roundRect (a context metódusait hívja, kitöltés/körvonal kapcsolható) ---
function fakeCtx() {
  const calls = [];
  const rec = name => (...a) => calls.push(name);
  return { calls, beginPath: rec('beginPath'), moveTo: rec('moveTo'), arcTo: rec('arcTo'), closePath: rec('closePath'), fill: rec('fill'), stroke: rec('stroke') };
}
{
  const ctx = fakeCtx();
  U.roundRect(ctx, 0, 0, 10, 10, 2, true, true);
  eq(ctx.calls.filter(c => c === 'arcTo').length, 4, 'roundRect 4 arcTo (sarkok)');
  assert(ctx.calls.includes('fill') && ctx.calls.includes('stroke'), 'roundRect fill+stroke ha mindkettő true');
  eq(ctx.calls[0], 'beginPath', 'roundRect beginPath-szel kezd');
}
{
  const ctx = fakeCtx();
  U.roundRect(ctx, 0, 0, 10, 10, 2, false, false);
  assert(!ctx.calls.includes('fill') && !ctx.calls.includes('stroke'), 'roundRect nincs fill/stroke ha false');
}

console.log(`canvas util: PASS (${passed} assertions)`);

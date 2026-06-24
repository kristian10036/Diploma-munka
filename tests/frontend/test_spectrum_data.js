'use strict';

// Egységtesztek a python-processor/static/ui/spectrum-data.js tiszta sweep-adat
// segédfüggvényeihez. ESM modul (tranzitív import spectrum-scale.js), Node 24
// require()-zel betöltve.

const D = require('../../python-processor/static/ui/spectrum-data.js');
const { NUM_BINS, binToFreq } = require('../../python-processor/static/ui/spectrum-scale.js');

let passed = 0;
function assert(c, m) { if (!c) throw new Error(m); passed += 1; }
function eq(a, b, m) { assert(a === b, `${m} (várt: ${JSON.stringify(b)}, kapott: ${JSON.stringify(a)})`); }

// --- extractSpectrumPayload (holt kód, de exportált és működő) ---
assert(Array.isArray(D.extractSpectrumPayload([1, 2, 3])) && D.extractSpectrumPayload([1, 2, 3])[1] === 2, 'extract tömb -> változatlan');
eq(D.extractSpectrumPayload({ spectrum: [7] })[0], 7, 'extract .spectrum');
eq(D.extractSpectrumPayload({ samples: [9] })[0], 9, 'extract .samples fallback');
eq(D.extractSpectrumPayload({ reference: [4] })[0], 4, 'extract .reference elsőbbség');
eq(D.extractSpectrumPayload(null).length, 0, 'extract null -> []');
eq(D.extractSpectrumPayload(42).length, 0, 'extract nem-objektum -> []');

// --- peakOfArray ---
{
  const r = D.peakOfArray([NaN, 1, 5, 2], 0, 3);
  eq(r.dbm, 5, 'peak dbm a max');
  eq(r.freq, binToFreq(2), 'peak freq a max indexéből');
}
eq(D.peakOfArray(null).dbm, null, 'peak null tömb -> {null,null}');
eq(D.peakOfArray([NaN, NaN]).freq, null, 'peak csupa-NaN -> {null,null}');
{
  // start/end ablak tiszteletben tartva
  const r = D.peakOfArray([10, 1, 2, 3], 1, 3);
  eq(r.dbm, 3, 'peak ablakon belüli max (a 10-es index kihagyva)');
}

// --- generateDemoSweep (nem-determinisztikus, de szerkezet rögzíthető) ---
{
  const sweep = D.generateDemoSweep();
  eq(sweep.length, NUM_BINS, 'demo sweep hossza = NUM_BINS');
  assert(sweep.every(p => typeof p.x === 'number' && typeof p.y === 'number'), 'demo sweep {x,y} pontok');
  assert(sweep.every(p => p.y >= -110 && p.y <= -6), 'demo sweep y a [DBM_MIN, -6] tartományban (clamp)');
  eq(sweep[0].x, binToFreq(0), 'demo sweep első x = binToFreq(0)');
}

console.log(`spectrum data: PASS (${passed} assertions)`);

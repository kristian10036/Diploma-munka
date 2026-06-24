'use strict';

// Egységtesztek a python-processor/static/ui/spectrum-scale.js tiszta
// konstansaihoz és skála-/formázó-segédfüggvényeihez. ESM modul, Node 24
// require()-zel betöltve.

const S = require('../../python-processor/static/ui/spectrum-scale.js');

let passed = 0;
function assert(c, m) { if (!c) throw new Error(m); passed += 1; }
function eq(a, b, m) { assert(a === b, `${m} (várt: ${JSON.stringify(b)}, kapott: ${JSON.stringify(a)})`); }
function approx(a, b, m, eps = 1e-9) { assert(Math.abs(a - b) <= eps, `${m} (várt ~${b}, kapott ${a})`); }

// --- konstansok ---
eq(S.FULL_MIN, 0, 'FULL_MIN');
eq(S.FULL_MAX, 24000, 'FULL_MAX');
eq(S.NUM_BINS, 24576, 'NUM_BINS');
eq(S.DBM_MIN, -110, 'DBM_MIN');
eq(S.DBM_MAX, 0, 'DBM_MAX');
eq(S.MIN_SPAN, 0.05, 'MIN_SPAN');

// --- clamp ---
eq(S.clamp(5, 0, 10), 5, 'clamp belül');
eq(S.clamp(-1, 0, 10), 0, 'clamp alsó határ');
eq(S.clamp(11, 0, 10), 10, 'clamp felső határ');

// --- freqToBin / binToFreq (a teljes tartomány végpontjai) ---
eq(S.freqToBin(S.FULL_MIN), 0, 'freqToBin alsó');
eq(S.freqToBin(S.FULL_MAX), S.NUM_BINS - 1, 'freqToBin felső');
eq(S.freqToBin(-100), 0, 'freqToBin tartomány alatt -> clamp 0');
eq(S.freqToBin(999999), S.NUM_BINS - 1, 'freqToBin tartomány felett -> clamp max');
eq(S.binToFreq(0), 0, 'binToFreq alsó');
eq(S.binToFreq(S.NUM_BINS - 1), 24000, 'binToFreq felső');

// --- dbmToY / yToDbm (plot {top, height}) ---
const plotY = { top: 0, height: 100 };
eq(S.dbmToY(S.DBM_MAX, plotY), 0, 'dbmToY DBM_MAX -> top');
eq(S.dbmToY(S.DBM_MIN, plotY), 100, 'dbmToY DBM_MIN -> alja');
eq(S.dbmToY(-55, plotY), 50, 'dbmToY közép');
eq(S.yToDbm(0, plotY), 0, 'yToDbm top -> DBM_MAX');
eq(S.yToDbm(100, plotY), -110, 'yToDbm alja -> DBM_MIN');
eq(S.yToDbm(50, plotY), -55, 'yToDbm közép');

// --- fullFreqToX / fullXToFreq (plot {left, width}) ---
const plotX = { left: 0, width: 1000 };
eq(S.fullFreqToX(S.FULL_MIN, plotX), 0, 'fullFreqToX alsó');
eq(S.fullFreqToX(S.FULL_MAX, plotX), 1000, 'fullFreqToX felső');
eq(S.fullFreqToX(12000, plotX), 500, 'fullFreqToX közép');
eq(S.fullXToFreq(0, plotX), 0, 'fullXToFreq alsó');
eq(S.fullXToFreq(1000, plotX), 24000, 'fullXToFreq felső');
eq(S.fullXToFreq(500, plotX), 12000, 'fullXToFreq közép');

// --- niceStep ---
eq(S.niceStep(1), 1, 'niceStep 1');
eq(S.niceStep(1.5), 2, 'niceStep 1.5 -> 2');
eq(S.niceStep(3), 5, 'niceStep 3 -> 5');
eq(S.niceStep(7), 10, 'niceStep 7 -> 10');
eq(S.niceStep(10), 10, 'niceStep 10');
eq(S.niceStep(15), 20, 'niceStep 15 -> 20');
approx(S.niceStep(0.5), 0.5, 'niceStep 0.5');

// --- formatFreq ---
eq(S.formatFreq(NaN), '--', 'formatFreq NaN');
eq(S.formatFreq(50), '50.000 MHz', 'formatFreq < 100 -> 3 tizedes');
eq(S.formatFreq(100), '100.00 MHz', 'formatFreq >= 100 -> 2 tizedes');
eq(S.formatFreq(2400), '2.4000 GHz', 'formatFreq GHz < 10 -> 4 tizedes');
eq(S.formatFreq(12000), '12.000 GHz', 'formatFreq GHz >= 10 -> 3 tizedes');
eq(S.formatFreq(2400, 2), '2.40 GHz', 'formatFreq fixed felülírás');

// --- formatSpan ---
eq(S.formatSpan(NaN), '--', 'formatSpan NaN');
eq(S.formatSpan(0.5), '500.0 kHz', 'formatSpan < 1 -> kHz');
eq(S.formatSpan(5), '5.000 MHz', 'formatSpan MHz');
eq(S.formatSpan(2000), '2.0000 GHz', 'formatSpan GHz');

// --- fmtHz (Hz -> MHz/kHz) ---
eq(S.fmtHz(NaN), '--', 'fmtHz NaN');
eq(S.fmtHz(2_400_000_000), '2400.000000 MHz', 'fmtHz >= 1e6 -> MHz 6 tizedes');
eq(S.fmtHz(12_500), '12.500 kHz', 'fmtHz < 1e6 -> kHz 3 tizedes');

console.log(`spectrum scale: PASS (${passed} assertions)`);

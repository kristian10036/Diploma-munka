'use strict';

// Egységtesztek a python-processor/static/ui/observation-format.js tiszta
// formázó-/adatkinyerő-segédfüggvényeihez. A modul ESM (export), de Node 24
// require()-zel betölthető, így a meglévő tests/frontend/*.js fixture-stílust
// követjük.

const F = require('../../python-processor/static/ui/observation-format.js');

let passed = 0;
function assert(condition, message) {
  if (!condition) throw new Error(message);
  passed += 1;
}
function eq(actual, expected, message) {
  assert(actual === expected, `${message} (várt: ${JSON.stringify(expected)}, kapott: ${JSON.stringify(actual)})`);
}

// firstFiniteNumber: az ELSŐ véges, NEGATÍV értéket adja vissza (RSSI/jelszint
// dBm tipikusan negatív), különben null.
eq(F.firstFiniteNumber(null, '', -50), -50, 'firstFiniteNumber skip null/üres');
eq(F.firstFiniteNumber(10, -30), -30, 'firstFiniteNumber pozitívot átugor');
eq(F.firstFiniteNumber(5, 0, 3), null, 'firstFiniteNumber nincs negatív -> null');
eq(F.firstFiniteNumber('-42.5'), -42.5, 'firstFiniteNumber string parse');
eq(F.firstFiniteNumber(), null, 'firstFiniteNumber üres -> null');

// observationRawPayload
assert(F.observationRawPayload({ raw_payload: { a: 1 } }).a === 1, 'observationRawPayload objektum');
assert(F.observationRawPayload({ raw_payload: '{"b":2}' }).b === 2, 'observationRawPayload JSON string');
eq(Object.keys(F.observationRawPayload({ raw_payload: 'nem json' })).length, 0, 'observationRawPayload hibás string -> {}');
eq(Object.keys(F.observationRawPayload({})).length, 0, 'observationRawPayload hiányzó -> {}');

// rawKismetSignal
eq(F.rawKismetSignal({ device_last_signal: -60 }), -60, 'rawKismetSignal device_last_signal');
eq(F.rawKismetSignal({ 'kismet.common.signal.last_signal': -71 }), -71, 'rawKismetSignal kismet kulcs');
eq(F.rawKismetSignal({ device_last_signal: 0 }), null, 'rawKismetSignal nem-negatív -> null');

// formatRssiSummary
eq(F.formatRssiSummary(-50), '-50.0 dBm', 'formatRssiSummary egyszerű');
eq(F.formatRssiSummary(-50, -53), '-50.0 dBm · +3.0 dB', 'formatRssiSummary delta');
eq(F.formatRssiSummary(-50, -50.2), '-50.0 dBm', 'formatRssiSummary kis delta elnyelve');
eq(F.formatRssiSummary(-50, null, -60, -40, -50), '-50.0 dBm · avg -50.0 (-60..-40)', 'formatRssiSummary avg/min/max');
eq(F.formatRssiSummary(null), '--', 'formatRssiSummary nincs érték');

// formatAge (a rendszeridőhöz képest; csak a mértékegység-utótagot rögzítjük)
eq(F.formatAge(null), '--', 'formatAge null');
eq(F.formatAge('garbage'), '--', 'formatAge érvénytelen');
eq(F.formatAge(new Date(Date.now() - 3 * 3600 * 1000).toISOString()), '3h', 'formatAge 3 óra');
assert(F.formatAge(new Date(Date.now() - 5000).toISOString()).endsWith('s'), 'formatAge másodperc utótag');

// formatRiskSummary
eq(F.formatRiskSummary('high', 'foo'), 'high: foo', 'formatRiskSummary szinttel és összefoglalóval');
eq(F.formatRiskSummary('high'), 'high', 'formatRiskSummary csak szint');
eq(F.formatRiskSummary(null), '--', 'formatRiskSummary unknown -> --');
eq(F.formatRiskSummary('unknown', 'x'), '--: x', 'formatRiskSummary unknown label összefoglalóval');

// formatManagementSummary
eq(F.formatManagementSummary(null), '--', 'formatManagementSummary null');
eq(F.formatManagementSummary('szöveg'), 'szöveg', 'formatManagementSummary string');
eq(F.formatManagementSummary({ deauth: 2, assoc: 0 }), 'deauth: 2', 'formatManagementSummary csak pozitív');
eq(F.formatManagementSummary({}), '--', 'formatManagementSummary üres objektum');

// formatServiceSummary
eq(F.formatServiceSummary(['a', 'b']), 'a, b', 'formatServiceSummary tömb');
eq(F.formatServiceSummary(['a', 'b', 'c', 'd', 'e']), 'a, b, c, d +1', 'formatServiceSummary csonkolás');
eq(F.formatServiceSummary('["x","y"]'), 'x, y', 'formatServiceSummary JSON string');
eq(F.formatServiceSummary('p, q'), 'p, q', 'formatServiceSummary vesszős string');
eq(F.formatServiceSummary([]), '--', 'formatServiceSummary üres');

// formatExactTime (locale-függő; csak a -- / nem-- ágat rögzítjük)
eq(F.formatExactTime(null), '--', 'formatExactTime null');
eq(F.formatExactTime('garbage'), '--', 'formatExactTime érvénytelen');
assert(typeof F.formatExactTime('2026-01-01T12:00:00Z') === 'string' && F.formatExactTime('2026-01-01T12:00:00Z') !== '--', 'formatExactTime érvényes');

// formatReferenceStatus
eq(F.formatReferenceStatus({ reference_status: 'in_reference' }), '✓', 'formatReferenceStatus in_reference');
eq(F.formatReferenceStatus({ reference_status: 'in_reference', has_differences: true }), '✓ ⚠', 'formatReferenceStatus eltéréssel');
eq(F.formatReferenceStatus({ reference_status: 'new' }), '＋', 'formatReferenceStatus new');
eq(F.formatReferenceStatus({ reference_status: 'not_compared' }), '—', 'formatReferenceStatus not_compared');
eq(F.formatReferenceStatus({ reference_status: 'ismeretlen' }), '—', 'formatReferenceStatus ismeretlen -> —');

// referenceRowClass
eq(F.referenceRowClass({ reference_status: 'new' }), ' class="row-baseline-new"', 'referenceRowClass new');
eq(F.referenceRowClass({ reference_status: 'in_reference', has_differences: true }), ' class="row-baseline-changed"', 'referenceRowClass changed');
eq(F.referenceRowClass({ reference_status: 'in_reference' }), '', 'referenceRowClass in_reference üres');
eq(F.referenceRowClass({ reference_status: 'not_compared' }), '', 'referenceRowClass not_compared üres');

// formatUnknownStatus (holt kód, de exportált és működő)
eq(F.formatUnknownStatus('unknown'), '--', 'formatUnknownStatus unknown');
eq(F.formatUnknownStatus(null), '--', 'formatUnknownStatus null');
eq(F.formatUnknownStatus('active'), 'active', 'formatUnknownStatus konkrét érték');

console.log(`observation format helpers: PASS (${passed} assertions)`);

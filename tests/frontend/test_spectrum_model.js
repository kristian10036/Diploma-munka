'use strict';

const Adapter = require('../../python-processor/static/spectrum-frame-adapter.js');
const ViewModel = require('../../python-processor/static/spectrum-view-model.js');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function makeFrame(count = 100, step = 1000) {
  return {
    schema_version: 1,
    sensor_id: 'fixture',
    source_type: 'mock',
    source_device: 'generator',
    device_model: 'generator',
    measurement_mode: 'spectrum',
    session_id: 'session',
    timestamp: new Date().toISOString(),
    sequence: 7,
    start_frequency_hz: 100000000,
    stop_frequency_hz: 100000000 + step * (count - 1),
    step_frequency_hz: step,
    center_frequency_hz: 100000000 + step * Math.floor((count - 1) / 2),
    sample_rate_hz: 1000000,
    rbw_hz: step,
    num_points: count,
    point_count: count,
    power_unit: 'dBm',
    powers_dbm: Array.from({ length: count }, (_, index) => -100 + index / count),
    flags: { overflow: false, dropped: false, inaccurate: false },
    metadata: { is_simulated: true },
  };
}

const hundred = Adapter.parseSpectrumFrame(makeFrame());
assert(hundred.numPoints === 100 && hundred.frequenciesHz[1] === 100001000, '100-point SpectrumFrame');
const large = Adapter.parseSpectrumFrame(makeFrame(65536, 10));
const wideFixture = makeFrame(3, 8997500000);
wideFixture.start_frequency_hz = 5000000;
wideFixture.stop_frequency_hz = 18000000000;
wideFixture.center_frequency_hz = 9002500000;
wideFixture.sample_rate_hz = 17995000000;
const wide = Adapter.parseSpectrumFrame(wideFixture);
assert(wide.startFrequencyHz === 5000000 && wide.stopFrequencyHz === 18000000000, 'hardware-wide frequency range');
assert(Number.isNaN(ViewModel.sampleNearest(wide, 1000000)), 'no sample below SDR measurement range');
assert(Number.isNaN(ViewModel.sampleNearest(wide, 19000000000)), 'no sample above SDR measurement range');
assert(Number.isFinite(ViewModel.sampleNearest(wide, 5000000)), 'sample inside SDR measurement range');

large.powersDbm[32768] = -5;
const envelope = ViewModel.minMaxEnvelope(large, large.startFrequencyHz, large.stopFrequencyHz, 320);
assert(envelope.some((point) => point.powerDbm === -5), 'peak-preserving envelope');
const partial = Adapter.parseSpectrumFrame([{ x: 2400, y: -90 }, { x: 2401, y: -40 }]);
assert(partial.startFrequencyHz === 2400000000 && partial.stopFrequencyHz === 2401000000, 'partial Hz range');
const tracker = Adapter.createSequenceTracker();
tracker.observe(hundred);
const gapFrame = makeFrame();
gapFrame.sequence = 10;
assert(tracker.observe(Adapter.parseSpectrumFrame(gapFrame)).gap === 2, 'sequence gap');
let rejected = 0;
const badCount = makeFrame();
badCount.num_points = 99;
for (const bad of [
  badCount,
  Object.assign(makeFrame(), { stop_frequency_hz: 1 }),
  Object.assign(makeFrame(), { powers_dbm: [NaN] }),
  Object.assign(makeFrame(), { powers_dbm: [Infinity] }),
]) {
  try { Adapter.parseSpectrumFrame(bad); } catch (_) { rejected += 1; }
}
assert(rejected === 4, 'invalid frames rejected');
const legacy = Adapter.parseSpectrumFrame([-90, -80], { legacyStartFrequencyHz: 10, legacyStopFrequencyHz: 20 });
assert(legacy.format === 'legacy-numbers' && legacy.frequenciesHz[1] === 20, 'legacy numeric compatibility');
const overview = new ViewModel.OverviewAccumulator({ minFrequencyHz: 1, maxFrequencyHz: 1000, bucketCount: 100, staleAfterMs: 100 });
overview.update(legacy, 1000);
const bucket = overview.bucketFor(20);
assert(overview.at(bucket, 1050).valid && !overview.at(bucket, 1050).stale && overview.at(bucket, 1200).stale, 'overview validity/stale');
assert(Adapter.isStale(Object.assign({}, hundred, { timestamp: '2026-01-01T00:00:00Z' }), Date.parse('2026-01-01T00:00:11Z'), 10000), 'stale state');
console.log('spectrum frame/view model: PASS');

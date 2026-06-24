'use strict';

const Adapter = require('../../python-processor/static/spectrum-frame-adapter.js');
const MaxHold = require('../../python-processor/static/maxhold-controller.js');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function makeFrame(powersDbm, {
  startFrequencyHz = 100000000,
  stepFrequencyHz = 1000,
  sourceType = 'aaronia',
  sourceDevice = 'SPECTRAN V6',
  sessionId = 'session-1',
  rbwHz = 1000,
  sequence = 1,
} = {}) {
  const count = powersDbm.length;
  return Adapter.parseSpectrumFrame({
    schema_version: 1,
    sensor_id: 'fixture',
    source_type: sourceType,
    source_device: sourceDevice,
    device_model: 'SPECTRAN V6',
    measurement_mode: 'spectrum',
    session_id: sessionId,
    timestamp: new Date('2026-06-23T00:00:00Z').toISOString(),
    sequence,
    start_frequency_hz: startFrequencyHz,
    stop_frequency_hz: startFrequencyHz + stepFrequencyHz * (count - 1),
    step_frequency_hz: stepFrequencyHz,
    center_frequency_hz: startFrequencyHz + stepFrequencyHz * Math.floor((count - 1) / 2),
    sample_rate_hz: stepFrequencyHz * count,
    rbw_hz: rbwHz,
    num_points: count,
    point_count: count,
    power_unit: 'dBm',
    powers_dbm: powersDbm,
    flags: { overflow: false, dropped: false, inaccurate: false },
    metadata: { is_simulated: false },
  });
}

function toArray(values) {
  return Array.from(values, (value) => Number(value));
}

const state = MaxHold.createState();
const frame1 = makeFrame([-100, -90, -80, -95]);
const frame2 = makeFrame([-98, -92, -70, -96]);
const frame3 = makeFrame([-120, -120, -120, -120]);

const init = MaxHold.updateFromFrame(state, frame1);
assert(init.reset && state.initialized, 'initial frame initializes maxhold');
assert(JSON.stringify(toArray(state.powersDbm)) === JSON.stringify([-100, -90, -80, -95]), 'single frame stored exactly');

const peak1 = MaxHold.peakInRange(state, frame1.startFrequencyHz, frame1.stopFrequencyHz);
assert(peak1.frequencyHz === frame1.frequenciesHz[2] && peak1.powerDbm === -80, 'peak follows native bin');

const update = MaxHold.updateFromFrame(state, frame2);
assert(update.updated && !update.reset, 'same grid updates without reset');
assert(JSON.stringify(toArray(state.powersDbm)) === JSON.stringify([-98, -90, -70, -95]), 'pointwise max applied');

const beforeLower = toArray(state.powersDbm);
MaxHold.updateFromFrame(state, frame3);
assert(JSON.stringify(toArray(state.powersDbm)) === JSON.stringify(beforeLower), 'maxhold never decreases without reset');

const sig1 = MaxHold.signatureFor(frame1);
const sig2 = { ...sig1, startFrequencyHz: sig1.startFrequencyHz + 0.25 };
assert(MaxHold.sameSignature(sig1, sig2), 'tiny floating-point differences stay on same grid');

const shifted = makeFrame([-50, -60, -70, -80], { startFrequencyHz: 200000000, sequence: 2 });
const shiftedUpdate = MaxHold.updateFromFrame(state, shifted);
assert(shiftedUpdate.reset && shiftedUpdate.reason === 'grid_changed', 'start-frequency change resets safely');
assert(JSON.stringify(toArray(state.powersDbm)) === JSON.stringify([-50, -60, -70, -80]), 'reset does not mix old bins by index');

const resized = makeFrame([-40, -35, -30, -25, -20], { startFrequencyHz: 300000000, stepFrequencyHz: 2000, sequence: 3, rbwHz: 2000 });
const resizedUpdate = MaxHold.updateFromFrame(state, resized);
assert(resizedUpdate.reset && state.powersDbm.length === 5, 'point-count and step changes reset without length errors');
assert(state.frequenciesHz.length === 5, 'frequency grid resets to current frame');

const resizedPeak = MaxHold.peakInRange(state, resized.startFrequencyHz, resized.stopFrequencyHz);
assert(resizedPeak.frequencyHz === resized.frequenciesHz[4] && resizedPeak.powerDbm === -20, 'peak follows resized native grid');

assert(MaxHold.signatureFor({}) === null, 'invalid frame signatures are rejected');
assert(JSON.stringify(toArray(frame1.powersDbm)) === JSON.stringify([-100, -90, -80, -95]), 'input frame data is not mutated');

console.log('maxhold controller: PASS');

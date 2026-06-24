(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.MaxHoldController = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const DEFAULT_TOLERANCE_HZ = 1;
  const DEFAULT_RELATIVE_TOLERANCE = 1e-9;

  function nearlyEqual(a, b, toleranceHz = DEFAULT_TOLERANCE_HZ, relativeTolerance = DEFAULT_RELATIVE_TOLERANCE) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
    const absolute = Math.abs(a - b);
    const relative = Math.max(Math.abs(a), Math.abs(b)) * relativeTolerance;
    return absolute <= Math.max(toleranceHz, relative);
  }

  function signatureFor(frame) {
    const hasFrequencies = Array.isArray(frame?.frequenciesHz) || ArrayBuffer.isView(frame?.frequenciesHz);
    const hasPowers = Array.isArray(frame?.powersDbm) || ArrayBuffer.isView(frame?.powersDbm);
    if (!frame || !hasFrequencies || !hasPowers) return null;
    return {
      sourceType: frame.sourceType ?? null,
      sourceDevice: frame.sourceDevice ?? null,
      sessionId: frame.sessionId ?? null,
      numPoints: Number.isInteger(frame.numPoints) ? frame.numPoints : frame.powersDbm.length,
      startFrequencyHz: frame.startFrequencyHz ?? null,
      stopFrequencyHz: frame.stopFrequencyHz ?? null,
      stepFrequencyHz: frame.stepFrequencyHz ?? null,
      rbwHz: frame.rbwHz ?? null,
    };
  }

  function sameSignature(previous, next, toleranceHz = DEFAULT_TOLERANCE_HZ, relativeTolerance = DEFAULT_RELATIVE_TOLERANCE) {
    if (!previous || !next) return false;
    if (previous.sourceType !== next.sourceType) return false;
    if (previous.sourceDevice !== next.sourceDevice) return false;
    if (previous.sessionId !== next.sessionId) return false;
    if (previous.numPoints !== next.numPoints) return false;
    if (!nearlyEqual(previous.startFrequencyHz, next.startFrequencyHz, toleranceHz, relativeTolerance)) return false;
    if (!nearlyEqual(previous.stopFrequencyHz, next.stopFrequencyHz, toleranceHz, relativeTolerance)) return false;
    if (!nearlyEqual(previous.stepFrequencyHz, next.stepFrequencyHz, toleranceHz, relativeTolerance)) return false;
    if (!nearlyEqual(previous.rbwHz, next.rbwHz, toleranceHz, relativeTolerance)) return false;
    return true;
  }

  function createState() {
    return {
      signature: null,
      frequenciesHz: null,
      powersDbm: null,
      initialized: false,
    };
  }

  function resetFromFrame(state, frame) {
    const nextSignature = signatureFor(frame);
    if (!nextSignature) {
      state.signature = null;
      state.frequenciesHz = null;
      state.powersDbm = null;
      state.initialized = false;
      return { reset: true, reason: 'no_frame' };
    }
    state.signature = nextSignature;
    state.frequenciesHz = Float64Array.from(frame.frequenciesHz);
    state.powersDbm = Float32Array.from(frame.powersDbm);
    state.initialized = true;
    return { reset: true, reason: 'initialized' };
  }

  function updateFromFrame(state, frame) {
    const nextSignature = signatureFor(frame);
    if (!nextSignature) return { reset: false, updated: false, reason: 'no_frame' };
    if (!state.initialized || !sameSignature(state.signature, nextSignature)) {
      const result = resetFromFrame(state, frame);
      if (result.reason === 'initialized' && state.signature) result.reason = 'grid_changed';
      return result;
    }
    const count = Math.min(state.powersDbm.length, frame.powersDbm.length);
    for (let index = 0; index < count; index += 1) {
      const current = frame.powersDbm[index];
      if (Number.isFinite(current)) state.powersDbm[index] = Math.max(state.powersDbm[index], current);
    }
    return { reset: false, updated: true, reason: 'updated' };
  }

  function peakInRange(state, startHz, endHz) {
    if (!state.initialized || !state.frequenciesHz || !state.powersDbm) {
      return { frequencyHz: null, powerDbm: null };
    }
    let bestPower = -Infinity;
    let bestIndex = -1;
    const frequenciesHz = state.frequenciesHz;
    const powersDbm = state.powersDbm;
    for (let index = 0; index < frequenciesHz.length && index < powersDbm.length; index += 1) {
      const frequencyHz = frequenciesHz[index];
      if (frequencyHz < startHz || frequencyHz > endHz) continue;
      const powerDbm = powersDbm[index];
      if (Number.isFinite(powerDbm) && powerDbm > bestPower) {
        bestPower = powerDbm;
        bestIndex = index;
      }
    }
    return bestIndex >= 0
      ? { frequencyHz: frequenciesHz[bestIndex], powerDbm: bestPower }
      : { frequencyHz: null, powerDbm: null };
  }

  return {
    createState,
    resetFromFrame,
    updateFromFrame,
    peakInRange,
    sameSignature,
    signatureFor,
  };
});

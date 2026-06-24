(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ViewportController = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const STATES = Object.freeze({
    IDLE: 'idle',
    PENDING: 'pending',
    RETUNING: 'retuning',
    WAITING_FOR_MATCHING_FRAME: 'waiting_for_matching_frame',
    STREAMING: 'streaming',
    ERROR: 'error',
  });

  const finitePositive = value => Number.isFinite(value) && value > 0;
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

  function defaultRequestId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    return `viewport-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function normalizeViewport(viewport) {
    if (!viewport || !finitePositive(viewport.centerFrequencyHz) || !finitePositive(viewport.spanHz)) {
      throw new TypeError('invalid viewport');
    }
    return {
      centerFrequencyHz: Math.round(viewport.centerFrequencyHz),
      spanHz: Math.round(viewport.spanHz),
      mode: viewport.mode === 'fixed' ? 'fixed' : 'sweep',
    };
  }

  class Controller {
    constructor(options = {}) {
      if (typeof options.sendRequest !== 'function') throw new TypeError('sendRequest is required');
      this.sendRequest = options.sendRequest;
      this.onStateChange = options.onStateChange || (() => {});
      this.onAccepted = options.onAccepted || (() => {});
      this.onMatchingFrame = options.onMatchingFrame || (() => {});
      this.scheduler = options.scheduler || {setTimeout, clearTimeout};
      this.now = options.now || (() => Date.now());
      this.requestId = options.requestId || defaultRequestId;
      this.debounceMs = clamp(Number(options.debounceMs) || 450, 400, 500);
      this.minimumPoints = Math.max(2, Math.round(Number(options.minimumPoints) || 2048));
      this.pointsPerPixel = clamp(Number(options.pointsPerPixel) || 4, 1, 8);
      this.centerThresholdRatio = finitePositive(options.centerThresholdRatio)
        ? options.centerThresholdRatio : 0.0005;
      this.spanThresholdRatio = finitePositive(options.spanThresholdRatio)
        ? options.spanThresholdRatio : 0.001;
      this.absoluteThresholdHz = finitePositive(options.absoluteThresholdHz)
        ? options.absoluteThresholdHz : 1;
      this.frameToleranceRatio = finitePositive(options.frameToleranceRatio)
        ? options.frameToleranceRatio : 0.01;
      this.state = STATES.IDLE;
      this.capabilities = null;
      this.canvasPhysicalWidth = 0;
      this.interacting = false;
      this.timer = null;
      this.pendingViewport = null;
      this.queuedViewport = null;
      this.inFlight = null;
      this.waiting = null;
      this.lastRequested = null;
      this.lastFrame = null;
      this.generation = 0;
    }

    setCapabilities(capabilities) {
      this.capabilities = capabilities || null;
      if (!this.supportsViewport()) this.cancelPending();
    }

    setCanvasPhysicalWidth(width) {
      if (finitePositive(width)) this.canvasPhysicalWidth = width;
    }

    supportsViewport() {
      return this.capabilities?.viewport_control === true
        && finitePositive(Number(this.capabilities.maximum_spectrum_points));
    }

    beginInteraction() {
      this.interacting = true;
      if (this.timer !== null) {
        this.scheduler.clearTimeout(this.timer);
        this.timer = null;
      }
    }

    endInteraction(viewport) {
      this.interacting = false;
      if (viewport) this.pendingViewport = normalizeViewport(viewport);
      if (this.pendingViewport) this.schedule(this.pendingViewport);
    }

    schedule(viewport) {
      const normalized = normalizeViewport(viewport);
      this.pendingViewport = normalized;
      if (!this.supportsViewport()) return false;
      if (this.interacting) return false;
      if (this.inFlight) {
        this.queuedViewport = normalized;
        return false;
      }
      if (this._equivalent(normalized, this.lastRequested)) return false;
      if (this.timer !== null) this.scheduler.clearTimeout(this.timer);
      this._setState(STATES.PENDING, {viewport: normalized});
      this.timer = this.scheduler.setTimeout(() => {
        this.timer = null;
        this._dispatch(normalized);
      }, this.debounceMs);
      return true;
    }

    cancelPending() {
      if (this.timer !== null) this.scheduler.clearTimeout(this.timer);
      this.timer = null;
      this.pendingViewport = null;
      this.queuedViewport = null;
      if (!this.inFlight && !this.waiting) this._setState(STATES.IDLE);
    }

    targetPoints() {
      const maximum = Math.max(2, Math.round(Number(this.capabilities?.maximum_spectrum_points) || 2));
      const visualTarget = Math.ceil(this.canvasPhysicalWidth * this.pointsPerPixel);
      return Math.round(clamp(Math.max(this.minimumPoints, visualTarget), 2, maximum));
    }

    observeFrame(frame, activeSourceType) {
      if (frame) this.lastFrame = frame;
      if (!this.waiting || !frame) return false;
      const request = this.waiting;
      const sourceType = frame.sourceType ?? frame.source_type;
      if (activeSourceType && sourceType !== activeSourceType) return false;
      if (request.sourceType && sourceType !== request.sourceType) return false;
      const timestamp = Date.parse(frame.timestamp);
      if (!Number.isFinite(timestamp) || timestamp <= request.requestedAtMs) return false;
      const sessionId = frame.sessionId ?? frame.session_id ?? null;
      const sequence = frame.sequence ?? null;
      if (sessionId === request.previousSessionId && sequence === request.previousSequence) return false;
      const start = Number(frame.startFrequencyHz ?? frame.start_frequency_hz);
      const stop = Number(frame.stopFrequencyHz ?? frame.stop_frequency_hz);
      const requestedStart = request.centerFrequencyHz - request.spanHz / 2;
      const requestedStop = request.centerFrequencyHz + request.spanHz / 2;
      const tolerance = Math.max(this.absoluteThresholdHz, request.spanHz * this.frameToleranceRatio);
      if (!Number.isFinite(start) || !Number.isFinite(stop)
          || start > requestedStart + tolerance || stop < requestedStop - tolerance) return false;
      this.waiting = null;
      this._setState(STATES.STREAMING, {request, frame});
      this.onMatchingFrame({request, frame});
      return true;
    }

    _equivalent(left, right) {
      if (!left || !right) return false;
      const referenceSpan = Math.max(left.spanHz, right.spanHz);
      const centerThreshold = Math.max(this.absoluteThresholdHz, referenceSpan * this.centerThresholdRatio);
      const spanThreshold = Math.max(this.absoluteThresholdHz, referenceSpan * this.spanThresholdRatio);
      return Math.abs(left.centerFrequencyHz - right.centerFrequencyHz) < centerThreshold
        && Math.abs(left.spanHz - right.spanHz) < spanThreshold;
    }

    _dispatch(viewport) {
      if (!this.supportsViewport() || this.interacting || this.inFlight
          || this._equivalent(viewport, this.lastRequested)) return;
      const maximumPoints = this.targetPoints();
      const requestedAtMs = this.now();
      const request = {
        request_id: this.requestId(),
        mode: viewport.mode,
        center_frequency_hz: viewport.centerFrequencyHz,
        span_hz: viewport.spanHz,
        maximum_points: maximumPoints,
        desired_rbw_hz: viewport.spanHz / maximumPoints,
      };
      const context = {
        generation: ++this.generation,
        requestedAtMs,
        centerFrequencyHz: viewport.centerFrequencyHz,
        spanHz: viewport.spanHz,
        sourceType: this.lastFrame?.sourceType ?? this.lastFrame?.source_type ?? null,
        previousSessionId: this.lastFrame?.sessionId ?? this.lastFrame?.session_id ?? null,
        previousSequence: this.lastFrame?.sequence ?? null,
        request,
      };
      this.lastRequested = viewport;
      this.inFlight = context;
      this._setState(STATES.RETUNING, context);
      Promise.resolve(this.sendRequest(request)).then(
        response => this._settleRequest(context, null, response),
        error => this._settleRequest(context, error, null),
      );
    }

    _settleRequest(context, error, response) {
      if (this.inFlight !== context) return;
      this.inFlight = null;
      const superseded = this.queuedViewport && !this._equivalent(this.queuedViewport, this.lastRequested);
      if (superseded) {
        const queued = this.queuedViewport;
        this.queuedViewport = null;
        this.schedule(queued);
        return;
      }
      this.queuedViewport = null;
      if (error) {
        this._setState(STATES.ERROR, {request: context, error});
        return;
      }
      this.waiting = context;
      this._setState(STATES.WAITING_FOR_MATCHING_FRAME, {request: context, response});
      this.onAccepted({request: context, response});
    }

    _setState(state, detail = null) {
      this.state = state;
      this.onStateChange({state, detail});
    }
  }

  return {Controller, STATES, normalizeViewport};
});

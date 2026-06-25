/*
 * demod-passband.js
 * -----------------------------------------------------------------------------
 * Forrásfüggetlen, DOM-mentes demodulációs passband logika. A Spectrum Monitor
 * és a Moduláció panel közös, egyetlen igazságforrásból (demodState) dolgozik.
 *
 * Ez a modul szándékosan tiszta (no canvas, no fetch, no document): a teljes
 * geometria-, snap-, hitbox-, hangolásterv- és debounce/sequence logika itt él,
 * így Node alatt önállóan unit-tesztelhető. Az index.html csak a rajzolást és az
 * egéreseményeket köti rá.
 *
 * Fontos műszaki határ: a SpectrumFrame egy teljesítményspektrum, amelyből
 * önmagában nem demodulálható hang. A passband a demodulációt VEZÉRLI, a hangot
 * egy IQ-képes adatút (SDRangel Rx DeviceSet / USRP / HackRF / SoapySDR) állítja
 * elő. A modul ezt a szétválasztást nem mossa össze.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.DemodPassband = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // SDRangel demodulátoronkénti alapértelmezett szűrő-sávszélességek (Hz).
  const DEFAULT_BANDWIDTHS = Object.freeze({
    AM: 10000, NFM: 12500, WFM: 75000, BFM: 180000,
    USB: 2700, LSB: 2700, DSB: 6000, CW: 500,
    DSD: 12500, FREEDV: 3000, M17: 12500, DAB: 1536000,
  });

  // Szimmetrikus sávú módok: start = f - bw/2, stop = f + bw/2.
  const SYMMETRIC_MODES = Object.freeze(new Set([
    'AM', 'NFM', 'WFM', 'BFM', 'DSB', 'DSD', 'M17', 'DAB', 'FREEDV', 'CW',
  ]));

  // Globális, UI-szintű biztonsági korlátok (a capability felülírhatja).
  const ABSOLUTE_MIN_BANDWIDTH_HZ = 100;
  const ABSOLUTE_MAX_BANDWIDTH_HZ = 500_000_000;

  function normalizeMode(mode) {
    return String(mode || '').trim().toUpperCase();
  }

  function defaultBandwidthFor(mode) {
    const value = DEFAULT_BANDWIDTHS[normalizeMode(mode)];
    return Number.isFinite(value) ? value : 12500;
  }

  function isSingleSideband(mode) {
    const m = normalizeMode(mode);
    return m === 'USB' || m === 'LSB';
  }

  /**
   * A passband geometria a tényleges SDRangel szűrőviselkedést tükrözi.
   *  - USB:  jobbra egyoldalas  (start = f,        stop = f + bw)
   *  - LSB:  balra egyoldalas   (start = f - bw,   stop = f)
   *  - CW:   keskeny, középre igazított (szimmetrikus)
   *  - többi: szimmetrikus      (start = f - bw/2, stop = f + bw/2)
   * @returns {{startHz:number, stopHz:number, centerHz:number}|null}
   */
  function computePassbandEdges(mode, frequencyHz, bandwidthHz) {
    if (!Number.isFinite(frequencyHz) || !Number.isFinite(bandwidthHz) || bandwidthHz <= 0) {
      return null;
    }
    const m = normalizeMode(mode);
    if (m === 'USB') {
      return { startHz: frequencyHz, stopHz: frequencyHz + bandwidthHz, centerHz: frequencyHz };
    }
    if (m === 'LSB') {
      return { startHz: frequencyHz - bandwidthHz, stopHz: frequencyHz, centerHz: frequencyHz };
    }
    const half = bandwidthHz / 2;
    return { startHz: frequencyHz - half, stopHz: frequencyHz + half, centerHz: frequencyHz };
  }

  /**
   * Egy él (start/stop) mozgatásából visszaszámolja a sávszélességet, a mód
   * geometriáját tiszteletben tartva. A középfrekvencia rögzített marad.
   * @param {'left'|'right'} edge melyik fogantyú mozdult
   * @returns {number} az új bandwidth Hz-ben (még nem clamp-elve)
   */
  function bandwidthFromEdge(mode, frequencyHz, edge, edgeFrequencyHz) {
    const m = normalizeMode(mode);
    if (m === 'USB') {
      // start rögzített a centeren; csak a jobb él mozog.
      return Math.abs(edgeFrequencyHz - frequencyHz);
    }
    if (m === 'LSB') {
      // stop rögzített a centeren; csak a bal él mozog.
      return Math.abs(frequencyHz - edgeFrequencyHz);
    }
    // Szimmetrikus: bármelyik él fél-sávszélességet definiál.
    return 2 * Math.abs(edgeFrequencyHz - frequencyHz);
  }

  /**
   * A frekvenciát a SpectrumFrame natív frekvenciarácsára igazítja.
   * A frame mezői: startFrequencyHz, stepFrequencyHz, numPoints.
   */
  function snapFrequencyToSpectrumBin(frequencyHz, frame) {
    if (
      !frame ||
      !Number.isFinite(frame.startFrequencyHz) ||
      !Number.isFinite(frame.stepFrequencyHz) ||
      frame.stepFrequencyHz <= 0
    ) {
      return frequencyHz;
    }
    const index = Math.round((frequencyHz - frame.startFrequencyHz) / frame.stepFrequencyHz);
    return frame.startFrequencyHz + index * frame.stepFrequencyHz;
  }

  /**
   * Igaz, ha a spektrumfelbontás túl durva a kívánt sávhoz (a teljes sávot
   * kevesebb mint ~4 bin fedné). Ez NEM blokkolja a demodulációt, mert az
   * IQ-adatút felbontása eltérhet a spektrumétól; csak UI-jelzés.
   */
  function isResolutionTooCoarse(bandwidthHz, frame, minBins = 4) {
    if (!frame || !Number.isFinite(frame.stepFrequencyHz) || frame.stepFrequencyHz <= 0) return false;
    if (!Number.isFinite(bandwidthHz) || bandwidthHz <= 0) return false;
    return bandwidthHz / frame.stepFrequencyHz < minBins;
  }

  /**
   * Capability-alapú sávszélesség-korlátozás. A frontend korlát nem
   * helyettesíti a backend validációt, csak a kézi bevitelt fogja meg.
   * @returns {{value:number, clamped:boolean, reason:string|null}}
   */
  function clampBandwidth(bandwidthHz, capability = {}) {
    const min = Number.isFinite(capability.minHz) ? capability.minHz : ABSOLUTE_MIN_BANDWIDTH_HZ;
    let max = Number.isFinite(capability.maxHz) ? capability.maxHz : ABSOLUTE_MAX_BANDWIDTH_HZ;
    if (Number.isFinite(capability.captureBandwidthHz) && capability.captureBandwidthHz > 0) {
      max = Math.min(max, capability.captureBandwidthHz);
    }
    if (!Number.isFinite(bandwidthHz) || bandwidthHz <= 0) {
      return { value: min, clamped: true, reason: 'invalid' };
    }
    if (bandwidthHz < min) return { value: min, clamped: true, reason: 'below_min' };
    if (bandwidthHz > max) return { value: max, clamped: true, reason: 'above_max' };
    return { value: bandwidthHz, clamped: false, reason: null };
  }

  /**
   * Passband geometria képernyő-X koordinátákban.
   * @param {function(number):number} freqHzToX  Hz -> canvas X
   */
  function computePixelGeometry(state, freqHzToX) {
    const edges = computePassbandEdges(state.mode, state.frequencyHz, state.bandwidthHz);
    if (!edges) return null;
    const leftX = freqHzToX(edges.startHz);
    const rightX = freqHzToX(edges.stopHz);
    const centerX = freqHzToX(edges.centerHz);
    return {
      ...edges,
      leftX: Math.min(leftX, rightX),
      rightX: Math.max(leftX, rightX),
      centerX,
      widthPx: Math.abs(rightX - leftX),
    };
  }

  /**
   * Hitbox-prioritás: bal fogantyú > jobb fogantyú > középvonal > sáv belseje.
   * A fogantyúk minimum kezelhető mérete handlePx (8-12 px), keskeny sávnál is.
   * @returns {'leftHandle'|'rightHandle'|'centerLine'|'body'|null}
   */
  function hitTestPassband(pixelGeometry, x, handlePx = 10) {
    if (!pixelGeometry) return null;
    const half = Math.max(4, handlePx) / 2;
    const { leftX, rightX, centerX } = pixelGeometry;
    if (Math.abs(x - leftX) <= half) return 'leftHandle';
    if (Math.abs(x - rightX) <= half) return 'rightHandle';
    if (Math.abs(x - centerX) <= half) return 'centerLine';
    if (x > leftX + half && x < rightX - half) return 'body';
    if (x >= leftX && x <= rightX) return 'body';
    return null;
  }

  /**
   * Eldönti, hogy a kiválasztott frekvenciához elég-e a demodulátor channel
   * offset módosítása, vagy a teljes DeviceSet áthangolása kell.
   *  - frekvencia a capture tartományon belül -> csak inputFrequencyOffset
   *  - kívül                                  -> retune + offset 0
   *  - bizonytalan capture                    -> konzervatív fallback (retune)
   * @returns {{action:'offset'|'retune', offsetHz:number, retuneToHz:number|null,
   *            conservative:boolean}}
   */
  function planChannelTuning(frequencyHz, deviceCenterHz, captureBandwidthHz) {
    const haveCenter = Number.isFinite(deviceCenterHz);
    const haveCapture = Number.isFinite(captureBandwidthHz) && captureBandwidthHz > 0;
    if (!haveCenter || !haveCapture) {
      return { action: 'retune', offsetHz: 0, retuneToHz: frequencyHz, conservative: true };
    }
    const halfSpan = captureBandwidthHz / 2;
    const offset = frequencyHz - deviceCenterHz;
    if (Math.abs(offset) <= halfSpan) {
      return { action: 'offset', offsetHz: Math.round(offset), retuneToHz: null, conservative: false };
    }
    return { action: 'retune', offsetHz: 0, retuneToHz: frequencyHz, conservative: false };
  }

  /**
   * Közös demodulációs állapot (egyetlen igazságforrás). A passband és a panel
   * is ebből dolgozik. requested* a felhasználói szándék, applied* az SDRangel
   * által visszaigazolt érték.
   */
  function createDemodState(overrides = {}) {
    return Object.assign({
      enabled: false,
      active: false,

      frequencyHz: null,
      bandwidthHz: 12500,
      mode: 'NFM',
      squelchDb: -60,
      volume: 1.0,

      deviceSetIndex: 0,
      channelIndex: null,

      deviceCenterFrequencyHz: null,
      inputFrequencyOffsetHz: 0,
      captureBandwidthHz: null,

      requestedFrequencyHz: null,
      appliedFrequencyHz: null,
      requestedBandwidthHz: 12500,
      appliedBandwidthHz: null,

      pendingUpdate: false,
      lastError: null,
    }, overrides);
  }

  /**
   * Debounce + monoton sequence az aktív demodulátor PATCH-frissítéséhez.
   * A vizuális sáv minden mozdulatnál frissül (a hívó dolga), de a hálózati
   * update csak debounce után fut, és a régi (késve érkező) válasz nem írja
   * felül az újabb állapotot.
   *
   * @param {object} opts
   * @param {{setTimeout:Function, clearTimeout:Function}} opts.scheduler
   * @param {number} opts.debounceMs  ~100-200 ms
   * @param {function(object, number):Promise} opts.send  payload, seq -> Promise
   * @param {function=} opts.onApplied  (result, payload, seq)
   * @param {function=} opts.onError    (error, payload, seq)
   */
  function createUpdateScheduler(opts) {
    const scheduler = opts.scheduler;
    const debounceMs = Number.isFinite(opts.debounceMs) ? opts.debounceMs : 150;
    const send = opts.send;
    const onApplied = opts.onApplied || (() => {});
    const onError = opts.onError || (() => {});

    let timer = null;
    let dispatchSeq = 0;   // utoljára kiküldött kérés sorszáma
    let appliedSeq = 0;    // utoljára alkalmazott (legfrissebb) válasz sorszáma
    let pendingPayload = null;
    let inFlight = 0;      // épp úton lévő kérések száma

    function schedule(payload) {
      pendingPayload = payload;
      if (timer !== null) scheduler.clearTimeout(timer);
      timer = scheduler.setTimeout(flush, debounceMs);
    }

    async function flush() {
      timer = null;
      if (pendingPayload === null) return undefined;
      const seq = ++dispatchSeq;
      const payload = pendingPayload;
      pendingPayload = null;
      inFlight += 1;
      try {
        const result = await send(payload, seq);
        if (seq < appliedSeq) return { stale: true, seq };  // újabb válasz már alkalmazva
        appliedSeq = seq;
        onApplied(result, payload, seq);
        return { stale: false, seq, result };
      } catch (error) {
        if (seq < appliedSeq) return { stale: true, seq, error };
        onError(error, payload, seq);
        return { stale: false, seq, error };
      } finally {
        inFlight -= 1;
      }
    }

    return {
      schedule,
      flush,
      get dispatchSeq() { return dispatchSeq; },
      get appliedSeq() { return appliedSeq; },
      get inFlight() { return inFlight; },
      get hasPending() { return pendingPayload !== null || timer !== null; },
    };
  }

  return {
    DEFAULT_BANDWIDTHS,
    SYMMETRIC_MODES,
    ABSOLUTE_MIN_BANDWIDTH_HZ,
    ABSOLUTE_MAX_BANDWIDTH_HZ,
    normalizeMode,
    defaultBandwidthFor,
    isSingleSideband,
    computePassbandEdges,
    bandwidthFromEdge,
    snapFrequencyToSpectrumBin,
    isResolutionTooCoarse,
    clampBandwidth,
    computePixelGeometry,
    hitTestPassband,
    planChannelTuning,
    createDemodState,
    createUpdateScheduler,
  };
});

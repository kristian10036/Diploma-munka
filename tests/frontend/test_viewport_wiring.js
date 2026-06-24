'use strict';

// Bekötési integrációs teszt: nem a Controller belső logikáját ismétli meg
// (ld. test_viewport_controller.js), hanem azt a mintát, ahogyan az
// index.html a valós Controller-t a zoom/pan/drag/acceptSweep handlerekbe
// köti - fake canvas-szélesség, fake capabilities és szimulált frame-ek
// mellett, a viewport-controller.js valós Controller osztályával.

const {Controller, STATES} = require('../../python-processor/static/viewport-controller.js');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

class FakeScheduler {
  constructor() { this.now = 0; this.nextId = 1; this.tasks = new Map(); }
  setTimeout(callback, delay) {
    const id = this.nextId++;
    this.tasks.set(id, {at: this.now + delay, callback});
    return id;
  }
  clearTimeout(id) { this.tasks.delete(id); }
  tick(milliseconds) {
    this.now += milliseconds;
    const due = [...this.tasks.entries()].filter(([, task]) => task.at <= this.now);
    for (const [id, task] of due) { this.tasks.delete(id); task.callback(); }
  }
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

// Az index.html-ben: setView() vége (zoomAt/dblclick/zoom-gombok/billentyűk
// mind ide futnak be) hívja a schedule()-t; mousedown -> beginInteraction(),
// mouseup -> endInteraction(currentRfViewport()) a pan/select/overview-drag
// köré. Ugyanezt a mintát modellezi itt egy minimális, Hz-alapú nézet.
function createWiringHarness(controller) {
  let centerHz = 2.45e9, spanHz = 100e6;
  function currentViewport() { return {centerFrequencyHz: centerHz, spanHz, mode: 'sweep'}; }
  return {
    currentViewport,
    zoomAt(factor) { spanHz *= factor; controller.schedule(currentViewport()); },
    pan(deltaHz) { centerHz += deltaHz; controller.schedule(currentViewport()); },
    beginDrag() { controller.beginInteraction(); },
    endDrag(deltaHz) { centerHz += deltaHz; controller.endInteraction(currentViewport()); },
  };
}

function fixture(overrides = {}) {
  const scheduler = new FakeScheduler();
  const requests = [];
  const states = [];
  const controller = new Controller({
    scheduler,
    now: () => 1000 + scheduler.now,
    sendRequest: request => {
      const pending = deferred();
      requests.push({request, pending});
      return pending.promise;
    },
    onStateChange: value => states.push(value.state),
    ...overrides,
  });
  const harness = createWiringHarness(controller);
  return {controller, scheduler, requests, states, harness};
}

async function microtasks() { await Promise.resolve(); await Promise.resolve(); }

async function run() {
  // Atomi gesztus (wheel/dblclick/zoom-gomb): a wiring schedule()-t hív
  // setView()-ből, a debounce egyetlen kérésre vonja össze a gyors ismétlést.
  {
    const {controller, scheduler, requests, harness} = fixture();
    controller.setCapabilities({viewport_control: true, maximum_spectrum_points: 8192});
    controller.setCanvasPhysicalWidth(1200);
    harness.zoomAt(0.5);
    harness.zoomAt(0.9);
    scheduler.tick(449);
    assert(requests.length === 0, 'debounce must wait for wiring-driven zoom');
    scheduler.tick(1);
    assert(requests.length === 1, 'rapid zoom wiring must collapse to one request');
  }

  // Pan-drag: beginInteraction()/endInteraction() közben a köztes mousemove
  // tickek nem hangolnak újra, csak a lezárt (mouseup utáni) viewport megy ki.
  {
    const {controller, scheduler, requests, harness} = fixture();
    controller.setCapabilities({viewport_control: true, maximum_spectrum_points: 8192});
    controller.setCanvasPhysicalWidth(1200);
    harness.beginDrag();
    harness.pan(1e6);
    harness.pan(1e6);
    scheduler.tick(1000);
    assert(requests.length === 0, 'active pan drag must not retune mid-gesture');
    harness.endDrag(1e6);
    scheduler.tick(450);
    assert(requests.length === 1, 'settled pan drag triggers exactly one retune');
  }

  // STREAMING csak az ÚJ viewportnak megfelelő, később érkező frame után áll
  // be (observeFrame az acceptSweep()-ből) - korábbi (stale) frame nem elég.
  {
    const {controller, scheduler, requests, harness} = fixture();
    controller.setCapabilities({viewport_control: true, maximum_spectrum_points: 8192});
    controller.setCanvasPhysicalWidth(1200);
    harness.zoomAt(0.1);
    scheduler.tick(450);
    requests[0].pending.resolve({status: 'accepted', num_points: 4800, step_frequency_hz: 2083});
    await microtasks();
    assert(controller.state === STATES.WAITING_FOR_MATCHING_FRAME, 'accepted response waits for a matching frame');

    const stale = controller.observeFrame({
      sourceType: 'mock', sessionId: 'session-1', sequence: 1,
      timestamp: new Date(500).toISOString(), startFrequencyHz: 0, stopFrequencyHz: 10e9,
    }, 'mock');
    assert(!stale && controller.state !== STATES.STREAMING, 'a frame timestamped before the request must not complete the retune');

    const viewport = harness.currentViewport();
    const matched = controller.observeFrame({
      sourceType: 'mock', sessionId: 'session-1', sequence: 2,
      timestamp: new Date(2000).toISOString(),
      startFrequencyHz: viewport.centerFrequencyHz - viewport.spanHz / 2,
      stopFrequencyHz: viewport.centerFrequencyHz + viewport.spanHz / 2,
    }, 'mock');
    assert(matched && controller.state === STATES.STREAMING, 'a frame matching the new viewport completes the retune');
  }

  // viewport_control=false (replay / jelenlegi hardveradapterek): a wiring
  // tisztán grafikus marad, soha nem megy ki kérés.
  {
    const {controller, scheduler, requests, harness} = fixture();
    controller.setCapabilities({viewport_control: false, maximum_spectrum_points: 8192});
    controller.setCanvasPhysicalWidth(1200);
    harness.zoomAt(0.5);
    harness.pan(1e6);
    scheduler.tick(1000);
    assert(requests.length === 0, 'viewport_control=false must keep the wiring purely graphical');
  }

  console.log('viewport wiring integration: PASS');
}

run().catch(error => { console.error(error); process.exitCode = 1; });

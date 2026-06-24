'use strict';

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

function fixture(overrides = {}) {
  const scheduler = new FakeScheduler();
  const requests = [];
  const accepted = [];
  const states = [];
  let ids = 0;
  const controller = new Controller({
    scheduler,
    now: () => 1000 + scheduler.now,
    requestId: () => `request-${++ids}`,
    sendRequest: request => {
      const pending = deferred();
      requests.push({request, pending});
      return pending.promise;
    },
    onAccepted: value => accepted.push(value),
    onStateChange: value => states.push(value.state),
    ...overrides,
  });
  controller.setCapabilities({viewport_control: true, maximum_spectrum_points: 8192});
  controller.setCanvasPhysicalWidth(1200);
  controller.observeFrame({
    sourceType: 'aaronia', sessionId: 'session-1', sequence: 10,
    timestamp: new Date(900).toISOString(), startFrequencyHz: 0, stopFrequencyHz: 10e9,
  }, 'aaronia');
  return {controller, scheduler, requests, accepted, states};
}

async function microtasks() { await Promise.resolve(); await Promise.resolve(); }

async function run() {
  {
    const {controller, scheduler, requests} = fixture();
    for (let index = 0; index < 20; index += 1) {
      controller.schedule({centerFrequencyHz: 2.46e9 + index * 1000, spanHz: 10e6});
    }
    scheduler.tick(449);
    assert(requests.length === 0, 'debounce must wait');
    scheduler.tick(1);
    assert(requests.length === 1, 'rapid wheel events must produce one request');
    assert(requests[0].request.maximum_points === 4800, 'target points use physical canvas width');
    assert(requests[0].request.desired_rbw_hz === 10e6 / 4800, 'desired RBW follows span/points');
  }

  {
    const {controller, scheduler, requests, accepted} = fixture();
    controller.schedule({centerFrequencyHz: 2.46e9, spanHz: 10e6});
    scheduler.tick(450);
    controller.schedule({centerFrequencyHz: 2.462e9, spanHz: 1e6});
    assert(requests.length === 1, 'no overlapping retune request');
    requests[0].pending.resolve({request_id: 'request-1', status: 'accepted'});
    await microtasks();
    assert(accepted.length === 0, 'superseded response must be ignored');
    assert(controller.state === STATES.PENDING, 'newest viewport remains pending');
    scheduler.tick(450);
    assert(requests.length === 2, 'queued viewport is sent after old response settles');
  }

  {
    const {controller, scheduler, requests} = fixture();
    const viewport = {centerFrequencyHz: 915e6, spanHz: 1e6};
    controller.schedule(viewport);
    scheduler.tick(450);
    requests[0].pending.resolve({status: 'accepted'});
    await microtasks();
    const matched = controller.observeFrame({
      sourceType: 'aaronia', sessionId: 'session-1', sequence: 11,
      timestamp: new Date(2000).toISOString(), startFrequencyHz: 914500000,
      stopFrequencyHz: 915500000,
    }, 'aaronia');
    assert(matched && controller.state === STATES.STREAMING, 'matching live frame completes retune');
    controller.schedule({centerFrequencyHz: 915000100, spanHz: 1000100});
    scheduler.tick(500);
    assert(requests.length === 1, 'practically identical viewport must not restart worker');
  }

  {
    const {controller, scheduler, requests} = fixture();
    controller.setCapabilities({viewport_control: false, maximum_spectrum_points: 8192});
    controller.schedule({centerFrequencyHz: 100e6, spanHz: 10e6});
    scheduler.tick(500);
    assert(requests.length === 0, 'capability gating prevents unsupported requests');
  }

  {
    const {controller, scheduler, requests} = fixture();
    controller.beginInteraction();
    controller.schedule({centerFrequencyHz: 433.92e6, spanHz: 2e6});
    scheduler.tick(1000);
    assert(requests.length === 0, 'active drag must not retune');
    controller.endInteraction();
    scheduler.tick(450);
    assert(requests.length === 1, 'settled interaction triggers one retune');
  }

  console.log('viewport controller: PASS');
}

run().catch(error => { console.error(error); process.exitCode = 1; });

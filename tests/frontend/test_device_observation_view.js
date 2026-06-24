'use strict';

// Egységtesztek a python-processor/static/ui/device-observation-view.js tiszta
// HTML-string-építőihez. ESM modul (tranzitív import html.js + observation-format.js),
// Node 24 require()-zel betöltve.

const V = require('../../python-processor/static/ui/device-observation-view.js');

let passed = 0;
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
  passed += 1;
}
function eq(actual, expected, msg) {
  assert(actual === expected, `${msg}\n  várt: ${JSON.stringify(expected)}\n  kapott: ${JSON.stringify(actual)}`);
}
function contains(haystack, needle, msg) {
  assert(haystack.includes(needle), `${msg} (hiányzik: ${JSON.stringify(needle)} ebből: ${JSON.stringify(haystack)})`);
}

// --- üres állapotok (pontos string) ---
eq(V.wifiObservationsHtml([]), '<tr><td colspan="12">Nincs Wi-Fi adat.</td></tr>', 'wifi üres');
eq(V.wifiObservationsHtml(null), '<tr><td colspan="12">Nincs Wi-Fi adat.</td></tr>', 'wifi null');
eq(V.wifiSecurityEventsHtml([]), '<tr><td colspan="10">Nincs Wi-Fi security esemény.</td></tr>', 'wifi security üres');
eq(V.bluetoothObservationsHtml([]), '<tr><td colspan="11">Nincs Bluetooth adat.</td></tr>', 'bluetooth üres');
eq(V.detectionRowsHtml([], 'Nincs anomália.'), '<tr><td colspan="5">Nincs anomália.</td></tr>', 'detection üres');
eq(V.detectionRowsHtml([], '<x>'), '<tr><td colspan="5">&lt;x&gt;</td></tr>', 'detection üres escapelve');

// --- detectionRowsHtml egy elemmel ---
eq(
  V.detectionRowsHtml([{ class_name: 'jammer', severity: 'high', explanation: 'erős jel', disposition: 'open' }], 'x'),
  '<tr><td>--</td><td>jammer</td><td>high</td><td>erős jel</td><td>open</td></tr>',
  'detection egy sor (detected_at nélkül -> --)'
);

// --- referenceSummaryHtml: darabszámok ---
{
  const items = [
    { reference_status: 'in_reference' }, { reference_status: 'in_reference' },
    { reference_status: 'new' },
  ];
  const html = V.referenceSummaryHtml(items, [{}, {}]);
  contains(html, 'Referenciában és aktuálisan is látható: <b>2</b>', 'ref summary in_reference=2');
  contains(html, 'Új eszköz: <b>1</b>', 'ref summary new=1');
  contains(html, 'Referenciában szerepelt, de most nem észlelt: <b>2</b>', 'ref summary missing=2');
  contains(html, 'missing-reference-toggle', 'ref summary toggle osztály');
}
eq(
  V.referenceSummaryHtml([], []),
  '<span>Referenciában és aktuálisan is látható: <b>0</b></span>'
  + '<span class="bs-new">Új eszköz: <b>0</b></span>'
  + '<span class="bs-missing missing-reference-toggle" tabindex="0" role="button">Referenciában szerepelt, de most nem észlelt: <b>0</b></span>',
  'ref summary üres pontos'
);

// --- deviceReferenceDetailsHtml ---
eq(V.deviceReferenceDetailsHtml(null, 'wifi'), '<p>Nincs betöltött referencia - az eszköz not_compared állapotú.</p>', 'detail null');
eq(V.deviceReferenceDetailsHtml({ reference_status: 'not_compared' }, 'wifi'), '<p>Nincs betöltött referencia - az eszköz not_compared állapotú.</p>', 'detail not_compared');
{
  const item = {
    reference_status: 'in_reference',
    reference_values: { ssid: 'RefNet', typical_channel: 6 },
    current_values: { ssid: 'RefNet', channel: 11 },
    differences: [{ field: 'channel' }],
    match_method: 'bssid', match_confidence: 'high', observation_count: 5,
  };
  const html = V.deviceReferenceDetailsHtml(item, 'wifi');
  contains(html, '<table class="kv-table">', 'detail kv-table');
  contains(html, 'Match: <b>bssid</b> (high)', 'detail match meta');
  contains(html, 'Observation count: <b>5</b>', 'detail observation count');
  contains(html, 'class="kv-diff"', 'detail eltérés jelölés (channel diff)');
  contains(html, 'RefNet', 'detail referenciaérték');
}

// --- missingReferenceDevicesHtml ---
{
  const html = V.missingReferenceDevicesHtml([
    { ssid: 'Net1', mac_address: 'aa:bb', vendor: 'Acme', last_seen: null },
  ], 'wifi');
  contains(html, '<table class="kv-table">', 'missing kv-table');
  contains(html, '<td>Net1</td>', 'missing wifi címke ssid');
  contains(html, '<td>aa:bb</td>', 'missing mac');
  contains(html, '<td>Acme</td>', 'missing vendor');
  contains(html, '<td>--</td>', 'missing last_seen nélkül -> --');
}
{
  // bluetooth ág: device_name a címke
  const html = V.missingReferenceDevicesHtml([{ device_name: 'BT-Hangszóró', mac_address: 'cc:dd' }], 'bluetooth');
  contains(html, '<td>BT-Hangszóró</td>', 'missing bluetooth címke device_name');
}

// --- wifi/bluetooth observation sor: kulcsmezők jelenléte + XSS-escape ---
{
  const html = V.wifiObservationsHtml([{
    stable_identity: 'id<1>', reference_status: 'new', ssid: 'My&Net',
    bssid: 'aa:bb:cc', device_type: 'ap', vendor: 'Acme', channel: 6,
    frequency_hz: 2437000000, encryption: 'WPA2',
  }]);
  contains(html, 'data-stable-identity="id&lt;1&gt;"', 'wifi sor: stable_identity escapelve');
  contains(html, 'My&amp;Net', 'wifi sor: ssid escapelve');
  contains(html, '2437.000 MHz', 'wifi sor: frekvencia MHz-ben');
  contains(html, 'row-baseline-new', 'wifi sor: új eszköz osztály');
}
{
  const html = V.bluetoothObservationsHtml([{
    stable_identity: 'bt1', reference_status: 'in_reference', has_differences: true,
    mac: '11:22', device_name: 'Fej&hallgató', vendor: 'X', address_type: 'public',
    bluetooth_type: 'BLE', service_uuids: ['180f', '180a'],
  }]);
  contains(html, 'Fej&amp;hallgató', 'bt sor: device_name escapelve');
  contains(html, 'row-baseline-changed', 'bt sor: megváltozott osztály');
  contains(html, '180f, 180a', 'bt sor: service uuid összegzés');
}

console.log(`device observation view: PASS (${passed} assertions)`);

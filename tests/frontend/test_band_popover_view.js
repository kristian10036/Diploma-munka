'use strict';

// Egységtesztek a python-processor/static/ui/band-popover-view.js tiszta
// popover-HTML-építőihez. ESM modul (tranzitív import html.js + spectrum-scale.js),
// Node 24 require()-zel betöltve.

const V = require('../../python-processor/static/ui/band-popover-view.js');

let passed = 0;
function assert(c, m) { if (!c) throw new Error(m); passed += 1; }
function eq(a, b, m) { assert(a === b, `${m}\n  várt: ${JSON.stringify(b)}\n  kapott: ${JSON.stringify(a)}`); }
function contains(h, n, m) { assert(h.includes(n), `${m} (hiányzik: ${JSON.stringify(n)} ebből: ${JSON.stringify(h)})`); }

// --- popRow (pontos, escapeléssel) ---
eq(V.popRow('ID', '42'), '<div class="pop-label">ID</div><div class="pop-value">42</div>', 'popRow alap');
eq(V.popRow('<x>', null), '<div class="pop-label">&lt;x&gt;</div><div class="pop-value">--</div>', 'popRow escape + null -> --');

// --- bandPopoverHtml ---
{
  const html = V.bandPopoverHtml({
    band_name: 'Wi-Fi 2.4', start_hz: 2400e6, end_hz: 2483e6,
    normal_min_dbm: -90, normal_max_dbm: -40, normal_values_are_temporary: false,
    peak_alarm_dbm: -30, anomaly_delta_db_above_baseline: 6, requires_site_baseline: true,
    external_band_id: 'B1', expected_devices: 'Wi-Fi AP', reference_profile: 'p',
    source_name: 'NMHH', source_file: 'tab.csv', source_pdf_page: 12, notes: 'megj<>',
  });
  contains(html, '<b>Wi-Fi 2.4</b>', 'band név');
  contains(html, '2.4000 GHz - 2.4830 GHz', 'band frekvencia formázva');
  contains(html, '-90.0 .. -40.0 dBm', 'band normal tartomány');
  contains(html, 'site/reference baseline', 'band nem-temp baseline');
  contains(html, '+6.0 dB baseline felett', 'band anomália delta');
  contains(html, 'helyszíni baseline kell', 'band requires baseline');
  contains(html, 'NMHH / tab.csv p.12', 'band forrás összefűzve');
  contains(html, 'megj&lt;&gt;', 'band notes escapelve');
}
// hiányzó mezők -> '--' / default name
{
  const html = V.bandPopoverHtml({});
  contains(html, '<b>Reference band</b>', 'band default név');
  contains(html, 'Nincs megjegyzes.', 'band default notes');
  // normal_values_are_temporary hiányzik -> falsy -> 'site/reference baseline'
  contains(html, 'site/reference baseline', 'band default baseline címke');
}

// --- nmhhPopoverHtml ---
{
  const html = V.nmhhPopoverHtml({ range_label: '2.4 GHz', uses: ['BT', 'Wi&Fi'] });
  contains(html, '<b>NMHH frekvenciakiosztás</b>', 'nmhh cím');
  contains(html, '2.4 GHz', 'nmhh range label');
  contains(html, '<div class="allocation-item">BT</div>', 'nmhh use 1');
  contains(html, '<div class="allocation-item">Wi&amp;Fi</div>', 'nmhh use 2 escapelve');
}
eq(
  V.nmhhPopoverHtml({ range_label: 'X', uses: [] }).includes('Nincs megnevezett alkalmazás.'),
  true,
  'nmhh üres uses -> placeholder'
);

console.log(`band popover view: PASS (${passed} assertions)`);

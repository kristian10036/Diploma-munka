// device-observation-view.js
// -----------------------------------------------------------------------------
// Tiszta (DOM-mentes, state-mentes) HTML-string-építők a Wi-Fi/Bluetooth
// eszközmegfigyelési táblázatokhoz, a referencia-összefoglalóhoz, a részletes
// összehasonlító dialógushoz és az anomália/hiányzó-eszköz listákhoz.
//
// Az index.html inline render-függvényeiből emelve: a HTML-építő template
// literálok SZÓ SZERINT változatlanok (script-alapú verbatim kiemelés), így a
// kimenet bájtra azonos. A DOM-ba írás, a state-Map-ek és a click-listenerek az
// index.html vékony wrapper-függvényeiben maradtak. A formázó-helpereket és az
// escapeHtml-t importálja.
// -----------------------------------------------------------------------------

import { escapeHtml } from './html.js';
import {
  firstFiniteNumber, observationRawPayload, rawKismetSignal, formatRssiSummary,
  formatAge, formatRiskSummary, formatManagementSummary, formatServiceSummary,
  formatExactTime, formatReferenceStatus, referenceRowClass,
} from './observation-format.js';

const WIFI_DETAIL_FIELDS = [
  ['ssid','SSID'], ['encryption','Titkosítás'], ['device_type','Típus'],
  ['channel','Csatorna'], ['frequency_hz','Frekvencia'], ['vendor','Vendor'],
];
const WIFI_DETAIL_REFERENCE_FIELD_MAP = {channel:'typical_channel', frequency_hz:'typical_frequency_hz'};
const WIFI_DETAIL_DIFF_FIELD_MAP = {frequency_hz:'frequency'};
const BLUETOOTH_DETAIL_FIELDS = [
  ['device_name','Eszköznév'], ['vendor','Vendor'], ['address_type','Address type'],
  ['bluetooth_type','Bluetooth type'], ['bluetooth_company_id','Company ID'],
  ['manufacturer_data_hash','Manufacturer hash'],
];
const BLUETOOTH_DETAIL_DIFF_FIELD_MAP = {bluetooth_company_id:'company_id'};

export function referenceSummaryHtml(items, missingItems){
  const inReference = (items||[]).filter(item => item.reference_status === 'in_reference').length;
  const newCount = (items||[]).filter(item => item.reference_status === 'new').length;
  const missingCount = (missingItems||[]).length;
  return [
    `<span>Referenciában és aktuálisan is látható: <b>${inReference}</b></span>`,
    `<span class="bs-new">Új eszköz: <b>${newCount}</b></span>`,
    `<span class="bs-missing missing-reference-toggle" tabindex="0" role="button">Referenciában szerepelt, de most nem észlelt: <b>${missingCount}</b></span>`,
  ].join('');
}

export function deviceReferenceDetailsHtml(item, protocol){
  if (!item || item.reference_status === 'not_compared') {
    return '<p>Nincs betöltött referencia - az eszköz not_compared állapotú.</p>';
  }
  const referenceValues = item.reference_values || {};
  const currentValues = item.current_values || {};
  const fields = protocol === 'wifi' ? WIFI_DETAIL_FIELDS : BLUETOOTH_DETAIL_FIELDS;
  const referenceFieldMap = protocol === 'wifi' ? WIFI_DETAIL_REFERENCE_FIELD_MAP : {};
  const diffFieldMap = protocol === 'wifi' ? WIFI_DETAIL_DIFF_FIELD_MAP : BLUETOOTH_DETAIL_DIFF_FIELD_MAP;
  const diffFields = new Set((item.differences||[]).map(entry => entry.field));
  const rows = fields.map(([field, label]) => {
    const referenceValue = referenceValues[referenceFieldMap[field] || field];
    const currentValue = currentValues[field];
    const changed = diffFields.has(diffFieldMap[field] || field);
    return `<tr${changed ? ' class="kv-diff"' : ''}><th>${escapeHtml(label)}</th><td>${escapeHtml(referenceValue ?? '--')}</td><td>${escapeHtml(currentValue ?? '--')}</td></tr>`;
  }).join('');
  const metaHtml = `
    <p>Match: <b>${escapeHtml(item.match_method || '--')}</b> (${escapeHtml(item.match_confidence || '--')})</p>
    ${item.match_detail ? `<p>${escapeHtml(item.match_detail)}</p>` : ''}
    <p>Observation count: <b>${escapeHtml(item.observation_count ?? '--')}</b></p>
    <p>Első észlelés (session): ${escapeHtml(item.first_seen_in_session ? new Date(item.first_seen_in_session).toLocaleString('hu-HU') : '--')}</p>
    <p>Utolsó észlelés (session): ${escapeHtml(item.last_seen_in_session ? new Date(item.last_seen_in_session).toLocaleString('hu-HU') : '--')}</p>
  `;
  const bodyHtml = `${metaHtml}<table class="kv-table"><thead><tr><th></th><th>Referenciaérték</th><th>Aktuális érték</th></tr></thead><tbody>${rows}</tbody></table>`;
  return bodyHtml;
}

export function missingReferenceDevicesHtml(missingItems, protocol){
  const rows = missingItems.map(item => {
    const label = protocol === 'wifi'
      ? (item.ssid || item.mac_address || item.stable_identity || '--')
      : (item.device_name || item.mac_address || item.stable_identity || '--');
    const lastSeen = item.last_seen ? new Date(item.last_seen).toLocaleString('hu-HU') : '--';
    return `<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(item.mac_address || '--')}</td><td>${escapeHtml(item.vendor || '--')}</td><td>${escapeHtml(lastSeen)}</td></tr>`;
  }).join('');
  const bodyHtml = `<table class="kv-table"><thead><tr><th>Eszköz</th><th>MAC</th><th>Vendor</th><th>Utoljára látva (referencia)</th></tr></thead><tbody>${rows}</tbody></table>`;
  return bodyHtml;
}

export function detectionRowsHtml(items, emptyText){
  if (!items?.length) {
    return `<tr><td colspan="5">${escapeHtml(emptyText)}</td></tr>`;
  }
  return items.map(item => {
    const timestamp = item.detected_at ? new Date(item.detected_at).toLocaleString('hu-HU') : '--';
    return `<tr><td>${escapeHtml(timestamp)}</td><td>${escapeHtml(item.class_name || '--')}</td><td>${escapeHtml(item.severity || '--')}</td><td>${escapeHtml(item.explanation || '--')}</td><td>${escapeHtml(item.disposition || '--')}</td></tr>`;
  }).join('');
}

export function wifiObservationsHtml(items){
  if (!items?.length) {
    return '<tr><td colspan="12">Nincs Wi-Fi adat.</td></tr>';
  }
  return items.map(item => {
    const observedAt = item.latest_observed_at || item.observed_at || item.last_seen;
    const raw = observationRawPayload(item);
    const signalValue = firstFiniteNumber(item.latest_signal_dbm, item.signal_dbm, item.rssi_dbm, rawKismetSignal(raw));
    const signal = formatRssiSummary(
      signalValue,
      item.previous_signal_dbm,
      item.rssi_min_dbm,
      item.rssi_max_dbm,
      item.rssi_avg_dbm
    );
    const frequency = Number.isFinite(Number(item.frequency_hz))
      ? `${(Number(item.frequency_hz) / 1e6).toFixed(3)} MHz`
      : '--';
    return `<tr${referenceRowClass(item)} data-stable-identity="${escapeHtml(item.stable_identity || '')}"><td class="ref-glyph">${escapeHtml(formatReferenceStatus(item))}</td><td>${escapeHtml(formatExactTime(observedAt))} · ${escapeHtml(formatAge(observedAt))}</td><td>${escapeHtml(item.bssid || '--')}</td><td>${escapeHtml(item.device_type || 'unknown')}</td><td>${escapeHtml(item.ssid || '--')}</td><td>${escapeHtml(item.vendor || '--')}</td><td>${escapeHtml(item.channel ?? '--')}</td><td>${escapeHtml(frequency)}</td><td>${escapeHtml(signal)}</td><td>${escapeHtml(item.encryption || '--')}</td><td>${escapeHtml(formatManagementSummary(item.management_frame_summary))}</td><td>${escapeHtml(formatRiskSummary(item.risk_level, item.risk_summary))}</td></tr>`;
  }).join('');
}

export function wifiSecurityEventsHtml(items){
  if (!items?.length) {
    return '<tr><td colspan="10">Nincs Wi-Fi security esemény.</td></tr>';
  }
  return items.map(item => {
    const timestamp = item.timestamp ? new Date(item.timestamp).toLocaleString('hu-HU') : '--';
    const bssidSsid = [item.bssid, item.ssid].filter(Boolean).join(' / ') || '--';
    const frameReason = [item.frame_type, item.reason_code ? `reason ${item.reason_code}` : null].filter(Boolean).join(' / ') || '--';
    const channelRssi = [
      item.channel ? `ch ${item.channel}` : null,
      Number.isFinite(Number(item.rssi_dbm)) ? `${Number(item.rssi_dbm).toFixed(0)} dBm` : null
    ].filter(Boolean).join(' / ') || '--';
    const eventText = [
      item.description || '--',
      item.confidence ? `bizalom: ${item.confidence}` : null,
      item.event_count ? `db: ${item.event_count}` : null
    ].filter(Boolean).join(' · ');
    return `<tr><td>${escapeHtml(timestamp)}</td><td>${escapeHtml(item.alert_type || '--')}</td><td>${escapeHtml(item.severity || '--')}</td><td>${escapeHtml(item.suspected_transmitter_mac || '--')}</td><td>${escapeHtml(item.destination_mac || '--')}</td><td>${escapeHtml(bssidSsid)}</td><td>${escapeHtml(frameReason)}</td><td>${escapeHtml(channelRssi)}</td><td>${escapeHtml(eventText)}</td><td>${escapeHtml(item.review_state || item.status || '--')}</td></tr>`;
  }).join('');
}

export function bluetoothObservationsHtml(items){
  if (!items?.length) {
    return '<tr><td colspan="11">Nincs Bluetooth adat.</td></tr>';
  }
  return items.map(item => {
    const observedAt = item.latest_observed_at || item.observed_at || item.last_seen;
    const raw = observationRawPayload(item);
    const rssiValue = firstFiniteNumber(
      item.latest_rssi_dbm,
      item.rssi_dbm,
      raw.bluetooth_rssi_last,
      raw.bluetooth_rssi_avg,
      raw.device_last_signal,
      rawKismetSignal(raw)
    );
    const rssi = formatRssiSummary(
      rssiValue,
      item.previous_rssi_dbm,
      item.rssi_min_dbm,
      item.rssi_max_dbm,
      item.rssi_avg_dbm
    );
    const serviceUuids = formatServiceSummary(item.service_uuids);
    const vendorMethod = item.vendor_resolution_method
      ? `${item.vendor_resolution_method}${item.vendor_confidence ? ` / ${item.vendor_confidence}` : ''}`
      : '--';
    return `<tr${referenceRowClass(item)} data-stable-identity="${escapeHtml(item.stable_identity || '')}"><td class="ref-glyph">${escapeHtml(formatReferenceStatus(item))}</td><td>${escapeHtml(formatExactTime(observedAt))} · ${escapeHtml(formatAge(observedAt))}</td><td>${escapeHtml(item.mac || '--')}</td><td>${escapeHtml(item.device_name || '--')}</td><td>${escapeHtml(rssi)}</td><td>${escapeHtml(item.vendor || '--')}</td><td>${escapeHtml(vendorMethod)}</td><td>${escapeHtml(item.address_type || '--')}</td><td>${escapeHtml(item.bluetooth_type || '--')}</td><td>${escapeHtml(serviceUuids)}</td><td>${escapeHtml(formatRiskSummary(item.risk_level, item.risk_summary))}</td></tr>`;
  }).join('');
}

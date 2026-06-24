// observation-format.js
// -----------------------------------------------------------------------------
// Tiszta, DOM-mentes formazó- és adatkinyerő-segédfüggvények a Wi-Fi/Bluetooth
// eszközmegfigyelési táblázatokhoz és a referencia-állapot megjelenítéséhez.
// Az index.html inline scriptjéből emelve, viselkedésmegőrző módon (a
// függvénytestek szó szerint változatlanok). Csak az argumentumaikból dolgoznak
// (a Date-alapuák a rendszeridből), nincs modul-szintű mutable state.
//
// formatUnknownStatus: az index.html-ben már a kiemelés előtt is használaton
// kívüli (holt) kód volt; itt változatlanul megőrizzük és exportáljuk.
// -----------------------------------------------------------------------------

export function firstFiniteNumber(...values){
  for (const value of values) {
    if (value === null || value === undefined || value === '') continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed < 0) return parsed;
  }
  return null;
}
export function observationRawPayload(item){
  if (item?.raw_payload && typeof item.raw_payload === 'object') return item.raw_payload;
  if (typeof item?.raw_payload === 'string') {
    try { return JSON.parse(item.raw_payload); } catch (_) { return {}; }
  }
  return {};
}
export function rawKismetSignal(raw){
  return firstFiniteNumber(
    raw.device_last_signal,
    raw['kismet.device.base.signal/kismet.common.signal.last_signal'],
    raw['kismet.common.signal.last_signal'],
    raw['kismet.device.base.signal.kismet.common.signal.last_signal'],
    raw['kismet.device.base.signal']?.['kismet.common.signal.last_signal']
  );
}
export function formatRssiSummary(latest, previous, minValue, maxValue, avgValue){
  const current = firstFiniteNumber(latest);
  if (current === null) return '--';
  const previousValue = firstFiniteNumber(previous);
  const average = firstFiniteNumber(avgValue);
  const minRssi = firstFiniteNumber(minValue);
  const maxRssi = firstFiniteNumber(maxValue);
  const parts = [`${current.toFixed(1)} dBm`];
  if (previousValue !== null) {
    const delta = current - previousValue;
    if (Math.abs(delta) >= 0.5) parts.push(`${delta > 0 ? '+' : ''}${delta.toFixed(1)} dB`);
  }
  if (average !== null && minRssi !== null && maxRssi !== null) {
    parts.push(`avg ${average.toFixed(1)} (${minRssi.toFixed(0)}..${maxRssi.toFixed(0)})`);
  }
  return parts.join(' · ');
}
export function formatAge(timestamp){
  if (!timestamp) return '--';
  const observedMs = new Date(timestamp).getTime();
  if (!Number.isFinite(observedMs)) return '--';
  const seconds = Math.max(0, Math.round((Date.now() - observedMs) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  return `${hours}h`;
}
export function formatUnknownStatus(value){
  const status = value || 'unknown';
  if (status === 'unknown') return '--';
  return status;
}
export function formatRiskSummary(level, summary){
  const risk = level || 'unknown';
  const label = risk === 'unknown' ? '--' : risk;
  return summary ? `${label}: ${summary}` : label;
}
export function formatManagementSummary(summary){
  if (!summary) return '--';
  if (typeof summary === 'string') return summary || '--';
  if (typeof summary !== 'object') return '--';
  const parts = Object.entries(summary)
    .filter(([, value]) => Number(value) > 0)
    .map(([key, value]) => `${key}: ${value}`);
  return parts.length ? parts.join(', ') : '--';
}
export function formatServiceSummary(serviceUuids){
  let values = [];
  if (Array.isArray(serviceUuids)) values = serviceUuids;
  else if (typeof serviceUuids === 'string') {
    try {
      const parsed = JSON.parse(serviceUuids);
      values = Array.isArray(parsed) ? parsed : serviceUuids.split(',').map(item => item.trim()).filter(Boolean);
    } catch (_) {
      values = serviceUuids.split(',').map(item => item.trim()).filter(Boolean);
    }
  }
  if (!values.length) return '--';
  const unique = [...new Set(values.map(value => String(value)).filter(Boolean))];
  const visible = unique.slice(0, 4).join(', ');
  return unique.length > 4 ? `${visible} +${unique.length - 4}` : visible;
}
export function formatExactTime(timestamp){
  if (!timestamp) return '--';
  const date = new Date(timestamp);
  return Number.isFinite(date.getTime()) ? date.toLocaleTimeString('hu-HU') : '--';
}
export const REFERENCE_STATUS_GLYPHS = {not_compared:'—', in_reference:'✓', new:'＋'};
export function formatReferenceStatus(item){
  const glyph = REFERENCE_STATUS_GLYPHS[item.reference_status] || '—';
  return item.reference_status === 'in_reference' && item.has_differences ? `${glyph} ⚠` : glyph;
}
export function referenceRowClass(item){
  if (item.reference_status === 'new') return ' class="row-baseline-new"';
  if (item.reference_status === 'in_reference' && item.has_differences) return ' class="row-baseline-changed"';
  return '';
}

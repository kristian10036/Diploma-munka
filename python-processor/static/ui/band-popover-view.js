// band-popover-view.js
// -----------------------------------------------------------------------------
// Tiszta HTML-string-építők a spektrum-sáv és az NMHH-frekvenciakiosztás
// popover tartalmához. Az index.html inline scriptjéből emelve, a template
// literálok szó szerint változatlanok (script-alapú verbatim kiemelés). A
// popover DOM-pozicionálása (placeBandPopover) és az innerHTML-írás az
// index.html vékony wrappereiben maradt. Importálja az escapeHtml-t és a
// formatFreq-et.
// -----------------------------------------------------------------------------

import { escapeHtml } from './html.js';
import { formatFreq } from './spectrum-scale.js';

export function popRow(label, value){
  return `<div class="pop-label">${escapeHtml(label)}</div><div class="pop-value">${escapeHtml(value ?? '--')}</div>`;
}

export function bandPopoverHtml(band){
  const freq = `${formatFreq(band.start_hz / 1e6)} - ${formatFreq(band.end_hz / 1e6)}`;
  const normal = Number.isFinite(Number(band.normal_min_dbm)) && Number.isFinite(Number(band.normal_max_dbm))
    ? `${Number(band.normal_min_dbm).toFixed(1)} .. ${Number(band.normal_max_dbm).toFixed(1)} dBm`
    : '--';
  const temporary = band.normal_values_are_temporary ? 'TEMP baseline' : 'site/reference baseline';
  const peakAlarm = Number.isFinite(Number(band.peak_alarm_dbm)) ? `${Number(band.peak_alarm_dbm).toFixed(1)} dBm` : '--';
  const delta = Number.isFinite(Number(band.anomaly_delta_db_above_baseline)) ? `+${Number(band.anomaly_delta_db_above_baseline).toFixed(1)} dB baseline felett` : '--';
  const baseline = band.requires_site_baseline ? 'helyszíni baseline kell' : 'nem kötelező';
  const source = `${band.source_name || '--'}${band.source_file ? ' / ' + band.source_file : ''}${band.source_pdf_page ? ' p.' + band.source_pdf_page : ''}`;
  return `<b>${escapeHtml(band.band_name || 'Reference band')}</b><div class="pop-grid">${
    popRow('ID', band.external_band_id || '--') +
    popRow('Frekvencia', freq) +
    popRow('Eszkozok', band.expected_devices || '--') +
    popRow('Profil', band.reference_profile || '--') +
    popRow('Normal', `${normal} (${temporary})`) +
    popRow('Peak alarm', peakAlarm) +
    popRow('Anomalia', delta) +
    popRow('Baseline', baseline) +
    popRow('Forras', source)
  }<div class="pop-note">${escapeHtml(band.notes || 'Nincs megjegyzes.')}</div></div>`;
}

export function nmhhPopoverHtml(band){
  const uses=(band.uses||[]).slice(0,20);
  return `<b>NMHH frekvenciakiosztás</b><div class="pop-grid">${
    popRow('Frekvenciasáv',band.range_label)
  }<div class="allocation-list">${uses.length
    ?uses.map(item=>`<div class="allocation-item">${escapeHtml(item)}</div>`).join('')
    :'<div class="allocation-item">Nincs megnevezett alkalmazás.</div>'}</div></div>`;
}

'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const pretty = value => JSON.stringify(value, null, 2);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const badge = value => {
    const text = String(value ?? 'unknown');
    const cls = /ready|running|ok|configured|healthy|device_found/i.test(text)
      ? 'ok' : /disabled|not_configured|not_trained|not_probed|unavailable/i.test(text) ? 'warn' : 'bad';
    return `<span class="ops-badge ${cls}">${esc(text)}</span>`;
  };
  async function api(path, options={}) {
    const response = await fetch(path, {
      ...options,
      headers: {'Content-Type':'application/json', ...(options.headers || {})}
    });
    let payload;
    try { payload = await response.json(); } catch (_) { payload = {detail:`HTTP ${response.status}`}; }
    if (!response.ok) throw new Error(payload.detail || payload?.error?.message || `HTTP ${response.status}`);
    return payload;
  }
  function kv(target, rows) {
    target.innerHTML = rows.map(([key,value]) => `<div class="k">${esc(key)}</div><div class="v">${typeof value === 'string' && value.startsWith('<span') ? value : esc(value)}</div>`).join('');
  }

  function metric(value, unit='', digits=2) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(digits)}${unit}` : '--';
  }

  function drawSeries(svg, payload) {
    if (!svg) return;
    const values = (payload?.series || []).flatMap(item => item.values || []).map(([,value]) => Number(value)).filter(Number.isFinite);
    if (values.length < 2) {
      svg.innerHTML = '<text x="12" y="75" class="monitoring-empty">Nincs még elegendő idősoros adat.</text>';
      return;
    }
    const min = Math.min(...values), max = Math.max(...values), span = Math.max(max-min, 0.000001);
    const points = values.map((value,index) => {
      const x = 8 + index * 484 / (values.length-1);
      const y = 128 - ((value-min)/span) * 112;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    svg.innerHTML = `<polyline class="monitoring-line" points="${points}"></polyline><text x="10" y="14" class="monitoring-label">max ${esc(max.toFixed(2))}</text><text x="10" y="137" class="monitoring-label">min ${esc(min.toFixed(2))}</text>`;
  }

  async function refreshRfAgent() {
    const output = byId('rfAgentRaw');
    try {
      const [status, capabilities, sources] = await Promise.all([
        api('/api/rf-agent/status'), api('/api/rf-agent/capabilities'), api('/api/rf-agent/sources')
      ]);
      const agent = status.agent || {};
      const source = agent.source || {};
      kv(byId('rfAgentSummary'), [
        ['integráció', badge(status.status)], ['forrás', source.backend || agent.mode || '--'],
        ['source state', badge(source.state)], ['frames', source.frames_produced ?? 0],
        ['dropped', source.frames_dropped ?? 0], ['recording', badge(agent.recording?.active ? 'active' : 'idle')]
      ]);
      kv(byId('rfHardwareSummary'), [
        ['Aaronia', badge(agent.aaronia?.probe_result || 'unknown')],
        ['USRP', badge(agent.usrp?.probe_result || agent.usrp?.status || 'unknown')],
        ['SDRangel control', badge(agent.sdrangel?.control_plane || 'unknown')],
        ['SDRangel data', badge(agent.sdrangel?.data_plane || 'unknown')]
      ]);
      output.textContent = `RF agent: ${status.status || 'ismeretlen'}; forrás: ${source.backend || agent.mode || 'ismeretlen'}; frame-ek: ${source.frames_produced ?? 0}.`;
    } catch (error) {
      kv(byId('rfAgentSummary'), [['állapot', badge('unreachable')], ['hiba', error.message]]);
      output.textContent = `Az RF agent állapota nem kérdezhető le: ${error.message}`;
    }
  }

  async function rfPost(path, body={}) {
    try { await api(path, {method:'POST', body:JSON.stringify(body)}); await refreshRfAgent(); }
    catch (error) { alert(error.message); }
  }

  // Forrás start/stop/select (replay kiválasztás) után a Spektrum nézet
  // viewport-controllere is friss capabilities-t kér, mert a backend váltás
  // megváltoztathatja a viewport_control/maximum_spectrum_points értékeket.
  function refreshViewportCapabilities() {
    window.refreshRfAgentCapabilities?.();
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return '--';
    const units = ['B','KiB','MiB','GiB','TiB'];
    let amount = bytes, index = 0;
    while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
    return `${amount.toFixed(index ? 2 : 0)} ${units[index]}`;
  }

  function recordingTuning(item) {
    if (item.recording_type === 'iq') {
      return `${metric(item.center_frequency_hz / 1e6, ' MHz', 6)} / ${metric(item.sample_rate / 1e6, ' MS/s', 3)}`;
    }
    if (item.recording_type === 'audio') {
      const center = Number.isFinite(Number(item.center_frequency_hz))
        ? metric(Number(item.center_frequency_hz) / 1e6, ' MHz', 6) : '--';
      return `${center} / ${metric(item.sample_rate, ' Hz', 0)}`;
    }
    const start = Number(item.start_frequency_hz), stop = Number(item.stop_frequency_hz);
    const span = Number.isFinite(start) && Number.isFinite(stop) ? (stop - start) / 1e6 : NaN;
    const rbw = Number(item.rbw_hz || item.metadata?.rbw_hz);
    return `${metric((start + stop) / 2e6, ' MHz', 6)} / span ${metric(span, ' MHz', 3)} / RBW ${metric(rbw, ' Hz', 0)}`;
  }

  async function refreshRecordings() {
    const rows = byId('recordingRows');
    try {
      const verify = Boolean(byId('recordingVerifyChecksums')?.checked);
      const [catalog, state, storage, capabilities] = await Promise.all([
        api(`/api/recordings/catalog?verify_checksums=${verify ? 'true' : 'false'}&limit=200`),
        api('/api/rf-agent/recordings/status').catch(error => ({active:false, last_error:error.message})),
        api('/api/recordings/storage/status'),
        api('/api/recordings/capabilities')
      ]);
      kv(byId('recordingSummary'), [
        ['állapot', badge(state.active ? 'recording' : 'idle')],
        ['ID', state.recording_id || '--'], ['frame count', state.frame_count ?? 0],
        ['utolsó hiba', state.last_error || '--']
      ]);
      kv(byId('recordingStorageSummary'), [
        ['szabad hely', formatBytes(storage.free_bytes)],
        ['minimum tartalék', formatBytes(storage.min_free_bytes)],
        ['tárhelyállapot', badge(storage.low_disk ? 'low_disk' : 'ok')],
        ['spectrum', badge(capabilities.types?.spectrum?.status)],
        ['IQ / SigMF', badge(capabilities.types?.iq?.status)],
        ['audio / WAV', badge(capabilities.types?.audio?.status)]
      ]);
      const metadata = catalog.items || [];
      rows.innerHTML = metadata.length ? metadata.map(item => {
        const type = item.recording_type || 'spectrum';
        const duration = Number(item.duration_seconds);
        const startDuration = `${esc(item.started_at || '--')}<br>${Number.isFinite(duration) ? esc(metric(duration, ' s', 2)) : '--'}`;
        const checksumState = item.checksum_status || (item.checksum_sha256 ? 'not_checked' : 'missing');
        const replay = type === 'spectrum' && item.status === 'completed'
          ? `<button data-replay="${esc(item.recording_id || '')}">Replay</button>`
          : '<span class="ops-badge warn">nincs spectrum replay</span>';
        return `<tr>
          <td>${esc(item.recording_id || '--')}</td><td>${esc(type)}${item.mock ? '<br><span class="ops-badge warn">mock</span>' : ''}</td>
          <td>${esc(item.source_type || item.source || '--')}</td><td>${startDuration}</td>
          <td>${esc(recordingTuning(item))}</td><td>${esc(formatBytes(item.size_bytes))}</td>
          <td>${badge(checksumState)}</td><td>${replay}</td></tr>`;
      }).join('') : '<tr><td colspan="8">Nincs felvétel.</td></tr>';
      rows.querySelectorAll('[data-replay]').forEach(button => button.addEventListener('click', () => {
        const speed = Number(byId('replaySpeed').value || 1);
        rfPost('/api/rf-agent/replay/start', {recording:button.dataset.replay, speed, loop:byId('replayLoop').checked})
          .then(refreshViewportCapabilities);
      }));
    } catch (error) {
      rows.innerHTML = `<tr><td colspan="8">${esc(error.message)}</td></tr>`;
    }
  }


  function formatTimestamp(value) {
    if (!value) return '--';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('hu-HU');
  }

  function formatDetectionFrequency(item) {
    const center = Number(item.center_frequency_hz);
    const start = Number(item.start_frequency_hz);
    const stop = Number(item.stop_frequency_hz);
    if (Number.isFinite(center)) return metric(center / 1e6, ' MHz', 6);
    if (Number.isFinite(start) && Number.isFinite(stop)) {
      return `${metric(start / 1e6, '–', 6)}${metric(stop / 1e6, ' MHz', 6)}`;
    }
    return '--';
  }

  async function loadDetections(domain) {
    try {
      return await api(`/api/detections?domain=${encodeURIComponent(domain)}&limit=100`);
    } catch (error) {
      const recent = await api(`/api/anomalies/recent?domain=${encodeURIComponent(domain)}&limit=100`);
      return {...recent, volatile:true, database_error:error.message};
    }
  }

  function renderDetectionRows(target, payload, domain) {
    const items = payload?.items || [];
    const spectrum = domain === 'spectrum';
    const columns = spectrum ? 7 : 5;
    if (!items.length) {
      target.innerHTML = `<tr><td colspan="${columns}">Nincs ${domain === 'spectrum' ? 'spektrum' : domain === 'wifi' ? 'Wi-Fi' : 'Bluetooth'} anomália.</td></tr>`;
      return;
    }
    target.innerHTML = items.map(item => {
      const id = item.id || '';
      const disposition = item.disposition || (payload.volatile ? 'nem perzisztált' : 'new');
      const review = id
        ? `<button type="button" data-review-detection="${esc(id)}">Review</button><br>${badge(disposition)}`
        : `<span class="ops-badge warn" title="${esc(payload.database_error || 'Csak memóriában elérhető esemény')}">csak memória</span>`;
      const common = `<td>${esc(formatTimestamp(item.detected_at))}</td><td>${esc(item.class_name || item.type || '--')}</td>`;
      if (spectrum) {
        return `<tr>${common}<td>${esc(formatDetectionFrequency(item))}</td><td>${badge(item.severity || 'info')}</td><td>${esc(metric(Number(item.confidence) * 100, '%', 1))}</td><td>${esc(item.explanation || '--')}</td><td>${review}</td></tr>`;
      }
      return `<tr>${common}<td>${badge(item.severity || 'info')}</td><td>${esc(item.explanation || '--')}</td><td>${review}</td></tr>`;
    }).join('');
    target.querySelectorAll('[data-review-detection]').forEach(button => button.addEventListener('click', () => reviewDetection(button.dataset.reviewDetection, domain)));
  }

  async function reviewDetection(id, domain) {
    const form = await openOperationModal({
      title:'Észlelés review', submitLabel:'Review mentése', fields:[
        {name:'disposition',label:'Minősítés',type:'select',value:'reviewed',options:[
          {value:'reviewed',label:'Átnézve'}, {value:'known',label:'Ismert jel'},
          {value:'changed',label:'Megváltozott ismert jel'}, {value:'false_positive',label:'Téves riasztás'}
        ]},
        {name:'reviewed_by',label:'Operátor',value:'operator',required:true,maxLength:200},
        {name:'review_notes',label:'Megjegyzés',type:'textarea',rows:4,maxLength:2000},
        {name:'known_signal_id',label:'Ismert jel UUID (opcionális)',maxLength:64},
        {name:'include_in_training',label:'Bevonható későbbi tanításba',type:'checkbox',checked:false}
      ]
    });
    if (!form) return;
    const payload = {
      disposition:form.disposition,
      reviewed_by:form.reviewed_by,
      review_notes:form.review_notes || null,
      known_signal_id:form.known_signal_id || null,
      include_in_training:form.include_in_training === 'on'
    };
    try {
      await api(`/api/detections/${encodeURIComponent(id)}/review`, {method:'PATCH', body:JSON.stringify(payload)});
      toastMsg('Review mentve');
      await refreshAnomalies(domain);
    } catch (error) { toastMsg(`Review hiba: ${error.message}`); }
  }

  async function refreshAnomalies(domain) {
    const target = byId(domain === 'spectrum' ? 'spectrumAnomalyRows' : domain === 'wifi' ? 'wifiAnomalyRows' : 'bluetoothAnomalyRows');
    if (!target) return;
    try { renderDetectionRows(target, await loadDetections(domain), domain); }
    catch (error) {
      const columns = domain === 'spectrum' ? 7 : 5;
      target.innerHTML = `<tr><td colspan="${columns}">${esc(error.message)}</td></tr>`;
    }
  }

  async function alertAction(id, action) {
    const form = await openOperationModal({
      title:action === 'acknowledge' ? 'Riasztás tudomásulvétele' : 'Riasztás lezárása',
      submitLabel:action === 'acknowledge' ? 'Tudomásul veszem' : 'Lezárás',
      fields:[
        {name:'operator',label:'Operátor',value:'operator',required:true,maxLength:200},
        {name:'note',label:'Megjegyzés',type:'textarea',rows:4,maxLength:2000}
      ]
    });
    if (!form) return;
    try {
      await api(`/api/alerts/${encodeURIComponent(id)}/${action}`, {method:'POST', body:JSON.stringify({operator:form.operator,note:form.note || null})});
      toastMsg(action === 'acknowledge' ? 'Riasztás tudomásul véve' : 'Riasztás lezárva');
      await refreshAlerts();
    } catch (error) { toastMsg(`Riasztásművelet hiba: ${error.message}`); }
  }

  async function refreshAlerts() {
    const target = byId('alertRows');
    if (!target) return;
    try {
      const payload = await api('/api/alerts?limit=100');
      const items = payload.items || [];
      target.innerHTML = items.length ? items.map(item => {
        const actions = item.status === 'resolved' ? '--' : [
          item.status === 'open' ? `<button type="button" data-alert-action="acknowledge" data-alert-id="${esc(item.id)}">Tudomásul</button>` : '',
          `<button type="button" data-alert-action="resolve" data-alert-id="${esc(item.id)}">Lezárás</button>`
        ].filter(Boolean).join(' ');
        return `<tr><td>${esc(formatTimestamp(item.last_seen_at || item.created_at))}</td><td>${esc(item.domain || '--')}</td><td>${badge(item.severity || 'warning')}</td><td>${badge(item.status || 'open')}</td><td>${esc(item.message || '--')}</td><td>${esc(item.occurrence_count ?? 1)}</td><td>${actions}</td></tr>`;
      }).join('') : '<tr><td colspan="7">Nincs riasztás.</td></tr>';
      target.querySelectorAll('[data-alert-action]').forEach(button => button.addEventListener('click', () => alertAction(button.dataset.alertId, button.dataset.alertAction)));
    } catch (error) {
      target.innerHTML = `<tr><td colspan="7">${esc(error.message)}</td></tr>`;
    }
  }

  async function refreshMl() {
    try {
      const [status, models] = await Promise.all([api('/api/ml/status'), api('/api/ml/models')]);
      kv(byId('mlSummary'), [
        ['model', status.model_version || '--'], ['type', status.model_type || '--'],
        ['állapot', badge(status.status)], ['available', String(Boolean(status.available))],
        ['inference device', status.device || 'cpu']
      ]);
      byId('mlRaw').textContent = pretty(models);
    } catch (error) { byId('mlRaw').textContent = error.stack || error.message; }
  }

  async function refreshSystem() {
    refreshAlerts();
    try {
      const [system, assistant, monitoring, aaronia, sdrangel] = await Promise.all([
        api('/api/system/status'), api('/api/assistant/status'), api('/api/monitoring/overview'),
        api('/api/rf-agent/aaronia/status').catch(error => ({probe_result:'unreachable', diagnostic:error.message})),
        api('/api/integrations/sdrangel/status').catch(error => ({status:'unreachable', diagnostic:error.message}))
      ]);
      const cards = byId('systemCards');
      const generation = assistant.generation || assistant;
      const rag = assistant.rag || {};
      const card = (name, rows) => `<div class="ops-card"><h3>${esc(name)}</h3><div class="ops-kv">${rows.map(([key,value,isBadge]) => `<div class="k">${esc(key)}</div><div class="v">${isBadge ? badge(value) : esc(value ?? '--')}</div>`).join('')}</div></div>`;
      cards.innerHTML = [
        card('Aaronia', [['állapot', aaronia.probe_result, true], ['library', aaronia.library_status || aaronia.probe_result, true], ['eszköz', aaronia.device_status || 'ismeretlen', true], ['hiba', aaronia.diagnostic || '--']]),
        card('SDRangel', [['állapot', sdrangel.status, true], ['API', sdrangel.control_plane, true], ['utolsó kapcsolat', sdrangel.last_successful_connection || '--'], ['hiba', sdrangel.diagnostic || '--']]),
        card('Ollama', [['állapot', generation.status, true], ['verzió', generation.ollama_version || '--'], ['generáló modell', generation.model || '--'], ['modell telepítve', generation.status === 'ready' ? 'igen' : 'nem']]),
        card('RAG', [['állapot', rag.status, true], ['embedding modell', rag.embedding_model || '--'], ['embedding telepítve', rag.embedding_model_installed ? 'igen' : 'nem'], ['dimenzió', rag.dimensions || '--'], ['index kompatibilis', rag.index_compatible ? 'igen' : 'nem'], ['újraindexelés', rag.reindex_required ? 'szükséges' : 'nem szükséges']]),
        card('Adatbázis', [['állapot', system.database?.status, true]]),
        card('Prometheus', [['állapot', monitoring.status?.status || (monitoring.status?.available ? 'ready' : 'unavailable'), true]])
      ].join('');
      const v = monitoring.values || {};
      byId('monitoringCards').innerHTML = [
        ['Spektrum frame/s', metric(v.ingest_fps ?? v.spectrum_fps)],
        ['Spektrum WS kliensek', metric(v.ingest_clients ?? v.spectrum_clients, '', 0)],
        ['Eldobott frame', metric(v.ingest_dropped, '', 0)],
        ['Érvénytelen frame', metric(v.ingest_invalid, '', 0)],
        ['HTTP kérés/s', metric(v.request_rate)],
        ['HTTP p95 késleltetés', metric(v.request_latency_p95, ' s', 3)],
        ['DB hibák / óra', metric(v.db_errors, '', 0)],
        ['Anomália queue', metric(v.anomaly_queue, '', 0)],
        ['Anomália drop', metric(v.anomaly_drops, '', 0)],
        ['Recording szabad hely', formatBytes(v.recording_disk_free)],
        ['Nyitott riasztások', metric(v.alerts_open, '', 0)],
        ['SDRangel IQ drop', metric(v.sdrangel_drops, '', 0)],
        ['SDRangel packet loss', metric(v.sdrangel_packet_loss, '', 0)]
      ].map(([name,value]) => `<div class="ops-card metric-card"><div class="metric-name">${esc(name)}</div><div class="metric-value">${esc(value)}</div></div>`).join('');
      if (monitoring.status?.available) {
        const [fpsSeries, requestSeries] = await Promise.all([
          api('/api/monitoring/series/ingest_fps?minutes=60&step_seconds=30'),
          api('/api/monitoring/series/request_rate?minutes=60&step_seconds=30')
        ]);
        drawSeries(byId('chartSpectrumFps'), fpsSeries);
        drawSeries(byId('chartRequestRate'), requestSeries);
      } else {
        drawSeries(byId('chartSpectrumFps'), null);
        drawSeries(byId('chartRequestRate'), null);
      }
      byId('systemRaw').textContent = `Rendszerállapot frissítve. Backend: ${system.backend?.status || 'ismeretlen'}; Ollama: ${generation.status || 'ismeretlen'}; RAG: ${rag.status || 'ismeretlen'}.`;
    } catch (error) { byId('systemRaw').textContent = `A rendszerállapot nem kérdezhető le: ${error.message}`; }
  }

  const refreshers = {
    spectrum:() => refreshAnomalies('spectrum'),
    wifi:() => refreshAnomalies('wifi'),
    bluetooth:() => refreshAnomalies('bluetooth'),
    rfagent:refreshRfAgent, recordings:refreshRecordings, ml:refreshMl, system:refreshSystem
  };
  document.querySelectorAll('.tab-button').forEach(button => button.addEventListener('click', () => {
    const refresh = refreshers[button.dataset.tab];
    if (refresh) refresh();
  }));

  byId('btnRfRefresh')?.addEventListener('click', refreshRfAgent);
  byId('btnRfStart')?.addEventListener('click', () => rfPost('/api/rf-agent/source/start').then(refreshViewportCapabilities));
  byId('btnRfStop')?.addEventListener('click', () => rfPost('/api/rf-agent/source/stop').then(refreshViewportCapabilities));
  byId('btnAaroniaProbe')?.addEventListener('click', () => rfPost('/api/rf-agent/aaronia/probe'));
  byId('btnUsrpProbe')?.addEventListener('click', () => rfPost('/api/rf-agent/usrp/probe'));
  byId('btnRecordingRefresh')?.addEventListener('click', refreshRecordings);
  byId('btnRecordingStart')?.addEventListener('click', () => rfPost('/api/rf-agent/recordings/start', {
    recording_id:byId('recordingId').value.trim() || undefined,
    description:byId('recordingDescription').value.trim() || undefined
  }).then(refreshRecordings));
  byId('btnRecordingStop')?.addEventListener('click', () => rfPost('/api/rf-agent/recordings/stop').then(refreshRecordings));
  byId('btnReplayPause')?.addEventListener('click', () => rfPost('/api/rf-agent/replay/pause'));
  byId('btnReplayResume')?.addEventListener('click', () => rfPost('/api/rf-agent/replay/resume'));
  byId('btnReplayStop')?.addEventListener('click', () => rfPost('/api/rf-agent/replay/stop'));
  byId('btnMlRefresh')?.addEventListener('click', refreshMl);
  byId('btnSystemRefresh')?.addEventListener('click', refreshSystem);
  byId('btnRefreshSpectrumAnomalies')?.addEventListener('click', () => refreshAnomalies('spectrum'));
  byId('btnRefreshWifiAnomalies')?.addEventListener('click', () => refreshAnomalies('wifi'));
  byId('btnRefreshBluetoothAnomalies')?.addEventListener('click', () => refreshAnomalies('bluetooth'));
  byId('btnAlertRefresh')?.addEventListener('click', refreshAlerts);
})();

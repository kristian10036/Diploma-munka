// Egyetlen hely a backend REST végpontok és statikus fájlok fetch-hívásaihoz.
// Minden függvény pontosan azt a Request-et construálja, amit korábban az
// index.html inline scriptje közvetlenül a hívás helyén épített fel, és a
// nyers fetch Promise<Response>-t adja vissza - a JSON parse, res.ok döntés
// és hibakezelés (call site-specifikus magyar üzenetek, csendben elnyelt
// hibák stb.) változatlanul a hívó oldalon marad.

function postJson(url, body, method = 'POST') {
  return fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// Runtime policy
export function fetchRuntimeReadiness() {
  return fetch('/api/health/ready', { cache: 'no-store' });
}

// Session kezelés
export function fetchActiveSession(query) {
  return fetch(`/api/sessions/active${query}`);
}
export function startSession(body) {
  return postJson('/api/sessions/start', body);
}
export function stopSession(id) {
  return fetch(`/api/sessions/${encodeURIComponent(id)}/stop`, { method: 'POST' });
}
export function fetchRecentSessions() {
  return fetch('/api/sessions?limit=50');
}
export function fetchSessionById(id) {
  return fetch(`/api/sessions/${encodeURIComponent(id)}`);
}

// Spektrum forrás
export function fetchSpectrumSourceStatus() {
  return fetch('/api/spectrum/source/status');
}

// Legacy device-baseline
export function saveDeviceBaseline(body) {
  return postJson('/api/device-baseline/save', body);
}
export function compareDeviceBaseline(params) {
  return fetch(`/api/device-baseline/compare?${params}`);
}
export function deactivateDeviceBaseline(body) {
  return postJson('/api/device-baseline/deactivate', body);
}

// Kismet/Bettercap/Wi-Fi/Bluetooth
export function fetchKismetStatus() {
  return fetch('/api/kismet/status');
}
export function fetchKismetImportStatus() {
  return fetch('/api/kismet/import/status');
}
export function fetchWifiDevices(params) {
  return fetch(`/api/wifi/devices?${params}`);
}
export function fetchWifiSecurityEvents(params) {
  return fetch(`/api/wifi/security-events?${params}`);
}
export function fetchDetections(params) {
  return fetch(`/api/detections?${params}`);
}
export function fetchBettercapStatus() {
  return fetch('/api/bettercap/status');
}
export function fetchBluetoothDevices(params) {
  return fetch(`/api/bluetooth/devices?${params}`);
}
export function importKismetLive(formData) {
  return fetch('/api/import/kismet/live', { method: 'POST', body: formData });
}
export function importKismetAlerts(params) {
  return fetch(`/api/import/kismet/alerts?${params}`, { method: 'POST' });
}

// Spektrum-referencia rétegek
export function fetchReferenceBands(params) {
  return fetch(`/api/references/bands?${params}`);
}
export function fetchReferenceImages(params) {
  return fetch(`/api/references/images?${params}`);
}
export function fetchNmhhAllocations() {
  return fetch('/nmhh-frequency-allocations.json', { cache: 'no-cache' });
}

// Reference-sets
export function captureReferenceSet(body) {
  return postJson('/api/reference-sets/capture', body);
}
export function saveSpectrumPeak(body) {
  return postJson('/api/spectrum/peaks', body);
}
export function fetchReferenceSetMeta(id) {
  return fetch(`/api/reference-sets/${id}`);
}
export function fetchReferenceSetSpectrum(id) {
  return fetch(`/api/reference-sets/${id}/spectrum`);
}
export function fetchReferenceSets(params) {
  return fetch(`/api/reference-sets?${params}`);
}

// Marker/known-signal CRUD
export function createMarker(body) {
  return postJson('/api/markers', body);
}
export function createKnownSignal(body) {
  return postJson('/api/known-signals', body);
}
export function fetchMarkers() {
  return fetch('/api/markers?limit=100');
}
export function fetchKnownSignals() {
  return fetch('/api/known-signals?limit=100');
}
export function updateMarker(id, body) {
  return postJson(`/api/markers/${id}`, body, 'PATCH');
}
export function deleteMarker(id) {
  return fetch(`/api/markers/${id}`, { method: 'DELETE' });
}
export function updateKnownSignalStatus(id, body) {
  return postJson(`/api/known-signals/${id}`, body, 'PATCH');
}
export function deleteKnownSignal(id) {
  return fetch(`/api/known-signals/${id}`, { method: 'DELETE' });
}

// Admin/retention
export function fetchRetentionPreview(dataset, olderThan) {
  return fetch(`/api/admin/retention/preview?dataset=${encodeURIComponent(dataset)}&older_than=${encodeURIComponent(olderThan)}`);
}
export function purgeRetention(body) {
  return postJson('/api/admin/retention/purge', body);
}

// Legacy spectrum reference import
export function importReferenceFile(formData) {
  return fetch('/api/references/import', { method: 'POST', body: formData });
}
export function fetchReferenceDetail(id) {
  return fetch(`/api/references/${id}?include_points=true`);
}

// RF Agent/SDRangel
export function fetchRfAgentCapabilities() {
  return fetch('/api/rf-agent/capabilities');
}
export function updateRfAgentViewport(body) {
  return postJson('/api/rf-agent/source/viewport', body);
}
export function updateSdrangelDemod(body) {
  return postJson('/api/rf-agent/sdrangel/demod/update', body, 'PATCH');
}
export function fetchSdrangelReadiness() {
  return fetch('/api/rf-agent/sdrangel/readiness');
}
export function createSdrangelDeviceSet(body) {
  return postJson('/api/integrations/sdrangel/devicesets', body);
}
export function tuneSdrangel(body) {
  return postJson('/api/rf-agent/sdrangel/tune', body);
}
export function startSdrangelDemod(body) {
  return postJson('/api/rf-agent/sdrangel/demod/start', body);
}
export function stopSdrangelDemod(body) {
  return postJson('/api/rf-agent/sdrangel/demod/stop', body);
}

BEGIN;

CREATE INDEX IF NOT EXISTS idx_rf_detections_domain_detected_id
  ON rf_detections (entity_domain, detected_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_rf_detections_disposition_detected
  ON rf_detections (disposition, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_detections_severity_detected
  ON rf_detections (severity, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_alerts_status_last_seen_id
  ON system_alerts (status, last_seen_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_system_alerts_domain_last_seen
  ON system_alerts (domain, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_alerts_severity_last_seen
  ON system_alerts (severity, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_spectrum_references_key_version
  ON spectrum_references (reference_key, version DESC)
  WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_spectrum_references_active
  ON spectrum_references (reference_key, updated_at DESC)
  WHERE is_active = true AND archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_known_signals_lookup_active
  ON known_signals (center_frequency_hz, frequency_tolerance_hz, updated_at DESC)
  WHERE archived_at IS NULL;

COMMIT;

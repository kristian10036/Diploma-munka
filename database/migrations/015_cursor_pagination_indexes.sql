BEGIN;

CREATE INDEX IF NOT EXISTS idx_rf_detections_detected_id
  ON rf_detections (detected_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_system_alerts_last_seen_id
  ON system_alerts (last_seen_at DESC, id DESC);

COMMIT;

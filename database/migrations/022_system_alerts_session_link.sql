-- Forward-only: link system_alerts to the measurement session that produced
-- them, so Wi-Fi/Bluetooth security events and alerts can be filtered by
-- measurement_session_id instead of relying on global/location-based lookups.
-- No existing column, table, or row is dropped or rewritten.
-- Rollback note: to roll back, drop only the objects this file creates
-- (the measurement_session_id column and its index). No other migration or
-- data is touched.

BEGIN;

ALTER TABLE system_alerts
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID
    REFERENCES measurement_sessions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_system_alerts_session
  ON system_alerts (measurement_session_id, last_seen_at DESC);

COMMIT;

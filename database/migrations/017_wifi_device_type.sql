-- Forward-only Wi-Fi device type alignment for Kismet-derived AP/client roles.
-- Rollback note: keep the columns unless a full data export confirms they are unused.

ALTER TABLE wifi_devices
  ADD COLUMN IF NOT EXISTS device_type TEXT DEFAULT 'unknown';

ALTER TABLE wifi_observations
  ADD COLUMN IF NOT EXISTS device_type TEXT DEFAULT 'unknown';

UPDATE wifi_devices
SET device_type = COALESCE(NULLIF(device_type, ''), 'unknown');

UPDATE wifi_observations
SET device_type = COALESCE(NULLIF(device_type, ''), 'unknown');

CREATE INDEX IF NOT EXISTS idx_wifi_devices_type_last_seen
  ON wifi_devices (device_type, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_wifi_observations_type_time
  ON wifi_observations (device_type, time DESC);


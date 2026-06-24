-- Forward-only Wi-Fi/Bluetooth stable identity and confidence metadata.
-- Rollback note: keep these columns unless a full export confirms the metadata is unused.

ALTER TABLE wifi_devices
  ADD COLUMN IF NOT EXISTS stable_identity TEXT,
  ADD COLUMN IF NOT EXISTS identity_confidence TEXT DEFAULT 'unknown';

ALTER TABLE wifi_observations
  ADD COLUMN IF NOT EXISTS stable_identity TEXT,
  ADD COLUMN IF NOT EXISTS identity_confidence TEXT DEFAULT 'unknown';

ALTER TABLE bluetooth_devices
  ADD COLUMN IF NOT EXISTS stable_identity TEXT,
  ADD COLUMN IF NOT EXISTS identity_confidence TEXT DEFAULT 'unknown';

ALTER TABLE bluetooth_observations
  ADD COLUMN IF NOT EXISTS stable_identity TEXT,
  ADD COLUMN IF NOT EXISTS identity_confidence TEXT DEFAULT 'unknown';

UPDATE wifi_devices
SET stable_identity = COALESCE(NULLIF(stable_identity, ''), bssid),
    identity_confidence = COALESCE(NULLIF(identity_confidence, ''), 'medium');

UPDATE wifi_observations
SET stable_identity = COALESCE(NULLIF(stable_identity, ''), bssid),
    identity_confidence = COALESCE(NULLIF(identity_confidence, ''), 'medium');

UPDATE bluetooth_devices
SET stable_identity = COALESCE(NULLIF(stable_identity, ''), mac_address),
    identity_confidence = COALESCE(NULLIF(identity_confidence, ''), 'medium');

UPDATE bluetooth_observations
SET stable_identity = COALESCE(NULLIF(stable_identity, ''), mac_address),
    identity_confidence = COALESCE(NULLIF(identity_confidence, ''), 'medium');

CREATE INDEX IF NOT EXISTS idx_wifi_devices_identity_last_seen
  ON wifi_devices (stable_identity, identity_confidence, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_wifi_observations_identity_time
  ON wifi_observations (stable_identity, identity_confidence, time DESC);

CREATE INDEX IF NOT EXISTS idx_bluetooth_devices_identity_last_seen
  ON bluetooth_devices (stable_identity, identity_confidence, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_bluetooth_observations_identity_time
  ON bluetooth_observations (stable_identity, identity_confidence, time DESC);

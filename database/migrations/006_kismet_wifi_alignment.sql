-- Phase 4 aligns the existing passive Wi-Fi and Kismet import tables without
-- replacing legacy primary keys or deleting data.

ALTER TABLE wifi_devices
  ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

UPDATE wifi_devices
SET id = COALESCE(id, gen_random_uuid()),
    created_at = COALESCE(created_at, first_seen, now()),
    updated_at = COALESCE(updated_at, last_seen, first_seen, now());

CREATE UNIQUE INDEX IF NOT EXISTS idx_wifi_devices_id
  ON wifi_devices (id) WHERE id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wifi_devices_ssid
  ON wifi_devices (lower(ssid)) WHERE ssid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wifi_devices_last_seen
  ON wifi_devices (last_seen DESC);

ALTER TABLE wifi_observations
  ADD COLUMN IF NOT EXISTS location_name TEXT,
  ADD COLUMN IF NOT EXISTS source_name TEXT,
  ADD COLUMN IF NOT EXISTS source_type TEXT,
  ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS signal_dbm DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS noise_dbm DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS encryption TEXT,
  ADD COLUMN IF NOT EXISTS raw_payload JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

UPDATE wifi_observations AS observation
SET location_name = location.name
FROM locations AS location
WHERE observation.location_id = location.id
  AND observation.location_name IS NULL;

UPDATE wifi_observations
SET source_name = COALESCE(source_name, capture_source, 'legacy_wifi'),
    source_type = COALESCE(source_type, 'wifi'),
    observed_at = COALESCE(observed_at, time),
    signal_dbm = COALESCE(signal_dbm, rssi_dbm),
    raw_payload = COALESCE(raw_payload, metadata, '{}'::jsonb),
    created_at = COALESCE(created_at, time, now());

CREATE INDEX IF NOT EXISTS idx_wifi_observations_session_observed
  ON wifi_observations (measurement_session_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_wifi_observations_location_observed
  ON wifi_observations (location_name, time DESC);
CREATE INDEX IF NOT EXISTS idx_wifi_observations_source_name
  ON wifi_observations (source_name, time DESC);

ALTER TABLE kismet_import_rows
  ADD COLUMN IF NOT EXISTS location_name TEXT,
  ADD COLUMN IF NOT EXISTS source_name TEXT,
  ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'kismet',
  ADD COLUMN IF NOT EXISTS source_file TEXT,
  ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS bssid TEXT,
  ADD COLUMN IF NOT EXISTS signal_dbm DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS noise_dbm DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS packet_count BIGINT,
  ADD COLUMN IF NOT EXISTS raw_payload JSONB DEFAULT '{}'::jsonb;

UPDATE kismet_import_rows AS import_row
SET location_name = location.name
FROM locations AS location
WHERE import_row.location_id = location.id
  AND import_row.location_name IS NULL;

UPDATE kismet_import_rows
SET source_name = COALESCE(source_name, 'kismet_file_import'),
    source_type = COALESCE(source_type, 'kismet'),
    imported_at = COALESCE(imported_at, created_at, now()),
    bssid = COALESCE(bssid, mac_address),
    signal_dbm = COALESCE(signal_dbm, rssi_dbm),
    first_seen = COALESCE(first_seen, measured_at),
    last_seen = COALESCE(last_seen, measured_at),
    raw_payload = COALESCE(raw_payload, raw_row, '{}'::jsonb);

CREATE INDEX IF NOT EXISTS idx_kismet_import_session_time
  ON kismet_import_rows (measurement_session_id, imported_at DESC);
CREATE INDEX IF NOT EXISTS idx_kismet_import_bssid_time
  ON kismet_import_rows (bssid, imported_at DESC);
CREATE INDEX IF NOT EXISTS idx_kismet_import_location_time
  ON kismet_import_rows (location_name, imported_at DESC);


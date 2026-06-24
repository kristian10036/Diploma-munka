-- Phase 5 aligns the existing passive Bluetooth/BLE and Bettercap import
-- tables without replacing legacy primary keys or deleting data.

ALTER TABLE bluetooth_devices
  ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
  ADD COLUMN IF NOT EXISTS address_type TEXT,
  ADD COLUMN IF NOT EXISTS bluetooth_type TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

UPDATE bluetooth_devices
SET id = COALESCE(id, gen_random_uuid()),
    created_at = COALESCE(created_at, first_seen, now()),
    updated_at = COALESCE(updated_at, last_seen, first_seen, now());

CREATE UNIQUE INDEX IF NOT EXISTS idx_bluetooth_devices_id
  ON bluetooth_devices (id) WHERE id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bluetooth_devices_name
  ON bluetooth_devices (lower(device_name)) WHERE device_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_bluetooth_devices_last_seen
  ON bluetooth_devices (last_seen DESC);

ALTER TABLE bluetooth_observations
  ADD COLUMN IF NOT EXISTS location_name TEXT,
  ADD COLUMN IF NOT EXISTS source_name TEXT,
  ADD COLUMN IF NOT EXISTS source_type TEXT,
  ADD COLUMN IF NOT EXISTS observed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS vendor TEXT,
  ADD COLUMN IF NOT EXISTS service_uuids JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS address_type TEXT,
  ADD COLUMN IF NOT EXISTS bluetooth_type TEXT,
  ADD COLUMN IF NOT EXISTS raw_payload JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

UPDATE bluetooth_observations AS observation
SET location_name = location.name
FROM locations AS location
WHERE observation.location_id = location.id
  AND observation.location_name IS NULL;

UPDATE bluetooth_observations
SET source_name = COALESCE(source_name, capture_source, 'legacy_bluetooth'),
    source_type = COALESCE(source_type, 'bluetooth'),
    observed_at = COALESCE(observed_at, time),
    service_uuids = CASE
      WHEN service_uuids IS NOT NULL AND service_uuids <> '[]'::jsonb THEN service_uuids
      WHEN service_uuid IS NOT NULL THEN jsonb_build_array(service_uuid)
      ELSE '[]'::jsonb
    END,
    raw_payload = COALESCE(raw_payload, metadata, '{}'::jsonb),
    created_at = COALESCE(created_at, time, now());

CREATE INDEX IF NOT EXISTS idx_bluetooth_observations_session_observed
  ON bluetooth_observations (measurement_session_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_bluetooth_observations_location_observed
  ON bluetooth_observations (location_name, time DESC);
CREATE INDEX IF NOT EXISTS idx_bluetooth_observations_source_name
  ON bluetooth_observations (source_name, time DESC);

ALTER TABLE bettercap_ble_import_rows
  ADD COLUMN IF NOT EXISTS location_name TEXT,
  ADD COLUMN IF NOT EXISTS source_name TEXT,
  ADD COLUMN IF NOT EXISTS source_file TEXT,
  ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ DEFAULT now(),
  ADD COLUMN IF NOT EXISTS service_uuids JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS address_type TEXT,
  ADD COLUMN IF NOT EXISTS bluetooth_type TEXT,
  ADD COLUMN IF NOT EXISTS first_seen TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS raw_payload JSONB DEFAULT '{}'::jsonb;

UPDATE bettercap_ble_import_rows AS import_row
SET location_name = location.name
FROM locations AS location
WHERE import_row.location_id = location.id
  AND import_row.location_name IS NULL;

UPDATE bettercap_ble_import_rows
SET source_name = COALESCE(source_name, 'bettercap_ble_file_import'),
    imported_at = COALESCE(imported_at, created_at, now()),
    service_uuids = CASE
      WHEN service_uuids IS NOT NULL AND service_uuids <> '[]'::jsonb THEN service_uuids
      WHEN service_uuid IS NOT NULL THEN jsonb_build_array(service_uuid)
      ELSE '[]'::jsonb
    END,
    first_seen = COALESCE(first_seen, measured_at),
    last_seen = COALESCE(last_seen, measured_at),
    raw_payload = COALESCE(raw_payload, raw_row, '{}'::jsonb);

CREATE INDEX IF NOT EXISTS idx_bettercap_ble_import_session_time
  ON bettercap_ble_import_rows (measurement_session_id, imported_at DESC);
CREATE INDEX IF NOT EXISTS idx_bettercap_ble_import_mac_time
  ON bettercap_ble_import_rows (mac_address, imported_at DESC);
CREATE INDEX IF NOT EXISTS idx_bettercap_ble_import_location_time
  ON bettercap_ble_import_rows (location_name, imported_at DESC);

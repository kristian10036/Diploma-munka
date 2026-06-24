-- Forward-only: Wi-Fi management-frame summary counters and a Wi-Fi/Bluetooth
-- device baseline (room/location reference), separate from the spectrum
-- reference system. No existing column, table, or row is dropped or rewritten.
-- Rollback note: to roll back, drop only the objects this file creates
-- (the management_frame_counts column and the device_baselines table plus its
-- indexes). No other migration or data is touched.

ALTER TABLE wifi_devices
  ADD COLUMN IF NOT EXISTS management_frame_counts JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE wifi_devices
SET management_frame_counts = '{}'::jsonb
WHERE management_frame_counts IS NULL;

CREATE TABLE IF NOT EXISTS device_baselines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT NOT NULL,
  protocol TEXT NOT NULL CHECK (protocol IN ('wifi', 'bluetooth')),
  stable_identity TEXT NOT NULL,
  identity_confidence TEXT NOT NULL DEFAULT 'unknown',
  mac_address TEXT,
  device_name TEXT,
  vendor TEXT,
  device_type TEXT,
  ssid TEXT,
  encryption TEXT,
  typical_channel INTEGER,
  typical_frequency_hz BIGINT,
  typical_rssi_min_dbm DOUBLE PRECISION,
  typical_rssi_max_dbm DOUBLE PRECISION,
  bluetooth_company_id INTEGER,
  service_uuid_fingerprint TEXT,
  manufacturer_data_hash TEXT,
  first_seen TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  user_alias TEXT,
  notes TEXT,
  expected_state TEXT NOT NULL DEFAULT 'expected' CHECK (expected_state IN ('expected', 'ignored')),
  version INTEGER NOT NULL DEFAULT 1,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deactivated_at TIMESTAMPTZ,
  created_by TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_device_baselines_active_lookup
  ON device_baselines (location_name, protocol, is_active, stable_identity);
CREATE INDEX IF NOT EXISTS idx_device_baselines_location_version
  ON device_baselines (location_name, protocol, version DESC);
CREATE INDEX IF NOT EXISTS idx_device_baselines_last_seen
  ON device_baselines (last_seen DESC);

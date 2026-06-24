-- Forward-only Bluetooth/BLE vendor resolution metadata.
-- Rollback note: keep these columns unless a full export confirms the metadata is unused.

ALTER TABLE bluetooth_devices
  ADD COLUMN IF NOT EXISTS vendor_resolution_method TEXT DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS vendor_confidence TEXT DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS bluetooth_company_id INTEGER,
  ADD COLUMN IF NOT EXISTS manufacturer_data_hash TEXT;

ALTER TABLE bluetooth_observations
  ADD COLUMN IF NOT EXISTS vendor_resolution_method TEXT DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS vendor_confidence TEXT DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS bluetooth_company_id INTEGER,
  ADD COLUMN IF NOT EXISTS manufacturer_data_hash TEXT;

UPDATE bluetooth_devices
SET vendor_resolution_method = COALESCE(NULLIF(vendor_resolution_method, ''), CASE WHEN vendor IS NULL THEN 'unknown' ELSE 'kismet' END),
    vendor_confidence = COALESCE(NULLIF(vendor_confidence, ''), CASE WHEN vendor IS NULL THEN 'unknown' ELSE 'medium' END);

UPDATE bluetooth_observations
SET vendor_resolution_method = COALESCE(NULLIF(vendor_resolution_method, ''), CASE WHEN vendor IS NULL THEN 'unknown' ELSE source_type END, 'unknown'),
    vendor_confidence = COALESCE(NULLIF(vendor_confidence, ''), CASE WHEN vendor IS NULL THEN 'unknown' ELSE 'medium' END);

CREATE INDEX IF NOT EXISTS idx_bluetooth_devices_vendor_resolution
  ON bluetooth_devices (vendor_resolution_method, vendor_confidence);

CREATE INDEX IF NOT EXISTS idx_bluetooth_observations_company_time
  ON bluetooth_observations (bluetooth_company_id, time DESC)
  WHERE bluetooth_company_id IS NOT NULL;


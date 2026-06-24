BEGIN;
CREATE TABLE IF NOT EXISTS spectrum_references (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_key TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT,
  device_name TEXT,
  source_type TEXT,
  antenna TEXT,
  downconverter_profile TEXT,
  start_frequency_hz BIGINT NOT NULL,
  stop_frequency_hz BIGINT NOT NULL,
  step_frequency_hz BIGINT,
  rbw_hz DOUBLE PRECISION,
  vbw_hz DOUBLE PRECISION,
  measured_at TIMESTAMPTZ,
  operator_name TEXT,
  notes TEXT,
  checksum_sha256 TEXT NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  is_active BOOLEAN NOT NULL DEFAULT false,
  valid_from TIMESTAMPTZ,
  valid_until TIMESTAMPTZ,
  creation_source TEXT NOT NULL CHECK (creation_source IN ('live','import','replay','converted')),
  original_filename TEXT,
  import_format TEXT NOT NULL,
  point_count INTEGER NOT NULL CHECK (point_count > 0),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ,
  UNIQUE (reference_key, version),
  CHECK (stop_frequency_hz > start_frequency_hz),
  CHECK (step_frequency_hz IS NULL OR step_frequency_hz > 0),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from < valid_until)
);
CREATE INDEX IF NOT EXISTS idx_spectrum_references_active_location
  ON spectrum_references (location_id, is_active, updated_at DESC) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_spectrum_references_key_version
  ON spectrum_references (reference_key, version DESC);
COMMIT;

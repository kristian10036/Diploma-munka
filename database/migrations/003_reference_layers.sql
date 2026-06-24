CREATE TABLE IF NOT EXISTS reference_bands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name TEXT NOT NULL,
  version TEXT,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT NOT NULL,
  start_hz BIGINT NOT NULL,
  end_hz BIGINT NOT NULL,
  band_name TEXT NOT NULL,
  expected_devices TEXT,
  normal_min_dbm DOUBLE PRECISION,
  normal_max_dbm DOUBLE PRECISION,
  priority INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_hz > start_hz)
);

CREATE INDEX IF NOT EXISTS idx_reference_bands_location_range
  ON reference_bands (location_id, start_hz, end_hz);

CREATE INDEX IF NOT EXISTS idx_reference_bands_priority
  ON reference_bands (priority DESC, start_hz);

CREATE TABLE IF NOT EXISTS reference_spectrum_points (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  time TIMESTAMPTZ NOT NULL,
  reference_id TEXT NOT NULL,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT NOT NULL,
  device_name TEXT,
  source_file TEXT,
  measured_frequency_hz BIGINT NOT NULL,
  actual_rf_frequency_hz BIGINT,
  power_dbm DOUBLE PRECISION NOT NULL,
  rbw_hz BIGINT,
  vbw_hz BIGINT,
  antenna TEXT,
  downconverter_profile TEXT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id, time)
);

SELECT create_hypertable('reference_spectrum_points', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_reference_spectrum_points_reference_freq
  ON reference_spectrum_points (reference_id, actual_rf_frequency_hz, measured_frequency_hz);

CREATE INDEX IF NOT EXISTS idx_reference_spectrum_points_location_freq_time
  ON reference_spectrum_points (location_id, actual_rf_frequency_hz, time DESC);

CREATE TABLE IF NOT EXISTS reference_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT,
  source_name TEXT,
  version TEXT,
  original_filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  sha256 TEXT NOT NULL,
  start_hz BIGINT NOT NULL,
  end_hz BIGINT NOT NULL,
  min_dbm DOUBLE PRECISION NOT NULL,
  max_dbm DOUBLE PRECISION NOT NULL,
  is_calibrated BOOLEAN NOT NULL DEFAULT TRUE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_hz > start_hz),
  CHECK (max_dbm > min_dbm)
);

CREATE INDEX IF NOT EXISTS idx_reference_images_location_range
  ON reference_images (location_id, start_hz, end_hz);

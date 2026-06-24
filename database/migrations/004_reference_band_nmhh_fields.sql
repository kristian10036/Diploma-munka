ALTER TABLE reference_bands
  ADD COLUMN IF NOT EXISTS external_band_id TEXT,
  ADD COLUMN IF NOT EXISTS source_file TEXT,
  ADD COLUMN IF NOT EXISTS source_pdf_page INTEGER,
  ADD COLUMN IF NOT EXISTS reference_profile TEXT,
  ADD COLUMN IF NOT EXISTS confidence TEXT,
  ADD COLUMN IF NOT EXISTS peak_alarm_dbm DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS anomaly_delta_db_above_baseline DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS requires_site_baseline BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS manual_site_baseline_allowed BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS normal_values_are_temporary BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_reference_bands_external_band_id
  ON reference_bands (external_band_id);

CREATE TABLE IF NOT EXISTS reference_band_site_baselines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_band_id UUID REFERENCES reference_bands(id) ON DELETE CASCADE,
  external_band_id TEXT,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT NOT NULL,
  normal_min_dbm DOUBLE PRECISION,
  normal_max_dbm DOUBLE PRECISION,
  measured_noise_floor_dbm DOUBLE PRECISION,
  measured_average_dbm DOUBLE PRECISION,
  measured_max_peak_dbm DOUBLE PRECISION,
  peak_alarm_dbm DOUBLE PRECISION,
  anomaly_delta_db DOUBLE PRECISION,
  measurement_device TEXT,
  antenna TEXT,
  rbw_hz BIGINT,
  vbw_hz BIGINT,
  detector TEXT,
  downconverter_profile TEXT,
  measured_at TIMESTAMPTZ,
  operator_name TEXT,
  confidence TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reference_band_site_baselines_band_location
  ON reference_band_site_baselines (reference_band_id, location_id);

CREATE INDEX IF NOT EXISTS idx_reference_band_site_baselines_external_location
  ON reference_band_site_baselines (external_band_id, location_id);

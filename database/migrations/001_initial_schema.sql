CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT NOT NULL UNIQUE,
  display_name TEXT,
  role TEXT NOT NULL DEFAULT 'viewer',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS locations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  address TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS measurement_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  vendor TEXT,
  model TEXT,
  serial_number TEXT,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sdr_devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES measurement_sources(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  device_type TEXT NOT NULL,
  vendor TEXT,
  model TEXT,
  serial_number TEXT,
  min_frequency_hz BIGINT,
  max_frequency_hz BIGINT,
  max_instant_bandwidth_hz BIGINT,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS downconverter_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID REFERENCES sdr_devices(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  lo_frequency_hz BIGINT NOT NULL,
  offset_hz BIGINT NOT NULL DEFAULT 0,
  correction_formula TEXT,
  valid_from_hz BIGINT,
  valid_to_hz BIGINT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calibration_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID REFERENCES sdr_devices(id) ON DELETE SET NULL,
  downconverter_profile_id UUID REFERENCES downconverter_profiles(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  calibration_date DATE,
  gain_offset_db DOUBLE PRECISION NOT NULL DEFAULT 0,
  correction_points JSONB NOT NULL DEFAULT '[]'::jsonb,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS measurement_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  source_id UUID REFERENCES measurement_sources(id) ON DELETE SET NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ,
  mode TEXT NOT NULL DEFAULT 'spectrum',
  title TEXT,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS reference_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  description TEXT,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reference_measurements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_profile_id UUID REFERENCES reference_profiles(id) ON DELETE SET NULL,
  session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  start_frequency_hz BIGINT,
  end_frequency_hz BIGINT,
  bin_width_hz BIGINT,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS frequency_bands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  reference_measurement_id UUID REFERENCES reference_measurements(id) ON DELETE SET NULL,
  start_frequency_hz BIGINT NOT NULL,
  end_frequency_hz BIGINT NOT NULL,
  name TEXT NOT NULL,
  services TEXT,
  expected_devices TEXT,
  normal_min_dbm DOUBLE PRECISION,
  normal_max_dbm DOUBLE PRECISION,
  source TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_frequency_hz > start_frequency_hz)
);

CREATE TABLE IF NOT EXISTS spectrum_samples (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  time TIMESTAMPTZ NOT NULL,
  session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  source_id UUID REFERENCES measurement_sources(id) ON DELETE SET NULL,
  device_id UUID REFERENCES sdr_devices(id) ON DELETE SET NULL,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  calibration_profile_id UUID REFERENCES calibration_profiles(id) ON DELETE SET NULL,
  downconverter_profile_id UUID REFERENCES downconverter_profiles(id) ON DELETE SET NULL,
  measured_frequency_hz BIGINT NOT NULL,
  actual_rf_frequency_hz BIGINT,
  lo_frequency_hz BIGINT,
  offset_hz BIGINT,
  power_dbm DOUBLE PRECISION NOT NULL,
  bandwidth_hz BIGINT,
  sample_index INTEGER,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, time)
);

SELECT create_hypertable('spectrum_samples', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS spectrum_peaks (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  time TIMESTAMPTZ NOT NULL,
  session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  source_id UUID REFERENCES measurement_sources(id) ON DELETE SET NULL,
  device_id UUID REFERENCES sdr_devices(id) ON DELETE SET NULL,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  peak_type TEXT NOT NULL,
  frequency_hz BIGINT NOT NULL,
  power_dbm DOUBLE PRECISION NOT NULL,
  window_start TIMESTAMPTZ,
  window_end TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, time)
);

SELECT create_hypertable('spectrum_peaks', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS anomalies (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  time TIMESTAMPTZ NOT NULL,
  session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  frequency_band_id UUID REFERENCES frequency_bands(id) ON DELETE SET NULL,
  anomaly_type TEXT NOT NULL,
  severity SMALLINT NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'open',
  frequency_hz BIGINT,
  measured_power_dbm DOUBLE PRECISION,
  expected_min_dbm DOUBLE PRECISION,
  expected_max_dbm DOUBLE PRECISION,
  delta_db DOUBLE PRECISION,
  description TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, time)
);

SELECT create_hypertable('anomalies', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS wifi_devices (
  bssid TEXT PRIMARY KEY,
  ssid TEXT,
  vendor TEXT,
  encryption TEXT,
  first_seen TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS wifi_observations (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  time TIMESTAMPTZ NOT NULL,
  bssid TEXT REFERENCES wifi_devices(bssid) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  source_id UUID REFERENCES measurement_sources(id) ON DELETE SET NULL,
  ssid TEXT,
  channel INTEGER,
  frequency_hz BIGINT,
  rssi_dbm DOUBLE PRECISION,
  packet_count BIGINT,
  observation_count BIGINT NOT NULL DEFAULT 1,
  capture_source TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, time)
);

SELECT create_hypertable('wifi_observations', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS bluetooth_devices (
  mac_address TEXT PRIMARY KEY,
  device_name TEXT,
  vendor TEXT,
  first_seen TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS bluetooth_observations (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  time TIMESTAMPTZ NOT NULL,
  mac_address TEXT REFERENCES bluetooth_devices(mac_address) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  source_id UUID REFERENCES measurement_sources(id) ON DELETE SET NULL,
  device_name TEXT,
  service_uuid TEXT,
  rssi_dbm DOUBLE PRECISION,
  observation_count BIGINT NOT NULL DEFAULT 1,
  capture_source TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (id, time)
);

SELECT create_hypertable('bluetooth_observations', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS csv_imports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  uploaded_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
  original_filename TEXT NOT NULL,
  import_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  total_rows INTEGER NOT NULL DEFAULT 0,
  processed_rows INTEGER NOT NULL DEFAULT 0,
  failed_rows INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS uploaded_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE SET NULL,
  original_filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  content_type TEXT,
  size_bytes BIGINT,
  sha256 TEXT,
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  document_type TEXT NOT NULL,
  source TEXT,
  content TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE,
  embedding_model TEXT NOT NULL,
  dimensions INTEGER,
  embedding DOUBLE PRECISION[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_frequency_bands_range ON frequency_bands (start_frequency_hz, end_frequency_hz);
CREATE INDEX IF NOT EXISTS idx_spectrum_samples_time_freq ON spectrum_samples (time DESC, actual_rf_frequency_hz);
CREATE INDEX IF NOT EXISTS idx_spectrum_samples_session_time ON spectrum_samples (session_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_spectrum_peaks_type_time ON spectrum_peaks (peak_type, time DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_status_time ON anomalies (status, time DESC);
CREATE INDEX IF NOT EXISTS idx_wifi_observations_bssid_time ON wifi_observations (bssid, time DESC);
CREATE INDEX IF NOT EXISTS idx_bluetooth_observations_mac_time ON bluetooth_observations (mac_address, time DESC);

CREATE TABLE IF NOT EXISTS import_error_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  device_type TEXT NOT NULL,
  row_number INTEGER NOT NULL,
  error_message TEXT NOT NULL,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS oscor_import_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measured_at TIMESTAMPTZ,
  row_number INTEGER NOT NULL,
  frequency_hz BIGINT,
  power_dbm DOUBLE PRECISION,
  bandwidth_hz BIGINT,
  signal_label TEXT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ddf_import_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measured_at TIMESTAMPTZ,
  row_number INTEGER NOT NULL,
  frequency_hz BIGINT,
  power_dbm DOUBLE PRECISION,
  azimuth_deg DOUBLE PRECISION,
  bearing_deg DOUBLE PRECISION,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pr100_import_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measured_at TIMESTAMPTZ,
  row_number INTEGER NOT NULL,
  frequency_hz BIGINT,
  power_dbm DOUBLE PRECISION,
  modulation TEXT,
  bandwidth_hz BIGINT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mesa_import_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measured_at TIMESTAMPTZ,
  row_number INTEGER NOT NULL,
  frequency_hz BIGINT,
  power_dbm DOUBLE PRECISION,
  signal_label TEXT,
  classification TEXT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kismet_import_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measured_at TIMESTAMPTZ,
  row_number INTEGER NOT NULL,
  mac_address TEXT,
  ssid TEXT,
  channel INTEGER,
  frequency_hz BIGINT,
  rssi_dbm DOUBLE PRECISION,
  vendor TEXT,
  encryption TEXT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bettercap_ble_import_rows (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  csv_import_id UUID REFERENCES csv_imports(id) ON DELETE CASCADE,
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measured_at TIMESTAMPTZ,
  row_number INTEGER NOT NULL,
  mac_address TEXT,
  device_name TEXT,
  rssi_dbm DOUBLE PRECISION,
  vendor TEXT,
  service_uuid TEXT,
  raw_row JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_import_errors_import ON import_error_rows (csv_import_id, row_number);
CREATE INDEX IF NOT EXISTS idx_oscor_import_location_time ON oscor_import_rows (location_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_ddf_import_location_time ON ddf_import_rows (location_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_pr100_import_location_time ON pr100_import_rows (location_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_mesa_import_location_time ON mesa_import_rows (location_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_kismet_import_mac_location ON kismet_import_rows (mac_address, location_id);
CREATE INDEX IF NOT EXISTS idx_bettercap_ble_import_mac_location ON bettercap_ble_import_rows (mac_address, location_id);

BEGIN;

ALTER TABLE spectrum_markers
  ADD COLUMN IF NOT EXISTS location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS category TEXT,
  ADD COLUMN IF NOT EXISTS color TEXT,
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_spectrum_markers_active_time
  ON spectrum_markers (created_at DESC) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_spectrum_markers_location
  ON spectrum_markers (location_id, created_at DESC);

CREATE TABLE IF NOT EXISTS known_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
  measurement_session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  center_frequency_hz BIGINT NOT NULL CHECK (center_frequency_hz > 0),
  frequency_tolerance_hz BIGINT NOT NULL CHECK (frequency_tolerance_hz > 0),
  bandwidth_hz BIGINT CHECK (bandwidth_hz IS NULL OR bandwidth_hz > 0),
  expected_power_min_dbm DOUBLE PRECISION,
  expected_power_max_dbm DOUBLE PRECISION,
  modulation TEXT,
  protocol TEXT,
  source_type TEXT,
  label TEXT NOT NULL CHECK (length(btrim(label)) BETWEEN 1 AND 200),
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'expired')),
  suppress_alerts BOOLEAN NOT NULL DEFAULT false,
  valid_from TIMESTAMPTZ,
  valid_until TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ,
  CHECK (expected_power_min_dbm IS NULL OR expected_power_max_dbm IS NULL OR expected_power_min_dbm <= expected_power_max_dbm),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from < valid_until)
);

CREATE INDEX IF NOT EXISTS idx_known_signals_frequency_active
  ON known_signals (center_frequency_hz) WHERE archived_at IS NULL AND status = 'active';
CREATE INDEX IF NOT EXISTS idx_known_signals_location_status
  ON known_signals (location_id, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_known_signals_session
  ON known_signals (measurement_session_id, updated_at DESC);

ALTER TABLE rf_detections
  ADD COLUMN IF NOT EXISTS known_signal_id UUID REFERENCES known_signals(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS disposition TEXT NOT NULL DEFAULT 'new',
  ADD COLUMN IF NOT EXISTS review_notes TEXT,
  ADD COLUMN IF NOT EXISTS suppression_reason TEXT,
  ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS reviewed_by TEXT,
  ADD COLUMN IF NOT EXISTS include_in_training BOOLEAN;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'rf_detections_disposition_check'
      AND conrelid = 'rf_detections'::regclass
  ) THEN
    ALTER TABLE rf_detections ADD CONSTRAINT rf_detections_disposition_check
      CHECK (disposition IN ('new', 'known', 'changed', 'false_positive', 'reviewed')) NOT VALID;
  END IF;
END
$$;
ALTER TABLE rf_detections VALIDATE CONSTRAINT rf_detections_disposition_check;
CREATE INDEX IF NOT EXISTS idx_rf_detections_known_signal
  ON rf_detections (known_signal_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_detections_disposition
  ON rf_detections (disposition, detected_at DESC);

COMMIT;

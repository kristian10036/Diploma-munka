BEGIN;

CREATE TABLE IF NOT EXISTS reference_sets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_key TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  name TEXT NOT NULL,
  location_id UUID NULL REFERENCES locations(id) ON DELETE SET NULL,
  location_name TEXT NOT NULL,
  source_measurement_session_id UUID NULL REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  capture_started_at TIMESTAMPTZ NULL,
  capture_ended_at TIMESTAMPTZ NULL,
  status TEXT NOT NULL CHECK (status IN ('draft', 'ready', 'archived')),
  is_active BOOLEAN NOT NULL DEFAULT false,
  created_by TEXT NULL,
  notes TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ NULL,
  UNIQUE (reference_key, version)
);

CREATE INDEX IF NOT EXISTS idx_reference_sets_location_active
  ON reference_sets (location_name, is_active, updated_at DESC)
  WHERE archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_reference_sets_location_id_active
  ON reference_sets (location_id, is_active, updated_at DESC)
  WHERE archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_reference_sets_session
  ON reference_sets (source_measurement_session_id);

ALTER TABLE spectrum_references
  ADD COLUMN IF NOT EXISTS reference_set_id UUID NULL REFERENCES reference_sets(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID NULL REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS reference_kind TEXT NULL,
  ADD COLUMN IF NOT EXISTS window_start TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS window_end TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS frame_count BIGINT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'spectrum_references_reference_kind_check'
      AND conrelid = 'spectrum_references'::regclass
  ) THEN
    ALTER TABLE spectrum_references
      ADD CONSTRAINT spectrum_references_reference_kind_check
      CHECK (reference_kind IS NULL OR reference_kind IN ('snapshot', 'max_hold', 'imported', 'replay'))
      NOT VALID;
  END IF;
END $$;

ALTER TABLE spectrum_references
  VALIDATE CONSTRAINT spectrum_references_reference_kind_check;

CREATE INDEX IF NOT EXISTS idx_spectrum_references_reference_set
  ON spectrum_references (reference_set_id);

CREATE INDEX IF NOT EXISTS idx_spectrum_references_measurement_session
  ON spectrum_references (measurement_session_id);

CREATE INDEX IF NOT EXISTS idx_spectrum_references_kind
  ON spectrum_references (reference_kind);

ALTER TABLE device_baselines
  ADD COLUMN IF NOT EXISTS reference_set_id UUID NULL REFERENCES reference_sets(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS source_measurement_session_id UUID NULL REFERENCES measurement_sessions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_device_baselines_reference_set
  ON device_baselines (reference_set_id);

CREATE INDEX IF NOT EXISTS idx_device_baselines_source_session
  ON device_baselines (source_measurement_session_id);

COMMIT;

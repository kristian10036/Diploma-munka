-- Phase 2 keeps the existing UUID identifiers because multiple tables already
-- reference them. Converting them to BIGSERIAL would be destructive.

ALTER TABLE measurement_sessions
  ADD COLUMN IF NOT EXISTS location_name TEXT,
  ADD COLUMN IF NOT EXISTS operator_name TEXT,
  ADD COLUMN IF NOT EXISTS environment_description TEXT,
  ADD COLUMN IF NOT EXISTS status TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE measurement_sessions AS session
SET location_name = location.name
FROM locations AS location
WHERE session.location_id = location.id
  AND (session.location_name IS NULL OR btrim(session.location_name) = '');

-- Preserve legacy rows whose location reference is missing while making the
-- unknown origin explicit instead of inventing a real location.
UPDATE measurement_sessions
SET location_name = 'legacy-unknown-' || left(id::text, 8)
WHERE location_name IS NULL OR btrim(location_name) = '';

UPDATE measurement_sessions
SET status = CASE WHEN ended_at IS NULL THEN 'active' ELSE 'stopped' END
WHERE status IS NULL OR status NOT IN ('active', 'stopped', 'archived');

UPDATE measurement_sessions
SET created_at = COALESCE(created_at, started_at, now()),
    updated_at = COALESCE(updated_at, ended_at, started_at, now());

ALTER TABLE measurement_sessions
  ALTER COLUMN location_name SET NOT NULL,
  ALTER COLUMN status SET DEFAULT 'active',
  ALTER COLUMN status SET NOT NULL,
  ALTER COLUMN created_at SET DEFAULT now(),
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET DEFAULT now(),
  ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'measurement_sessions_status_check'
      AND conrelid = 'measurement_sessions'::regclass
  ) THEN
    ALTER TABLE measurement_sessions
      ADD CONSTRAINT measurement_sessions_status_check
      CHECK (status IN ('active', 'stopped', 'archived')) NOT VALID;
  END IF;
END
$$;

ALTER TABLE measurement_sessions
  VALIDATE CONSTRAINT measurement_sessions_status_check;

CREATE INDEX IF NOT EXISTS idx_measurement_sessions_location_name
  ON measurement_sessions (location_name);
CREATE INDEX IF NOT EXISTS idx_measurement_sessions_started_at
  ON measurement_sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_measurement_sessions_status
  ON measurement_sessions (status);

ALTER TABLE measurement_sources
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID,
  ADD COLUMN IF NOT EXISTS source_name TEXT,
  ADD COLUMN IF NOT EXISTS device_name TEXT,
  ADD COLUMN IF NOT EXISTS adapter_name TEXT,
  ADD COLUMN IF NOT EXISTS status TEXT,
  ADD COLUMN IF NOT EXISTS config JSONB,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE measurement_sources
SET source_name = COALESCE(NULLIF(btrim(source_name), ''), name),
    status = COALESCE(NULLIF(btrim(status), ''), 'configured'),
    config = COALESCE(config, metadata, '{}'::jsonb),
    updated_at = COALESCE(updated_at, created_at, now());

ALTER TABLE measurement_sources
  ALTER COLUMN source_name SET NOT NULL,
  ALTER COLUMN status SET DEFAULT 'configured',
  ALTER COLUMN status SET NOT NULL,
  ALTER COLUMN config SET DEFAULT '{}'::jsonb,
  ALTER COLUMN config SET NOT NULL,
  ALTER COLUMN updated_at SET DEFAULT now(),
  ALTER COLUMN updated_at SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'measurement_sources_session_fk'
      AND conrelid = 'measurement_sources'::regclass
  ) THEN
    ALTER TABLE measurement_sources
      ADD CONSTRAINT measurement_sources_session_fk
      FOREIGN KEY (measurement_session_id)
      REFERENCES measurement_sessions(id) ON DELETE CASCADE;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_measurement_sources_session
  ON measurement_sources (measurement_session_id);
CREATE INDEX IF NOT EXISTS idx_measurement_sources_type
  ON measurement_sources (source_type);
CREATE INDEX IF NOT EXISTS idx_measurement_sources_source_name
  ON measurement_sources (source_name);

-- Spectrum samples, peaks and anomalies already use their legacy session_id
-- UUID columns. Add nullable links only to tables that do not have one yet.
ALTER TABLE wifi_observations
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE bluetooth_observations
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE IF EXISTS oscor_import_rows
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE IF EXISTS ddf_import_rows
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE IF EXISTS pr100_import_rows
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE IF EXISTS mesa_import_rows
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE IF EXISTS kismet_import_rows
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;
ALTER TABLE IF EXISTS bettercap_ble_import_rows
  ADD COLUMN IF NOT EXISTS measurement_session_id UUID;

DO $$
DECLARE
  target_table TEXT;
  constraint_name TEXT;
BEGIN
  FOREACH target_table IN ARRAY ARRAY[
    'wifi_observations',
    'bluetooth_observations',
    'oscor_import_rows',
    'ddf_import_rows',
    'pr100_import_rows',
    'mesa_import_rows',
    'kismet_import_rows',
    'bettercap_ble_import_rows'
  ]
  LOOP
    constraint_name := target_table || '_measurement_session_fk';
    IF to_regclass('public.' || target_table) IS NOT NULL
       AND NOT EXISTS (
         SELECT 1 FROM pg_constraint
         WHERE conname = constraint_name
           AND conrelid = to_regclass('public.' || target_table)
       ) THEN
      EXECUTE format(
        'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (measurement_session_id) REFERENCES measurement_sessions(id) ON DELETE SET NULL',
        target_table,
        constraint_name
      );
    END IF;
  END LOOP;
END
$$;

DO $$
DECLARE
  target_table TEXT;
  index_name TEXT;
BEGIN
  FOREACH target_table IN ARRAY ARRAY[
    'wifi_observations',
    'bluetooth_observations',
    'oscor_import_rows',
    'ddf_import_rows',
    'pr100_import_rows',
    'mesa_import_rows',
    'kismet_import_rows',
    'bettercap_ble_import_rows'
  ]
  LOOP
    IF to_regclass('public.' || target_table) IS NOT NULL THEN
      index_name := 'idx_' || target_table || '_measurement_session';
      EXECUTE format(
        'CREATE INDEX IF NOT EXISTS %I ON %I (measurement_session_id)',
        index_name,
        target_table
      );
    END IF;
  END LOOP;
END
$$;


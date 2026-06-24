-- Operational metadata required by the RF/ML/assistant control plane.
-- Full IQ and full-resolution spectrum recordings remain on the filesystem.

CREATE TABLE IF NOT EXISTS spectrum_markers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  measurement_session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  recording_id TEXT REFERENCES spectrum_recordings(recording_id) ON DELETE SET NULL,
  frequency_hz BIGINT NOT NULL CHECK (frequency_hz > 0),
  power_dbm DOUBLE PRECISION,
  label TEXT NOT NULL,
  notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_spectrum_markers_frequency
  ON spectrum_markers (frequency_hz);
CREATE INDEX IF NOT EXISTS idx_spectrum_markers_session
  ON spectrum_markers (measurement_session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_spectrum_markers_recording
  ON spectrum_markers (recording_id, created_at DESC);

CREATE TABLE IF NOT EXISTS rf_detections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  measurement_session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  recording_id TEXT REFERENCES spectrum_recordings(recording_id) ON DELETE SET NULL,
  source_type TEXT,
  model_name TEXT,
  model_version TEXT,
  class_name TEXT NOT NULL,
  confidence DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  start_frequency_hz BIGINT,
  stop_frequency_hz BIGINT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (start_frequency_hz IS NULL OR start_frequency_hz >= 0),
  CHECK (stop_frequency_hz IS NULL OR start_frequency_hz IS NULL OR stop_frequency_hz >= start_frequency_hz)
);

CREATE INDEX IF NOT EXISTS idx_rf_detections_time
  ON rf_detections (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_detections_session
  ON rf_detections (measurement_session_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_detections_recording
  ON rf_detections (recording_id, detected_at DESC);

CREATE TABLE IF NOT EXISTS system_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at TIMESTAMPTZ,
  severity TEXT NOT NULL DEFAULT 'info',
  status TEXT NOT NULL DEFAULT 'open',
  source TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  CHECK (severity IN ('info', 'warning', 'error', 'critical')),
  CHECK (status IN ('open', 'acknowledged', 'resolved'))
);

CREATE INDEX IF NOT EXISTS idx_system_alerts_open
  ON system_alerts (status, severity, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor TEXT NOT NULL DEFAULT 'system',
  event_type TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  success BOOLEAN NOT NULL DEFAULT true,
  details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_events_time
  ON audit_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_entity
  ON audit_events (entity_type, entity_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_type
  ON audit_events (event_type, occurred_at DESC);

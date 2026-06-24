BEGIN;

ALTER TABLE rf_detections
  ADD COLUMN IF NOT EXISTS entity_domain TEXT NOT NULL DEFAULT 'spectrum',
  ADD COLUMN IF NOT EXISTS detector_name TEXT,
  ADD COLUMN IF NOT EXISTS detector_version TEXT,
  ADD COLUMN IF NOT EXISTS severity TEXT NOT NULL DEFAULT 'info',
  ADD COLUMN IF NOT EXISTS explanation TEXT,
  ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'rf_detections_entity_domain_check'
      AND conrelid = 'rf_detections'::regclass
  ) THEN
    ALTER TABLE rf_detections ADD CONSTRAINT rf_detections_entity_domain_check
      CHECK (entity_domain IN ('spectrum', 'wifi', 'bluetooth', 'technical')) NOT VALID;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'rf_detections_severity_check'
      AND conrelid = 'rf_detections'::regclass
  ) THEN
    ALTER TABLE rf_detections ADD CONSTRAINT rf_detections_severity_check
      CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')) NOT VALID;
  END IF;
END
$$;
ALTER TABLE rf_detections VALIDATE CONSTRAINT rf_detections_entity_domain_check;
ALTER TABLE rf_detections VALIDATE CONSTRAINT rf_detections_severity_check;
CREATE INDEX IF NOT EXISTS idx_rf_detections_domain_time
  ON rf_detections (entity_domain, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_detections_review_queue
  ON rf_detections (disposition, severity, detected_at DESC);

ALTER TABLE system_alerts
  ADD COLUMN IF NOT EXISTS domain TEXT NOT NULL DEFAULT 'technical',
  ADD COLUMN IF NOT EXISTS assignee TEXT,
  ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS acknowledged_by TEXT,
  ADD COLUMN IF NOT EXISTS acknowledgement_note TEXT,
  ADD COLUMN IF NOT EXISTS resolved_by TEXT,
  ADD COLUMN IF NOT EXISTS resolution_note TEXT,
  ADD COLUMN IF NOT EXISTS deduplication_key TEXT,
  ADD COLUMN IF NOT EXISTS occurrence_count BIGINT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS suppression_until TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rf_detection_id UUID REFERENCES rf_detections(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'system_alerts_domain_check'
      AND conrelid = 'system_alerts'::regclass
  ) THEN
    ALTER TABLE system_alerts ADD CONSTRAINT system_alerts_domain_check
      CHECK (domain IN ('technical', 'rf_security', 'wifi_security', 'bluetooth_security')) NOT VALID;
  END IF;
END
$$;
ALTER TABLE system_alerts VALIDATE CONSTRAINT system_alerts_domain_check;
CREATE UNIQUE INDEX IF NOT EXISTS idx_system_alerts_active_dedup
  ON system_alerts (deduplication_key)
  WHERE deduplication_key IS NOT NULL AND status IN ('open', 'acknowledged');
CREATE INDEX IF NOT EXISTS idx_system_alerts_domain_status
  ON system_alerts (domain, status, severity, last_seen_at DESC);

COMMIT;

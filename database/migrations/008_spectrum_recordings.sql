CREATE TABLE IF NOT EXISTS spectrum_recordings (
  recording_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  measurement_session_id UUID REFERENCES measurement_sessions(id) ON DELETE SET NULL,
  sensor_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_device TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'completed',
  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  first_frame_timestamp TIMESTAMPTZ,
  last_frame_timestamp TIMESTAMPTZ,
  frame_count BIGINT NOT NULL CHECK (frame_count >= 0),
  start_frequency_hz BIGINT NOT NULL CHECK (start_frequency_hz >= 0),
  stop_frequency_hz BIGINT NOT NULL CHECK (stop_frequency_hz >= start_frequency_hz),
  num_points INTEGER NOT NULL CHECK (num_points > 0),
  frame_file TEXT NOT NULL,
  compression TEXT NOT NULL DEFAULT 'zstd',
  checksum_algorithm TEXT NOT NULL DEFAULT 'sha256',
  checksum_sha256 CHAR(64) NOT NULL,
  description TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT spectrum_recordings_source_type_check CHECK (source_type IN ('mock', 'replay', 'aaronia', 'usrp')),
  CONSTRAINT spectrum_recordings_status_check CHECK (status IN ('recording', 'completed', 'failed')),
  CONSTRAINT spectrum_recordings_compression_check CHECK (compression IN ('zstd', 'none')),
  CONSTRAINT spectrum_recordings_checksum_check
    CHECK (checksum_algorithm = 'sha256' AND checksum_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_spectrum_recordings_session ON spectrum_recordings (session_id);
CREATE INDEX IF NOT EXISTS idx_spectrum_recordings_measurement_session ON spectrum_recordings (measurement_session_id);
CREATE INDEX IF NOT EXISTS idx_spectrum_recordings_started_at ON spectrum_recordings (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_spectrum_recordings_source_type ON spectrum_recordings (source_type);

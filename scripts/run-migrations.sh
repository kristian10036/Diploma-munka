#!/usr/bin/env sh
set -eu

script="$(mktemp)"
trap 'rm -f "$script"' EXIT
cat > "$script" <<'SQL'
\set ON_ERROR_STOP on
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  checksum_sha256 CHAR(64) NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SELECT pg_advisory_lock(hashtext('dm-schema-migrations'));
SQL

for migration in /migrations/*.sql; do
  version="$(basename "$migration")"
  checksum="$(sha256sum "$migration" | awk '{print $1}')"
  if grep -Eiq '(^|[[:space:]])(DROP[[:space:]]+(TABLE|COLUMN|SCHEMA|DATABASE)|TRUNCATE)([[:space:]]|$)' "$migration"; then
    [ "${ALLOW_DESTRUCTIVE_MIGRATIONS:-false}" = "true" ] && [ "${BACKUP_CONFIRMED:-false}" = "true" ] || {
      echo "ERROR: destructive migration $version requires ALLOW_DESTRUCTIVE_MIGRATIONS=true and BACKUP_CONFIRMED=true" >&2
      exit 1
    }
  fi
  cat >> "$script" <<SQL
SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = '$version') AS is_applied,
       COALESCE((SELECT checksum_sha256 = '$checksum' FROM schema_migrations WHERE version = '$version'), true) AS checksum_matches
\gset
\if :is_applied
  \if :checksum_matches
    \echo 'Already applied: $version'
  \else
    \echo 'ERROR: checksum mismatch for $version'
    \quit 1
  \endif
\else
  \echo 'Applying $version'
  \i $migration
  INSERT INTO schema_migrations(version, checksum_sha256) VALUES ('$version', '$checksum');
\endif
SQL
done
cat >> "$script" <<'SQL'
SELECT pg_advisory_unlock(hashtext('dm-schema-migrations'));
SQL
psql -f "$script"

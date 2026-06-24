#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env
apply=false; force=false; backup=""
while (($#)); do case "$1" in --apply) apply=true;; --force) force=true;; *) backup="$1";; esac; shift; done
[[ -n "$backup" && -d "$backup" ]] || { echo "Használat: $0 BACKUP_DIR [--apply] [--force]" >&2; exit 2; }
[[ -f "$backup/SHA256SUMS" ]] || { echo "HIBA: SHA256SUMS hiányzik" >&2; exit 1; }
(cd "$backup" && sha256sum -c SHA256SUMS)
echo "Checksum rendben. Mód: $([[ $apply == true ]] && echo APPLY || echo DRY-RUN), force=$force"
[[ $apply == true ]] || { echo "A restore nem módosított adatot."; exit 0; }

if [[ -f "$backup/database/postgres.dump" ]]; then
  existing="$(compose exec -T database psql -U "${POSTGRES_USER:-tscm_app}" -d "${POSTGRES_DB:-tscm_security}" -Atc "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'" | tr -d '[:space:]')"
  if [[ "${existing:-0}" -gt 0 && $force == false ]]; then
    echo "HIBA: az adatbázis nem üres. Használd a --force kapcsolót." >&2; exit 1
  fi
  if [[ $force == true ]]; then
    compose exec -T database pg_restore --clean --if-exists --no-owner \
      -U "${POSTGRES_USER:-tscm_app}" -d "${POSTGRES_DB:-tscm_security}" \
      < "$backup/database/postgres.dump"
  else
    compose exec -T database pg_restore --no-owner \
      -U "${POSTGRES_USER:-tscm_app}" -d "${POSTGRES_DB:-tscm_security}" \
      < "$backup/database/postgres.dump"
  fi
fi
restore_archive() {
  local archive=$1 target=$2 temp extracted_root
  [[ -f "$archive" ]] || return 0
  mkdir -p "$target"
  if [[ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" && $force == false ]]; then
    echo "HIBA: $target nem üres; --force szükséges" >&2
    exit 1
  fi
  temp="$(mktemp -d)"
  trap 'rm -rf "$temp"' RETURN
  tar -xzf "$archive" -C "$temp"
  extracted_root="$(find "$temp" -mindepth 1 -maxdepth 1 -type d -print -quit)"
  [[ -n "$extracted_root" ]] || { echo "HIBA: üres vagy hibás archívum: $archive" >&2; exit 1; }
  if [[ $force == true ]]; then
    find "$target" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  fi
  cp -a "$extracted_root"/. "$target"/
  rm -rf "$temp"
  trap - RETURN
}
restore_archive "$backup/files/recordings.tar.gz" "${RECORDINGS_ROOT:-$PROJECT_ROOT/recordings}"
restore_archive "$backup/files/ml-models.tar.gz" "${ML_MODEL_ROOT:-$PROJECT_ROOT/ml/models}"
restore_archive "$backup/files/ml-data.tar.gz" "${ML_DATA_ROOT:-$PROJECT_ROOT/ml/data}"
echo "Restore befejezve. Futtasd: bash scripts/post-migration-check.sh"

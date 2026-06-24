#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env
apply=false
[[ "${1:-}" == "--apply" ]] && apply=true
root="${BACKUP_ROOT:-$PROJECT_ROOT/backups/runtime}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$root/$stamp"
echo "Backup cél: $destination"
echo "Mód: $([[ $apply == true ]] && echo APPLY || echo DRY-RUN)"
echo "Tartalom: PostgreSQL custom dump, Kismet/uploads/recordings, konfigurációk, migrációk, ML metadata, checksumok."
[[ $apply == true ]] || { echo "Indítás: bash scripts/backup.sh --apply"; exit 0; }
mkdir -p "$destination"/{database,files,config,metadata}
chmod 700 "$destination"

compose exec -T database pg_dump -Fc \
  -U "${POSTGRES_USER:-tscm_app}" -d "${POSTGRES_DB:-tscm_security}" \
  > "$destination/database/postgres.dump"

cp compose*.yaml "$destination/config/" 2>/dev/null || true
cp -a database/migrations "$destination/config/"
cp -a config "$destination/config/project-config"
[[ -d prometheus ]] && cp -a prometheus "$destination/config/prometheus"
for file in README.md RUNNING.md ARCHITECTURE.md BACKUP_RESTORE.md MIGRATION.md; do [[ -f "$file" ]] && cp "$file" "$destination/config/"; done
if [[ -f .env ]]; then install -m 600 .env "$destination/config/env.protected"; fi

archive_path(){ local source=$1 name=$2; [[ -e "$source" ]] || return 0; tar -C "$(dirname "$source")" -czf "$destination/files/$name.tar.gz" "$(basename "$source")"; }
archive_path "${RECORDINGS_ROOT:-$PROJECT_ROOT/recordings}" recordings
archive_path "${ML_MODEL_ROOT:-$PROJECT_ROOT/ml/models}" ml-models
archive_path "${ML_DATA_ROOT:-$PROJECT_ROOT/ml/data}" ml-data
archive_path "${EXPORT_ROOT:-$PROJECT_ROOT/exports}" exports
archive_path "$PROJECT_ROOT/data" project-data

copy_service_path(){ local service=$1 source=$2 name=$3; local id; id="$(compose ps -q "$service" 2>/dev/null || true)"; [[ -n "$id" ]] || return 0; mkdir -p "$destination/files/$name"; docker cp "$id:$source/." "$destination/files/$name/" 2>/dev/null || true; tar -C "$destination/files" -czf "$destination/files/$name.tar.gz" "$name"; rm -rf "$destination/files/$name"; }
copy_service_path backend /app/uploads uploads
copy_service_path kismet /data/kismet kismet

{
  echo "created_at=$stamp"
  echo "project=$(project_name)"
  echo "hostname=$(hostname)"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unavailable)"
  echo "docker_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unavailable)"
  echo "compose_version=$(docker compose version --short 2>/dev/null || echo unavailable)"
} > "$destination/metadata/manifest.txt"
(cd "$destination" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
chmod 600 "$destination/SHA256SUMS"
echo "Backup elkészült: $destination"

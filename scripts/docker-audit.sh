#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require_command docker
project="$(project_name)"

echo "== Projekt =="
echo "root: $PROJECT_ROOT"
echo "compose project: $project"
echo "compose files: ${COMPOSE_FILES[*]}"

echo -e "\n== Compose service-ek =="
compose config --services
mapfile -t services < <(compose config --services)

echo -e "\n== Compose config ellenőrzés =="
compose config --quiet && echo "OK"

echo -e "\n== Projekt containerek =="
docker ps -a --filter "label=com.docker.compose.project=$project" \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}'

echo -e "\n== Futó containerek =="
docker ps --filter "label=com.docker.compose.project=$project" \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'

echo -e "\n== Leállított containerek =="
docker ps -a --filter "label=com.docker.compose.project=$project" --filter status=exited \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Status}}'

echo -e "\n== Orphan gyanús containerek =="
service_csv=",$(IFS=,; echo "${services[*]}"),"
found=0
while IFS=$'\t' read -r id name service; do
  [[ -z "$id" ]] && continue
  if [[ "$service_csv" != *",$service,"* ]]; then
    printf '%s\t%s\tservice=%s\n' "$id" "$name" "$service"
    found=1
  fi
done < <(docker ps -a --filter "label=com.docker.compose.project=$project" \
  --format '{{.ID}}\t{{.Names}}\t{{.Label "com.docker.compose.service"}}')
[[ $found -eq 0 ]] && echo "nincs"

echo -e "\n== Projekt image-ek =="
docker image ls --format '{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}' \
  | awk -F '\t' -v p="$project" '$1 ~ ("^" p "-") || $1 ~ ("^" p "_") {print}' || true

echo -e "\n== Dangling image-ek (csak lista) =="
docker image ls --filter dangling=true --format 'table {{.ID}}\t{{.CreatedSince}}\t{{.Size}}'

echo -e "\n== Projekt networkök =="
docker network ls --filter "label=com.docker.compose.project=$project" \
  --format 'table {{.ID}}\t{{.Name}}\t{{.Driver}}'

echo -e "\n== Projekt volume-ok (SOHA nem törlendők automatikusan) =="
docker volume ls --filter "label=com.docker.compose.project=$project" \
  --format 'table {{.Name}}\t{{.Driver}}'

echo -e "\n== Docker lemezhasználat =="
docker system df

echo -e "\n== Build cache =="
docker builder du 2>/dev/null || echo "build cache adat nem érhető el"

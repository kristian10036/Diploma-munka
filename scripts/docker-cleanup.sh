#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require_command docker
apply=false
include_build_cache=false
for arg in "$@"; do
  case "$arg" in
    --apply) apply=true ;;
    --include-build-cache) include_build_cache=true ;;
    *) echo "Használat: $0 [--apply] [--include-build-cache]" >&2; exit 2 ;;
  esac
done
project="$(project_name)"
mapfile -t services < <(compose config --services)
service_csv=",$(IFS=,; echo "${services[*]}"),"

orphans=()
while IFS=$'\t' read -r id service; do
  [[ -z "$id" ]] && continue
  [[ "$service_csv" == *",$service,"* ]] || orphans+=("$id")
done < <(docker ps -a --filter "label=com.docker.compose.project=$project" \
  --format '{{.ID}}\t{{.Label "com.docker.compose.service"}}')

used_images="$(docker ps -a --format '{{.Image}}' | sort -u)"
old_images=()
while IFS=$'\t' read -r repo tag id; do
  [[ -z "$repo" ]] && continue
  if [[ "$repo" =~ ^${project}[-_] ]] && ! grep -Fxq "$repo:$tag" <<<"$used_images"; then
    old_images+=("$id")
  fi
done < <(docker image ls --format '{{.Repository}}\t{{.Tag}}\t{{.ID}}')

unused_networks=()
while IFS= read -r network_id; do
  [[ -z "$network_id" ]] && continue
  attached="$(docker network inspect -f '{{len .Containers}}' "$network_id" 2>/dev/null || echo 1)"
  [[ "$attached" == 0 ]] && unused_networks+=("$network_id")
done < <(docker network ls --filter "label=com.docker.compose.project=$project" -q)

echo "Mód: $([[ $apply == true ]] && echo APPLY || echo DRY-RUN)"
echo "Orphan containerek: ${orphans[*]:-nincs}"
echo "Nem használt projektimage-ek: ${old_images[*]:-nincs}"
echo "Nem használt projektnetworkök: ${unused_networks[*]:-nincs}"
echo "Volume-okhoz a script nem nyúl."

if [[ $apply == false ]]; then
  echo "Tényleges törléshez: bash scripts/docker-cleanup.sh --apply"
  exit 0
fi

((${#orphans[@]})) && docker rm -f "${orphans[@]}"
((${#old_images[@]})) && docker image rm "${old_images[@]}" || true
((${#unused_networks[@]})) && docker network rm "${unused_networks[@]}" || true
# Only dangling layers are globally safe to prune; volumes are explicitly excluded.
docker image prune -f
if [[ $include_build_cache == true ]]; then
  docker builder prune -f --filter 'until=168h'
fi
echo "Cleanup kész. Volume nem lett törölve."

#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

COMPOSE_FILES=(compose.yaml)
[[ -f compose.rf.yaml ]] && COMPOSE_FILES+=(compose.rf.yaml)
[[ -f compose.ai.yaml ]] && COMPOSE_FILES+=(compose.ai.yaml)
COMPOSE_ARGS=()
for file in "${COMPOSE_FILES[@]}"; do COMPOSE_ARGS+=( -f "$file" ); done

compose() { docker compose "${COMPOSE_ARGS[@]}" "$@"; }
project_name() {
  if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then printf '%s\n' "$COMPOSE_PROJECT_NAME"; return; fi
  basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9_-' '_'
}
require_command() { command -v "$1" >/dev/null 2>&1 || { echo "HIBA: hiányzó parancs: $1" >&2; exit 1; }; }
load_env() {
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
}

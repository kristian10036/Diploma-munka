#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
require_command python3
bash scripts/offline-acceptance.sh
if [[ "${1:-}" == "--offline" ]]; then
  exit 0
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "WARN: Docker nem érhető el; az offline acceptance sikeres, a konténeres rész kimaradt."
  exit 0
fi
require_command curl
load_env
failures=0
warnings=0
pass(){ echo "PASS: $*"; }
warn(){ echo "WARN: $*"; warnings=$((warnings+1)); }
fail(){ echo "FAIL: $*" >&2; failures=$((failures+1)); }
check_url(){ local name=$1 url=$2; curl -fsS --max-time 8 "$url" >/tmp/diploma-acceptance.json && pass "$name" || fail "$name ($url)"; }

echo "== Compose =="
compose config --quiet && pass "Compose config valid" || fail "Compose config invalid"
mapfile -t services < <(compose config --services)

for service in database backend frontend reverse-proxy spectrum-ingest mosquitto; do
  if printf '%s\n' "${services[@]}" | grep -Fxq "$service"; then
    id="$(compose ps -q "$service" 2>/dev/null || true)"
    [[ -n "$id" ]] || { fail "$service container missing"; continue; }
    state="$(docker inspect -f '{{.State.Status}}' "$id")"
    [[ "$state" == running ]] && pass "$service running" || fail "$service state=$state"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id")"
    [[ "$health" == healthy || "$health" == none ]] && pass "$service health=$health" || fail "$service health=$health"
  fi
done

migrate_id="$(compose ps -aq migrate 2>/dev/null || true)"
if [[ -n "$migrate_id" ]]; then
  exit_code="$(docker inspect -f '{{.State.ExitCode}}' "$migrate_id")"
  [[ "$exit_code" == 0 ]] && pass "migrate exit 0" || fail "migrate exit=$exit_code"
fi

port="${HTTP_PORT:-8080}"
check_url "backend liveness" "http://127.0.0.1:${port}/api/health/live"
check_url "backend readiness" "http://127.0.0.1:${port}/api/health/ready"
check_url "backend detailed status" "http://127.0.0.1:${port}/api/health/status"
check_url "frontend" "http://127.0.0.1:${port}/"
check_url "ML status" "http://127.0.0.1:${port}/api/ml/status"
check_url "assistant status" "http://127.0.0.1:${port}/api/assistant/status"
check_url "RAG status" "http://127.0.0.1:${port}/api/rag/status"
check_url "system status" "http://127.0.0.1:${port}/api/system/status"
check_url "recording metadata DB API" "http://127.0.0.1:${port}/api/recordings/metadata?limit=1"
check_url "marker API" "http://127.0.0.1:${port}/api/markers?limit=1"
check_url "audit API" "http://127.0.0.1:${port}/api/audit/events?limit=1"
check_url "recording orphan audit" "http://127.0.0.1:${port}/api/recordings/orphan-audit"
check_url "anomaly status" "http://127.0.0.1:${port}/api/anomalies/status"
check_url "Prometheus-backed monitoring facade" "http://127.0.0.1:${port}/api/monitoring/overview"

if curl -fsS --max-time 3 "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/health" >/dev/null 2>&1; then
  pass "RF agent health"
  check_url "RF agent status" "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/status"
  check_url "RF agent capabilities" "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/capabilities"
  python3 scripts/websocket-smoke.py "ws://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/ws/spectrum" && pass "Spectrum WebSocket/schema" || fail "Spectrum WebSocket/schema"
  if [[ "${ACCEPTANCE_WRITE_TESTS:-false}" == true ]]; then
    recording_id="acceptance-$(date -u +%Y%m%dT%H%M%SZ)"
    if curl -fsS -X POST -H 'Content-Type: application/json'       -d "{\"recording_id\":\"$recording_id\",\"description\":\"acceptance write test\"}"       "http://127.0.0.1:${port}/api/rf-agent/recordings/start" >/dev/null; then
      sleep 2
      if curl -fsS -X POST -H 'Content-Type: application/json' -d '{}'         "http://127.0.0.1:${port}/api/rf-agent/recordings/stop"         | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("frame_count",0)>0; assert len(d.get("checksum_sha256",""))==64; assert d.get("metadata_persisted") is True'; then
        pass "recording write/checksum/metadata persistence"
      else
        fail "recording stop/checksum/metadata persistence"
      fi
    else
      fail "recording start"
    fi
  else
    pass "recording write test skipped (ACCEPTANCE_WRITE_TESTS=false)"
  fi
else
  [[ "${RF_AGENT_INTEGRATION_ENABLED:-true}" == false ]] && pass "RF agent disabled" || warn "RF agent not reachable; core can still run"
fi

if printf '%s\n' "${services[@]}" | grep -Fxq kismet; then
  if curl -fsS --max-time 5 "http://127.0.0.1:2501/system/status.json" >/dev/null 2>&1; then pass "Kismet reachable"; else warn "Kismet not reachable or no source"; fi
fi

# Orphan check scoped to the project.
project="$(project_name)"; service_csv=",$(IFS=,; echo "${services[*]}"),"; orphan_count=0
while IFS= read -r service; do [[ -z "$service" || "$service_csv" == *",$service,"* ]] || orphan_count=$((orphan_count+1)); done \
  < <(docker ps -a --filter "label=com.docker.compose.project=$project" --format '{{.Label "com.docker.compose.service"}}')
[[ $orphan_count -eq 0 ]] && pass "no orphan containers" || fail "$orphan_count orphan container(s)"

bash scripts/backup.sh >/dev/null && pass "backup dry-run" || fail "backup dry-run"

echo "== Eredmény: failures=$failures warnings=$warnings =="
[[ $failures -eq 0 ]]

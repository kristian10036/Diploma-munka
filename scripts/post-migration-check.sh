#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env
bash scripts/acceptance-test.sh
if command -v uhd_find_devices >/dev/null; then uhd_find_devices || true; fi
if curl -fsS --max-time 3 "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/health" >/dev/null 2>&1; then
  curl -fsS "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/aaronia/status" || true
  echo
  curl -fsS "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/usrp/status" || true
  echo
  curl -fsS "http://127.0.0.1:${RF_AGENT_HTTP_PORT:-8765}/sdrangel/status" || true
  echo
fi
echo "Post-migration check kész. A valós RF hardvert külön mérési teszttel validáld."

#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
load_env
port="${HTTP_PORT:-8080}"
curl -fsS "http://127.0.0.1:${port}/api/recordings/orphan-audit" | python3 -m json.tool

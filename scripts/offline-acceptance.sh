#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
failures=0
warnings=0
pass(){ echo "PASS: $*"; }
warn(){ echo "WARN: $*"; warnings=$((warnings+1)); }
fail(){ echo "FAIL: $*" >&2; failures=$((failures+1)); }

export PYTHONPATH="$ROOT/python-processor"
export APP_MODE=demo
export LOG_LEVEL=ERROR
# Deterministic CI/offline checks; do not let BLAS spawn one worker per CPU.
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

python_compile_targets=(
  conftest.py
  python-processor/app
  python-processor/main.py
  python-processor/tests
  spectrum-ingest/app.py
  spectrum-ingest/test_app.py
  tests
)

python -m compileall -q "${python_compile_targets[@]}" && pass "Python syntax" || fail "Python syntax"
python -m pytest -q python-processor/tests tests/frontend/test_ui_static.py >/tmp/dm-offline-pytest.log 2>&1 && pass "offline pytest checks" || { cat /tmp/dm-offline-pytest.log; fail "offline pytest checks"; }
python -m pytest -q spectrum-ingest/test_app.py >/tmp/dm-offline-ingest.log 2>&1 && pass "spectrum-ingest tests" || { cat /tmp/dm-offline-ingest.log; fail "spectrum-ingest tests"; }

if python -c 'import coverage' >/dev/null 2>&1; then
  python -m coverage run -m pytest -q python-processor/tests tests/frontend/test_ui_static.py >/tmp/dm-coverage.log 2>&1 \
    && python -m coverage report >/tmp/dm-coverage-report.log 2>&1 \
    && pass "coverage" \
    || { cat /tmp/dm-coverage.log; cat /tmp/dm-coverage-report.log 2>/dev/null || true; fail "coverage"; }
else
  warn "coverage not installed; coverage check skipped"
fi

if command -v ruff >/dev/null 2>&1; then
  ruff check . >/tmp/dm-ruff-check.log 2>&1 && pass "ruff check" || { cat /tmp/dm-ruff-check.log; fail "ruff check"; }
  ruff format --check . >/tmp/dm-ruff-format.log 2>&1 && pass "ruff format" || { cat /tmp/dm-ruff-format.log; fail "ruff format"; }
else
  warn "ruff not installed; Ruff checks skipped"
fi

if command -v node >/dev/null 2>&1; then
  js_syntax_targets=(
    python-processor/static/api/api-client.js
    python-processor/static/demod-passband.js
    python-processor/static/maxhold-controller.js
    python-processor/static/rag.js
    python-processor/static/spectrum-frame-adapter.js
    python-processor/static/spectrum-view-model.js
    python-processor/static/system-tabs.js
    python-processor/static/ui/band-popover-view.js
    python-processor/static/ui/device-observation-view.js
    python-processor/static/ui/html.js
    python-processor/static/ui/observation-format.js
    python-processor/static/ui/spectrum-scale.js
    python-processor/static/viewport-controller.js
    tests/frontend/test_band_popover_view.js
    tests/frontend/test_demod_passband.js
    tests/frontend/test_device_observation_view.js
    tests/frontend/test_html_util.js
    tests/frontend/test_maxhold_controller.js
    tests/frontend/test_observation_format.js
    tests/frontend/test_spectrum_model.js
    tests/frontend/test_spectrum_scale.js
    tests/frontend/test_viewport_controller.js
  )
  node --check "${js_syntax_targets[@]}" && pass "frontend external JavaScript syntax" || fail "frontend external JavaScript syntax"
  node tests/frontend/test_demod_passband.js >/tmp/dm-demod-passband.log 2>&1 && pass "demod passband fixtures" || { cat /tmp/dm-demod-passband.log; fail "demod passband fixtures"; }
  node tests/frontend/test_maxhold_controller.js >/tmp/dm-maxhold-controller.log 2>&1 && pass "max-hold controller fixtures" || { cat /tmp/dm-maxhold-controller.log; fail "max-hold controller fixtures"; }
  node tests/frontend/test_spectrum_model.js >/tmp/dm-spectrum-model.log 2>&1 && pass "SpectrumFrame/view-model fixtures" || { cat /tmp/dm-spectrum-model.log; fail "SpectrumFrame/view-model fixtures"; }
  node tests/frontend/test_viewport_controller.js >/tmp/dm-viewport-controller.log 2>&1 && pass "viewport controller fixtures" || { cat /tmp/dm-viewport-controller.log; fail "viewport controller fixtures"; }
  node tests/frontend/test_observation_format.js >/tmp/dm-observation-format.log 2>&1 && pass "observation format fixtures" || { cat /tmp/dm-observation-format.log; fail "observation format fixtures"; }
  node tests/frontend/test_html_util.js >/tmp/dm-html-util.log 2>&1 && pass "html util fixtures" || { cat /tmp/dm-html-util.log; fail "html util fixtures"; }
  node tests/frontend/test_device_observation_view.js >/tmp/dm-device-observation-view.log 2>&1 && pass "device observation view fixtures" || { cat /tmp/dm-device-observation-view.log; fail "device observation view fixtures"; }
  node tests/frontend/test_spectrum_scale.js >/tmp/dm-spectrum-scale.log 2>&1 && pass "spectrum scale fixtures" || { cat /tmp/dm-spectrum-scale.log; fail "spectrum scale fixtures"; }
  node tests/frontend/test_band_popover_view.js >/tmp/dm-band-popover-view.log 2>&1 && pass "band popover view fixtures" || { cat /tmp/dm-band-popover-view.log; fail "band popover view fixtures"; }
  python - <<'PY' && pass "frontend inline JavaScript syntax" || fail "frontend inline JavaScript syntax"
from pathlib import Path
import re, subprocess, tempfile
text=Path('python-processor/static/index.html').read_text(encoding='utf-8')
for index, script in enumerate(re.findall(r'<script(?: type="module")?>(.*?)</script>', text, re.S)):
    path=Path(tempfile.gettempdir())/f'dm-inline-{index}.mjs'
    path.write_text(script, encoding='utf-8')
    subprocess.run(['node','--check',str(path)],check=True)
PY
else
  warn "node not installed; frontend JS syntax check skipped"
fi

PYTHONPATH="$ROOT/python-processor" python scripts/mock-load-fixture.py --points 1024 --frames 10 --clients 3 --output /tmp/dm-load-fixture.json >/tmp/dm-load-fixture.log 2>&1 && pass "offline load fixture" || { cat /tmp/dm-load-fixture.log; fail "offline load fixture"; }

python - <<'PY' && pass "static production invariants" || fail "static production invariants"
from pathlib import Path
import re, yaml
root=Path('.')
compose=yaml.safe_load((root/'compose.yaml').read_text())
assert set(compose['services']['reverse-proxy'].get('ports', []))
allowed_public_ports = {
    'spectrum-ingest': {"127.0.0.1:${SDRANGEL_AUDIO_UDP_PORT:-9998}:9998/udp"},
}
for name, service in compose['services'].items():
    if name != 'reverse-proxy':
        actual_ports = set(service.get('ports', []))
        assert actual_ports == allowed_public_ports.get(name, set()), f'unnecessary public port: {name}'
rf=yaml.safe_load((root/'compose.rf.yaml').read_text())
assert not rf['services']['rf-agent'].get('ports')
assert 'grafana' not in {name.lower() for name in compose['services']}
html=(root/'python-processor/static/index.html').read_text(encoding='utf-8')
labels=re.findall(r'<button[^>]*class="tab-button[^"]*"[^>]*>(.*?)</button>',html,re.S)
labels=[re.sub('<[^>]+>','',item).strip() for item in labels]
expected=['Spektrum','Wi-Fi','Bluetooth / BLE','RF Agent','Felvételek','ML osztályozás','RAG','Rendszerállapot']
assert labels[:8] == expected, labels[:8]
assert len((root/'python-processor/main.py').read_text().splitlines()) <= 10
assert 'unsupported_peak_format' in (root/'python-processor/app/services/references/importers.py').read_text()
assert (root/'prometheus/prometheus.yml').is_file()
assert 'remote_write' not in (root/'prometheus/prometheus.yml').read_text()
PY

set +e
APP_MODE=production AUTH_MODE=disabled DATABASE_URL='' LOG_LEVEL=ERROR \
  timeout 20s python -c 'import main' >/tmp/dm-production-failfast.log 2>&1
failfast_rc=$?
set -e
if [[ $failfast_rc -ne 0 ]] && [[ $failfast_rc -ne 124 ]] && grep -q 'Invalid production configuration' /tmp/dm-production-failfast.log; then
  pass "production fail-fast"
else
  cat /tmp/dm-production-failfast.log
  fail "production fail-fast"
fi

bash -n scripts/*.sh && pass "shell syntax" || fail "shell syntax"

echo "Offline acceptance: failures=$failures warnings=$warnings"
[[ $failures -eq 0 ]]

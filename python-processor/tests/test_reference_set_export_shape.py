import json
from pathlib import Path

from app.routers.reference_sets import _export_payload

GOLDEN_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "fixtures"
    / "reference_set_export_golden.json"
)


class ScriptedCursor:
    """Replays canned fetchone/fetchall results in call order, ignoring SQL text."""

    def __init__(self, results: list):
        self._results = list(results)
        self._current = None

    def execute(self, query, params=None):
        self._current = self._results.pop(0)

    def fetchone(self):
        return self._current

    def fetchall(self):
        return self._current


def _canned_export_rows():
    reference_set = {
        "id": "11111111-1111-1111-1111-111111111111",
        "reference_key": "golden_fixture",
        "version": 1,
        "name": "Golden fixture reference",
        "location_name": "lab",
        "status": "ready",
        "is_active": True,
    }
    spectrum_reference = {
        "id": "22222222-2222-2222-2222-222222222222",
        "reference_key": "golden_fixture",
        "version": 1,
        "point_count": 2,
        "checksum_sha256": "0" * 64,
        "is_active": True,
    }
    spectrum_points = [
        {"frequency_hz": 100_000_000, "power_dbm": -90.0},
        {"frequency_hz": 101_000_000, "power_dbm": -88.5},
    ]
    device_baselines = [
        {
            "protocol": "wifi",
            "stable_identity": "golden-device-1",
            "device_name": "Golden AP",
            "mac_address": "AA:BB:CC:DD:EE:FF",
        }
    ]
    return reference_set, spectrum_reference, spectrum_points, device_baselines


def test_export_payload_shape_matches_golden_fixture():
    reference_set, spectrum_reference, spectrum_points, device_baselines = _canned_export_rows()
    cur = ScriptedCursor([reference_set, spectrum_reference, spectrum_points, device_baselines])

    payload = _export_payload(cur, reference_set["id"])
    payload["manifest"]["exported_at"] = "FIXED_FOR_GOLDEN_COMPARISON"
    serialized = json.loads(json.dumps(payload, default=str, ensure_ascii=False))

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert serialized == golden, (
        f"reference-set export shape changed; if intentional, update {GOLDEN_PATH} to match"
    )

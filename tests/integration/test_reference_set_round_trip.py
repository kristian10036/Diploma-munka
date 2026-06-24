"""Reference-set export -> import -> export round trip against a live Postgres.

Requires DATABASE_URL with the full schema migrated (database/migrations/).
Skipped when no database is configured; this is intentionally an
integration check, not part of the offline baseline.
"""

from __future__ import annotations

import io
import json
import os
import uuid

import psycopg
import pytest
from app.application import app
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get("DATABASE_URL", "")

SPECTRUM_POINTS = [
    {"frequency_hz": 100_000_000 + step * 1_000_000, "power_dbm": -90.0 + step} for step in range(5)
]


def _cleanup(reference_set_ids: list[str]) -> None:
    if not reference_set_ids:
        return
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM spectrum_references WHERE reference_set_id = ANY(%s)",
                (reference_set_ids,),
            )
            spectrum_reference_ids = [str(row["id"]) for row in cur.fetchall()]
            if spectrum_reference_ids:
                cur.execute(
                    "DELETE FROM reference_spectrum_points WHERE reference_id = ANY(%s)",
                    (spectrum_reference_ids,),
                )
            cur.execute(
                "DELETE FROM device_baselines WHERE reference_set_id = ANY(%s)",
                (reference_set_ids,),
            )
            cur.execute(
                "DELETE FROM spectrum_references WHERE reference_set_id = ANY(%s)",
                (reference_set_ids,),
            )
            cur.execute("DELETE FROM reference_sets WHERE id = ANY(%s)", (reference_set_ids,))
        conn.commit()


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not configured; run against the live stack to exercise this test",
)
def test_reference_set_export_import_export_round_trip():
    client = TestClient(app)
    reference_set_ids: list[str] = []
    location_name = f"round_trip_test_{uuid.uuid4().hex[:8]}"
    try:
        capture_response = client.post(
            "/api/reference-sets/capture",
            json={
                "name": "Round trip baseline test",
                "reference_key": f"roundtrip_{uuid.uuid4().hex[:12]}",
                "location_name": location_name,
                "spectrum_points": SPECTRUM_POINTS,
                "include_wifi": False,
                "include_bluetooth": False,
                "activate": False,
            },
        )
        assert capture_response.status_code == 201, capture_response.text
        captured = capture_response.json()
        first_id = captured["reference_set"]["id"]
        location_id = captured["reference_set"]["location_id"]
        reference_set_ids.append(first_id)

        # Seed one device baseline directly: capture_reference_set only writes
        # device_baselines through save_baseline(), which requires live session
        # observations. Inserting directly isolates this test from that path
        # while still exercising the export/import device_baselines handling.
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO device_baselines
                      (location_id, location_name, protocol, stable_identity, identity_confidence,
                       mac_address, device_name, reference_set_id)
                    VALUES (%s, %s, 'wifi', %s, 'certain', 'AA:BB:CC:DD:EE:FF',
                            'round-trip-test-device', %s)
                    """,
                    (
                        location_id,
                        location_name,
                        f"roundtrip-device-{uuid.uuid4().hex[:8]}",
                        first_id,
                    ),
                )
            conn.commit()

        first_export = client.get(f"/api/reference-sets/{first_id}/export")
        assert first_export.status_code == 200, first_export.text
        first_payload = first_export.json()
        assert [
            (point["frequency_hz"], point["power_dbm"])
            for point in first_payload["spectrum_points"]
        ] == [(p["frequency_hz"], p["power_dbm"]) for p in SPECTRUM_POINTS]
        assert len(first_payload["device_baselines"]) == 1

        import_response = client.post(
            "/api/reference-sets/import",
            files={
                "file": (
                    "roundtrip.json",
                    io.BytesIO(json.dumps(first_payload).encode("utf-8")),
                    "application/json",
                )
            },
            data={"activate": "false"},
        )
        assert import_response.status_code == 201, import_response.text
        imported = import_response.json()
        second_id = imported["reference_set"]["id"]
        reference_set_ids.append(second_id)

        second_export = client.get(f"/api/reference-sets/{second_id}/export")
        assert second_export.status_code == 200, second_export.text
        second_payload = second_export.json()
        assert [
            (point["frequency_hz"], point["power_dbm"])
            for point in second_payload["spectrum_points"]
        ] == [(p["frequency_hz"], p["power_dbm"]) for p in SPECTRUM_POINTS]

        # Known critical bug (major_refactor_prompt.pdf, Fázis 3 "Kritikus hiba
        # javítása"): /api/reference-sets/import ignores device_baselines from
        # the export payload, so they are silently dropped on round trip. This
        # assertion documents today's behavior; flip it to == 1 once that fix
        # lands so this test starts proving the fix instead of the bug.
        assert second_payload["device_baselines"] == []
    finally:
        _cleanup(reference_set_ids)

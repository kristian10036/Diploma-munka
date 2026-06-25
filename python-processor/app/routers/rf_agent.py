from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from app.db import _write_audit_event, get_db
from app.metrics import (
    SDRANGEL_IQ_PACKET_LOSS,
    SDRANGEL_IQ_PACKETS_DROPPED,
    SDRANGEL_IQ_QUEUE_DEPTH,
    SDRANGEL_IQ_RECONNECTS,
)
from app.rf_agent_client import RfAgentUnavailable, request_rf_agent, rf_agent_status
from app.runtime import RF_AGENT_SETTINGS, SDRANGEL_IQ_DATA_PLANE
from app.schemas import (
    RecordingStartRequest,
    ReplaySeekRequest,
    ReplayStartRequest,
    SdrangelDemodRequest,
    SdrangelDemodUpdateRequest,
    SdrangelDeviceSetRequest,
    SdrangelTuneRequest,
    ViewportRequest,
)

router = APIRouter()


def _rf_proxy(path: str, method: str = "GET", body: dict[str, Any] | None = None):
    try:
        return request_rf_agent(RF_AGENT_SETTINGS, path, method=method, body=body)
    except RfAgentUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _persist_recording_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Persist finalized RF recording metadata without coupling the C++ writer to PostgreSQL.

    The recording on disk remains authoritative. A database failure is surfaced in the
    response but does not invalidate a recording that was already atomically finalized.
    """
    result = dict(metadata)
    result["metadata_persisted"] = False
    required = (
        "recording_id",
        "session_id",
        "sensor_id",
        "source_type",
        "source_device",
        "started_at",
        "frame_count",
        "start_frequency_hz",
        "stop_frequency_hz",
        "num_points",
        "frame_file",
        "compression",
        "checksum_algorithm",
        "checksum_sha256",
    )
    missing = [name for name in required if result.get(name) in (None, "")]
    if missing:
        result["metadata_persist_error"] = f"missing_fields:{','.join(missing)}"
        return result

    measurement_session_id: str | None = None
    session_id = str(result["session_id"])
    try:
        candidate = str(uuid.UUID(session_id))
    except (ValueError, TypeError, AttributeError):
        candidate = ""

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                if candidate:
                    cur.execute("SELECT id FROM measurement_sessions WHERE id = %s", (candidate,))
                    row = cur.fetchone()
                    if row:
                        measurement_session_id = str(row["id"])
                cur.execute(
                    """
                    INSERT INTO spectrum_recordings
                      (recording_id, session_id, measurement_session_id, sensor_id,
                       source_type, source_device, status, started_at, ended_at,
                       first_frame_timestamp, last_frame_timestamp, frame_count,
                       start_frequency_hz, stop_frequency_hz, num_points, frame_file,
                       compression, checksum_algorithm, checksum_sha256, description,
                       metadata, updated_at)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (recording_id) DO UPDATE SET
                      session_id = EXCLUDED.session_id,
                      measurement_session_id = EXCLUDED.measurement_session_id,
                      sensor_id = EXCLUDED.sensor_id,
                      source_type = EXCLUDED.source_type,
                      source_device = EXCLUDED.source_device,
                      status = EXCLUDED.status,
                      started_at = EXCLUDED.started_at,
                      ended_at = EXCLUDED.ended_at,
                      first_frame_timestamp = EXCLUDED.first_frame_timestamp,
                      last_frame_timestamp = EXCLUDED.last_frame_timestamp,
                      frame_count = EXCLUDED.frame_count,
                      start_frequency_hz = EXCLUDED.start_frequency_hz,
                      stop_frequency_hz = EXCLUDED.stop_frequency_hz,
                      num_points = EXCLUDED.num_points,
                      frame_file = EXCLUDED.frame_file,
                      compression = EXCLUDED.compression,
                      checksum_algorithm = EXCLUDED.checksum_algorithm,
                      checksum_sha256 = EXCLUDED.checksum_sha256,
                      description = EXCLUDED.description,
                      metadata = EXCLUDED.metadata,
                      updated_at = now()
                    """,
                    (
                        str(result["recording_id"]),
                        session_id,
                        measurement_session_id,
                        str(result["sensor_id"]),
                        str(result["source_type"]),
                        str(result["source_device"]),
                        str(result.get("status") or "completed"),
                        result["started_at"],
                        result.get("ended_at"),
                        result.get("first_frame_timestamp"),
                        result.get("last_frame_timestamp"),
                        int(result["frame_count"]),
                        int(result["start_frequency_hz"]),
                        int(result["stop_frequency_hz"]),
                        int(result["num_points"]),
                        str(result["frame_file"]),
                        str(result["compression"]),
                        str(result["checksum_algorithm"]),
                        str(result["checksum_sha256"]),
                        result.get("description"),
                        Jsonb(metadata),
                    ),
                )
            conn.commit()
        result["metadata_persisted"] = True
        result["measurement_session_id"] = measurement_session_id
        _write_audit_event(
            "recording.metadata.persisted",
            entity_type="spectrum_recording",
            entity_id=str(result["recording_id"]),
            details={"source_type": result["source_type"], "frame_count": result["frame_count"]},
        )
    except Exception as exc:
        result["metadata_persist_error"] = str(exc)
        _write_audit_event(
            "recording.metadata.persist_failed",
            entity_type="spectrum_recording",
            entity_id=str(result.get("recording_id") or ""),
            success=False,
            details={"error": str(exc)},
        )
    return result


@router.get("/api/rf-agent/status")
def get_rf_agent_status():
    return rf_agent_status(RF_AGENT_SETTINGS)


@router.get("/api/rf-agent/capabilities")
def get_rf_agent_capabilities():
    return _rf_proxy("/capabilities")


@router.get("/api/rf-agent/sources")
def get_rf_agent_sources():
    return _rf_proxy("/sources")


@router.post("/api/rf-agent/source/start")
def start_rf_agent_source():
    return _rf_proxy("/source/start", "POST", {})


@router.post("/api/rf-agent/source/stop")
def stop_rf_agent_source():
    return _rf_proxy("/source/stop", "POST", {})


@router.post("/api/rf-agent/source/viewport")
def configure_rf_agent_viewport(request: ViewportRequest):
    return _rf_proxy("/source/viewport", "POST", request.model_dump(exclude_none=True))


@router.get("/api/rf-agent/recordings")
def get_rf_agent_recordings():
    return _rf_proxy("/recordings")


@router.get("/api/rf-agent/recordings/status")
def get_rf_agent_recording_status():
    return _rf_proxy("/recordings/status")


@router.get("/api/rf-agent/recordings/{recording_id}")
def get_rf_agent_recording(recording_id: str):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", recording_id):
        raise HTTPException(status_code=422, detail="invalid_recording_id")
    return _rf_proxy(f"/recordings/{recording_id}")


@router.post("/api/rf-agent/recordings/start")
def start_rf_agent_recording(request: RecordingStartRequest):
    return _rf_proxy("/recordings/start", "POST", request.model_dump(exclude_none=True))


@router.post("/api/rf-agent/recordings/stop")
def stop_rf_agent_recording():
    metadata = _rf_proxy("/recordings/stop", "POST", {})
    return _persist_recording_metadata(metadata)


@router.get("/api/recordings/metadata")
def list_recording_metadata(limit: int = 100):
    bounded_limit = min(max(limit, 1), 500)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT recording_id, session_id, measurement_session_id, sensor_id,
                       source_type, source_device, status, started_at, ended_at,
                       frame_count, start_frequency_hz, stop_frequency_hz, num_points,
                       frame_file, compression, checksum_algorithm, checksum_sha256,
                       description, metadata, created_at, updated_at
                FROM spectrum_recordings
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = cur.fetchall()
    return {"items": rows, "count": len(rows)}


@router.post("/api/rf-agent/replay/start")
def start_rf_agent_replay(request: ReplayStartRequest):
    return _rf_proxy("/replay/start", "POST", request.model_dump())


@router.post("/api/rf-agent/replay/pause")
def pause_rf_agent_replay():
    return _rf_proxy("/replay/pause", "POST", {})


@router.post("/api/rf-agent/replay/resume")
def resume_rf_agent_replay():
    return _rf_proxy("/replay/resume", "POST", {})


@router.post("/api/rf-agent/replay/seek")
def seek_rf_agent_replay(request: ReplaySeekRequest):
    return _rf_proxy("/replay/seek", "POST", request.model_dump())


@router.post("/api/rf-agent/replay/stop")
def stop_rf_agent_replay():
    return _rf_proxy("/replay/stop", "POST", {})


@router.get("/api/rf-agent/aaronia/status")
def get_aaronia_status():
    return _rf_proxy("/aaronia/status")


@router.post("/api/rf-agent/aaronia/probe")
def run_aaronia_probe():
    return _rf_proxy("/aaronia/probe", "POST", {})


@router.get("/api/rf-agent/usrp/status")
def get_usrp_status():
    return _rf_proxy("/usrp/status")


@router.post("/api/rf-agent/usrp/probe")
def run_usrp_probe():
    return _rf_proxy("/usrp/probe", "POST", {})


@router.get("/api/rf-agent/hackrf/status")
def get_hackrf_status():
    return _rf_proxy("/hackrf/status")


@router.post("/api/rf-agent/hackrf/probe")
def run_hackrf_probe():
    return _rf_proxy("/hackrf/probe", "POST", {})


@router.get("/api/rf-agent/sdrangel/status")
def get_sdrangel_status():
    return _rf_proxy("/sdrangel/status")


@router.get("/api/integrations/sdrangel/status")
def get_sdrangel_integration_status():
    return _rf_proxy("/sdrangel/status")


@router.get("/api/integrations/sdrangel/devicesets")
def get_sdrangel_devicesets():
    return _rf_proxy("/sdrangel/devicesets")


@router.get("/api/integrations/sdrangel/devices")
def get_sdrangel_devices():
    return _rf_proxy("/sdrangel/devices")


@router.post("/api/integrations/sdrangel/devicesets")
def create_sdrangel_deviceset(request: SdrangelDeviceSetRequest):
    return _rf_proxy("/sdrangel/devicesets", "POST", request.model_dump())


@router.get("/api/rf-agent/sdrangel/data-plane/status")
def get_sdrangel_data_plane_status():
    status = SDRANGEL_IQ_DATA_PLANE.status()
    SDRANGEL_IQ_QUEUE_DEPTH.set(float(status["queue_depth"]))
    SDRANGEL_IQ_PACKETS_DROPPED.set(float(status["packets_dropped"]))
    SDRANGEL_IQ_PACKET_LOSS.set(float(status["packet_loss"]))
    SDRANGEL_IQ_RECONNECTS.set(float(status["reconnects"]))
    return status


@router.get("/api/rf-agent/sdrangel/readiness")
def get_sdrangel_readiness():
    data_plane = SDRANGEL_IQ_DATA_PLANE.status()
    try:
        control = _rf_proxy("/sdrangel/status")
    except HTTPException as exc:
        control = {
            "status": "unreachable",
            "control_plane": "unreachable",
            "error": str(exc.detail),
        }
    try:
        devicesets = _rf_proxy("/sdrangel/devicesets")
    except HTTPException as exc:
        devicesets = {"devicesetcount": 0, "error": str(exc.detail)}
    try:
        capabilities = _rf_proxy("/capabilities")
    except HTTPException as exc:
        capabilities = {"iq": False, "error": str(exc.detail)}
    try:
        source = _rf_proxy("/sources/current").get("source", {})
    except HTTPException:
        source = {}
    native_iq_ready = bool(capabilities.get("iq")) and source.get("backend") in {"usrp", "hackrf"}
    control_ready = control.get("status") == "ready" and control.get("control_plane") == "ready"
    deviceset_ready = int(devicesets.get("devicesetcount", 0)) > 0
    reasons = []
    if not native_iq_ready and not control_ready:
        reasons.append("sdrangel_control_not_ready")
    if not native_iq_ready and not deviceset_ready:
        reasons.append("sdrangel_deviceset_missing")
    return {
        "ready": not reasons,
        "reasons": reasons,
        "control_plane": control,
        "data_plane": data_plane,
        "devicesets": devicesets,
        "source_capabilities": capabilities,
        "source": source,
        "native_iq_audio": native_iq_ready,
        "audio_output": {
            "status": "native_iq"
            if native_iq_ready
            else ("controlled_by_sdrangel" if deviceset_ready else "not_configured"),
            "hardware_tested": False,
        },
        "accepted_demodulators": (
            ["AM", "NFM", "WFM"]
            if native_iq_ready
            else [
                "AM",
                "NFM",
                "WFM",
                "BFM",
                "USB",
                "LSB",
                "DSB",
                "CW",
                "DSD",
                "FREEDV",
                "M17",
                "DAB",
            ]
        ),
        "verified_optional_settings": [
            "inputFrequencyOffset",
            "rfBandwidth/bandwidth",
            "squelch",
            "audioMute",
            "volume",
            "audioDeviceName",
        ],
    }


@router.post("/api/rf-agent/sdrangel/tune")
def tune_sdrangel(request: SdrangelTuneRequest):
    return _rf_proxy("/sdrangel/tune", "POST", request.model_dump())


@router.post("/api/rf-agent/sdrangel/demod/start")
def start_sdrangel_demod(request: SdrangelDemodRequest):
    readiness = get_sdrangel_readiness()
    if not readiness["ready"]:
        raise HTTPException(
            status_code=409,
            detail={"code": "sdrangel_demod_not_ready", "reasons": readiness["reasons"]},
        )
    payload = request.model_dump(exclude_none=True)
    result = _rf_proxy("/sdrangel/demod/start", "POST", payload)
    result["requested"] = request.model_dump(exclude_none=True)
    result["accepted_optional_settings"] = [
        key
        for key in ("bandwidth_hz", "squelch_db", "audio_sample_rate", "audio_device", "volume")
        if key in payload
    ]
    return result


@router.post("/api/rf-agent/sdrangel/demod/stop")
def stop_sdrangel_demod(request: SdrangelDemodRequest):
    return _rf_proxy("/sdrangel/demod/stop", "POST", request.model_dump(exclude_none=True))


@router.patch("/api/rf-agent/sdrangel/demod/update")
def update_sdrangel_demod(request: SdrangelDemodUpdateRequest):
    """Visszafelé kompatibilis élő frissítés egy már futó SDRangel csatornán.

    Nem hoz létre és nem töröl csatornát: a meglévő demodulátor settings
    végpontját PATCH-eli (inputFrequencyOffset / rfBandwidth / squelch / volume),
    illetve szükség esetén a DeviceSet központi frekvenciáját hangolja át.
    """
    payload = request.model_dump(exclude_none=True)
    result = _rf_proxy("/sdrangel/demod/update", "PATCH", payload)
    if isinstance(result, dict):
        result.setdefault("requested", payload)
    return result

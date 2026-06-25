from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from app.db import get_db
from app.metrics import COLLECTOR_STATUS
from app.ml import RF_CLASSES, MlUnavailableError, describe_all_models
from app.rf_agent_client import rf_agent_status
from app.runtime import (
    ASSISTANT_SETTINGS,
    BETTERCAP_COLLECTOR,
    BETTERCAP_IMPORT_LOCK,
    BETTERCAP_IMPORT_STATE,
    BETTERCAP_SETTINGS,
    BLUETOOTH_ADAPTER_CONFLICT_WARNING,
    DATABASE_URL,
    DEVICE_IMPORT_TABLES,
    KISMET_COLLECTOR,
    KISMET_IMPORT_LOCK,
    KISMET_IMPORT_STATE,
    KISMET_SETTINGS,
    ML_CLASSIFIER,
    ML_SETTINGS,
    OLLAMA_URL,
    RECORDING_STORAGE,
    RF_AGENT_SETTINGS,
    SPECTRUM_SOURCE_MANAGER,
    mqtt_status,
)
from app.schemas import MlClassifyRequest
from app.security import SETTINGS as SECURITY_SETTINGS
from app.services.persistence import (
    ensure_bettercap_measurement_source,
    ensure_kismet_measurement_source,
    resolve_import_session,
)
from app.utils.parsing import (
    is_kismet_bluetooth_row,
    mac_is_locally_administered,
    normalize_bettercap_row,
    normalize_kismet_alert_row,
    normalize_kismet_bluetooth_row,
    normalize_kismet_row,
    normalize_wifi_management_frame_type,
)

router = APIRouter()


def _same_text(left: Any, right: Any) -> bool:
    return ("" if left is None else str(left).strip()) == (
        "" if right is None else str(right).strip()
    )


def _same_int(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def _same_float(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return False


def _rssi_changed(previous: Any, current: Any) -> bool:
    if previous is None and current is None:
        return False
    if previous is None or current is None:
        return True
    try:
        return abs(float(current) - float(previous)) >= KISMET_SETTINGS.history_rssi_delta_db
    except (TypeError, ValueError):
        return True


def _heartbeat_due(previous_observed_at: Any, current_observed_at: datetime) -> bool:
    if not isinstance(previous_observed_at, datetime):
        return True
    if previous_observed_at.tzinfo is None:
        previous_observed_at = previous_observed_at.replace(tzinfo=timezone.utc)
    if current_observed_at.tzinfo is None:
        current_observed_at = current_observed_at.replace(tzinfo=timezone.utc)
    heartbeat = timedelta(seconds=KISMET_SETTINGS.history_heartbeat_seconds)
    return current_observed_at - previous_observed_at >= heartbeat


def _wifi_history_needed(
    cur, session_id: Any, location_name: str | None, bssid: str, fields: dict[str, Any]
) -> bool:
    cur.execute(
        """
        SELECT COALESCE(observed_at, time) AS observed_at,
               ssid, channel, frequency_hz, COALESCE(signal_dbm, rssi_dbm) AS signal_dbm,
               encryption, device_type, stable_identity, identity_confidence
        FROM wifi_observations
        WHERE bssid = %s
          AND measurement_session_id IS NOT DISTINCT FROM %s
          AND location_name IS NOT DISTINCT FROM %s
        ORDER BY COALESCE(observed_at, time) DESC
        LIMIT 1
        """,
        (bssid, session_id, location_name),
    )
    previous = cur.fetchone()
    if not previous:
        return True
    if _heartbeat_due(previous["observed_at"], fields["observed_at"]):
        return True
    if _rssi_changed(previous["signal_dbm"], fields["signal_dbm"]):
        return True
    return not (
        _same_text(previous["ssid"], fields["ssid"])
        and _same_int(previous["channel"], fields["channel"])
        and _same_int(previous["frequency_hz"], fields["frequency_hz"])
        and _same_text(previous["encryption"], fields["encryption"])
        and _same_text(previous["device_type"], fields["device_type"])
        and _same_text(previous["stable_identity"], fields["stable_identity"])
        and _same_text(previous["identity_confidence"], fields["identity_confidence"])
    )


def _bluetooth_history_needed(
    cur, session_id: Any, location_name: str | None, mac: str, fields: dict[str, Any]
) -> bool:
    cur.execute(
        """
        SELECT COALESCE(observed_at, time) AS observed_at,
               device_name, rssi_dbm, vendor, service_uuids, address_type, bluetooth_type,
               vendor_resolution_method, vendor_confidence, bluetooth_company_id,
               manufacturer_data_hash, stable_identity, identity_confidence
        FROM bluetooth_observations
        WHERE mac_address = %s
          AND measurement_session_id IS NOT DISTINCT FROM %s
          AND location_name IS NOT DISTINCT FROM %s
        ORDER BY COALESCE(observed_at, time) DESC
        LIMIT 1
        """,
        (mac, session_id, location_name),
    )
    previous = cur.fetchone()
    if not previous:
        return True
    if _heartbeat_due(previous["observed_at"], fields["observed_at"]):
        return True
    if _rssi_changed(previous["rssi_dbm"], fields["rssi_dbm"]):
        return True
    previous_services = previous["service_uuids"] or []
    return not (
        _same_text(previous["device_name"], fields["device_name"])
        and _same_text(previous["vendor"], fields["vendor"])
        and sorted(previous_services) == sorted(fields["service_uuids"])
        and _same_text(previous["address_type"], fields["address_type"])
        and _same_text(previous["bluetooth_type"], fields["bluetooth_type"])
        and _same_text(previous["vendor_resolution_method"], fields["vendor_resolution_method"])
        and _same_text(previous["vendor_confidence"], fields["vendor_confidence"])
        and _same_int(previous["bluetooth_company_id"], fields["bluetooth_company_id"])
        and _same_text(previous["manufacturer_data_hash"], fields["manufacturer_data_hash"])
        and _same_text(previous["stable_identity"], fields["stable_identity"])
        and _same_text(previous["identity_confidence"], fields["identity_confidence"])
    )


_VENDOR_METHOD_RANK = {
    "bluetooth_company_id": 4,
    "bettercap": 3,
    "kismet": 2,
    "oui": 1,
}


def _vendor_rank(method: Any) -> int:
    return _VENDOR_METHOD_RANK.get(str(method or "").strip().lower(), 0)


def _merge_bluetooth_vendor_fields(cur, mac: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Resolve which collector's vendor data should win for this MAC.

    Vendor priority (highest first): Bluetooth Company Identifier, explicit
    Bettercap manufacturer/vendor, Kismet manufacturer, OUI, unknown. A poll
    from a lower-priority collector (e.g. Kismet polling again after
    Bettercap already resolved a company ID) must not downgrade
    already-known, higher-confidence vendor data.
    """
    cur.execute(
        """
        SELECT vendor, vendor_resolution_method, vendor_confidence,
               bluetooth_company_id, manufacturer_data_hash
        FROM bluetooth_devices
        WHERE mac_address = %s
        """,
        (mac,),
    )
    existing = cur.fetchone()
    if not existing or _vendor_rank(fields.get("vendor_resolution_method")) >= _vendor_rank(
        existing["vendor_resolution_method"]
    ):
        return fields
    return {
        **fields,
        "vendor": existing["vendor"],
        "vendor_resolution_method": existing["vendor_resolution_method"],
        "vendor_confidence": existing["vendor_confidence"],
        "bluetooth_company_id": existing["bluetooth_company_id"],
        "manufacturer_data_hash": existing["manufacturer_data_hash"],
    }


def _increment_wifi_management_frame_count(
    cur,
    bssid: str | None,
    frame_type_raw: str | None,
    alert_type_raw: str | None,
    increment: int | None,
) -> None:
    """Best-effort per-device management-frame counter, derived only from frame
    types we can actually recognize in the ingested Kismet alert/eventbus data.
    Unrecognized labels are skipped rather than guessed (see normalize_wifi_management_frame_type).
    """
    if not bssid:
        return
    canonical_type = normalize_wifi_management_frame_type(
        frame_type_raw
    ) or normalize_wifi_management_frame_type(alert_type_raw)
    if not canonical_type:
        return
    safe_increment = increment if isinstance(increment, int) and increment > 0 else 1
    cur.execute(
        """
        INSERT INTO wifi_devices (bssid, management_frame_counts, created_at, updated_at)
        VALUES (%s, jsonb_build_object(%s, %s::int), now(), now())
        ON CONFLICT (bssid) DO UPDATE SET
          management_frame_counts = jsonb_set(
            COALESCE(wifi_devices.management_frame_counts, '{}'::jsonb),
            ARRAY[%s],
            to_jsonb(COALESCE((wifi_devices.management_frame_counts ->> %s)::int, 0) + %s::int)
          ),
          updated_at = now()
        """,
        (bssid, canonical_type, safe_increment, canonical_type, canonical_type, safe_increment),
    )


def _upsert_wifi_security_alert(
    cur,
    *,
    severity: str,
    alert_type: str,
    message: str,
    entity_id: str | None,
    metadata: dict[str, Any],
    dedup_key: str,
    observed_at: datetime,
    source: str,
    session_id: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO system_alerts
          (severity, status, source, code, message, entity_type, entity_id,
           metadata, domain, deduplication_key, occurrence_count,
           last_seen_at, measurement_session_id, updated_at)
        VALUES (%s, 'open', %s, %s, %s, 'wifi_security_event',
                %s, %s, 'wifi_security', %s, 1, %s, %s, now())
        ON CONFLICT (deduplication_key)
          WHERE deduplication_key IS NOT NULL AND status IN ('open','acknowledged')
        DO UPDATE SET
          occurrence_count = system_alerts.occurrence_count + 1,
          last_seen_at = GREATEST(system_alerts.last_seen_at, EXCLUDED.last_seen_at),
          severity = EXCLUDED.severity,
          message = EXCLUDED.message,
          metadata = system_alerts.metadata || EXCLUDED.metadata,
          updated_at = now()
        """,
        (
            severity,
            source,
            alert_type,
            message,
            entity_id,
            Jsonb(metadata),
            dedup_key,
            observed_at,
            session_id,
        ),
    )


def _wifi_security_change_alerts(
    previous: dict[str, Any] | None,
    fields: dict[str, Any],
    bssid: str,
) -> list[dict[str, Any]]:
    """Locally derived Wi-Fi security events for conditions Kismet does not
    natively alert on: a brand-new open/unencrypted AP, a known AP changing its
    security setting, and the same BSSID suddenly advertising a different SSID
    (a classic AP-impersonation/Evil-Twin red flag). Kismet's own alert/eventbus
    classes (DEAUTHFLOOD, APSPOOF, ...) are handled separately in
    import_kismet_alert_rows and are not duplicated here.
    """
    alerts: list[dict[str, Any]] = []
    encryption = (fields.get("encryption") or "").strip().lower()
    is_open = encryption in {"", "open", "none", "opn"}
    common = {
        "suspected_transmitter_mac": bssid,
        "destination_mac": None,
        "bssid": bssid,
        "ssid": fields.get("ssid"),
        "channel": fields.get("channel"),
        "frequency_hz": fields.get("frequency_hz"),
        "rssi_dbm": fields.get("rssi_dbm") or fields.get("signal_dbm"),
    }
    if previous is None:
        if is_open:
            # A locally administered BSSID is commonly a phone hotspot/Wi-Fi
            # Direct group or a randomized client MAC misclassified as an AP,
            # not a fixed rogue access point, so report it at lower confidence
            # instead of staying silent (observed in live testing: most
            # never-before-seen open "APs" in a populated area fall in this
            # bucket).
            confidence = "low" if mac_is_locally_administered(bssid) else "medium"
            alerts.append(
                {
                    "alert_type": "new_open_ap",
                    "severity": "warning",
                    "confidence": confidence,
                    "message": (
                        f"Új, titkosítás nélküli AP jelent meg: {fields.get('ssid') or bssid}"
                    ),
                    "dedup_key": f"wifi_security:new_open_ap:{bssid}",
                    **common,
                }
            )
        return alerts

    previous_encryption = (previous.get("encryption") or "").strip().lower()
    if previous_encryption and encryption and previous_encryption != encryption:
        alerts.append(
            {
                "alert_type": "ap_security_changed",
                "severity": "warning" if is_open else "info",
                "confidence": "high",
                "message": (
                    f"Ismert AP ({bssid}) titkosítása megváltozott: "
                    f"{previous_encryption} -> {encryption}"
                ),
                "dedup_key": f"wifi_security:ap_security_changed:{bssid}:{encryption}",
                **common,
            }
        )

    previous_ssid = (previous.get("ssid") or "").strip()
    current_ssid = (fields.get("ssid") or "").strip()
    if previous_ssid and current_ssid and previous_ssid != current_ssid:
        alerts.append(
            {
                "alert_type": "bssid_fingerprint_changed",
                "severity": "warning",
                "confidence": "medium",
                "message": (
                    f"Azonos BSSID ({bssid}) más SSID-vel jelent meg: "
                    f"{previous_ssid} -> {current_ssid}"
                ),
                "dedup_key": f"wifi_security:bssid_fingerprint_changed:{bssid}:{current_ssid}",
                **common,
            }
        )
    return alerts


@router.get("/api/health/live")
async def health_live():
    return {"status": "alive", "service": "tscm-backend"}


def _database_health() -> dict[str, Any]:
    if not DATABASE_URL:
        return {
            "configured": False,
            "required": SECURITY_SETTINGS.app_mode == "production",
            "status": "not_configured",
        }
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok")
                cur.fetchone()
        return {"configured": True, "required": True, "status": "available"}
    except Exception as exc:
        return {
            "configured": True,
            "required": True,
            "status": "unavailable",
            "error_type": type(exc).__name__,
        }


def _recording_health() -> dict[str, Any]:
    try:
        storage = RECORDING_STORAGE.status().as_dict()
        state = (
            "unavailable"
            if not storage["writable"]
            else ("degraded" if storage["low_disk"] else "available")
        )
        return {"required": True, "status": state, **storage}
    except Exception as exc:
        return {"required": True, "status": "unavailable", "error_type": type(exc).__name__}


async def _detailed_health() -> dict[str, Any]:
    database, spectrum = await asyncio.gather(
        asyncio.to_thread(_database_health),
        SPECTRUM_SOURCE_MANAGER.refresh_status(),
    )
    recording, ollama, rf_agent = await asyncio.gather(
        asyncio.to_thread(_recording_health),
        asyncio.to_thread(ASSISTANT_SETTINGS.live_status),
        asyncio.to_thread(rf_agent_status, RF_AGENT_SETTINGS),
    )
    COLLECTOR_STATUS.labels(collector="spectrum_source").set(
        1 if spectrum.get("status") in {"ok", "ready", "running"} else 0
    )
    COLLECTOR_STATUS.labels(collector="mqtt").set(1 if mqtt_status().get("available") else 0)
    COLLECTOR_STATUS.labels(collector="kismet").set(
        1 if KISMET_SETTINGS.enabled and KISMET_IMPORT_STATE.get("last_error") is None else 0
    )
    COLLECTOR_STATUS.labels(collector="bettercap").set(
        1 if BETTERCAP_SETTINGS.enabled and BETTERCAP_IMPORT_STATE.get("last_error") is None else 0
    )
    core_failures = [
        name
        for name, value in {"database": database, "recording_storage": recording}.items()
        if value.get("required") and value.get("status") == "unavailable"
    ]
    return {
        "status": "ready" if not core_failures else "not_ready",
        "service": "tscm-backend",
        "app_mode": SECURITY_SETTINGS.app_mode,
        "app_profile": SECURITY_SETTINGS.app_mode,
        "synthetic_fallback_allowed": SECURITY_SETTINGS.allow_synthetic_fallback,
        "core_failures": core_failures,
        "dependencies": {
            "database": database,
            "recording_storage": recording,
            "spectrum_source": {"required": False, **spectrum},
            "mqtt": {"required": False, **mqtt_status()},
            "ollama": {"required": False, "configured": bool(OLLAMA_URL), **ollama},
            "rf_agent": {"required": False, **rf_agent},
        },
        "supported_imports": sorted(DEVICE_IMPORT_TABLES.keys()),
        "supported_reference_layers": ["bands", "spectrum", "images"],
    }


@router.get("/api/health/ready")
async def health_ready():
    payload = await _detailed_health()
    return JSONResponse(status_code=200 if payload["status"] == "ready" else 503, content=payload)


@router.get("/api/health/status")
async def health_status():
    return await _detailed_health()


@router.get("/api/health")
async def health_check():
    """Backward-compatible detailed health endpoint."""
    payload = await _detailed_health()
    payload["legacy_status"] = "ok" if payload["status"] == "ready" else "degraded"
    return payload


@router.get("/api/ml/status")
def ml_status():
    status = ML_CLASSIFIER.status()
    if ML_SETTINGS.warnings:
        status["config_warnings"] = list(ML_SETTINGS.warnings)
    return status


@router.get("/api/ml/models")
def ml_models():
    return {
        "models": describe_all_models(),
        "classes": list(RF_CLASSES),
        "ml_enabled": ML_SETTINGS.enabled,
        "active_model_type": ML_SETTINGS.model_type,
    }


@router.post("/api/ml/classify")
def ml_classify(request: MlClassifyRequest):
    if not 1 <= len(request.frames) <= 128:
        raise HTTPException(
            status_code=422, detail="frames must contain between 1 and 128 SpectrumFrame objects"
        )
    status = ML_CLASSIFIER.status()
    if not status["available"]:
        raise HTTPException(
            status_code=503,
            detail=f"ML classification unavailable (status: {status['status']})",
        )
    try:
        return ML_CLASSIFIER.classify(request.frames)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MlUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/api/spectrum/source/status")
async def spectrum_source_status():
    return await SPECTRUM_SOURCE_MANAGER.refresh_status()


@router.get("/api/kismet/status")
async def kismet_status():
    status = await KISMET_COLLECTOR.refresh_status()
    status.update(
        {
            "last_imported_wifi": KISMET_IMPORT_STATE["last_imported_wifi"],
            "last_imported_bluetooth": KISMET_IMPORT_STATE["last_imported_bluetooth"],
        }
    )
    if KISMET_SETTINGS.warnings:
        status["config_warnings"] = list(KISMET_SETTINGS.warnings)
    return status


@router.get("/api/kismet/import/status")
async def kismet_import_status():
    return {
        **KISMET_IMPORT_STATE,
        "poll_interval_seconds": KISMET_SETTINGS.poll_interval_seconds,
        "kismet_url": KISMET_SETTINGS.api_url,
    }


@router.get("/api/kismet/devices")
async def kismet_live_devices(limit: int = 100):
    limit = max(1, min(limit, 5000))
    result = await KISMET_COLLECTOR.fetch_devices(limit=limit)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/api/kismet/alerts")
async def kismet_live_alerts(limit: int = 100):
    limit = max(1, min(limit, 5000))
    result = await KISMET_COLLECTOR.fetch_alerts(limit=limit)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


def import_kismet_alert_rows(
    result: dict[str, Any], measurement_session_id: str | None = None
) -> dict[str, Any]:
    rows = result.get("alerts", [])
    imported_at = datetime.now(timezone.utc)
    imported_alerts = 0
    skipped_rows = 0
    errors: list[dict[str, Any]] = []
    with get_db() as conn:
        with conn.cursor() as cur:
            for row_number, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    skipped_rows += 1
                    errors.append(
                        {"row_number": row_number, "error": "Nem objektum tipusu Kismet alert sor."}
                    )
                    continue
                try:
                    fields = normalize_kismet_alert_row(row, imported_at)
                    metadata = {
                        "kismet_alert": True,
                        "source_url": result.get("url"),
                        "fetched_at": result.get("fetched_at"),
                        "suspected_transmitter_mac": fields["suspected_transmitter_mac"],
                        "destination_mac": fields["destination_mac"],
                        "bssid": fields["bssid"],
                        "ssid": fields["ssid"],
                        "frame_type": fields["frame_type"],
                        "reason_code": fields["reason_code"],
                        "channel": fields["channel"],
                        "frequency_hz": fields["frequency_hz"],
                        "rssi_dbm": fields["rssi_dbm"],
                        "confidence": fields["confidence"],
                        "event_count": fields["event_count"],
                        "raw_alert": row,
                    }
                    entity_id = (
                        fields["bssid"]
                        or fields["suspected_transmitter_mac"]
                        or fields["destination_mac"]
                    )
                    _upsert_wifi_security_alert(
                        cur,
                        severity=fields["severity"],
                        alert_type=fields["alert_type"],
                        message=fields["message"],
                        entity_id=entity_id,
                        metadata=metadata,
                        dedup_key=fields["deduplication_key"],
                        observed_at=fields["observed_at"],
                        source="kismet_alert_api",
                        session_id=measurement_session_id,
                    )
                    _increment_wifi_management_frame_count(
                        cur,
                        fields["bssid"] or fields["suspected_transmitter_mac"],
                        fields["frame_type"],
                        fields["alert_type"],
                        fields["event_count"],
                    )
                    imported_alerts += 1
                except Exception as exc:
                    skipped_rows += 1
                    errors.append({"row_number": row_number, "error": str(exc)})
        conn.commit()
    return {
        "source": "kismet_alert_api",
        "total_rows": len(rows),
        "imported_alerts": imported_alerts,
        "skipped_rows": skipped_rows,
        "errors": errors[:100],
        "fetched_at": result.get("fetched_at"),
        "source_url": result.get("url"),
    }


def import_kismet_device_rows(
    result: dict[str, Any],
    measurement_session_id: str | None,
    location_name: str | None,
    source_name: str,
    allow_without_session: bool,
) -> dict[str, Any]:
    rows = result.get("devices", [])
    if not rows:
        return {
            "source": "kismet_live_api",
            "total_rows": 0,
            "imported_wifi": 0,
            "imported_bluetooth": 0,
            "skipped_rows": 0,
            "message": "A Kismet API nem adott vissza importalhato eszkozt.",
        }

    imported_at = datetime.now(timezone.utc)
    cleaned_source_name = source_name.strip() or "kismet_live_api"
    imported_wifi = 0
    imported_bluetooth = 0
    suppressed_wifi_history = 0
    suppressed_bluetooth_history = 0
    skipped_rows = 0
    errors: list[dict[str, Any]] = []

    with get_db() as conn:
        with conn.cursor() as cur:
            session_id, resolved_location_name, location_id = resolve_import_session(
                cur,
                measurement_session_id,
                location_name,
                allow_without_session,
            )
            source_id = ensure_kismet_measurement_source(cur, session_id, cleaned_source_name)

            for row_number, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    skipped_rows += 1
                    errors.append(
                        {"row_number": row_number, "error": "Nem objektum tipusu Kismet sor."}
                    )
                    continue

                try:
                    if is_kismet_bluetooth_row(row):
                        fields = normalize_kismet_bluetooth_row(row, imported_at)
                        mac = fields["mac"]
                        if not mac:
                            skipped_rows += 1
                            errors.append(
                                {"row_number": row_number, "error": "Hianyzo Bluetooth MAC cim."}
                            )
                            continue
                        primary_service_uuid = (
                            fields["service_uuids"][0] if fields["service_uuids"] else None
                        )
                        vendor_fields = _merge_bluetooth_vendor_fields(cur, mac, fields)
                        cur.execute(
                            """
                            INSERT INTO bluetooth_devices
                              (mac_address, device_name, vendor, first_seen, last_seen,
                               address_type, bluetooth_type, vendor_resolution_method,
                               vendor_confidence, bluetooth_company_id, manufacturer_data_hash,
                               stable_identity, identity_confidence, metadata, created_at,
                               updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    now(), now())
                            ON CONFLICT (mac_address) DO UPDATE SET
                              device_name = COALESCE(
                                EXCLUDED.device_name, bluetooth_devices.device_name
                              ),
                              vendor = EXCLUDED.vendor,
                              first_seen = LEAST(
                                COALESCE(bluetooth_devices.first_seen, EXCLUDED.first_seen),
                                EXCLUDED.first_seen
                              ),
                              last_seen = GREATEST(
                                COALESCE(bluetooth_devices.last_seen, EXCLUDED.last_seen),
                                EXCLUDED.last_seen
                              ),
                              address_type = COALESCE(
                                EXCLUDED.address_type, bluetooth_devices.address_type
                              ),
                              bluetooth_type = COALESCE(
                                EXCLUDED.bluetooth_type, bluetooth_devices.bluetooth_type
                              ),
                              vendor_resolution_method = EXCLUDED.vendor_resolution_method,
                              vendor_confidence = EXCLUDED.vendor_confidence,
                              bluetooth_company_id = EXCLUDED.bluetooth_company_id,
                              manufacturer_data_hash = EXCLUDED.manufacturer_data_hash,
                              stable_identity = COALESCE(
                                EXCLUDED.stable_identity, bluetooth_devices.stable_identity
                              ),
                              identity_confidence = COALESCE(
                                EXCLUDED.identity_confidence, bluetooth_devices.identity_confidence
                              ),
                              metadata = bluetooth_devices.metadata || EXCLUDED.metadata,
                              updated_at = now()
                            """,
                            (
                                mac,
                                fields["device_name"],
                                vendor_fields["vendor"],
                                fields["first_seen"],
                                fields["last_seen"],
                                fields["address_type"],
                                fields["bluetooth_type"],
                                vendor_fields["vendor_resolution_method"],
                                vendor_fields["vendor_confidence"],
                                vendor_fields["bluetooth_company_id"],
                                vendor_fields["manufacturer_data_hash"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                Jsonb(
                                    {
                                        "last_source": cleaned_source_name,
                                        "last_kismet_live_import": imported_at.isoformat(),
                                    }
                                ),
                            ),
                        )
                        if _bluetooth_history_needed(
                            cur, session_id, resolved_location_name, mac, fields
                        ):
                            cur.execute(
                                """
                                INSERT INTO bluetooth_observations
                                  (time, observed_at, measurement_session_id, location_id,
                                   location_name, source_id, source_name, source_type,
                                   mac_address, device_name, service_uuid, rssi_dbm,
                                   vendor, service_uuids, address_type, bluetooth_type,
                                   vendor_resolution_method, vendor_confidence,
                                   bluetooth_company_id, manufacturer_data_hash,
                                   stable_identity, identity_confidence,
                                   observation_count, capture_source, raw_payload, metadata,
                                   created_at)
                                VALUES
                                  (%s, %s, %s, %s, %s, %s, %s, 'kismet', %s, %s,
                                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                   now())
                                """,
                                (
                                    fields["observed_at"],
                                    fields["observed_at"],
                                    session_id,
                                    location_id,
                                    resolved_location_name,
                                    source_id,
                                    cleaned_source_name,
                                    mac,
                                    fields["device_name"],
                                    primary_service_uuid,
                                    fields["rssi_dbm"],
                                    fields["vendor"],
                                    Jsonb(fields["service_uuids"]),
                                    fields["address_type"],
                                    fields["bluetooth_type"],
                                    fields["vendor_resolution_method"],
                                    fields["vendor_confidence"],
                                    fields["bluetooth_company_id"],
                                    fields["manufacturer_data_hash"],
                                    fields["stable_identity"],
                                    fields["identity_confidence"],
                                    fields["observation_count"],
                                    cleaned_source_name,
                                    Jsonb(row),
                                    Jsonb(
                                        {
                                            "source_url": result.get("url"),
                                            "fetched_at": result.get("fetched_at"),
                                        }
                                    ),
                                ),
                            )
                            imported_bluetooth += 1
                        else:
                            suppressed_bluetooth_history += 1
                    else:
                        fields = normalize_kismet_row(row, imported_at)
                        bssid = fields["bssid"]
                        if not bssid:
                            skipped_rows += 1
                            errors.append(
                                {"row_number": row_number, "error": "Hianyzo Wi-Fi BSSID/MAC cim."}
                            )
                            continue
                        cur.execute(
                            "SELECT ssid, encryption FROM wifi_devices WHERE bssid = %s",
                            (bssid,),
                        )
                        previous_wifi_device = cur.fetchone()
                        cur.execute(
                            """
                            INSERT INTO wifi_devices
                              (bssid, ssid, vendor, encryption, first_seen, last_seen,
                               device_type, stable_identity, identity_confidence,
                               metadata, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                            ON CONFLICT (bssid) DO UPDATE SET
                              ssid = COALESCE(EXCLUDED.ssid, wifi_devices.ssid),
                              vendor = COALESCE(EXCLUDED.vendor, wifi_devices.vendor),
                              encryption = COALESCE(EXCLUDED.encryption, wifi_devices.encryption),
                              device_type = CASE
                                WHEN EXCLUDED.device_type IS NOT NULL
                                     AND EXCLUDED.device_type <> 'unknown'
                                THEN EXCLUDED.device_type
                                ELSE wifi_devices.device_type
                              END,
                              stable_identity = COALESCE(
                                EXCLUDED.stable_identity, wifi_devices.stable_identity
                              ),
                              identity_confidence = COALESCE(
                                EXCLUDED.identity_confidence, wifi_devices.identity_confidence
                              ),
                              first_seen = LEAST(
                                COALESCE(wifi_devices.first_seen, EXCLUDED.first_seen),
                                EXCLUDED.first_seen
                              ),
                              last_seen = GREATEST(
                                COALESCE(wifi_devices.last_seen, EXCLUDED.last_seen),
                                EXCLUDED.last_seen
                              ),
                              metadata = wifi_devices.metadata || EXCLUDED.metadata,
                              updated_at = now()
                            """,
                            (
                                bssid,
                                fields["ssid"],
                                fields["vendor"],
                                fields["encryption"],
                                fields["first_seen"],
                                fields["last_seen"],
                                fields["device_type"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                Jsonb(
                                    {
                                        "last_source": cleaned_source_name,
                                        "last_kismet_live_import": imported_at.isoformat(),
                                    }
                                ),
                            ),
                        )
                        for security_alert in _wifi_security_change_alerts(
                            previous_wifi_device, fields, bssid
                        ):
                            _upsert_wifi_security_alert(
                                cur,
                                severity=security_alert["severity"],
                                alert_type=security_alert["alert_type"],
                                message=security_alert["message"],
                                entity_id=bssid,
                                metadata={**security_alert, "kismet_live_device_change": True},
                                dedup_key=security_alert["dedup_key"],
                                observed_at=fields["observed_at"],
                                source="kismet_live_api",
                                session_id=session_id,
                            )
                        if _wifi_history_needed(
                            cur, session_id, resolved_location_name, bssid, fields
                        ):
                            cur.execute(
                                """
                                INSERT INTO wifi_observations
                                  (time, observed_at, measurement_session_id, location_id,
                                   location_name, source_id, source_name, source_type,
                                   bssid, ssid, channel, frequency_hz, rssi_dbm,
                                   signal_dbm, noise_dbm, encryption, device_type,
                                   stable_identity, identity_confidence, packet_count,
                                   observation_count, capture_source, raw_payload, metadata,
                                   created_at)
                                VALUES
                                  (%s, %s, %s, %s, %s, %s, %s, 'kismet', %s, %s,
                                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, now())
                                """,
                                (
                                    fields["observed_at"],
                                    fields["observed_at"],
                                    session_id,
                                    location_id,
                                    resolved_location_name,
                                    source_id,
                                    cleaned_source_name,
                                    bssid,
                                    fields["ssid"],
                                    fields["channel"],
                                    fields["frequency_hz"],
                                    fields["rssi_dbm"],
                                    fields["signal_dbm"],
                                    fields["noise_dbm"],
                                    fields["encryption"],
                                    fields["device_type"],
                                    fields["stable_identity"],
                                    fields["identity_confidence"],
                                    fields["packet_count"],
                                    cleaned_source_name,
                                    Jsonb(row),
                                    Jsonb(
                                        {
                                            "source_url": result.get("url"),
                                            "fetched_at": result.get("fetched_at"),
                                        }
                                    ),
                                ),
                            )
                            imported_wifi += 1
                        else:
                            suppressed_wifi_history += 1
                except Exception as exc:
                    skipped_rows += 1
                    errors.append({"row_number": row_number, "error": str(exc)})
        conn.commit()

    return {
        "source": "kismet_live_api",
        "location_name": resolved_location_name,
        "measurement_session_id": str(session_id) if session_id else None,
        "total_rows": len(rows),
        "imported_wifi": imported_wifi,
        "imported_bluetooth": imported_bluetooth,
        "suppressed_wifi_history": suppressed_wifi_history,
        "suppressed_bluetooth_history": suppressed_bluetooth_history,
        "skipped_rows": skipped_rows,
        "errors": errors[:100],
        "fetched_at": result.get("fetched_at"),
        "source_url": result.get("url"),
    }


async def run_kismet_live_import(
    measurement_session_id: str | None = None,
    location_name: str | None = None,
    source_name: str = "kismet_live_api",
    allow_without_session: bool = True,
) -> dict[str, Any]:
    async with KISMET_IMPORT_LOCK:
        KISMET_IMPORT_STATE["last_poll_at"] = datetime.now(timezone.utc).isoformat()
        result = await KISMET_COLLECTOR.fetch_devices(limit=None)
        KISMET_IMPORT_STATE["last_total_devices"] = result.get("total_devices", 0)
        if "error" in result:
            KISMET_IMPORT_STATE["last_error"] = result["error"]
            raise HTTPException(status_code=503, detail=f"Kismet API hiba: {result['error']}")

        try:
            imported = await asyncio.to_thread(
                import_kismet_device_rows,
                result,
                measurement_session_id,
                location_name,
                source_name,
                allow_without_session,
            )
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            KISMET_IMPORT_STATE["last_error"] = str(detail)
            raise

        KISMET_IMPORT_STATE.update(
            {
                "last_import_at": datetime.now(timezone.utc).isoformat(),
                "last_imported_wifi": imported.get("imported_wifi", 0),
                "last_imported_bluetooth": imported.get("imported_bluetooth", 0),
                "last_suppressed_wifi_history": imported.get("suppressed_wifi_history", 0),
                "last_suppressed_bluetooth_history": imported.get(
                    "suppressed_bluetooth_history", 0
                ),
                "last_skipped_rows": imported.get("skipped_rows", 0),
                "last_error": None,
            }
        )
        return imported


@router.post("/api/import/kismet/live")
async def import_kismet_live(
    measurement_session_id: str | None = Form(None),
    location_name: str | None = Form(None),
    source_name: str = Form("kismet_live_api"),
    allow_without_session: bool = Form(False),
):
    return await run_kismet_live_import(
        measurement_session_id=measurement_session_id,
        location_name=location_name,
        source_name=source_name,
        allow_without_session=allow_without_session,
    )


@router.post("/api/import/kismet/alerts")
async def import_kismet_alerts(measurement_session_id: str | None = None):
    async with KISMET_IMPORT_LOCK:
        result = await KISMET_COLLECTOR.fetch_alerts(limit=None)
        if "error" in result:
            KISMET_IMPORT_STATE["last_error"] = result["error"]
            raise HTTPException(status_code=503, detail=f"Kismet alert API hiba: {result['error']}")
        try:
            imported = await asyncio.to_thread(
                import_kismet_alert_rows, result, measurement_session_id
            )
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            KISMET_IMPORT_STATE["last_error"] = str(detail)
            raise
        KISMET_IMPORT_STATE.update(
            {
                "last_imported_alerts": imported.get("imported_alerts", 0),
                "last_error": None,
            }
        )
        return imported


def import_bettercap_ble_rows(
    result: dict[str, Any],
    measurement_session_id: str | None,
    location_name: str | None,
    source_name: str,
    allow_without_session: bool,
) -> dict[str, Any]:
    """Merge live Bettercap BLE devices into the same bluetooth_devices/
    bluetooth_observations tables Kismet writes to, so the same physical BLE
    device never appears twice. Only vendor/manufacturer/service-UUID fields
    are allowed to enrich an existing row (see _merge_bluetooth_vendor_fields);
    Kismet's RSSI history is untouched."""
    rows = result.get("devices", [])
    if not rows:
        return {
            "source": "bettercap_ble_api",
            "total_rows": 0,
            "imported_bluetooth": 0,
            "suppressed_bluetooth_history": 0,
            "skipped_rows": 0,
            "message": "A Bettercap API nem adott vissza importalhato BLE eszkozt.",
        }

    imported_at = datetime.now(timezone.utc)
    cleaned_source_name = source_name.strip() or "bettercap_ble_live_api"
    imported_bluetooth = 0
    suppressed_bluetooth_history = 0
    skipped_rows = 0
    errors: list[dict[str, Any]] = []

    with get_db() as conn:
        with conn.cursor() as cur:
            session_id, resolved_location_name, location_id = resolve_import_session(
                cur,
                measurement_session_id,
                location_name,
                allow_without_session,
            )
            source_id = ensure_bettercap_measurement_source(cur, session_id, cleaned_source_name)

            for row_number, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    skipped_rows += 1
                    errors.append(
                        {
                            "row_number": row_number,
                            "error": "Nem objektum tipusu Bettercap BLE sor.",
                        }
                    )
                    continue

                try:
                    fields = normalize_bettercap_row(row, imported_at)
                    mac = fields["mac"]
                    if not mac:
                        skipped_rows += 1
                        errors.append(
                            {"row_number": row_number, "error": "Hianyzo Bluetooth MAC cim."}
                        )
                        continue
                    service_uuids = fields["service_uuids"]
                    primary_service_uuid = service_uuids[0] if service_uuids else None
                    vendor_fields = _merge_bluetooth_vendor_fields(cur, mac, fields)
                    cur.execute(
                        """
                        INSERT INTO bluetooth_devices
                          (mac_address, device_name, vendor, first_seen, last_seen,
                           address_type, bluetooth_type, vendor_resolution_method,
                           vendor_confidence, bluetooth_company_id, manufacturer_data_hash,
                           stable_identity, identity_confidence, metadata, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                now(), now())
                        ON CONFLICT (mac_address) DO UPDATE SET
                          device_name = COALESCE(
                            EXCLUDED.device_name, bluetooth_devices.device_name
                          ),
                          vendor = EXCLUDED.vendor,
                          first_seen = LEAST(
                            COALESCE(bluetooth_devices.first_seen, EXCLUDED.first_seen),
                            EXCLUDED.first_seen
                          ),
                          last_seen = GREATEST(
                            COALESCE(bluetooth_devices.last_seen, EXCLUDED.last_seen),
                            EXCLUDED.last_seen
                          ),
                          address_type = COALESCE(
                            EXCLUDED.address_type, bluetooth_devices.address_type
                          ),
                          bluetooth_type = COALESCE(
                            EXCLUDED.bluetooth_type, bluetooth_devices.bluetooth_type
                          ),
                          vendor_resolution_method = EXCLUDED.vendor_resolution_method,
                          vendor_confidence = EXCLUDED.vendor_confidence,
                          bluetooth_company_id = EXCLUDED.bluetooth_company_id,
                          manufacturer_data_hash = EXCLUDED.manufacturer_data_hash,
                          stable_identity = COALESCE(
                            EXCLUDED.stable_identity, bluetooth_devices.stable_identity
                          ),
                          identity_confidence = COALESCE(
                            EXCLUDED.identity_confidence, bluetooth_devices.identity_confidence
                          ),
                          metadata = bluetooth_devices.metadata || EXCLUDED.metadata,
                          updated_at = now()
                        """,
                        (
                            mac,
                            fields["device_name"],
                            vendor_fields["vendor"],
                            fields["first_seen"],
                            fields["last_seen"],
                            fields["address_type"],
                            fields["bluetooth_type"],
                            vendor_fields["vendor_resolution_method"],
                            vendor_fields["vendor_confidence"],
                            vendor_fields["bluetooth_company_id"],
                            vendor_fields["manufacturer_data_hash"],
                            fields["stable_identity"],
                            fields["identity_confidence"],
                            Jsonb(
                                {
                                    "last_source": cleaned_source_name,
                                    "last_bettercap_live_import": imported_at.isoformat(),
                                }
                            ),
                        ),
                    )
                    if _bluetooth_history_needed(
                        cur, session_id, resolved_location_name, mac, fields
                    ):
                        cur.execute(
                            """
                            INSERT INTO bluetooth_observations
                              (time, observed_at, measurement_session_id, location_id,
                               location_name, source_id, source_name, source_type,
                               mac_address, device_name, service_uuid, rssi_dbm,
                               vendor, service_uuids, address_type, bluetooth_type,
                               vendor_resolution_method, vendor_confidence,
                               bluetooth_company_id, manufacturer_data_hash,
                               stable_identity, identity_confidence,
                               observation_count, capture_source, raw_payload, metadata,
                               created_at)
                            VALUES
                              (%s, %s, %s, %s, %s, %s, %s, 'bettercap_ble', %s, %s,
                               %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               now())
                            """,
                            (
                                fields["observed_at"],
                                fields["observed_at"],
                                session_id,
                                location_id,
                                resolved_location_name,
                                source_id,
                                cleaned_source_name,
                                mac,
                                fields["device_name"],
                                primary_service_uuid,
                                fields["rssi_dbm"],
                                fields["vendor"],
                                Jsonb(service_uuids),
                                fields["address_type"],
                                fields["bluetooth_type"],
                                fields["vendor_resolution_method"],
                                fields["vendor_confidence"],
                                fields["bluetooth_company_id"],
                                fields["manufacturer_data_hash"],
                                fields["stable_identity"],
                                fields["identity_confidence"],
                                fields["observation_count"],
                                cleaned_source_name,
                                Jsonb(row),
                                Jsonb(
                                    {
                                        "source_url": result.get("url"),
                                        "fetched_at": result.get("fetched_at"),
                                    }
                                ),
                            ),
                        )
                        imported_bluetooth += 1
                    else:
                        suppressed_bluetooth_history += 1
                except Exception as exc:
                    skipped_rows += 1
                    errors.append({"row_number": row_number, "error": str(exc)})
        conn.commit()

    return {
        "source": "bettercap_ble_api",
        "location_name": resolved_location_name,
        "measurement_session_id": str(session_id) if session_id else None,
        "total_rows": len(rows),
        "imported_bluetooth": imported_bluetooth,
        "suppressed_bluetooth_history": suppressed_bluetooth_history,
        "skipped_rows": skipped_rows,
        "errors": errors[:100],
        "fetched_at": result.get("fetched_at"),
        "source_url": result.get("url"),
    }


async def run_bettercap_live_import(
    measurement_session_id: str | None = None,
    location_name: str | None = None,
    source_name: str = "bettercap_ble_live_api",
    allow_without_session: bool = True,
) -> dict[str, Any]:
    async with BETTERCAP_IMPORT_LOCK:
        BETTERCAP_IMPORT_STATE["last_poll_at"] = datetime.now(timezone.utc).isoformat()
        result = await BETTERCAP_COLLECTOR.fetch_devices(limit=None)
        BETTERCAP_IMPORT_STATE["last_total_devices"] = result.get("total_devices", 0)
        if "error" in result:
            BETTERCAP_IMPORT_STATE["last_error"] = result["error"]
            raise HTTPException(status_code=503, detail=f"Bettercap API hiba: {result['error']}")

        try:
            imported = await asyncio.to_thread(
                import_bettercap_ble_rows,
                result,
                measurement_session_id,
                location_name,
                source_name,
                allow_without_session,
            )
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            BETTERCAP_IMPORT_STATE["last_error"] = str(detail)
            raise

        BETTERCAP_IMPORT_STATE.update(
            {
                "last_import_at": datetime.now(timezone.utc).isoformat(),
                "last_imported_bluetooth": imported.get("imported_bluetooth", 0),
                "last_suppressed_bluetooth_history": imported.get(
                    "suppressed_bluetooth_history", 0
                ),
                "last_skipped_rows": imported.get("skipped_rows", 0),
                "last_error": None,
            }
        )
        return imported


@router.get("/api/bettercap/devices")
async def bettercap_live_devices(limit: int = 100):
    limit = max(1, min(limit, 5000))
    result = await BETTERCAP_COLLECTOR.fetch_devices(limit=limit)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/api/import/bettercap-ble/live")
async def import_bettercap_ble_live(
    measurement_session_id: str | None = Form(None),
    location_name: str | None = Form(None),
    source_name: str = Form("bettercap_ble_live_api"),
    allow_without_session: bool = Form(False),
):
    return await run_bettercap_live_import(
        measurement_session_id=measurement_session_id,
        location_name=location_name,
        source_name=source_name,
        allow_without_session=allow_without_session,
    )


@router.get("/api/bettercap/status")
async def bettercap_status():
    status = await BETTERCAP_COLLECTOR.refresh_status()
    status.update(
        {
            "last_imported_bluetooth": BETTERCAP_IMPORT_STATE["last_imported_bluetooth"],
            "import_running": BETTERCAP_IMPORT_STATE["running"],
            "last_poll_at": BETTERCAP_IMPORT_STATE["last_poll_at"],
            "last_import_at": BETTERCAP_IMPORT_STATE["last_import_at"],
            "last_import_error": BETTERCAP_IMPORT_STATE["last_error"],
            "kismet_bluetooth_interface": KISMET_SETTINGS.bluetooth_interface,
            "adapter_conflict_warning": BLUETOOTH_ADAPTER_CONFLICT_WARNING,
        }
    )
    if BETTERCAP_SETTINGS.warnings:
        status["config_warnings"] = list(BETTERCAP_SETTINGS.warnings)
    return status

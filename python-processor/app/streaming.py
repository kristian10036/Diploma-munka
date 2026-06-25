from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.metrics import (
    ANOMALY_QUEUE_DEPTH,
    ANOMALY_QUEUE_DROPS,
    BACKEND_WS_CLIENTS,
    SPECTRUM_FRAME_POINTS,
    SPECTRUM_FRAMES_TOTAL,
    SPECTRUM_SOURCE_ERRORS_TOTAL,
)
from app.routers.health_collectors import (
    import_kismet_alert_rows,
    run_bettercap_live_import,
    run_kismet_live_import,
)
from app.runtime import (
    ANOMALY_PIPELINE,
    BETTERCAP_IMPORT_STATE,
    BETTERCAP_SETTINGS,
    KISMET_COLLECTOR,
    KISMET_IMPORT_STATE,
    KISMET_SETTINGS,
    SPECTRUM_SETTINGS,
    SPECTRUM_SOURCE_MANAGER,
    connect_mqtt,
    connected_websockets,
    disconnect_mqtt,
    mqtt_client,
)
from app.services.anomaly import SpectrumEnvelope
from app.services.anomaly.repository import persist_detection_batch
from app.spectrum import SpectrumSourceUnavailable

logger = logging.getLogger(__name__)

router = APIRouter()
KISMET_IMPORT_TASK: asyncio.Task | None = None
KISMET_ALERT_IMPORT_TASK: asyncio.Task | None = None
BETTERCAP_IMPORT_TASK: asyncio.Task | None = None
SPECTRUM_BROADCAST_TASK: asyncio.Task | None = None


async def generate_and_broadcast_spectrum():
    initial_status = SPECTRUM_SOURCE_MANAGER.get_status()
    logger.info(
        "background_started",
        extra={
            "structured": {
                "spectrum_source": initial_status.get("mode"),
                "status": initial_status.get("status"),
            }
        },
    )
    last_source_error: str | None = None
    last_demo_alert_bucket: int | None = None
    anomaly_sequence = 0

    while True:
        try:
            frame = await SPECTRUM_SOURCE_MANAGER.read_frame()
            SPECTRUM_FRAMES_TOTAL.labels(source_mode=frame.source_mode).inc()
            SPECTRUM_FRAME_POINTS.observe(len(frame.points))
            last_source_error = None
        except SpectrumSourceUnavailable as exc:
            message = str(exc)
            if message != last_source_error:
                logger.warning(
                    "spectrum_source_no_frame", extra={"structured": {"message": message}}
                )
                last_source_error = message
            SPECTRUM_SOURCE_ERRORS_TOTAL.labels(error_type="source_unavailable").inc()
            await asyncio.sleep(1.0)
            continue
        except Exception as exc:
            message = f"Nem vart spektrum forras hiba: {exc}"
            if message != last_source_error:
                logger.warning(
                    "spectrum_source_degraded", extra={"structured": {"message": message}}
                )
                last_source_error = message
            SPECTRUM_SOURCE_ERRORS_TOTAL.labels(error_type="unexpected").inc()
            await asyncio.sleep(1.0)
            continue

        spectrum_data_packet = [point.to_websocket_dict() for point in frame.points]

        anomaly_sequence += 1
        envelope = SpectrumEnvelope(
            frequencies_hz=tuple(
                int(round(point.frequency_mhz * 1_000_000)) for point in frame.points
            ),
            powers_dbm=tuple(float(point.power_dbm) for point in frame.points),
            sequence=frame.sequence if frame.sequence is not None else anomaly_sequence,
            timestamp=frame.timestamp.isoformat(),
            source_type=frame.source_mode,
        )
        accepted = ANOMALY_PIPELINE.submit_nowait(envelope)
        ANOMALY_QUEUE_DEPTH.set(ANOMALY_PIPELINE.queue.qsize())
        ANOMALY_QUEUE_DROPS.set(ANOMALY_PIPELINE.dropped_frames)
        if not accepted:
            SPECTRUM_SOURCE_ERRORS_TOTAL.labels(error_type="anomaly_queue_full").inc()

        if (
            frame.source_mode == "simulator"
            and SPECTRUM_SETTINGS.demo_anomaly_enabled
            and SPECTRUM_SETTINGS.start_mhz
            <= SPECTRUM_SETTINGS.demo_anomaly_frequency_mhz
            <= SPECTRUM_SETTINGS.end_mhz
        ):
            alert_bucket = int(asyncio.get_running_loop().time() // 15)
            if alert_bucket != last_demo_alert_bucket:
                nearest_point = min(
                    frame.points,
                    key=lambda point: abs(
                        point.frequency_mhz - SPECTRUM_SETTINGS.demo_anomaly_frequency_mhz
                    ),
                )
                try:
                    mqtt_client.publish(
                        "tscm/alerts",
                        (
                            "DEMO ANOMALIA: "
                            f"{nearest_point.frequency_mhz:.3f} MHz, "
                            f"{nearest_point.power_dbm:.2f} dBm"
                        ),
                    )
                except Exception as exc:
                    logger.warning(
                        "mqtt_publish_failed",
                        extra={"structured": {"error_type": type(exc).__name__}},
                    )
                last_demo_alert_bucket = alert_bucket

        if connected_websockets:
            payload = json.dumps(spectrum_data_packet)
            disconnected = []
            for ws in list(connected_websockets):
                try:
                    await ws.send_text(payload)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                if ws in connected_websockets:
                    connected_websockets.remove(ws)

        # A live WebSocket source already provides pacing. Sleeping here would
        # manufacture backpressure and discard most real hardware frames.
        if frame.source_mode == "simulator":
            await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0)


# ==========================================
# WEBSOCKET VEGPONT A FRONTENDNEK
# ==========================================
@router.websocket("/ws/spectrum")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    BACKEND_WS_CLIENTS.set(len(connected_websockets))
    logger.info(
        "websocket_connected", extra={"structured": {"active_clients": len(connected_websockets)}}
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
        BACKEND_WS_CLIENTS.set(len(connected_websockets))
        logger.info(
            "websocket_disconnected",
            extra={"structured": {"active_clients": len(connected_websockets)}},
        )


async def collect_kismet_alerts_in_background():
    """Polling fallback for the Kismet alert/eventbus stream (Wi-Fi security
    events), independent of device import so a Kismet outage never blocks
    device polling or the rest of the backend."""
    while True:
        try:
            result = await KISMET_COLLECTOR.fetch_alerts(limit=None)
            if "error" not in result:
                imported = await asyncio.to_thread(import_kismet_alert_rows, result)
                KISMET_IMPORT_STATE["last_imported_alerts"] = imported.get("imported_alerts", 0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "kismet_background_alert_import_failed", extra={"structured": {"detail": str(exc)}}
            )
        await asyncio.sleep(KISMET_SETTINGS.poll_interval_seconds)


async def collect_kismet_in_background():
    KISMET_IMPORT_STATE["running"] = True
    try:
        while True:
            try:
                await run_kismet_live_import(
                    source_name="kismet_live_background",
                    allow_without_session=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                KISMET_IMPORT_STATE["last_error"] = str(detail)
                logger.warning(
                    "kismet_background_import_failed", extra={"structured": {"detail": detail}}
                )
            await asyncio.sleep(KISMET_SETTINGS.poll_interval_seconds)
    finally:
        KISMET_IMPORT_STATE["running"] = False


async def collect_bettercap_in_background():
    """Polling fallback for live Bettercap BLE enrichment. Bettercap is an
    optional enrichment source only: any failure here is logged and retried,
    never raised, so a Bettercap outage never affects Kismet or the rest of
    the backend."""
    BETTERCAP_IMPORT_STATE["running"] = True
    try:
        while True:
            try:
                await run_bettercap_live_import(
                    source_name="bettercap_ble_live_background",
                    allow_without_session=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                BETTERCAP_IMPORT_STATE["last_error"] = str(detail)
                logger.warning(
                    "bettercap_background_import_failed", extra={"structured": {"detail": detail}}
                )
            await asyncio.sleep(BETTERCAP_SETTINGS.poll_interval_seconds)
    finally:
        BETTERCAP_IMPORT_STATE["running"] = False


# FastAPI inditasakor a hatterfolyamatok is elindulnak.
async def startup_event():
    connect_mqtt()
    ANOMALY_PIPELINE.set_persist_callback(persist_detection_batch)
    await ANOMALY_PIPELINE.start()
    global \
        SPECTRUM_BROADCAST_TASK, \
        KISMET_IMPORT_TASK, \
        KISMET_ALERT_IMPORT_TASK, \
        BETTERCAP_IMPORT_TASK
    SPECTRUM_BROADCAST_TASK = asyncio.create_task(generate_and_broadcast_spectrum())
    if KISMET_SETTINGS.enabled:
        KISMET_IMPORT_TASK = asyncio.create_task(collect_kismet_in_background())
        KISMET_ALERT_IMPORT_TASK = asyncio.create_task(collect_kismet_alerts_in_background())
    if BETTERCAP_SETTINGS.enabled and BETTERCAP_SETTINGS.ble_enabled:
        BETTERCAP_IMPORT_TASK = asyncio.create_task(collect_bettercap_in_background())


async def shutdown_event():
    global \
        SPECTRUM_BROADCAST_TASK, \
        KISMET_IMPORT_TASK, \
        KISMET_ALERT_IMPORT_TASK, \
        BETTERCAP_IMPORT_TASK
    await ANOMALY_PIPELINE.stop()
    if SPECTRUM_BROADCAST_TASK is not None:
        SPECTRUM_BROADCAST_TASK.cancel()
        try:
            await SPECTRUM_BROADCAST_TASK
        except asyncio.CancelledError:
            pass
        SPECTRUM_BROADCAST_TASK = None
    if KISMET_IMPORT_TASK is not None:
        KISMET_IMPORT_TASK.cancel()
        try:
            await KISMET_IMPORT_TASK
        except asyncio.CancelledError:
            pass
        KISMET_IMPORT_TASK = None
    if KISMET_ALERT_IMPORT_TASK is not None:
        KISMET_ALERT_IMPORT_TASK.cancel()
        try:
            await KISMET_ALERT_IMPORT_TASK
        except asyncio.CancelledError:
            pass
        KISMET_ALERT_IMPORT_TASK = None
    if BETTERCAP_IMPORT_TASK is not None:
        BETTERCAP_IMPORT_TASK.cancel()
        try:
            await BETTERCAP_IMPORT_TASK
        except asyncio.CancelledError:
            pass
        BETTERCAP_IMPORT_TASK = None
    disconnect_mqtt()

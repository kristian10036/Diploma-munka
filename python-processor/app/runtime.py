from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from app.assistant import AssistantSettings
from app.config import BettercapSettings, DeviceBaselineSettings, KismetSettings, SpectrumSettings
from app.ml import RuleBasedRfClassifier
from app.rag import RagSettings
from app.rf_agent_client import RfAgentSettings
from app.services.collectors import BettercapCollector, KismetCollectorStub
from app.services.anomaly import OnlineAnomalyPipeline
from app.services.recordings import RecordingCatalog, RecordingSettings, RecordingStorage
from app.services.sdrangel import IqDataPlane, IqDataPlaneConfig, MockIqSink
from app.spectrum import SpectrumSourceManager

logger = logging.getLogger(__name__)

MQTT_BROKER = os.getenv("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
RECORDING_SETTINGS = RecordingSettings.from_env()
RECORDING_STORAGE = RecordingStorage(RECORDING_SETTINGS)
RECORDING_CATALOG = RecordingCatalog(RECORDING_SETTINGS)
SDRANGEL_IQ_CONFIG = IqDataPlaneConfig.from_env()
SDRANGEL_IQ_DATA_PLANE = IqDataPlane(SDRANGEL_IQ_CONFIG, MockIqSink())
ANOMALY_PIPELINE = OnlineAnomalyPipeline(queue_size=max(1, int(os.getenv("ANOMALY_QUEUE_SIZE", "32"))))

SPECTRUM_SETTINGS = SpectrumSettings.from_env()
SPECTRUM_SOURCE_MANAGER = SpectrumSourceManager(SPECTRUM_SETTINGS)
ML_CLASSIFIER = RuleBasedRfClassifier()
ASSISTANT_SETTINGS = AssistantSettings.from_env()
RAG_SETTINGS = RagSettings.from_env()
RF_AGENT_SETTINGS = RfAgentSettings.from_env()
KISMET_SETTINGS = KismetSettings.from_env()
KISMET_COLLECTOR = KismetCollectorStub(KISMET_SETTINGS)
BETTERCAP_SETTINGS = BettercapSettings.from_env()
BETTERCAP_COLLECTOR = BettercapCollector(BETTERCAP_SETTINGS)
DEVICE_BASELINE_SETTINGS = DeviceBaselineSettings.from_env()
SINGLE_ACTIVE_MEASUREMENT_SESSION = os.getenv("SINGLE_ACTIVE_MEASUREMENT_SESSION", "true").strip().lower() not in {"0", "false", "no", "off"}


def bluetooth_adapter_conflict_warning(
    kismet_settings: KismetSettings, bettercap_settings: BettercapSettings
) -> str | None:
    """Detect Kismet and Bettercap being configured for the same Bluetooth
    adapter. Returns a human-readable warning, or None. Never disables
    Kismet - the caller only logs/surfaces this, it does not stop anything."""
    if not (bettercap_settings.enabled and bettercap_settings.ble_enabled):
        return None
    if kismet_settings.bluetooth_interface != bettercap_settings.ble_interface:
        return None
    return (
        "Kismet (KISMET_BLUETOOTH_INTERFACE) es Bettercap (BETTERCAP_BLE_INTERFACE) "
        f"ugyanazt a Bluetooth adaptert hasznalja ({kismet_settings.bluetooth_interface}). "
        "Ez utkozo HCI hozzaferest okozhat; Kismet tovabb fut, de a Bettercap BLE recon "
        "megbizhatatlan lehet. Allits be kulon adaptert (pl. hci0 / hci1)."
    )


BLUETOOTH_ADAPTER_CONFLICT_WARNING = bluetooth_adapter_conflict_warning(KISMET_SETTINGS, BETTERCAP_SETTINGS)
if BLUETOOTH_ADAPTER_CONFLICT_WARNING:
    logger.warning(
        "bluetooth_adapter_conflict",
        extra={"structured": {"interface": KISMET_SETTINGS.bluetooth_interface}},
    )

KISMET_IMPORT_STATE: dict[str, Any] = {
    "enabled": KISMET_SETTINGS.enabled,
    "running": False,
    "last_poll_at": None,
    "last_import_at": None,
    "last_total_devices": 0,
    "last_imported_wifi": 0,
    "last_imported_bluetooth": 0,
    "last_imported_alerts": 0,
    "last_suppressed_wifi_history": 0,
    "last_suppressed_bluetooth_history": 0,
    "last_skipped_rows": 0,
    "last_error": None,
}
KISMET_IMPORT_LOCK = asyncio.Lock()

BETTERCAP_IMPORT_STATE: dict[str, Any] = {
    "enabled": BETTERCAP_SETTINGS.enabled and BETTERCAP_SETTINGS.ble_enabled,
    "running": False,
    "last_poll_at": None,
    "last_import_at": None,
    "last_total_devices": 0,
    "last_imported_bluetooth": 0,
    "last_suppressed_bluetooth_history": 0,
    "last_skipped_rows": 0,
    "last_error": None,
}
BETTERCAP_IMPORT_LOCK = asyncio.Lock()

DEVICE_IMPORT_TABLES = {
    "oscor": "oscor_import_rows",
    "ddf": "ddf_import_rows",
    "pr100": "pr100_import_rows",
    "mesa": "mesa_import_rows",
    "kismet": "kismet_import_rows",
    "bettercap_ble": "bettercap_ble_import_rows",
}
MAC_RE = re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b")
connected_websockets: list[Any] = []

mqtt_client = mqtt.Client()
_mqtt_connected = False

def connect_mqtt() -> None:
    global _mqtt_connected
    if _mqtt_connected:
        return
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        _mqtt_connected = True
    except Exception as exc:
        # MQTT is optional for core startup. The health/status endpoints expose failures.
        logger.warning("mqtt_connection_unavailable", extra={"structured": {"broker": MQTT_BROKER, "port": MQTT_PORT, "error_type": type(exc).__name__}})

def disconnect_mqtt() -> None:
    global _mqtt_connected
    if not _mqtt_connected:
        return
    try:
        mqtt_client.disconnect()
    finally:
        _mqtt_connected = False

def mqtt_status() -> dict[str, Any]:
    return {
        "enabled": True,
        "available": _mqtt_connected,
        "status": "connected" if _mqtt_connected else "degraded",
        "broker": MQTT_BROKER,
        "port": MQTT_PORT,
    }

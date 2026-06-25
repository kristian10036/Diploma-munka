import os
from dataclasses import dataclass


def _read_float(name: str, default: float, warnings: list[str]) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        warnings.append(f"{name} is invalid; using {default}.")
        return default


def _read_int(name: str, default: int, warnings: list[str]) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        warnings.append(f"{name} is invalid; using {default}.")
        return default


def _read_bool(name: str, default: bool, warnings: list[str]) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    warnings.append(f"{name} is invalid; using {str(default).lower()}.")
    return default


@dataclass(frozen=True)
class SpectrumSettings:
    source_mode: str
    start_mhz: float
    end_mhz: float
    point_count: int
    demo_anomaly_enabled: bool
    demo_anomaly_frequency_mhz: float
    demo_anomaly_level_dbm: float
    aaronia_rtsa_url: str
    aaronia_timeout_seconds: float
    spectrum_ingest_ws_url: str
    spectrum_ingest_timeout_seconds: float
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "SpectrumSettings":
        warnings: list[str] = []
        start_mhz = _read_float("SPECTRUM_START_MHZ", 88.0, warnings)
        end_mhz = _read_float("SPECTRUM_END_MHZ", 108.0, warnings)
        if end_mhz <= start_mhz:
            warnings.append("Spectrum end must be greater than start; using 88-108 MHz.")
            start_mhz, end_mhz = 88.0, 108.0

        point_count = _read_int("SPECTRUM_POINT_COUNT", 100, warnings)
        if point_count < 2:
            warnings.append("SPECTRUM_POINT_COUNT must be at least 2; using 100.")
            point_count = 100
        elif point_count > 100_000:
            warnings.append("SPECTRUM_POINT_COUNT is too large; limiting it to 100000.")
            point_count = 100_000

        timeout_seconds = _read_float("AARONIA_TIMEOUT_SECONDS", 5.0, warnings)
        if timeout_seconds <= 0:
            warnings.append("AARONIA_TIMEOUT_SECONDS must be positive; using 5.")
            timeout_seconds = 5.0

        ingest_timeout = _read_float("SPECTRUM_INGEST_TIMEOUT_SECONDS", 5.0, warnings)
        if ingest_timeout <= 0:
            warnings.append("SPECTRUM_INGEST_TIMEOUT_SECONDS must be positive; using 5.")
            ingest_timeout = 5.0

        return cls(
            source_mode=os.getenv("SPECTRUM_SOURCE_MODE", "simulator").strip().lower(),
            start_mhz=start_mhz,
            end_mhz=end_mhz,
            point_count=point_count,
            demo_anomaly_enabled=_read_bool("DEMO_ANOMALY_ENABLED", True, warnings),
            demo_anomaly_frequency_mhz=_read_float("DEMO_ANOMALY_FREQUENCY_MHZ", 2460.0, warnings),
            demo_anomaly_level_dbm=_read_float("DEMO_ANOMALY_LEVEL_DBM", -35.0, warnings),
            aaronia_rtsa_url=os.getenv(
                "AARONIA_RTSA_URL", "http://host.docker.internal:54664"
            ).strip(),
            aaronia_timeout_seconds=timeout_seconds,
            spectrum_ingest_ws_url=os.getenv(
                "SPECTRUM_INGEST_WS_URL", "ws://spectrum-ingest:8001/ws/spectrum"
            ).strip(),
            spectrum_ingest_timeout_seconds=ingest_timeout,
            warnings=tuple(warnings),
        )

    def public_simulator_config(self) -> dict[str, float | int | bool]:
        return {
            "start_mhz": self.start_mhz,
            "end_mhz": self.end_mhz,
            "point_count": self.point_count,
            "demo_anomaly_enabled": self.demo_anomaly_enabled,
            "demo_anomaly_frequency_mhz": self.demo_anomaly_frequency_mhz,
            "demo_anomaly_level_dbm": self.demo_anomaly_level_dbm,
        }


@dataclass(frozen=True)
class KismetSettings:
    enabled: bool
    api_url: str
    api_key: str
    username: str
    password: str
    devices_endpoint: str
    alerts_endpoint: str
    poll_interval_seconds: float
    timeout_seconds: float
    history_rssi_delta_db: float
    history_heartbeat_seconds: float
    bluetooth_interface: str
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "KismetSettings":
        warnings: list[str] = []
        timeout_seconds = _read_float("KISMET_TIMEOUT_SECONDS", 5.0, warnings)
        if timeout_seconds <= 0:
            warnings.append("KISMET_TIMEOUT_SECONDS must be positive; using 5.")
            timeout_seconds = 5.0
        poll_interval_seconds = _read_float("KISMET_POLL_INTERVAL_SECONDS", 15.0, warnings)
        if poll_interval_seconds < 5:
            warnings.append("KISMET_POLL_INTERVAL_SECONDS must be at least 5; using 15.")
            poll_interval_seconds = 15.0
        history_rssi_delta_db = _read_float("KISMET_HISTORY_RSSI_DELTA_DB", 3.0, warnings)
        if history_rssi_delta_db < 0:
            warnings.append("KISMET_HISTORY_RSSI_DELTA_DB must be non-negative; using 3.")
            history_rssi_delta_db = 3.0
        history_heartbeat_seconds = _read_float("KISMET_HISTORY_HEARTBEAT_SECONDS", 10.0, warnings)
        if history_heartbeat_seconds < 1:
            warnings.append("KISMET_HISTORY_HEARTBEAT_SECONDS must be at least 1; using 10.")
            history_heartbeat_seconds = 10.0
        endpoint = os.getenv("KISMET_DEVICES_ENDPOINT", "/devices/views/all/devices.json").strip()
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        alerts_endpoint = os.getenv("KISMET_ALERTS_ENDPOINT", "/alerts/all_alerts.json").strip()
        if not alerts_endpoint.startswith("/"):
            alerts_endpoint = "/" + alerts_endpoint
        bluetooth_interface = (
            os.getenv("KISMET_BLUETOOTH_INTERFACE", "hci0").strip().lower() or "hci0"
        )
        return cls(
            enabled=_read_bool("KISMET_INTEGRATION_ENABLED", False, warnings),
            api_url=os.getenv("KISMET_API_URL", "http://host.docker.internal:2501")
            .strip()
            .rstrip("/"),
            api_key=os.getenv("KISMET_API_KEY", "").strip(),
            username=os.getenv("KISMET_HTTPD_USERNAME", "").strip(),
            password=os.getenv("KISMET_HTTPD_PASSWORD", "").strip(),
            devices_endpoint=endpoint,
            alerts_endpoint=alerts_endpoint,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            history_rssi_delta_db=history_rssi_delta_db,
            history_heartbeat_seconds=history_heartbeat_seconds,
            bluetooth_interface=bluetooth_interface,
            warnings=tuple(warnings),
        )


@dataclass(frozen=True)
class DeviceBaselineSettings:
    wifi_missing_grace_seconds: float
    bluetooth_missing_grace_seconds: float
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "DeviceBaselineSettings":
        warnings: list[str] = []
        wifi_grace = _read_float("WIFI_BASELINE_MISSING_GRACE_SECONDS", 180.0, warnings)
        if wifi_grace < 0:
            warnings.append("WIFI_BASELINE_MISSING_GRACE_SECONDS must be non-negative; using 180.")
            wifi_grace = 180.0
        bluetooth_grace = _read_float("BLUETOOTH_BASELINE_MISSING_GRACE_SECONDS", 300.0, warnings)
        if bluetooth_grace < 0:
            warnings.append(
                "BLUETOOTH_BASELINE_MISSING_GRACE_SECONDS must be non-negative; using 300."
            )
            bluetooth_grace = 300.0
        return cls(
            wifi_missing_grace_seconds=wifi_grace,
            bluetooth_missing_grace_seconds=bluetooth_grace,
            warnings=tuple(warnings),
        )


@dataclass(frozen=True)
class BettercapSettings:
    enabled: bool
    api_url: str
    username: str
    password: str
    timeout_seconds: float
    ble_enabled: bool
    ble_interface: str
    poll_interval_seconds: float
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "BettercapSettings":
        warnings: list[str] = []
        timeout_seconds = _read_float("BETTERCAP_API_TIMEOUT_SECONDS", 5.0, warnings)
        if timeout_seconds <= 0:
            warnings.append("BETTERCAP_API_TIMEOUT_SECONDS must be positive; using 5.")
            timeout_seconds = 5.0
        poll_interval_seconds = _read_float("BETTERCAP_POLL_INTERVAL_SECONDS", 2.0, warnings)
        if poll_interval_seconds < 1:
            warnings.append("BETTERCAP_POLL_INTERVAL_SECONDS must be at least 1; using 2.")
            poll_interval_seconds = 2.0
        ble_interface = os.getenv("BETTERCAP_BLE_INTERFACE", "hci1").strip().lower() or "hci1"
        return cls(
            enabled=_read_bool("BETTERCAP_INTEGRATION_ENABLED", False, warnings),
            api_url=os.getenv("BETTERCAP_API_URL", "http://host.docker.internal:8081")
            .strip()
            .rstrip("/"),
            username=os.getenv("BETTERCAP_USERNAME", "user").strip() or "user",
            password=os.getenv("BETTERCAP_PASSWORD", "pass").strip() or "pass",
            timeout_seconds=timeout_seconds,
            ble_enabled=_read_bool("BETTERCAP_BLE_ENABLED", True, warnings),
            ble_interface=ble_interface,
            poll_interval_seconds=poll_interval_seconds,
            warnings=tuple(warnings),
        )

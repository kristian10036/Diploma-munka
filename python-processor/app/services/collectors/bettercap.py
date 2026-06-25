import asyncio
import base64
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import BettercapSettings


class BettercapCollector:
    """Bettercap REST API collector for passive BLE device discovery (ble.recon).

    Bettercap is an optional enrichment source: Kismet remains the primary
    Wi-Fi/Bluetooth data source, so every method here is best-effort and
    never raises on connectivity failures.
    """

    def __init__(self, settings: BettercapSettings):
        self.settings = settings
        self._probe: dict[str, Any] = {
            "reachable": None,
            "last_probe_at": None,
        }
        self._ble_recon_active: bool | None = None
        self._last_device_count: int | None = None
        self._last_fetch_at: str | None = None
        self._last_successful_connection_at: str | None = None
        self._last_error: str | None = None

    @property
    def devices_url(self) -> str:
        return f"{self.settings.api_url}/api/session/ble"

    @property
    def modules_url(self) -> str:
        return f"{self.settings.api_url}/api/session/modules"

    def is_healthy(self) -> bool:
        return bool(self._probe.get("reachable")) and self._last_error is None

    def get_status(self) -> dict[str, Any]:
        credentials_configured = bool(self.settings.username and self.settings.password)
        if not self.settings.enabled:
            return {
                "enabled": False,
                "ble_enabled": self.settings.ble_enabled,
                "status": "disabled",
                "message": (
                    "Bettercap live integration disabled. Passive file import is still available."
                ),
                "url": self.settings.api_url,
                "ble_interface": self.settings.ble_interface,
                "reachable": None,
                "healthy": False,
                "ble_recon_active": False,
                "credentials_configured": credentials_configured,
                "last_successful_connection_at": self._last_successful_connection_at,
                "last_error": self._last_error,
            }

        reachable = self._probe.get("reachable")
        if reachable is True:
            status = "reachable"
            message = "Bettercap API reachable. Live BLE polling is available."
        elif reachable is False:
            status = "unreachable"
            message = "Bettercap API not reachable. Kismet continues to provide Bluetooth/BLE data."
        else:
            status = "not_checked"
            message = "Bettercap live integration enabled but not checked yet."

        return {
            "enabled": True,
            "ble_enabled": self.settings.ble_enabled,
            "status": status,
            "message": message,
            "url": self.settings.api_url,
            "ble_interface": self.settings.ble_interface,
            "reachable": reachable,
            "healthy": self.is_healthy(),
            "ble_recon_active": bool(self._ble_recon_active),
            "credentials_configured": credentials_configured,
            "poll_interval_seconds": self.settings.poll_interval_seconds,
            "last_device_count": self._last_device_count,
            "last_fetch_at": self._last_fetch_at,
            "last_successful_connection_at": self._last_successful_connection_at,
            "last_error": self._last_error,
            "last_probe_at": self._probe.get("last_probe_at"),
        }

    async def refresh_status(self) -> dict[str, Any]:
        if self.settings.enabled:
            self._probe, self._ble_recon_active = await asyncio.to_thread(self._probe_sync)
        return self.get_status()

    async def fetch_devices(self, limit: int | None = None) -> dict[str, Any]:
        if not self.settings.enabled:
            return {
                "enabled": False,
                "devices": [],
                "total_devices": 0,
                "message": "Bettercap live integration disabled.",
            }
        return await asyncio.to_thread(self._fetch_devices_sync, limit)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "tscm-bettercap-ble-collector/1.0",
        }
        if self.settings.username and self.settings.password:
            raw = f"{self.settings.username}:{self.settings.password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    def _request_json(self, url: str) -> Any:
        request = Request(url, method="GET", headers=self._headers())
        with urlopen(request, timeout=self.settings.timeout_seconds) as response:
            body = response.read()
        if not body:
            return None
        return json.loads(body.decode("utf-8", errors="replace"))

    @staticmethod
    def _extract_ble_recon_running(payload: Any) -> bool | None:
        if not isinstance(payload, list):
            return None
        for module in payload:
            if isinstance(module, dict) and module.get("name") == "ble.recon":
                running = module.get("running")
                return running if isinstance(running, bool) else None
        return None

    def _probe_sync(self) -> tuple[dict[str, Any], bool | None]:
        probed_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = self._request_json(self.modules_url)
            self._last_successful_connection_at = probed_at
            return (
                {
                    "reachable": True,
                    "last_probe_at": probed_at,
                    "probe_message": "Bettercap session/modules endpoint returned JSON",
                },
                self._extract_ble_recon_running(payload),
            )
        except HTTPError as exc:
            # 401/403 still means the endpoint is alive; auth config is the problem.
            return (
                {
                    "reachable": True,
                    "last_probe_at": probed_at,
                    "probe_message": f"Bettercap endpoint responded with HTTP {exc.code}",
                },
                None,
            )
        except (URLError, TimeoutError, OSError) as exc:
            return (
                {
                    "reachable": False,
                    "last_probe_at": probed_at,
                    "probe_message": f"Bettercap endpoint unavailable: {exc}",
                },
                None,
            )
        except Exception as exc:
            return (
                {
                    "reachable": False,
                    "last_probe_at": probed_at,
                    "probe_message": f"Bettercap probe failed safely: {exc}",
                },
                None,
            )

    @staticmethod
    def _extract_devices(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            devices = payload.get("devices")
            if isinstance(devices, list):
                return [item for item in devices if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _fetch_devices_sync(self, limit: int | None = None) -> dict[str, Any]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = self._request_json(self.devices_url)
            devices = self._extract_devices(payload)
            total = len(devices)
            if limit is not None and limit > 0:
                devices = devices[:limit]
            self._last_device_count = total
            self._last_fetch_at = fetched_at
            self._last_successful_connection_at = fetched_at
            self._last_error = None
            return {
                "enabled": True,
                "source": "bettercap_ble_api",
                "url": self.devices_url,
                "fetched_at": fetched_at,
                "total_devices": total,
                "returned_devices": len(devices),
                "devices": devices,
            }
        except Exception as exc:
            self._last_error = str(exc)
            self._last_fetch_at = fetched_at
            return {
                "enabled": True,
                "source": "bettercap_ble_api",
                "url": self.devices_url,
                "fetched_at": fetched_at,
                "total_devices": 0,
                "returned_devices": 0,
                "devices": [],
                "error": str(exc),
            }


# Backwards-compatible name used elsewhere in the project.
BettercapCollectorStub = BettercapCollector

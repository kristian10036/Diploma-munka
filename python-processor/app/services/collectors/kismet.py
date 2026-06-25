import asyncio
import base64
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import KismetSettings

KISMET_DEVICE_FIELDS: list[Any] = [
    "kismet.device.base.macaddr",
    "kismet.device.base.name",
    "kismet.device.base.phyname",
    "kismet.device.base.type",
    "kismet.device.base.basic_type_set",
    "kismet.device.base.channel",
    "kismet.device.base.frequency",
    "kismet.device.base.first_time",
    "kismet.device.base.last_time",
    "kismet.device.base.packets.total",
    "kismet.device.base.manuf",
    ["kismet.device.base.signal/kismet.common.signal.last_signal", "device_last_signal"],
    ["kismet.device.base.signal/kismet.common.signal.last_noise", "device_last_noise"],
    ["bluetooth.device/bluetooth.device.rssi_last", "bluetooth_rssi_last"],
    ["bluetooth.device/bluetooth.device.rssi_avg", "bluetooth_rssi_avg"],
    ["bluetooth.device/bluetooth.device.rssi_count", "bluetooth_rssi_count"],
    "bluetooth.device.rssi_last",
    "bluetooth.device.rssi_avg",
    "bluetooth.device.rssi_count",
    "bluetooth.device.address",
    "bluetooth.device.name",
    "bluetooth.device.alias",
    "bluetooth.device.vendor",
    "bluetooth.device.address_type",
    "bluetooth.device.type",
    "dot11.device.last_beaconed_ssid",
    "dot11.device.last_probed_ssid",
    "dot11.device.type",
    "dot11.device.role",
]


class KismetCollector:
    """Small Kismet REST collector for live passive device polling."""

    # The "all devices" view is paginated server-side (page/length); once a
    # long-running Kismet instance accumulates more devices than fit on a
    # single page (very easy with Wi-Fi MAC-randomization noise), whichever
    # devices Kismet happens to order first - frequently all-Bluetooth - are
    # the only ones ever returned, silently starving Wi-Fi import forever.
    # The last-time view is naturally bounded by recency instead of a fixed
    # page size, so it keeps returning every currently-active device (every
    # phy) regardless of how many devices Kismet has accumulated in total.
    LIVE_WINDOW_SECONDS = 300

    def __init__(self, settings: KismetSettings):
        self.settings = settings
        self._probe: dict[str, Any] = {
            "reachable": None,
            "last_probe_at": None,
        }
        self._last_device_count: int | None = None
        self._last_fetch_at: str | None = None
        self._last_error: str | None = None

    @property
    def devices_url(self) -> str:
        return f"{self.settings.api_url}{self.settings.devices_endpoint}"

    @property
    def last_time_devices_url(self) -> str:
        return f"{self.settings.api_url}/devices/last-time/-{self.LIVE_WINDOW_SECONDS}/devices.json"

    @property
    def alerts_url(self) -> str:
        return f"{self.settings.api_url}{self.settings.alerts_endpoint}"

    def get_status(self) -> dict[str, Any]:
        if not self.settings.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "Kismet live integration disabled. File import is available.",
                "url": self.settings.api_url,
                "devices_url": self.devices_url,
                "alerts_url": self.alerts_url,
                "api_key_configured": bool(self.settings.api_key),
                "basic_auth_configured": bool(self.settings.username and self.settings.password),
            }

        if self._probe["reachable"] is True:
            status = "reachable"
            message = "Kismet API reachable. Live device polling is available."
        elif self._probe["reachable"] is False:
            status = "unreachable"
            message = "Kismet API not reachable. File import is still available."
        else:
            status = "not_checked"
            message = "Kismet live integration enabled but not checked yet."
        return {
            "enabled": True,
            "status": status,
            "message": message,
            "url": self.settings.api_url,
            "devices_url": self.devices_url,
            "alerts_url": self.alerts_url,
            "api_key_configured": bool(self.settings.api_key),
            "basic_auth_configured": bool(self.settings.username and self.settings.password),
            "poll_interval_seconds": self.settings.poll_interval_seconds,
            "last_device_count": self._last_device_count,
            "last_fetch_at": self._last_fetch_at,
            "last_error": self._last_error,
            **self._probe,
        }

    async def refresh_status(self) -> dict[str, Any]:
        if self.settings.enabled:
            self._probe = await asyncio.to_thread(self._probe_sync)
        return self.get_status()

    async def fetch_devices(self, limit: int | None = None) -> dict[str, Any]:
        if not self.settings.enabled:
            return {
                "enabled": False,
                "devices": [],
                "total_devices": 0,
                "message": "Kismet live integration disabled.",
            }
        return await asyncio.to_thread(self._fetch_devices_sync, limit)

    async def fetch_alerts(self, limit: int | None = None) -> dict[str, Any]:
        if not self.settings.enabled:
            return {
                "enabled": False,
                "alerts": [],
                "total_alerts": 0,
                "message": "Kismet live integration disabled.",
            }
        return await asyncio.to_thread(self._fetch_alerts_sync, limit)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "tscm-kismet-live-collector/1.0",
        }
        if self.settings.api_key:
            # Kept for Kismet deployments that use API-token style frontends/proxies.
            headers["KISMET"] = self.settings.api_key
        if self.settings.username and self.settings.password:
            raw = f"{self.settings.username}:{self.settings.password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    def _request_json(self, url: str) -> Any:
        request = Request(url, method="GET", headers=self._headers())
        return self._read_json(request)

    def _post_devices_json(self) -> Any:
        form = urlencode(
            {"json": json.dumps({"fields": KISMET_DEVICE_FIELDS}, separators=(",", ":"))}
        ).encode("utf-8")
        headers = {
            **self._headers(),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        request = Request(self.last_time_devices_url, data=form, method="POST", headers=headers)
        return self._read_json(request)

    def _read_json(self, request: Request) -> Any:
        with urlopen(request, timeout=self.settings.timeout_seconds) as response:
            body = response.read()
        if not body:
            return None
        return json.loads(body.decode("utf-8", errors="replace"))

    def _probe_sync(self) -> dict[str, Any]:
        probed_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = self._request_json(self.settings.api_url + "/system/status.json")
            return {
                "reachable": True,
                "last_probe_at": probed_at,
                "probe_message": "Kismet status endpoint returned JSON",
                "probe_payload_type": type(payload).__name__,
            }
        except HTTPError as exc:
            # 401/403 still means that the endpoint is alive; auth config is the problem.
            return {
                "reachable": True,
                "last_probe_at": probed_at,
                "probe_message": f"Kismet endpoint responded with HTTP {exc.code}",
            }
        except (URLError, TimeoutError, OSError) as exc:
            return {
                "reachable": False,
                "last_probe_at": probed_at,
                "probe_message": f"Kismet endpoint unavailable: {exc}",
            }
        except Exception as exc:
            return {
                "reachable": False,
                "last_probe_at": probed_at,
                "probe_message": f"Kismet probe failed safely: {exc}",
            }

    def _extract_devices(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("devices", "data", "rows", "observations"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            # Kismet sometimes returns a keyed object from some endpoints.
            dict_values = [value for value in payload.values() if isinstance(value, dict)]
            if dict_values:
                return dict_values
        return []

    def _extract_alerts(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("alerts", "data", "rows", "events", "messages"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            dict_values = [value for value in payload.values() if isinstance(value, dict)]
            if dict_values:
                return dict_values
        return []

    def _fetch_devices_sync(self, limit: int | None = None) -> dict[str, Any]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            fetch_method = "POST"
            try:
                payload = self._post_devices_json()
            except Exception:
                # Compatibility fallback for older Kismet versions and proxies
                # which only allow the unfiltered devices GET endpoint.
                fetch_method = "GET"
                payload = self._request_json(self.devices_url)
            devices = self._extract_devices(payload)
            total = len(devices)
            if limit is not None and limit > 0:
                devices = devices[:limit]
            self._last_device_count = total
            self._last_fetch_at = fetched_at
            self._last_error = None
            return {
                "enabled": True,
                "source": "kismet_live_api",
                "url": self.devices_url,
                "fetch_method": fetch_method,
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
                "source": "kismet_live_api",
                "url": self.devices_url,
                "fetched_at": fetched_at,
                "total_devices": 0,
                "returned_devices": 0,
                "devices": [],
                "error": str(exc),
            }

    def _fetch_alerts_sync(self, limit: int | None = None) -> dict[str, Any]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        try:
            payload = self._request_json(self.alerts_url)
            alerts = self._extract_alerts(payload)
            total = len(alerts)
            if limit is not None and limit > 0:
                alerts = alerts[:limit]
            self._last_error = None
            return {
                "enabled": True,
                "source": "kismet_alert_api",
                "url": self.alerts_url,
                "fetched_at": fetched_at,
                "total_alerts": total,
                "returned_alerts": len(alerts),
                "alerts": alerts,
            }
        except Exception as exc:
            self._last_error = str(exc)
            return {
                "enabled": True,
                "source": "kismet_alert_api",
                "url": self.alerts_url,
                "fetched_at": fetched_at,
                "total_alerts": 0,
                "returned_alerts": 0,
                "alerts": [],
                "error": str(exc),
            }


# Backwards-compatible name used by main.py in the current project.
KismetCollectorStub = KismetCollector

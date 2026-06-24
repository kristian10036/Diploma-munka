import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import SpectrumSettings

from .base import SpectrumFrame, SpectrumSource, SpectrumSourceUnavailable


class AaroniaRTSAHTTPSource(SpectrumSource):
    """Safe Aaronia RTSA connectivity probe; real spectrum parsing is not implemented."""

    mode = "aaronia_rtsa"

    def __init__(self, settings: SpectrumSettings):
        self.settings = settings
        self._probe_result: dict[str, Any] = {
            "reachable": None,
            "last_probe_at": None,
            "probe_message": "Connection has not been probed yet",
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "active": False,
            "status": "not_ready",
            "message": "Aaronia RTSA source configured but real parser is not implemented yet",
            "url": self.settings.aaronia_rtsa_url,
            "timeout_seconds": self.settings.aaronia_timeout_seconds,
            **self._probe_result,
        }

    async def probe(self) -> dict[str, Any]:
        self._probe_result = await asyncio.to_thread(self._probe_sync)
        return self.get_status()

    def _probe_sync(self) -> dict[str, Any]:
        probed_at = datetime.now(timezone.utc).isoformat()
        request = Request(
            self.settings.aaronia_rtsa_url,
            method="GET",
            headers={"User-Agent": "tscm-spectrum-source-probe/1.0"},
        )
        try:
            with urlopen(request, timeout=self.settings.aaronia_timeout_seconds) as response:
                status_code = getattr(response, "status", None)
            return {
                "reachable": True,
                "last_probe_at": probed_at,
                "probe_message": f"HTTP endpoint reachable (status {status_code}); parser TODO",
            }
        except HTTPError as exc:
            return {
                "reachable": True,
                "last_probe_at": probed_at,
                "probe_message": f"HTTP endpoint responded with status {exc.code}; parser TODO",
            }
        except (URLError, TimeoutError, OSError) as exc:
            return {
                "reachable": False,
                "last_probe_at": probed_at,
                "probe_message": f"HTTP endpoint unavailable: {exc}",
            }
        except Exception as exc:
            return {
                "reachable": False,
                "last_probe_at": probed_at,
                "probe_message": f"HTTP endpoint probe failed safely: {exc}",
            }

    async def read_frame(self) -> SpectrumFrame:
        if self._probe_result["reachable"] is None:
            await self.probe()
        # TODO: Implement only after the actual Aaronia RTSA HTTP payload and
        # its frequency/power semantics are documented and validated.
        raise SpectrumSourceUnavailable(
            "Aaronia RTSA frame parser is not implemented; no RF data was produced."
        )

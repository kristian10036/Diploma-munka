from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query
from prometheus_client import REGISTRY

from app.metrics import PROMETHEUS_QUERY_ERRORS
from app.runtime import PROMETHEUS_URL, mqtt_status

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

_ALLOWED_QUERIES = {
    "request_rate": 'sum(rate(dm_http_requests_total[5m]))',
    "request_latency_p95": 'histogram_quantile(0.95, sum(rate(dm_http_request_duration_seconds_bucket[5m])) by (le))',
    "spectrum_fps": 'sum(rate(dm_spectrum_frames_total[1m]))',
    "spectrum_clients": 'dm_backend_websocket_clients',
    "ingest_fps": 'spectrum_ingest_source_fps',
    "ingest_dropped": 'spectrum_ingest_dropped_frames_total',
    "ingest_invalid": 'spectrum_ingest_invalid_frames_total',
    "ingest_clients": 'spectrum_ingest_connected_clients',
    "db_errors": 'increase(dm_db_connection_errors_total[1h])',
    "anomaly_queue": 'dm_anomaly_queue_depth',
    "anomaly_drops": 'dm_anomaly_queue_dropped_frames',
    "recording_disk_free": 'dm_recording_disk_free_bytes',
    "alerts_open": 'sum(dm_alerts_open)',
    "sdrangel_drops": 'dm_sdrangel_iq_packets_dropped',
    "sdrangel_packet_loss": 'dm_sdrangel_iq_packet_loss',
}


def _local_sample(name: str, labels: dict[str, str] | None = None) -> float | None:
    try:
        value = REGISTRY.get_sample_value(name, labels or {})
        return float(value) if value is not None else None
    except Exception:
        return None


def _prometheus_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{PROMETHEUS_URL}{path}?{urlencode(params)}"
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=2.5) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        PROMETHEUS_QUERY_ERRORS.inc()
        raise RuntimeError(str(exc)) from exc
    if payload.get("status") != "success":
        PROMETHEUS_QUERY_ERRORS.inc()
        raise RuntimeError(payload.get("error") or "prometheus_query_failed")
    return payload["data"]


def _instant(query: str) -> list[dict[str, Any]]:
    return _prometheus_json("/api/v1/query", {"query": query}).get("result", [])


@router.get("/status")
def monitoring_status() -> dict[str, Any]:
    try:
        build = _prometheus_json("/api/v1/status/buildinfo", {})
        return {
            "implemented": True,
            "enabled": True,
            "available": True,
            "status": "ready",
            "url": PROMETHEUS_URL,
            "version": build.get("version"),
            "offline_local": True,
            "grafana_used": False,
        }
    except RuntimeError as exc:
        return {
            "implemented": True,
            "enabled": True,
            "available": False,
            "status": "unreachable",
            "url": PROMETHEUS_URL,
            "offline_local": True,
            "grafana_used": False,
            "error": str(exc),
        }


@router.get("/overview")
def monitoring_overview() -> dict[str, Any]:
    status = monitoring_status()
    values: dict[str, Any] = {}
    if status["available"]:
        for key, query in _ALLOWED_QUERIES.items():
            try:
                result = _instant(query)
                values[key] = float(result[0]["value"][1]) if result else None
            except (RuntimeError, KeyError, TypeError, ValueError):
                values[key] = None
    else:
        values = {
            "request_rate": None,
            "request_latency_p95": None,
            "spectrum_fps": None,
            "spectrum_clients": _local_sample("dm_backend_websocket_clients"),
            "ingest_fps": None,
            "ingest_dropped": None,
            "ingest_invalid": None,
            "ingest_clients": None,
            "db_errors": _local_sample("dm_db_connection_errors_total"),
            "anomaly_queue": _local_sample("dm_anomaly_queue_depth"),
            "anomaly_drops": _local_sample("dm_anomaly_queue_dropped_frames"),
            "recording_disk_free": _local_sample("dm_recording_disk_free_bytes"),
            "alerts_open": None,
            "sdrangel_drops": _local_sample("dm_sdrangel_iq_packets_dropped"),
            "sdrangel_packet_loss": _local_sample("dm_sdrangel_iq_packet_loss"),
        }
    return {
        "status": status,
        "mqtt": mqtt_status(),
        "values": values,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/series/{series_name}")
def monitoring_series(
    series_name: str,
    minutes: int = Query(60, ge=5, le=1440),
    step_seconds: int = Query(30, ge=5, le=3600),
) -> dict[str, Any]:
    query = _ALLOWED_QUERIES.get(series_name)
    if query is None:
        raise HTTPException(status_code=404, detail="unknown_monitoring_series")
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    try:
        data = _prometheus_json(
            "/api/v1/query_range",
            {
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step_seconds,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail={"code": "prometheus_unavailable", "message": str(exc)}) from exc
    series = []
    for item in data.get("result", []):
        series.append({
            "metric": item.get("metric", {}),
            "values": [[float(ts), float(value)] for ts, value in item.get("values", [])],
        })
    return {"name": series_name, "query": query, "series": series, "start": start.isoformat(), "end": end.isoformat()}

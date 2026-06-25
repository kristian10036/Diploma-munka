from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS_TOTAL = Counter(
    "dm_http_requests_total", "Backend HTTP requests", ("method", "path", "status")
)
HTTP_REQUEST_SECONDS = Histogram(
    "dm_http_request_duration_seconds", "Backend HTTP request duration", ("method", "path")
)
DB_CONNECTION_SECONDS = Histogram(
    "dm_db_connection_duration_seconds", "PostgreSQL connection establishment duration"
)
DB_CONNECTION_ERRORS = Counter(
    "dm_db_connection_errors_total", "PostgreSQL connection establishment failures"
)
SPECTRUM_FRAMES_TOTAL = Counter(
    "dm_spectrum_frames_total", "Spectrum frames produced by the backend source", ("source_mode",)
)
SPECTRUM_FRAME_POINTS = Histogram(
    "dm_spectrum_frame_points",
    "Number of points in backend spectrum frames",
    buckets=(16, 64, 128, 256, 512, 1024, 4096, 16384, 65536, 131072),
)
SPECTRUM_SOURCE_ERRORS_TOTAL = Counter(
    "dm_spectrum_source_errors_total", "Spectrum source errors", ("error_type",)
)
BACKEND_WS_CLIENTS = Gauge(
    "dm_backend_websocket_clients", "Connected clients on the legacy backend spectrum WebSocket"
)
PROMETHEUS_QUERY_ERRORS = Counter(
    "dm_prometheus_query_errors_total", "Failed local Prometheus HTTP API queries"
)
REFERENCE_IMPORTS_TOTAL = Counter(
    "dm_reference_imports_total", "Versioned reference imports", ("format", "result")
)
REFERENCE_IMPORTED_POINTS = Histogram(
    "dm_reference_imported_points",
    "Points retained after reference import and resampling",
    buckets=(2, 10, 100, 1000, 10000, 65536, 100000),
)

RECORDING_BYTES_TOTAL = Counter(
    "dm_recording_bytes_total", "Bytes finalized by backend recording writers", ("recording_type",)
)
RECORDING_ITEMS_TOTAL = Counter(
    "dm_recordings_finalized_total",
    "Recordings finalized by backend writers",
    ("recording_type", "result"),
)
RECORDING_DISK_FREE_BYTES = Gauge(
    "dm_recording_disk_free_bytes", "Free bytes on the recording filesystem"
)
RECORDING_LOW_DISK = Gauge(
    "dm_recording_low_disk", "1 when recording free space is below the configured reserve"
)
SDRANGEL_IQ_QUEUE_DEPTH = Gauge(
    "dm_sdrangel_iq_queue_depth", "Current SDRangel IQ data-plane queue depth"
)
SDRANGEL_IQ_PACKETS_DROPPED = Gauge(
    "dm_sdrangel_iq_packets_dropped", "Packets dropped by the SDRangel IQ data-plane queue"
)
SDRANGEL_IQ_PACKET_LOSS = Gauge(
    "dm_sdrangel_iq_packet_loss", "Packet-loss count reported by SDRangel IQ sources"
)
SDRANGEL_IQ_RECONNECTS = Gauge(
    "dm_sdrangel_iq_reconnects", "Reconnect attempts by the SDRangel IQ data plane"
)
ANOMALY_QUEUE_DEPTH = Gauge("dm_anomaly_queue_depth", "Current online anomaly pipeline queue depth")
ANOMALY_QUEUE_DROPS = Gauge(
    "dm_anomaly_queue_dropped_frames", "Spectrum frames dropped by the anomaly queue"
)
ANOMALY_DETECTIONS_TOTAL = Counter(
    "dm_anomaly_detections_total", "Anomaly detections", ("domain", "class_name", "severity")
)
ANOMALY_INFERENCE_SECONDS = Histogram(
    "dm_anomaly_inference_seconds", "Rule/statistical anomaly processing latency"
)
RECORDING_FRAMES_TOTAL = Counter(
    "dm_recording_frames_total",
    "Frames or samples finalized by recording writers",
    ("recording_type",),
)
ML_INFERENCE_SECONDS = Histogram(
    "dm_ml_inference_seconds",
    "Online rule/statistical or trained-model inference latency",
    ("pipeline",),
)
ML_QUEUE_DEPTH = Gauge("dm_ml_queue_depth", "Current online analysis queue depth", ("pipeline",))
ML_QUEUE_DROPS = Gauge(
    "dm_ml_queue_dropped_frames", "Frames dropped by online analysis queues", ("pipeline",)
)
COLLECTOR_STATUS = Gauge(
    "dm_collector_available", "Collector availability (1 available, 0 unavailable)", ("collector",)
)
ALERTS_OPEN = Gauge("dm_alerts_open", "Open or acknowledged alerts", ("severity",))


def _normalized_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path


def install_metrics(app: FastAPI) -> None:
    """Install a local Prometheus endpoint and bounded-label request metrics."""

    @app.middleware("http")
    async def prometheus_http_middleware(request: Request, call_next: Callable):
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            path = _normalized_path(request)
            HTTP_REQUESTS_TOTAL.labels(request.method, path, str(status)).inc()
            HTTP_REQUEST_SECONDS.labels(request.method, path).observe(time.perf_counter() - started)

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

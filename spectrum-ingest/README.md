# Spectrum ingest

Állapot: **implemented; tested with mock**.

A service az RF agent `SpectrumFrame v1` WebSocketét fogyasztja, validálja, majd bounded kliens queue-kon továbbítja. Az upstream kiesése `degraded` állapot, nem teszi unhealthyvé a core service-t.

Endpointok:

- `GET /health`
- `GET /status`
- `GET /metrics`
- `WebSocket /ws/spectrum`
- `WebSocket /ws/status`

Metrikák: `received_frames`, `invalid_frames`, `dropped_frames`, `sequence_gaps`, `connected_clients`, `source_latency_ms`, `source_fps`, `outgoing_fps`.

Unit teszt:

```bash
docker build --target test -f spectrum-ingest/Dockerfile spectrum-ingest
```

Korlátok: recording integráció és perzisztens metrikaexport még nincs implementálva. Valós Aaronia/USRP upstreammel nincs tesztelve.

# Offline monitoring Prometheusszal, Grafana nélkül

A Prometheus kizárólag a helyi Docker-hálózaton futó metrikagyűjtő és idősoros
lekérdező motor. Nincs `remote_write`, felhős telemetria vagy Grafana-függőség.
A felhasználói megjelenítést a saját **Rendszerállapot** fül adja.

## Adatút

```text
backend /metrics ───────┐
spectrum-ingest metrics ├─> helyi Prometheus ─> backend monitoring API ─> saját UI
egyéb exporterek később ┘
```

A Prometheus nincs host portra publikálva. A backend az alábbi, engedélyezett
API-kon keresztül kérdezi le:

- `GET /api/monitoring/status`
- `GET /api/monitoring/overview`
- `GET /api/monitoring/series/{series_name}`

A frontend nem kap szabad PromQL-hozzáférést. Az engedélyezett sorozatok a
`python-processor/app/routers/monitoring.py` fájlban vannak felsorolva.

## Fő metrikák

- HTTP kérési darabszám és késleltetés;
- SpectrumFrame darabszám, frame-méret, invalid/eldobott frame és sequence gap;
- backend és ingest WebSocket kliensek;
- DB kapcsolati hibák;
- recording darabszám, byte, frame/sample és szabad lemez;
- anomália/ML queue, drop, detektálás és inference idő;
- nyitott riasztások súlyosság szerint;
- SDRangel IQ queue, drop, packet loss és reconnect;
- collector elérhetőség.

Ha a Prometheus nem érhető el, a Rendszerállapot néhány aktuális, processzen
belüli metrikát továbbra is megmutat, de történeti grafikon nem áll rendelkezésre.
Ez `unreachable`/`degraded` állapot, nem hamis nulla.

## Offline image-kezelés

Internetkapcsolatos előkészítő gépen:

```bash
docker compose -f compose.yaml pull
docker save -o dm-core-images.tar \
  prom/prometheus:v3.5.0 \
  timescale/timescaledb:2.17.2-pg16 \
  eclipse-mosquitto:2.0.20 \
  nginx:1.27.5-alpine
sha256sum dm-core-images.tar > dm-core-images.tar.sha256
```

Offline célgépen:

```bash
sha256sum -c dm-core-images.tar.sha256
docker load -i dm-core-images.tar
docker compose -f compose.yaml up -d
```

A saját buildelt image-eket ugyanígy kell exportálni. A pontos image-listát a
`docker compose ... config --images` paranccsal kell előállítani azon a gépen,
ahol a végleges profil összeáll.

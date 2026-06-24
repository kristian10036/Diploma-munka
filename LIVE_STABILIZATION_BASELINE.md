# Live stabilization baseline

Dátum: 2026-06-22 (Europe/Budapest)

## Git baseline

- Baseline commit: `7e28b4609737d7c1065477f65589973bb465389d`
- Commit: `chore: import working RF monitoring baseline`
- Remote: `https://github.com/kristian10036/Diploma-munka.git`
- A remote a baseline létrehozásakor üres volt, ezért a fenti root commit az első
  megváltoztathatatlan forrásállapot.
- A futtatókörnyezet üres, read-only `.git` könyvtárat biztosít. A tényleges
  helyi metadata `.git-local`; a Git parancsok formája:
  `git --git-dir=.git-local <parancs>`.
- `.env`, recording, upload, backup, cache és runtime adat nem került a
  baseline commitba.

## Compose és futó szolgáltatások

Az ellenőrzött konfiguráció:

```text
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml config --quiet
PASS
```

| Szolgáltatás | Baseline állapot |
| --- | --- |
| backend | running, healthy |
| database | running, healthy |
| frontend | running, healthy |
| kismet | running, healthcheck nélkül |
| mosquitto | running, healthy |
| ollama | running, healthy |
| prometheus | running, healthy |
| reverse-proxy | running, healthy; host `8080/tcp` |
| rf-agent | running, healthy |
| spectrum-ingest | running, healthy; localhost `9998/udp` |

A baseline rögzítésekor szolgáltatásleállítás vagy -újraindítás nem történt.

## Teszteredmények

| Ellenőrzés | Eredmény | Megjegyzés |
| --- | --- | --- |
| Python compile | PASS | dokumentált offline acceptance része |
| Backend unit | PASS, 57/57 | runtime image-ben, read-only source mounttal |
| Frontend külső JavaScript syntax | PASS | Node `--check` |
| Frontend inline JavaScript syntax | PASS | inline script blokkok külön ellenőrizve |
| SpectrumFrame/view-model fixture | PASS | Node fixture |
| Frontend statikus smoke | PASS | fő fülsor és DOM invariánsok |
| Spectrum-ingest unit | PASS | runtime image-ben, read-only source mounttal |
| C++ build | PASS | Docker `test` target, Debug baseline build |
| CTest | PASS, 11/11 | friss `ctest --output-on-failure` futás |
| Shell syntax | PASS | `bash -n scripts/*.sh` |
| Compose config | PASS | a három karbantartott Compose-réteggel |
| WebSocket smoke | PASS | reverse proxy `/ws/spectrum`, 16384 pont, Aaronia |
| Élő health/readiness/status | PASS | backend, ingest és RF-agent elérhető |

### Dokumentált baseline-hibák

A host Python környezetből futtatott `scripts/acceptance-test.sh --offline`
négy hibát jelez. Ezek a baseline részei, és nem zoom-regressziók:

1. A host Pythonból hiányzik a `prometheus_client`, ezért négy backend
   tesztmodul collectionje hibázik. Ugyanezek a runtime image-ben 57/57 PASS.
2. Ugyanezért a host spectrum-ingest unit futás hibázik; a runtime image-ben PASS.
3. Ugyanezért az offline load fixture hoston nem indul.
4. A statikus production invariáns minden nem reverse-proxy `ports` bejegyzést
   elutasít, ezért a spectrum-ingest localhost-only `9998/udp` relay portját is
   hibának tekinti.

## Aaronia élő állapot

| Tulajdonság | Baseline érték |
| --- | --- |
| Source state | `running` |
| Source backend/type | `aaronia` |
| Device | `A3-x-83000043.xxaaaxbx` |
| Modell | `SPECTRAN V6 6 GHz / 492 MHz RTBW` |
| Measurement mode | `sweepsa` |
| Szimulált adat | `false` |
| Probe státusz | `not_probed`; a futó worker adatút külön igazolt |
| Capability | spectrum, tuning, gain, recording és viewport control |
| Maximum spectrum points capability | 65536 |
| Capability frekvenciatartomány | 5 MHz – 18 GHz |

Az RF-agent státusz szerint a forrás elérhető és folyamatosan termel frame-et.
Az ingest `source_connected=true`, `invalid_frames=0` állapotú volt.

## Tényleges SpectrumFrame-adatok

Az értékek nem viewport-válasz becslései, hanem a WebSocketen érkezett valós
Aaronia SpectrumFrame mezői.

| Mutató | Baseline érték |
| --- | ---: |
| Start | 75,000,000 Hz |
| Stop | 5,999,633,439 Hz |
| Center | 3,037,316,719 Hz |
| Tényleges span | 5,924,633,439 Hz |
| RBW | 361,633.30078125 Hz |
| Step frequency | 361,633 Hz |
| SDK packet pontszám | nincs külön instrumentálva a baseline-ban |
| Worker kimeneti pontszám | 16,384 |
| Ingest/WebSocket pontszám | 16,384 |
| Power tömb elemszám | 16,384 |
| JSON payload méret | 308,197–308,218 byte |
| RF-agent WebSocket megfigyelt FPS | 6.52 |
| Ingest WebSocket megfigyelt FPS | 5.20 |
| `dropped` | `true` |
| `inaccurate` | `true` |
| `overflow` | `false` |
| RF-agent 20-frame minta sequence gap | 4 |
| Ingest 20-frame minta sequence gap | 1 |
| Ingest összesített `received_frames` | 5,452 |
| Ingest összesített `dropped_frames` | 2,153 |
| Ingest összesített `sequence_gaps` | 520 |
| Ingest source latency | 67.946 ms |
| Worker metadata `worker_dropped_frames` | növekvő; a mintában 6,802 |

A baseline nem tartalmaz külön SDK packet pontszámot vagy canvas-oldali
frame-byte mérést. Ezekhez az 1. fázisban célzott, additív instrumentálás kell;
nem szabad a 16,384 worker pontból visszakövetkeztetni az SDK packet pontszámára.

## Erőforrásminta

Egyetlen `docker stats --no-stream` mintából:

| Komponens | CPU | Memória |
| --- | ---: | ---: |
| rf-agent | 122.04% | 188.4 MiB |
| spectrum-ingest | 26.26% | 63.04 MiB |
| backend | 49.00% | 187.4 MiB |

## WebSocket-adatút

```text
Aaronia SDK packet
→ aaronia-worker
→ NDJSON IPC
→ rf-agent latest-frame buffer
→ rf-agent /ws/spectrum
→ spectrum-ingest
→ reverse proxy /ws/spectrum
→ browser SpectrumFrameAdapter
→ SpectrumViewModel
→ natív detail trace + külön overview accumulator
```

- A reverse proxy WebSocket smoke PASS, `source_type=aaronia`, 16,384 pont.
- Az ingest az RF-agent host WebSockethez csatlakozik és valós frame-et továbbít.
- A frontend adapter megtartja a natív `frequenciesHz` és `powersDbm` tömböt.
- A detail envelope, marker és nearest-sample számítás a natív frame-re épül.
- A `NUM_BINS=24576` külön teljes tartományú overview/reference/maxhold rács.
- A baseline UI WebSocket-hiba esetén automatikus demo fallbacket indít; ennek
  production tiltása külön, későbbi kompatibilis fázis.

## API-kompatibilitási baseline

A backend OpenAPI baseline 104 pathot és 113 műveletet tartalmaz. Megőrzendő
kritikus kompatibilitási felületek:

| Terület | Megőrzendő route/kontraktus |
| --- | --- |
| Health | `/api/health`, `/api/health/live`, `/api/health/ready`, `/api/health/status` |
| Spectrum source | `/api/spectrum/source/status` |
| RF-agent állapot | `/api/rf-agent/status`, `/api/rf-agent/capabilities`, `/api/rf-agent/sources` |
| Viewport | `POST /api/rf-agent/source/viewport` → `POST /source/viewport` |
| Aaronia | `/api/rf-agent/aaronia/status`, `/api/rf-agent/aaronia/probe` |
| USRP/HackRF | meglévő status/probe route-ok; hardver állapot nem minősíthető `ready` értékre teszt nélkül |
| Recording/replay | `/api/rf-agent/recordings*`, `/api/rf-agent/replay/*`, `/api/recordings/*` |
| WebSocket | `/ws/spectrum`, `/ws/status`, `/ws/audio` |
| Marker/known signal | `/api/markers*`, `/api/known-signals*` |
| Reference/maxhold munkafolyamat | `/api/references*`, `/api/spectrum/reference-captures`, `/api/spectrum/peaks` |
| Session/import | `/api/sessions*`, `/api/import*`, `/api/imports/{device_type}` |
| Anomaly/alert/audit | `/api/anomalies*`, `/api/detections*`, `/api/alerts*`, `/api/audit/events` |
| Monitoring/system | `/api/monitoring/*`, `/api/system/status` |

A SpectrumFrame v1 kötelező mezői változatlanok: `schema_version`, source és
session azonosítók, timestamp, sequence, start/stop/step/center, RBW,
`num_points`, `powers_dbm`, `flags`, `metadata`. A régi tömbös frontend payloadok
az adapteren keresztül továbbra is támogatottak.

## Baseline következtetések az 1. fázishoz

1. A széles sweep natív pontszáma 16,384, de a tényleges lépés/RBW körülbelül
   361.6 kHz; puszta vizuális zoom nem javít ezen.
2. A worker és az ingest között már a baseline-ban van drop és sequence gap.
   Bináris protokoll csak külön mérési bizonyíték alapján vezethető be.
3. Az SDK packet eredeti pontszáma és a downsampling factor nincs a jelenlegi
   frame-ben bizonyíthatóan instrumentálva.
4. A hardveres viewport jelenleg csak kézi tartományalkalmazáskor indul; wheel,
   pan, dupla kattintás, kijelölés és overview navigáció nem retune-ol automatikusan.

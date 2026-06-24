# Diploma RF monitoring platform

Moduláris, offline-képes RF/Wi-Fi/Bluetooth megfigyelő és elemző rendszer.
A HP demonstrációs gépen teljesen használható mock és replay módban, majd ugyanaz
az adattárolási és webes réteg átköltöztethető modernebb, AVX2-képes hardverszerverre.

## Fő komponensek

- **C++ RF agent:** közös `SpectrumFrame v1`, mock, replay, recording, Aaronia és
  USRP izolált probe, SDRangel REST control plane.
- **Spectrum ingest:** WebSocket reconnect, frame-validáció, bounded latest-frame
  elosztás és metrikák.
- **FastAPI backend:** PostgreSQL/TimescaleDB, Kismet/BLE, mérési sessionök,
  referenciák, ML, context-grounded assistant és pgvector RAG.
- **Frontend:** spektrum/waterfall, Wi-Fi, Bluetooth, RF Agent, Felvételek, ML,
  külön RAG-asszisztens és Rendszerállapot fülek.
- **Offline AI:** opcionális Ollama generáló modell és külön embeddingmodell.
- **Üzemeltetés:** helyi/offline Prometheus, saját Rendszerállapot UI Grafana nélkül,
  biztonságos Docker audit/cleanup, backup/restore, migrációs és acceptance scriptek.

## Gyors indítás

```bash
cp .env.example .env
# Állítsd be legalább a POSTGRES_PASSWORD értékét.

set -a
source .env
source config/hp-demo.env
set +a

docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  -f compose.dev.yaml \
  up -d --build
```

Web UI: `http://SERVER_IP:8080`

A `compose.dev.yaml` kizárólag override: bind mountot és backend reloadot ad,
önállóan nem indítható. Demo/production jellegű indításnál hagyd el:

```bash
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml up -d --build
```

Az egyszeri Ollama modelltelepítés: `bash scripts/ollama-setup.sh`. A
`qwen3:8b` és `bge-m3` a `ollama-data` volume-ban marad image-frissítés után is.

A részletes indítási módokat a [RUNNING.md](RUNNING.md), a költözést a
[MIGRATION.md](MIGRATION.md), a Grafana nélküli offline monitoringot pedig a
[MONITORING.md](MONITORING.md) tartalmazza. Az architektúra leírása az
[ARCHITECTURE.md](ARCHITECTURE.md), a phase2 tételes eredménye pedig a
[PHASE2_IMPLEMENTATION_REPORT.md](PHASE2_IMPLEMENTATION_REPORT.md) fájlban található.

## Állapotjelölések

A dokumentáció következetesen külön választja:

- `implemented` – a kód elkészült;
- `tested` – automata vagy élő teszt lefutott;
- `tested only with mock/replay` – hardver nélkül igazolt;
- `hardware not tested` – valós eszközzel még nincs bizonyítva;
- `experimental` – implementált, de verzió/hardverfüggő;
- `not implemented` – nincs tényleges adatút.

## Fontos korlátok

- A valós **Aaronia SpectrumFrame adatút** még nincs implementálva; az izolált
  SDK-probe elkészült. CPU/loader/SDK hibánál részletes állapotot ad, miközben
  a fő rf-agent életben marad.
- A **USRP UHD discovery probe** opcionálisan fordítható; a folyamatos IQ/FFT
  worker adatút még nincs kész és nincs valós USRP-vel tesztelve.
- Az **SDRangel control plane** implementált, de valós SDRangel-verzióval még
  tesztelendő. Az IQ data plane verziózott, bounded mock rétege elkészült; a
  tényleges SDRangel input/plugin továbbra is `not_configured`/`hardware_not_tested`.
- A klasszikus és CNN RF modellek valós, megfelelően címkézett adatok nélkül
  `not_trained` állapotúak.

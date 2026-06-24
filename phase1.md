# Diploma projekt – folytatási és véglegesítési specifikáció

A meglévő `Diploma_munka5_kismet_integrated` projekt fejlesztését kell folytatnod.

A korábbi fejlesztési specifikáció alapján a munka elvileg a 11. pontig jutott el. Ne indulj nulláról, ne valósítsd meg vakon újra az 1–11. pontot, és ne írj felül működő megoldásokat.

Első lépésként auditáld a jelenlegi projektállapotot, ellenőrizd az eddig létrehozott kódot, dokumentációt, Compose-fájlokat, adatbázis-migrációkat és Git diffet. Ezután javítsd az esetleges félbehagyott vagy hibás részeket, majd folytasd a fejlesztést a 12. ponttól.

---

# 0. Kötelező kezdő audit

Mielőtt módosítasz bármit:

```bash
pwd
git status
git diff --stat
git diff
find . -maxdepth 3 -type f | sort
docker compose config
docker compose ps -a
```

Olvasd el legalább:

```text
README.md
RUNNING.md
PROJECT_AUDIT.md
ARCHITECTURE.md
RF_AGENT.md
MIGRATION.md
BACKUP_RESTORE.md
compose.yaml
compose.rf.yaml
compose.ai.yaml
compose.dev.yaml
.env.example
config/hp-demo.env
config/production-hardware.env
```

Vizsgáld át:

```text
backend/
spectrum-ingest/
rf-agent/
ml/
database/migrations/
scripts/
docker/
frontend/
```

Készíts:

```text
PHASE_1_11_REVIEW.md
```

Ebben az 1–11. pont mindegyikéhez adj státuszt:

```text
DONE
PARTIAL
BROKEN
NOT IMPLEMENTED
NOT APPLICABLE
```

Minden ponthoz írd le:

* mely fájlok valósítják meg;
* milyen teszt bizonyítja;
* mi hiányzik;
* szükséges-e korrekció;
* változott-e a publikus API vagy a WebSocket séma.

Az audit után először csak a félbehagyott vagy hibás korábbi részeket javítsd.

---

# 1. Hardverkörnyezet

## Jelenlegi HP demonstrációs szerver

```text
HP EliteBook
Intel Core i5-2540M
AVX támogatás: igen
AVX2 támogatás: nincs
Debian Linux
Docker és Docker Compose
```

A HP feladata:

* hordozható szerver;
* fejlesztési környezet;
* demonstrációs gép;
* PostgreSQL/TimescaleDB;
* backend;
* frontend;
* reverse proxy;
* Mosquitto;
* Kismet;
* Wi-Fi és Bluetooth adatgyűjtés;
* mock spektrumforrás;
* replay spektrumforrás;
* C++ RF agent mock/replay módban;
* CNN CPU-inferencia kis modellel;
* opcionális Ollama-integráció, ha rendelkezésre áll elég erőforrás.

A HP-n az Aaronia SDK-t izolált folyamatban ténylegesen ki kell próbálni.

Nem feltételezhető előre, hogy működik vagy nem működik AVX2 nélkül.

## Későbbi célgép

```text
Nagy teljesítményű Linux szerver vagy RF munkaállomás
AVX2 vagy AVX512 CPU
Aaronia SPECTRAN V6 Plus
USRP B210/N310/X310/X410
UHD driver
SDRangel
nagyobb memória és tárhely
```

A projekt költöztetéséhez ne kelljen forráskódot átírni. Csak konfiguráció, natív függőségek, build kapcsolók és környezeti változók változhatnak.

---

# 2. Az 1–11. pontból elvárt jelenlegi állapot

Ezeket ellenőrizd, de ne valósítsd meg újra, ha már helyesen elkészültek:

1. Projekt-audit.
2. Monorepo könyvtárstruktúra.
3. Compose core/RF/AI/dev felosztás.
4. A korábbi monolitikus `main.py` modulokra bontása.
5. Kismet RSSI-normalizálás.
6. Kismet Wi-Fi/Bluetooth integráció megtartása.
7. C++ RF agent és Aaronia backend kezdete.
8. USRP backend vagy skeleton.
9. Közös `SpectrumFrame`.
10. Mock backend.
11. Replay backend.

Az alábbi kritikus feltételeket külön ellenőrizd.

---

# 3. Refaktorálási kompatibilitás ellenőrzése

Ha a korábbi `main.py` már szét lett bontva, bizonyítsd, hogy nem változott meg a publikus viselkedés.

Legyen:

```text
tests/api/
tests/websocket/
tests/integration/
```

Ellenőrizd:

* endpoint URL-ek;
* HTTP methodok;
* request mezők;
* response mezők;
* HTTP státuszkódok;
* WebSocket frame-ek;
* frontend által használt endpointok;
* adatbázis-lekérdezések;
* sessionkezelés;
* fájlfeltöltések;
* Kismet import;
* Wi-Fi/Bluetooth lekérdezés;
* spektrum WebSocket.

Ha még nincs, készíts OpenAPI snapshotot:

```text
tests/snapshots/openapi.json
```

Készíts WebSocket séma-karakterizációs teszteket.

Ne változtasd meg a publikus API-t csak azért, hogy szebb legyen a belső kód.

---

# 4. Kismet RSSI bizonyítása

A javítás nem tekinthető késznek pusztán attól, hogy a kódban szerepel az RSSI mapping.

Bizonyítsd SQL-lel:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(signal_dbm) AS signal_rows,
    COUNT(rssi_dbm) AS rssi_rows
FROM wifi_observations;
```

Bluetooth:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(rssi_dbm) AS rssi_rows
FROM bluetooth_observations;
```

Készíts dokumentált tesztet újonnan importált sorokkal.

Ne a régi, már hibásan importált sorok számából következtess.

A collector támogassa a Kismet valós mezőaliasait, többek között:

```text
device_last_signal
kismet.common.signal.last_signal
kismet.device.base.signal/kismet.common.signal.last_signal
bluetooth_rssi_last
bluetooth_rssi_avg
bluetooth.device.rssi_last
bluetooth.device.rssi_avg
```

---

# 5. Aaronia folyamatizoláció – kötelező korrekció

A `libAaroniaRTSAAPI.so` vendor libraryt a fő `rf-agent` folyamat nem töltheti be közvetlenül.

A sima `dlopen()` nem védi meg a fő folyamatot egy `SIGILL`, `SIGSEGV` vagy más natív crash ellen.

Készüljön három komponens:

```text
rf-agent
aaronia-probe
aaronia-worker
```

## `rf-agent`

A stabil főfolyamat:

* REST API;
* WebSocket;
* source-választás;
* mock/replay backend;
* worker felügyelet;
* recording;
* státusz;
* health;
* reconnect;
* hibatűrés.

A vendor SDK hibája nem állíthatja le.

## `aaronia-probe`

Külön futtatható rövid életű program.

Feladata:

1. CPU feature információ gyűjtése.
2. Aaronia header/library helyének ellenőrzése.
3. `dlopen(..., RTLD_NOW | RTLD_LOCAL)`.
4. Szükséges szimbólumok feloldása `dlsym()` segítségével.
5. `AARTSAAPI_Init_With_Path()` biztonságos tesztje.
6. Strukturált JSON eredmény kiírása stdout-ra.
7. Kilépés.

Lehetséges eredmények:

```text
sdk_not_found
sdk_symbol_missing
library_load_failed
library_sigill
library_sigsegv
sdk_init_failed
sdk_ready
probe_timeout
unknown_failure
```

A fő `rf-agent` subprocessként indítsa a probe-ot.

Vizsgálja:

* normál exit kód;
* signal miatti leállás;
* timeout;
* stdout JSON;
* stderr diagnosztika.

Példa státusz:

```json
{
  "backend": "aaronia",
  "cpu_has_avx": true,
  "cpu_has_avx2": false,
  "probe_attempted": true,
  "probe_result": "library_sigill",
  "available": false
}
```

A CPUID AVX2 eredménye csak diagnosztikai adat.

Az AVX2 hiánya nem akadályozhatja meg az izolált probe futását.

Ne állítsd, hogy biztosan van SSE4.2 fallback. Ezt csak valós HP-teszt bizonyíthatja.

## `aaronia-worker`

A valódi Aaronia hardverkezelés külön processzben fusson.

Feladata:

* SDK inicializálás;
* eszközfelderítés;
* eszköznyitás;
* konfiguráció;
* indítás;
* packet olvasás;
* packet fogyasztás;
* leállítás;
* reconnect;
* diagnosztika.

A fő `rf-agent` felügyelje:

* PID;
* heartbeat;
* exit status;
* signal;
* restart backoff;
* utolsó hiba;
* utolsó sikeres frame.

A worker crash ne okozzon teljes rendszerleállást.

Ne legyen végtelen restart loop.

Használj exponenciális vagy korlátozott backoffot.

---

# 6. Aaronia SDK implementáció szabályai

Csak a következő források alapján dolgozz:

```text
aaroniartsaapi.h
RawSpectrum.cpp
SweepSpectrum.cpp
EnumDevices.cpp
ConfigTree.cpp
RawIQ.cpp
IQReceiver.cpp
```

Ne találj ki API-függvényeket, paramétereket vagy channel jelentést.

A dokumentált híváslánc alapján dolgozz:

```text
AARTSAAPI_Init_With_Path
AARTSAAPI_Open
AARTSAAPI_RescanDevices
AARTSAAPI_EnumDevice
AARTSAAPI_OpenDevice
AARTSAAPI_ConfigRoot
AARTSAAPI_ConfigFind
AARTSAAPI_ConfigSetString
AARTSAAPI_ConnectDevice
AARTSAAPI_StartDevice
AARTSAAPI_GetPacket
AARTSAAPI_ConsumePackets
AARTSAAPI_StopDevice
AARTSAAPI_DisconnectDevice
AARTSAAPI_CloseDevice
AARTSAAPI_Close
AARTSAAPI_Shutdown
```

Az SDK error code-okhoz készíts saját, dokumentált leképezést.

Minden native resource RAII wrapperen keresztül legyen kezelve.

A leállítás többször is biztonságosan meghívható legyen.

## Build

```cmake
option(ENABLE_AARONIA "Build Aaronia helper processes" ON)
```

Az `ENABLE_AARONIA=ON` ne jelentse automatikusan azt, hogy a hardveres source induláskor aktiválódik.

A tényleges kiválasztás:

```env
RF_SOURCE_MODE=aaronia
```

Ha nincs SDK:

* a core és mock/replay build működjön;
* a probe adjon `sdk_not_found` státuszt;
* ne legyen linkerhiba az egész projektben.

---

# 7. USRP architektúra

A USRP backend lehet külön worker folyamat is:

```text
usrp-worker
```

Az UHD hibája ne döntse be a fő RF agentet.

Build kapcsoló:

```cmake
option(ENABLE_USRP "Enable UHD USRP support" OFF)
```

Ha UHD elérhető:

```cmake
find_package(UHD REQUIRED)
```

Támogatandó:

* device discovery;
* device args;
* serial;
* center frequency;
* sample rate;
* gain;
* bandwidth;
* antenna;
* clock source;
* time source;
* RX stream;
* timeout;
* overflow;
* dropped sample;
* reconnect;
* több channel későbbi lehetősége.

Ne legyen egyetlen USRP-modellre hardcode-olva.

HP-n alapból:

```env
ENABLE_USRP=false
```

---

# 8. Közös SpectrumFrame – végleges séma

Minden spektrumforrás pontosan ugyanazt a sémát adja.

```json
{
  "schema_version": 1,
  "sensor_id": "hp-demo-01",
  "source_type": "mock",
  "source_device": "mock-generator",
  "session_id": "uuid",
  "timestamp": "2026-06-19T12:00:00.000Z",
  "sequence": 12345,
  "start_frequency_hz": 2400000000,
  "stop_frequency_hz": 2499902343,
  "step_frequency_hz": 97656,
  "center_frequency_hz": 2450000000,
  "sample_rate_hz": 100000000,
  "rbw_hz": 97656,
  "num_points": 1024,
  "power_unit": "dBm",
  "powers_dbm": [],
  "flags": {
    "overflow": false,
    "dropped": false,
    "inaccurate": false
  },
  "metadata": {
    "is_simulated": true
  }
}
```

Matematikai szabály:

```text
frequency[i] =
start_frequency_hz + i × step_frequency_hz
```

```text
stop_frequency_hz =
start_frequency_hz
+ step_frequency_hz × (num_points - 1)
```

Kötelező validáció:

* `powers_dbm.size() == num_points`;
* `num_points > 0`;
* `step_frequency_hz > 0`;
* `start_frequency_hz < stop_frequency_hz`;
* center frequency a tartományon belül;
* NaN és Infinity elutasítása;
* maximális frame-méret;
* növekvő sequence;
* szabályos timestamp;
* hibás frame eldobása;
* hibás frame ne állítsa le a streamet.

Mock és replay forrás esetén:

```json
{
  "is_simulated": true
}
```

Mock adat nem használhat:

```text
source_type=aaronia
source_type=usrp
```

---

# 9. 12. pont – közös FFT pipeline

Most innen folytasd az új fejlesztést.

Készíts közös FFT komponenst az IQ-forrásokhoz.

Javasolt szerkezet:

```text
rf-agent/include/rf_agent/dsp/
rf-agent/src/dsp/
```

Komponensek:

```text
FftProcessor
WindowFunction
DcBlocker
SpectrumAverager
MaxHoldProcessor
PeakDetector
FrameRateLimiter
CalibrationProcessor
```

Támogatás:

* FFT size;
* Hann window;
* Blackman-Harris window;
* rectangular window csak teszteléshez;
* DC offset eltávolítás;
* komplex IQ feldolgozás;
* FFT shift;
* dBFS számítás;
* kalibrációs offset;
* averaging;
* max hold;
* peak detection;
* frame rate limit;
* dropped frame statisztika.

Konfiguráció:

```env
FFT_SIZE=2048
FFT_WINDOW=hann
FFT_AVERAGING=4
FFT_MAX_FPS=5
FFT_CALIBRATION_OFFSET_DB=0
FFT_PEAK_THRESHOLD_DB=10
```

A HP-demó alapértékei maradjanak alacsonyak.

Az FFT pipeline legyen unit tesztelhető generált sinus és zaj bemenettel.

Tesztelje:

* egyetlen ismert frekvenciájú sinus csúcsát;
* két sinus elkülönítését;
* zajpadlót;
* DC komponenst;
* Hann ablakot;
* dBFS konverziót;
* NaN/Inf kezelést.

---

# 10. 13. pont – spectrum-ingest service

A spektrumfogadás legyen külön service.

Feladata:

* RF agent WebSocket kapcsolat;
* reconnect;
* exponential backoff;
* schema validation;
* sequence gap felismerés;
* frame rate mérés;
* latency mérés;
* hibás frame eldobás;
* frontend kliensek kiszolgálása;
* lassú kliens kezelése;
* source status továbbítása;
* recording integráció;
* WebSocket kapcsolat állapota.

Konfiguráció:

```env
RF_AGENT_URL=http://rf-agent:8765
RF_AGENT_WS_URL=ws://rf-agent:8765/ws/spectrum
SPECTRUM_SOURCE_MODE=mock
SPECTRUM_INGEST_MAX_QUEUE=32
SPECTRUM_INGEST_RECONNECT_SECONDS=2
SPECTRUM_CLIENT_MAX_FPS=5
```

Ne legyen korlátlan queue.

Lassú kliensnél régi frame dobható, de az újabb frame-ek maradjanak elérhetők.

Legyen metrika:

```text
received_frames
invalid_frames
dropped_frames
sequence_gaps
connected_clients
source_latency_ms
source_fps
outgoing_fps
```

A frontend ugyanazt az endpointot használja mock, replay, Aaronia és USRP esetén.

---

# 11. 14. pont – RF agent REST és WebSocket API

Kötelező endpointok:

```text
GET  /health
GET  /status
GET  /capabilities
GET  /sources
GET  /sources/current

POST /sources/select
POST /source/start
POST /source/stop
POST /source/configure

GET  /recordings
GET  /recordings/{id}
POST /recordings/start
POST /recordings/stop

POST /replay/start
POST /replay/pause
POST /replay/resume
POST /replay/seek
POST /replay/stop

GET  /aaronia/probe
POST /aaronia/probe
GET  /aaronia/status

GET  /usrp/status

GET  /sdrangel/status
POST /sdrangel/tune
POST /sdrangel/demod/start
POST /sdrangel/demod/stop

WebSocket /ws/spectrum
WebSocket /ws/status
```

Minden hibának strukturált JSON választ kell adnia.

Példa:

```json
{
  "error": {
    "code": "SOURCE_NOT_AVAILABLE",
    "message": "Aaronia SDK probe failed",
    "details": {
      "probe_result": "library_sigill"
    }
  }
}
```

Mock/replay módban az Aaronia vagy USRP hibája nem teheti unhealthyvé a teljes agentet.

---

# 12. Spectrum recording és replay formátum

A recording könyvtárszerkezete:

```text
recordings/
└── session_uuid/
    ├── metadata.json
    ├── frames.ndjson.zst
    └── checksum.sha256
```

`metadata.json` tartalma:

```json
{
  "schema_version": 1,
  "recording_id": "uuid",
  "session_id": "uuid",
  "source_type": "mock",
  "source_device": "mock-generator",
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601",
  "frame_count": 0,
  "start_frequency_hz": 0,
  "stop_frequency_hz": 0,
  "num_points": 0,
  "compression": "zstd",
  "checksum_algorithm": "sha256"
}
```

Replay funkció:

* start;
* stop;
* pause;
* resume;
* seek;
* loop;
* 0.5×;
* 1×;
* 2×;
* 5×;
* eredeti timestamp-alapú időzítés;
* sérült frame kihagyása;
* checksum ellenőrzés.

A PostgreSQL csak recording metadata adatokat tároljon.

---

# 13. CNN-alapú RF jelosztályozás

Ez a diplomamunka elsődleges ML komponense.

## Fontos adatforrás-korrekció

A Kismet RSSI idősor nem RF spektrogram.

CNN-bemenet csak:

* valós SPECTRAN spektrum;
* valós USRP spektrum;
* IQ-ból generált spektrogram;
* megfelelően címkézett szimulált spektrum vagy IQ.

Kismet használható:

* időszinkron címkézésre;
* Wi-Fi csatorna meghatározására;
* Bluetooth jelenlét kontextusára;
* SSID/BSSID/MAC kontextusra;
* weak label előállítására;
* mérési eredmény validálására.

## Adathalmaz

Szerkezet:

```text
ml/data/
├── raw/
├── processed/
├── labels/
└── splits/
```

Az adathalmaz felosztása recording vagy session szerint történjen.

Tilos véletlenszerű frame-szintű train/validation split, mert ugyanazon mérés szomszédos frame-jei adatszivárgást okozhatnak.

## Első osztályok

```text
wifi_2_4g
wifi_5g
bluetooth
zigbee
narrowband_unknown
wideband_unknown
noise
unknown
```

Ne ígérj olyan osztályt, amelyhez nincs elegendő adat.

## Modellek összehasonlítása

Készüljön legalább:

1. Szabályalapú baseline.
2. Klasszikus ML baseline, például RandomForest vagy SVM spektrumjellemzőkkel.
3. Kis CNN spektrogramokon.

## CNN

Példa:

```text
Conv2d(1, 32, 3)
BatchNorm
ReLU
MaxPool

Conv2d(32, 64, 3)
BatchNorm
ReLU
MaxPool

Conv2d(64, 128, 3)
BatchNorm
ReLU
GlobalAveragePooling

Linear(128, num_classes)
```

A kimeneten ne legyen explicit Softmax a tréningmodellben, ha `CrossEntropyLoss` használatos.

Metrikák:

* accuracy;
* precision;
* recall;
* macro F1;
* per-class F1;
* confusion matrix;
* inference latency;
* modellméret.

A HP-n csak kis CPU-inferencia legyen kötelező.

A tanítás külön folyamat és külön profile lehet.

## API

```text
POST /api/ml/classify
GET  /api/ml/status
GET  /api/ml/models
```

A classify válasz:

```json
{
  "model_version": "rf_classifier_v1",
  "predicted_class": "wifi_2_4g",
  "confidence": 0.94,
  "top_predictions": [
    {
      "class": "wifi_2_4g",
      "confidence": 0.94
    }
  ],
  "inference_time_ms": 12.4
}
```

Ha nincs modell:

```json
{
  "available": false,
  "status": "model_not_loaded"
}
```

---

# 14. Context-grounded assistant és valódi RAG

A jelenlegi keyword-match megoldást váltsd le.

## Első szint

Ha csak strukturált SQL-adatokból állítasz össze kontextust, a komponens neve:

```text
context-grounded assistant
```

Ne nevezd RAG-nak.

Folyamat:

1. Felhasználói kérdés.
2. Releváns session/Wi-Fi/Bluetooth/spektrum/ML-adatok SQL-lekérdezése.
3. Rövid, strukturált kontextus.
4. Ollama API-hívás.
5. Válasz, a felhasznált mérési rekordok azonosítóival.

## Valódi RAG opcionálisan

Valódi RAG csak akkor legyen késznek jelölve, ha van:

* embedding generálás;
* `pgvector` vagy más vektorindex;
* dokumentumdarabolás;
* retrieval;
* top-k releváns rekord;
* forrásazonosító;
* kontextus és válasz elkülönítése.

Ollama opcionális:

```env
AI_ENABLED=false
OLLAMA_URL=http://ollama:11434
OLLAMA_MODEL=
```

Ha nincs Ollama:

```json
{
  "available": false,
  "status": "ai_component_not_available"
}
```

A core stack ettől még működjön.

---

# 15. SDRangel integráció

Különítsd el:

```text
control plane
data plane
```

## Control plane

Az SDRangel REST API használható:

* státusz;
* device set;
* center frequency;
* demodulátor létrehozása;
* AM;
* NFM;
* WFM;
* USB;
* LSB;
* start;
* stop;
* channel konfiguráció.

Konfiguráció:

```env
SDRANGEL_ENABLED=false
SDRANGEL_API_URL=http://127.0.0.1:8091
SDRANGEL_TIMEOUT_SECONDS=5
```

A HP-n alapból disabled.

## Data plane

Az IQ-adatot a REST API nem továbbítja.

Ne állítsd késznek az IQ → SDRangel adatkapcsolatot addig, amíg nincs kiválasztva és tesztelve:

* kompatibilis hálózati IQ-formátum;
* meglévő SDRangel sample-source;
* vagy saját SDRangel input plugin.

Készíts:

```text
SDRANGEL_INTEGRATION.md
```

Ebben külön dokumentáld:

* mi működik;
* mi csak skeleton;
* mi igényel valós SDRangel tesztet;
* milyen IQ formátumot vár;
* milyen sample rate-et és adattípust használ;
* hogyan kezelhető a backpressure.

Frontend demoduláció gomb csak akkor legyen aktív, ha:

```text
RF source running
SDRangel reachable
control plane ready
data plane configured
```

---

# 16. Adattárolás

## PostgreSQL

Ide kerül:

* measurement session;
* RF source metadata;
* eszközmetadata;
* recording metadata;
* peak;
* detection;
* alert;
* marker;
* ritkított spectrum snapshot;
* ML eredmény;
* fájl elérési út;
* checksum;
* Kismet Wi-Fi eszköz;
* Bluetooth eszköz;
* audit esemény.

## Fájlrendszer

Ide kerül:

* teljes spectrum recording;
* IQ recording;
* replay fájl;
* audio recording;
* PCAP;
* `.kismet`;
* export;
* ML modell;
* dataset.

Az IQ-adat nem kerülhet PostgreSQL-be.

Host könyvtárak:

```text
/srv/diploma/postgres
/srv/diploma/kismet
/srv/diploma/uploads
/srv/diploma/recordings/spectrum
/srv/diploma/recordings/iq
/srv/diploma/recordings/audio
/srv/diploma/exports
/srv/diploma/backups
/srv/diploma/ml/models
/srv/diploma/ml/data
```

Ezek `.env` változókkal felülírhatók legyenek.

---

# 17. Service-stabilitás

Minden hosszú életű service:

```yaml
restart: unless-stopped
```

Kivéve:

```text
migrate
egyszeri jobok
probe jobok
```

A `migrate`:

* egyszer fusson;
* sikeres exit code 0;
* ne restartoljon.

Healthcheck:

* database;
* backend;
* frontend;
* reverse-proxy;
* spectrum-ingest;
* rf-agent;
* mosquitto, ha értelmesen megoldható;
* Kismet opcionálisan.

A teljes rendszer ne legyen unhealthy csak azért, mert:

* Aaronia disabled;
* USRP disabled;
* SDRangel disabled;
* Ollama disabled.

Logrotáció:

```yaml
logging:
  driver: local
  options:
    max-size: "10m"
    max-file: "3"
```

Ne legyen végtelen lognövekedés.

---

# 18. HP-demómód

Fájl:

```text
config/hp-demo.env
```

Ajánlott alapértékek:

```env
RF_SOURCE_MODE=replay

ENABLE_AARONIA=true
AARONIA_AUTO_START=false
AARONIA_PROBE_ON_START=true

ENABLE_USRP=false
SDRANGEL_ENABLED=false
AI_ENABLED=false

ML_ENABLED=true
ML_DEVICE=cpu

FFT_SIZE=2048
FFT_WINDOW=hann
FFT_AVERAGING=4
FFT_MAX_FPS=5

SPECTRUM_CLIENT_MAX_FPS=5
```

Az `ENABLE_AARONIA=true` itt csak azt jelenti, hogy a probe elérhető.

Nem jelenti azt, hogy a hardware source automatikusan elindul.

A HP-demó tudja:

* teljes frontend;
* spektrum;
* mock;
* replay;
* zoom;
* pan;
* marker;
* max hold;
* peak detection;
* session;
* recording;
* Kismet;
* Wi-Fi;
* Bluetooth;
* RSSI;
* ML inference;
* rendszerállapot;
* Aaronia probe eredmény.

---

# 19. Produkciós hardvermód

Fájl:

```text
config/production-hardware.env
```

Példa:

```env
RF_SOURCE_MODE=aaronia

ENABLE_AARONIA=true
AARONIA_AUTO_START=false

ENABLE_USRP=true
SDRANGEL_ENABLED=true
AI_ENABLED=true
ML_ENABLED=true

FFT_SIZE=4096
FFT_MAX_FPS=10
```

Ne tartalmazzon valódi jelszót, tokent vagy titkot.

---

# 20. Docker audit és biztonságos cleanup

Készíts vagy javíts:

```text
scripts/docker-audit.sh
scripts/docker-cleanup.sh
```

## Audit

Csak listázzon:

* compose service-ek;
* futó container;
* leállított container;
* orphan container;
* projektimage;
* dangling image;
* network;
* volume;
* build cache;
* disk usage.

## Cleanup

Alapból dry-run.

Törlés csak:

```bash
bash scripts/docker-cleanup.sh --apply
```

Törölhető:

* projekthez tartozó orphan container;
* bizonyíthatóan régi projektimage;
* dangling image;
* nem használt projektnetwork;
* build cache.

Soha ne töröljön:

* volume;
* PostgreSQL volume;
* Kismet volume;
* uploads;
* recording;
* ML modell;
* dataset;
* más projekthez tartozó komponenst.

Tilos:

```bash
docker system prune -a --volumes
docker compose down -v
```

---

# 21. Backup és restore

Készíts vagy javíts:

```text
scripts/backup.sh
scripts/restore.sh
BACKUP_RESTORE.md
```

Backup:

* PostgreSQL `pg_dump` custom format;
* Kismet fájlok;
* uploads;
* spectrum recording;
* IQ metadata és fájlok opcionálisan;
* audio;
* exportok;
* Compose fájlok;
* adatbázis-migrációk;
* `.env` védetten;
* ML modellek;
* dataset metadata;
* Git commit hash;
* verzió;
* checksumok.

A restore alapból dry-run.

Tényleges írás csak:

```bash
bash scripts/restore.sh --apply
```

A restore ne írjon felül meglévő adatot explicit kapcsoló nélkül.

---

# 22. Migráció HP-ról nagy szerverre

Készíts vagy frissíts:

```text
MIGRATION.md
scripts/pre-migration-check.sh
scripts/post-migration-check.sh
```

A migráció sorrendje:

1. Git állapot ellenőrzése.
2. Acceptance test.
3. Teljes backup.
4. Backup checksum ellenőrzése.
5. Projekt másolása.
6. Host könyvtárak létrehozása.
7. Docker/Compose ellenőrzése.
8. Natív Aaronia SDK telepítése.
9. UHD telepítése.
10. SDRangel telepítése.
11. Environment konfiguráció.
12. Core stack indítása.
13. PostgreSQL restore.
14. Kismet restore.
15. Recording restore.
16. ML modellek restore.
17. RF komponensek buildje.
18. Aaronia probe.
19. USRP probe.
20. SDRangel control teszt.
21. Acceptance test.
22. Hardveres mérési teszt.

Ne legyen szükség forráskód átírására.

---

# 23. Acceptance teszt

Készíts vagy frissíts:

```text
scripts/acceptance-test.sh
```

A teszt ne töröljön adatot.

Ellenőrizze:

* Compose config valid;
* kötelező env változók;
* database healthy;
* migrate sikeres;
* backend healthy;
* frontend elérhető;
* reverse proxy elérhető;
* spectrum-ingest healthy;
* RF agent healthy;
* Mosquitto;
* mock source;
* replay source;
* spectrum WebSocket;
* frame schema;
* sequence;
* peak detection;
* recording;
* Kismet opcionálisan;
* Wi-Fi endpoint;
* Bluetooth endpoint;
* RSSI új sorokban;
* ML status;
* ML classify endpoint;
* Aaronia probe;
* USRP disabled vagy ready;
* SDRangel disabled vagy reachable;
* Ollama disabled vagy reachable;
* nincs restart loop;
* nincs orphan container;
* kötelező volume-ok/mountok;
* backup elkészíthető.

A hardware hiánya ne jelentsen teszthibát, ha az adott integration disabled.

A helytelenül konfigurált aktív hardware mód viszont legyen hiba.

---

# 24. Frontend

Meglévő dizájnt indokolatlanul ne módosítsd.

Fülek:

```text
Spektrum
Wi-Fi / Kismet
Bluetooth / BLE
RF Agent
Felvételek
ML osztályozás
Rendszerállapot
```

## RF Agent tab

Mutassa:

* current source;
* source status;
* source device;
* capabilities;
* FPS;
* dropped frame;
* sequence gap;
* latency;
* worker PID;
* worker restart count;
* Aaronia probe;
* USRP status;
* SDRangel status.

## Felvételek tab

* recording lista;
* metaadat;
* replay indítás;
* pause;
* resume;
* seek;
* speed;
* loop;
* checksum status.

## ML tab

* model status;
* model version;
* utolsó osztályozás;
* confidence;
* top predictions;
* inference latency;
* confusion matrix csak értékelési nézetben.

Mock/replay adat mindig legyen jól láthatóan megjelölve.

---

# 25. Dokumentáció

Készíts vagy frissíts:

```text
README.md
RUNNING.md
ARCHITECTURE.md
RF_AGENT.md
AARONIA_INTEGRATION.md
SDRANGEL_INTEGRATION.md
ML_CLASSIFIER.md
MIGRATION.md
BACKUP_RESTORE.md
PROJECT_AUDIT.md
PHASE_1_11_REVIEW.md
```

A dokumentációban egyértelműen különítsd el:

```text
implemented
tested
tested only with mock
tested only with replay
hardware not tested
experimental
not implemented
```

Ne állíts működőnek olyan hardverintegrációt, amelyet nem teszteltél valós eszközzel.

---

# 26. Kötelező munkasorrend

Ebben a sorrendben dolgozz:

1. Jelenlegi Git és projektállapot audit.
2. `PHASE_1_11_REVIEW.md`.
3. Az 1–11. pont hibás vagy félbehagyott részeinek javítása.
4. API/WebSocket kompatibilitási tesztek.
5. Teljes baseline acceptance test.
6. Aaronia probe/worker folyamatizoláció korrekciója.
7. Közös FFT pipeline.
8. Spectrum ingest.
9. RF agent REST/WebSocket API.
10. Recording és replay formátum.
11. Frontend RF Agent/Recordings tab.
12. Adatbázis-migrációk és metadata tárolás.
13. ML baseline.
14. CNN prototípus.
15. ML API és frontend.
16. Context-grounded assistant.
17. Valódi RAG csak opcionálisan.
18. SDRangel control plane.
19. SDRangel data plane dokumentált skeleton.
20. USRP worker/skeleton ellenőrzése.
21. Service-stabilitás.
22. Docker audit/cleanup.
23. Backup/restore.
24. Migráció.
25. Acceptance teszt véglegesítése.
26. Dokumentáció.
27. Végső audit.

Minden nagyobb pont után:

```bash
git status
git diff --stat
docker compose config
docker compose build
docker compose ps
bash scripts/acceptance-test.sh
```

Ha a teljes acceptance test egy köztes fázisban még nem alkalmazható, futtasd a releváns részteszteket, és dokumentáld.

---

# 27. Fontos tiltások

Ne:

* írj újra mindent nulláról;
* valósítsd meg újra a már helyesen elkészült 1–11. pontot;
* törölj volume-ot;
* törölj PostgreSQL-adatot;
* törölj Kismet-adatot;
* törölj recordingot;
* törölj ML-modellt vagy datasetet;
* találj ki nem dokumentált Aaronia API-t;
* feltételezz SSE4.2 fallbacket bizonyíték nélkül;
* töltsd be a vendor libraryt a fő RF agent folyamatba;
* próbálj C++ exceptionnel `SIGILL` hibát kezelni;
* küldj mock adatot Aaronia vagy USRP néven;
* kezeld a Kismet RSSI-t valódi RF spektrogramként;
* nevezz egyszerű SQL-contextet RAG-nak;
* keverd össze az SDRangel REST API-t az IQ data plane-nel;
* tedd kötelezővé az RF hardvert;
* tedd kötelezővé az AI-t;
* módosítsd indokolatlanul az UI-t;
* használj `docker system prune -a --volumes` parancsot;
* használj `docker compose down -v` parancsot;
* állíts működőnek hardverintegrációt valós teszt nélkül.

---

# 28. Végső jelentés

A munka végén készíts:

```text
IMPLEMENTATION_REPORT.md
```

Tartalmazza:

* az 1–11. pont auditjának eredményét;
* mit kellett javítani a korábbi implementációban;
* létrehozott fájlok;
* módosított fájlok;
* törölt fájlok;
* törlés indoka;
* service-ek;
* Compose-felosztás;
* adatbázis-migrációk;
* RF agent állapota;
* Aaronia probe eredménye;
* Aaronia worker állapota;
* USRP állapota;
* SDRangel control plane állapota;
* SDRangel data plane állapota;
* mock állapota;
* replay állapota;
* FFT tesztek;
* recording tesztek;
* RSSI tesztek;
* ML baseline eredmény;
* CNN eredmény;
* inference latency;
* Ollama/context assistant állapota;
* valódi RAG állapota;
* backup/restore teszt;
* migrációs teszt;
* acceptance test eredmény;
* ismert korlátok;
* következő fejlesztési lépések.

A végső összefoglalóban ne csak azt írd, hogy „elkészült”.

Minden állításhoz adj:

* fájlútvonalat;
* parancsot;
* teszteredményt;
* vagy pontos indoklást, ha nem volt tesztelhető.

A cél egy működő, stabil és migrálható HP-demórendszer, amely mock és replay módban teljesen használható, a valós Aaronia/USRP/SDRangel hardverintegrációt pedig biztonságos és professzionális architektúrával készíti elő.

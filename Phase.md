A meglévő `Diploma_munka5_kismet_integrated` projektet kell teljesen átvizsgálnod, rendbe tenned és olyan professzionális, moduláris architektúrára átalakítanod, amely jelenleg egy régi HP Debian gépen demó módban teljes egészében futtatható, később pedig minimális módosítással átköltöztethető egy nagy teljesítményű szerverre.

A projektet ne írd újra nulláról. A meglévő működő funkciókat tartsd meg, javítsd és rendezd logikus szerkezetbe.

## Hardverkörnyezet

A jelenlegi fejlesztési és demonstrációs gép:

```text
HP laptop
Intel Core i5-2540M
nincs AVX2 támogatás
Debian Linux
Docker és Docker Compose
```

Ez a gép jelenleg:

* hordozható szerver;
* fejlesztési környezet;
* iskolai demonstrációs gép;
* PostgreSQL-adatbázis;
* webes frontend és backend;
* Kismet Wi-Fi/Bluetooth adatgyűjtő;
* mock és replay spektrumforrás;
* a teljes projekt központi tárolási helye.

Fontos: az Aaronia RTSA Suite PRO ezen a gépen AVX2 hiánya miatt nem fut.

A későbbi végleges rendszer egy nagy teljesítményű szerveren vagy modern RF munkaállomáson fog futni, ahol elérhető lesz:

* Aaronia SPECTRAN V6;
* Aaronia Linux SDK;
* USRP eszközök;
* UHD driver;
* SDRangel;
* nagyobb CPU-, memória-, hálózati és tárhelykapacitás.

## Fő cél

Egyetlen, könnyen migrálható monorepo készüljön, amely tartalmazza:

* Docker Compose alapú szerveroldali rendszert;
* saját C++ RF agentet;
* Aaronia SPECTRAN V6 backend előkészítést;
* Ettus USRP/UHD backend előkészítést;
* mock és replay módot;
* spectrum ingest szolgáltatást;
* SDRangel-vezérlési előkészítést;
* Wi-Fi/Kismet integrációt;
* Bluetooth/BLE integrációt;
* PostgreSQL-adatbázist;
* teljes backup/restore rendszert;
* biztonságos Docker-auditot és takarítást;
* dokumentált migrációs folyamatot.

A HP gépen minden olyan komponens működjön, amelyhez nem kell valós Aaronia vagy USRP hardver.

A hardverfüggő részek a HP-n:

* fordítható vagy legalább strukturálisan tesztelhető skeletonként legyenek jelen;
* `disabled`, `unavailable` vagy `unsupported_cpu` állapotot adjanak;
* ne induljanak újra folyamatosan;
* ne küldjenek hamis valós hardveradatot;
* a rendszer mock és replay módban teljesen működjön nélkülük.

# 1. Először teljes projekt-audit

Mielőtt bármit törölsz vagy jelentősen módosítasz, vizsgáld át:

* összes Compose fájl;
* összes Dockerfile;
* összes service;
* Docker image definíciók;
* volume-ok;
* networkök;
* backend API-k;
* frontend;
* adatbázis-migrációk;
* PostgreSQL-táblák;
* Kismet service;
* Kismet import és collector;
* Bluetooth/BLE import;
* spektrumforrások;
* WebSocket-kezelés;
* spectrum recording;
* mock forrás;
* replay forrás;
* Aaronia stubok;
* SDRangel stubok;
* Mosquitto/MQTT használat;
* Ollama és AI komponensek;
* shell scriptek;
* dokumentáció;
* `.env` és `.env.example`;
* nem használt könyvtárak;
* duplikált kód;
* elavult service-ek;
* ideiglenes vagy tesztfájlok.

Készíts:

```text
PROJECT_AUDIT.md
```

Ebben minden komponenst kategorizálj:

* szükséges core komponens;
* opcionális RF komponens;
* opcionális AI komponens;
* fejlesztői komponens;
* tesztkomponens;
* elavult;
* duplikált;
* biztonságosan eltávolítható;
* tisztázandó.

Csak bizonyíthatóan nem használt vagy duplikált komponenst törölj.

# 2. Végleges monorepo-struktúra

A projekt ajánlott szerkezete:

```text
Diploma_munka5_kismet_integrated/
├── compose.yaml
├── compose.rf.yaml
├── compose.ai.yaml
├── compose.dev.yaml
├── .env.example
├── README.md
├── RUNNING.md
├── PROJECT_AUDIT.md
├── ARCHITECTURE.md
├── RF_AGENT.md
├── MIGRATION.md
├── BACKUP_RESTORE.md
│
├── frontend/
│
├── backend/
│
├── spectrum-ingest/
│
├── rf-agent/
│   ├── CMakeLists.txt
│   ├── cmake/
│   ├── include/
│   ├── src/
│   ├── tests/
│   ├── config/
│   └── README.md
│
├── database/
│   └── migrations/
│
├── docker/
│   ├── backend/
│   ├── frontend/
│   ├── kismet/
│   ├── spectrum-ingest/
│   └── rf-agent/
│
├── scripts/
│   ├── docker-audit.sh
│   ├── docker-cleanup.sh
│   ├── backup.sh
│   ├── restore.sh
│   ├── acceptance-test.sh
│   ├── pre-migration-check.sh
│   ├── post-migration-check.sh
│   └── export-diagnostics.sh
│
├── recordings/
├── config/
└── tests/
```

Ne mozgass át vakon mindent. Csak akkor alakítsd át a könyvtárstruktúrát, ha az importok, build context-ek, Dockerfile-ok és dokumentáció is követik a módosítást.

# 3. Compose-felosztás

## `compose.yaml`

Csak a core rendszer:

* database;
* migrate;
* mosquitto;
* backend;
* frontend;
* reverse-proxy;
* spectrum-ingest.

A core rendszernek működnie kell RF hardver és AI nélkül.

Indítás:

```bash
docker compose up -d
```

## `compose.rf.yaml`

RF-specifikus opcionális komponensek:

* kismet;
* Kismet collector, ha külön service;
* Bluetooth collector, ha külön service;
* rf-agent mock/replay módban;
* esetleges RF kapcsolati bridge-ek.

Indítás:

```bash
docker compose -f compose.yaml -f compose.rf.yaml up -d
```

## `compose.ai.yaml`

Csak opcionális AI:

* Ollama;
* AI elemző komponensek.

Az AI nem lehet kötelező a core rendszerhez.

## `compose.dev.yaml`

Csak fejlesztéshez:

* bind mount;
* hot reload;
* debug port;
* részletes log;
* fejlesztői environment változók.

# 4. Saját C++ RF agent

Készíts egy saját C++17 vagy C++20 alapú `rf-agent` komponenst.

Az agent célja:

```text
RF hardver
   ↓
saját C++ rf-agent
   ├── FFT/spektrum adatok
   ├── IQ-adatok
   ├── hardvervezérlés
   ├── recording
   ├── állapot és diagnosztika
   └── REST/WebSocket/MQTT kommunikáció
```

Az agentnek több backendje legyen.

Közös absztrakció:

```cpp
class IRfSource
{
public:
    virtual ~IRfSource() = default;

    virtual bool initialize() = 0;
    virtual bool start() = 0;
    virtual void stop() = 0;

    virtual SourceStatus status() const = 0;
    virtual SourceCapabilities capabilities() const = 0;

    virtual bool setCenterFrequency(std::uint64_t frequencyHz) = 0;
    virtual bool setSampleRate(std::uint64_t sampleRateHz) = 0;
    virtual bool setGain(double gainDb) = 0;

    virtual std::optional<SpectrumFrame> readSpectrumFrame() = 0;
    virtual std::optional<IqFrame> readIqFrame() = 0;
};
```

Backendek:

```text
MockRfSource
ReplayRfSource
AaroniaRfSource
UsrpRfSource
```

A backend kiválasztása konfigurációból történjen:

```env
RF_SOURCE_MODE=mock
```

Lehetséges értékek:

```text
mock
replay
aaronia
usrp
```

# 5. Mock backend

A HP-n teljesen működőképes legyen.

Generáljon:

* zajpadlót;
* több mozgó vagy állandó jelet;
* keskenysávú csúcsokat;
* szélessávú jelet;
* rövid burst jelet;
* változó amplitúdót;
* max holdhoz használható adatot.

A mock adat egyértelműen legyen megjelölve:

```json
{
  "source_type": "mock",
  "is_simulated": true
}
```

Soha ne jelenjen meg valós Aaronia vagy USRP adatként.

# 6. Replay backend

A HP-n teljesen működőképes legyen.

Tudjon korábban mentett spektrumadatokat visszajátszani.

Támogatás:

* indítás;
* leállítás;
* pause;
* resume;
* loop;
* seek;
* 0.5× sebesség;
* 1× sebesség;
* 2× sebesség;
* 5× sebesség.

Javasolt recording formátum:

```text
recordings/
└── session_uuid/
    ├── metadata.json
    ├── frames.ndjson.zst
    └── checksum.sha256
```

A formátum legyen verziózott:

```json
{
  "schema_version": 1
}
```

# 7. Aaronia backend

Készíts `AaroniaRfSource` implementációt vagy biztonságos skeletonját.

Használja majd:

```text
libAaroniaRTSAAPI.so
aaroniartsaapi.h
```

A build opcionális legyen:

```cmake
option(ENABLE_AARONIA "Enable Aaronia SPECTRAN V6 support" OFF)
```

Ha `ENABLE_AARONIA=ON`, akkor:

* keresse meg az Aaronia headert;
* keresse meg a `libAaroniaRTSAAPI.so` könyvtárat;
* csak akkor fordítsa az Aaronia backendet, ha ezek megvannak;
* különben adjon egyértelmű CMake hibát.

A HP i5-2540M processzorán nincs AVX2.

Ezért HP-n az Aaronia backend:

* ne legyen kötelező;
* ne legyen default;
* ne induljon el automatikusan;
* `unsupported_cpu` státuszt adhasson;
* az egész agent ettől még működjön mock és replay módban.

Az AVX2 ellenőrzés ne csak build időben, hanem runtime is történjen.

Példa státusz:

```json
{
  "backend": "aaronia",
  "enabled": false,
  "available": false,
  "status": "unsupported_cpu",
  "required_cpu_feature": "avx2"
}
```

Ne találj ki nem dokumentált Aaronia API-hívásokat.

Használd a telepített SDK headerét és mintaprogramjait referenciaként:

```text
RawSpectrum
SweepSpectrum
RawIQ
IQReceiver
EnumDevices
ConfigTree
```

Első körben az Aaronia backend elfogadható állapotai:

```text
disabled
sdk_not_found
unsupported_cpu
device_not_found
not_initialized
ready
running
error
```

# 8. USRP backend

Készíts `UsrpRfSource` backendet Ettus UHD API használatával.

Build kapcsoló:

```cmake
option(ENABLE_USRP "Enable Ettus USRP UHD support" OFF)
```

Ha engedélyezve van:

```cmake
find_package(UHD REQUIRED)
```

Az USRP backend tudja:

* eszközfelderítés;
* sorozatszám és eszköztípus lekérése;
* center frequency;
* sample rate;
* gain;
* bandwidth;
* antenna port;
* clock source;
* time source;
* stream indítás;
* stream leállítás;
* overflow és timeout kezelés;
* IQ frame olvasás;
* spektrum számítás FFT-vel.

Ne legyen hardcode-olva egyetlen USRP-modellre.

A konfiguráció támogassa:

```env
USRP_DEVICE_ARGS=
USRP_CENTER_FREQUENCY_HZ=100000000
USRP_SAMPLE_RATE_HZ=20000000
USRP_GAIN_DB=20
USRP_BANDWIDTH_HZ=20000000
USRP_ANTENNA=RX2
USRP_CLOCK_SOURCE=internal
USRP_TIME_SOURCE=internal
```

Később használható legyen például:

* USRP B200/B210;
* N310;
* X310;
* X410.

# 9. Közös SpectrumFrame modell

Minden RF backend azonos adatstruktúrát adjon.

Példa:

```json
{
  "schema_version": 1,
  "sensor_id": "hp-demo-01",
  "source_type": "mock",
  "source_device": "mock-generator",
  "session_id": "uuid",
  "timestamp": "2026-06-19T12:00:00.000Z",
  "sequence": 12345,
  "center_frequency_hz": 2450000000,
  "start_frequency_hz": 2400000000,
  "stop_frequency_hz": 2500000000,
  "sample_rate_hz": 100000000,
  "rbw_hz": 10000,
  "frequencies_hz": [],
  "powers_dbm": [],
  "metadata": {
    "gain_db": 20,
    "antenna": "RX",
    "is_simulated": true
  }
}
```

Validáció:

* azonos hosszúságú frequency és power tömb;
* `start < stop`;
* center frequency a tartományban;
* növekvő sequence;
* szabályos timestamp;
* NaN és Infinity kiszűrése;
* maximum frame-méret;
* hibás frame eldobása;
* hibás frame ne állítsa le az agentet.

# 10. FFT feldolgozás

Az IQ-forrásokhoz közös FFT pipeline készüljön.

Támogassa:

* FFT size konfiguráció;
* Hann window;
* Blackman-Harris opcionálisan;
* DC offset kezelés;
* dBFS számítás;
* kalibrációs offset;
* averaging;
* max hold;
* peak detection;
* frame rate limit.

Konfiguráció:

```env
FFT_SIZE=4096
FFT_WINDOW=hann
FFT_AVERAGING=4
FFT_MAX_FPS=10
FFT_CALIBRATION_OFFSET_DB=0
```

Ne terheld túl a HP-t.

HP demómódban alacsonyabb alapértékeket használj.

# 11. IQ kezelés

A teljes nagysebességű IQ-adatot ne mentsd PostgreSQL-be.

Az IQ:

* memóriában streamelhető;
* fájlba rögzíthető;
* később SDRangel felé továbbítható;
* metadata kerüljön PostgreSQL-be.

Az agentben legyen közös `IqFrame` modell.

A teljes IQ stream továbbítása legyen opcionális és alapból kikapcsolva.

# 12. SDRangel-integráció előkészítése

A rendszer később natívan futó SDRangelt fog vezérelni.

Az SDRangel nem kötelező a HP demómódhoz.

Konfiguráció:

```env
SDRANGEL_ENABLED=false
SDRANGEL_API_URL=http://127.0.0.1:8091
SDRANGEL_TIMEOUT_SECONDS=5
```

Az agent vagy külön `demod-controller` modul tudja:

* SDRangel health ellenőrzés;
* device set lekérdezés;
* center frequency beállítás;
* AM demodulátor;
* NFM demodulátor;
* WFM demodulátor;
* USB/LSB demodulátor;
* start;
* stop;
* státuszlekérdezés.

Ne állítsd működőnek addig, amíg nincs valós SDRangel API teszt.

A frontendben a demodulációs gomb:

* mock/replay módban disabled vagy demo státuszú;
* valós SDRangel esetén aktív;
* egyértelmű státuszt mutat.

# 13. RF agent kommunikáció

Az agent biztosítson REST API-t:

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
POST /recordings/start
POST /recordings/stop
POST /replay/start
POST /replay/pause
POST /replay/resume
POST /replay/seek
POST /replay/stop
GET  /sdrangel/status
POST /sdrangel/tune
POST /sdrangel/demod/start
POST /sdrangel/demod/stop
```

Spectrum stream:

```text
WebSocket /ws/spectrum
```

Opcionális MQTT:

```text
rf/spectrum/frame
rf/spectrum/peak
rf/source/status
rf/source/error
rf/recording/status
rf/sdrangel/status
```

A bináris vagy tömörített továbbítás legyen előkészítve, de első körben JSON WebSocket is elfogadható demóhoz.

# 14. Spectrum ingest service

A meglévő backendből különítsd el vagy logikailag válaszd le a spectrum ingest feladatot.

A `spectrum-ingest`:

* fogadja az rf-agent frame-jeit;
* validálja a sémát;
* továbbítsa a frontendnek;
* kezelje a reconnectet;
* kezelje a sequence gapet;
* mérje a frame rate-et;
* mérje a késleltetést;
* ne álljon le hibás frame miatt;
* támogassa a mock/replay/local agent módot.

Konfiguráció:

```env
RF_AGENT_URL=http://rf-agent:8765
RF_AGENT_WS_URL=ws://rf-agent:8765/ws/spectrum
SPECTRUM_SOURCE_MODE=mock
```

# 15. Spektrum adattárolás

A PostgreSQL-be kerüljenek:

* sessionök;
* forrás metaadatai;
* eszköz metaadatai;
* felvételi metaadatok;
* detektált peakek;
* riasztások;
* marker események;
* ritkított spektrum snapshotok;
* fájl elérési utak;
* checksumok.

Fájlrendszerbe kerüljenek:

* teljes spectrum recordingok;
* IQ recordingok;
* replay fájlok;
* exportok;
* hangfelvételek;
* PCAP;
* `.kismet` fájlok.

Javasolt host könyvtárak:

```text
/srv/diploma/postgres
/srv/diploma/kismet
/srv/diploma/uploads
/srv/diploma/recordings/spectrum
/srv/diploma/recordings/iq
/srv/diploma/recordings/audio
/srv/diploma/exports
/srv/diploma/backups
```

Ezek `.env` változókkal legyenek felülírhatók.

# 16. Kismet Wi-Fi és Bluetooth

A meglévő Kismet funkciókat ne rontsd el.

Ellenőrizd:

* `.kismet` fájl mentése;
* PostgreSQL live import;
* háttércollector;
* Wi-Fi RSSI;
* Bluetooth RSSI;
* SSID;
* BSSID;
* MAC;
* channel;
* frequency;
* vendor;
* Bluetooth device name;
* service UUID;
* source;
* timestamp;
* session nélküli legutóbbi adatok;
* több source támogatása.

A frontendben legyen külön:

```text
Spektrum
Wi-Fi / Kismet
Bluetooth / BLE
RF Agent
Felvételek
Rendszerállapot
```

A spektrum maradjon az alapértelmezett oldal.

# 17. Docker és natív komponensek

A HP-n demóhoz az `rf-agent` Dockerben is futhat mock és replay módban.

Valós hardveres üzemben később az agent futhasson natívan is.

Ezért ugyanaz az agent:

* ne tartalmazzon Docker-specifikus üzleti logikát;
* környezeti változókból konfigurálható legyen;
* Dockerben mock/replay módban működjön;
* natívan Aaronia/USRP módban működjön;
* systemd service-ként is telepíthető legyen.

Készíts systemd mintát:

```text
deploy/systemd/rf-agent.service
```

# 18. Biztonságos Docker-rendrakás

Azonosítsd a felesleges:

* orphan containereket;
* régi projektimage-eket;
* dangling image-eket;
* régi build cache-t;
* már nem használt networköket;
* duplikált service-eket.

Készíts:

```text
scripts/docker-audit.sh
scripts/docker-cleanup.sh
```

A `docker-audit.sh` csak listázzon.

A `docker-cleanup.sh` alapból csak dry-run legyen.

Csak így töröljön:

```bash
scripts/docker-cleanup.sh --apply
```

Soha ne töröljön:

* volume-ot;
* PostgreSQL adatot;
* Kismet adatot;
* uploadot;
* recordingot;
* más projekthez tartozó elemet.

Tilos:

```bash
docker system prune -a --volumes
```

A `docker compose down` ne használjon `-v` kapcsolót.

# 19. Service-stabilitás

Minden hosszú életű service:

```yaml
restart: unless-stopped
```

Ahol értelmes:

```yaml
healthcheck:
```

Az adatbázis legyen healthy a backend indulása előtt.

A migrate service:

* egyszer fusson le;
* sikeresen álljon le;
* ne restartoljon folyamatosan.

Logrotáció:

```yaml
logging:
  driver: local
```

Erőforráskorlátokat is dokumentálj a HP-hoz:

* backend memória;
* PostgreSQL memória;
* Kismet memória;
* rf-agent CPU;
* spectrum frame rate.

Ne állíts be irreálisan alacsony limiteket, amelyek instabillá teszik a rendszert.

# 20. HP-demómód

Legyen külön példa konfiguráció:

```text
config/hp-demo.env
```

Ajánlott:

```env
RF_SOURCE_MODE=replay
ENABLE_AARONIA=false
ENABLE_USRP=false
SDRANGEL_ENABLED=false
AI_ENABLED=false
FFT_SIZE=2048
FFT_MAX_FPS=5
```

A HP-demómód tudja:

* teljes webes felület;
* spektrum replay;
* max hold;
* marker;
* zoom;
* pan;
* peak detection;
* session kezelés;
* Wi-Fi;
* Bluetooth;
* Kismet;
* adatbázis;
* export;
* rendszerállapot.

# 21. Végleges szervermód

Legyen példa:

```text
config/production-hardware.env
```

Ebben legyen előkészítve:

```env
RF_SOURCE_MODE=aaronia
ENABLE_AARONIA=true
ENABLE_USRP=true
SDRANGEL_ENABLED=true
AI_ENABLED=false
```

Ne tartalmazzon valódi jelszót vagy titkot.

# 22. Backup és restore

Készíts:

```text
scripts/backup.sh
scripts/restore.sh
```

Backup tartalma:

* PostgreSQL `pg_dump` custom format;
* Kismet `.kismet` fájlok;
* uploads;
* spectrum recording;
* IQ recording metadata;
* exportok;
* Compose fájlok;
* migrációk;
* `.env` külön védett fájlként;
* projektverzió;
* Git commit hash;
* checksumok.

A restore alapból ne írjon felül semmit.

Csak:

```bash
scripts/restore.sh --apply
```

módban végezzen visszaállítást.

# 23. Migráció

Készíts:

```text
MIGRATION.md
scripts/pre-migration-check.sh
scripts/post-migration-check.sh
```

A migrációnak működnie kell:

```text
HP Debian
    ↓
új nagy teljesítményű Linux szerver
```

A költözés során ne kelljen forráskódot átírni.

Csak:

* projekt másolás;
* `.env` módosítás;
* natív Aaronia SDK telepítés;
* UHD telepítés;
* SDRangel telepítés;
* backup restore;
* build feature kapcsolók;
* acceptance test.

# 24. Acceptance tesztek

Készíts:

```text
scripts/acceptance-test.sh
```

Ellenőrizze:

* Compose config valid;
* core service-ek futnak;
* PostgreSQL healthy;
* migrate sikeres;
* backend health;
* frontend;
* reverse proxy;
* MQTT;
* mock source;
* replay source;
* WebSocket spectrum;
* peak detection;
* recording;
* Kismet opcionálisan;
* Wi-Fi endpoint;
* Bluetooth endpoint;
* RSSI-adatok;
* rf-agent health;
* source capabilities;
* Aaronia disabled státusz HP-n;
* USRP disabled státusz HP-n;
* SDRangel disabled státusz;
* nincs restart loop;
* nincs orphan container;
* volume-ok léteznek;
* mentés létrehozható.

# 25. Dokumentáció

Készíts vagy frissíts:

```text
README.md
RUNNING.md
ARCHITECTURE.md
RF_AGENT.md
PROJECT_AUDIT.md
BACKUP_RESTORE.md
MIGRATION.md
```

Dokumentáld:

## HP demo indítás

```bash
docker compose \
  --env-file config/hp-demo.env \
  -f compose.yaml \
  -f compose.rf.yaml \
  up -d --build
```

## Core indítás

```bash
docker compose up -d
```

## Logok

```bash
docker compose logs -f --tail=100
```

## Audit

```bash
bash scripts/docker-audit.sh
```

## Cleanup dry-run

```bash
bash scripts/docker-cleanup.sh
```

## Acceptance test

```bash
bash scripts/acceptance-test.sh
```

## Backup

```bash
bash scripts/backup.sh
```

# 26. Fejlesztési sorrend

A munkát ebben a sorrendben végezd:

1. teljes audit;
2. biztonsági mentési pont;
3. compose ellenőrzés;
4. felesleges definíciók azonosítása;
5. biztonságos rendrakás;
6. core service-ek stabilizálása;
7. Kismet/Wi-Fi/Bluetooth teszt;
8. közös SpectrumFrame modell;
9. mock backend;
10. replay backend;
11. rf-agent REST/WebSocket;
12. spectrum-ingest kapcsolat;
13. frontend RF Agent és Recordings oldal;
14. Aaronia skeleton;
15. USRP/UHD skeleton;
16. SDRangel controller skeleton;
17. backup/restore;
18. acceptance test;
19. dokumentáció;
20. végső audit.

Minden nagyobb lépés után futtasd a teszteket.

# 27. Fontos tiltások

Ne:

* töröld a volume-okat;
* töröld a PostgreSQL-adatot;
* töröld a Kismet-adatot;
* töröld a recordingokat;
* találj ki Aaronia API-hívásokat;
* állítsd működőnek a hardverintegrációt valós teszt nélkül;
* küldj mock adatot Aaronia vagy USRP néven;
* tedd kötelezővé az AI-t;
* tedd kötelezővé a valós RF hardvert;
* írj mindent újra nulláról;
* módosítsd indokolatlanul a jelenlegi UI dizájnt;
* használd a `docker system prune -a --volumes` parancsot.

# 28. Végső jelentés

A munka végén készíts részletes összefoglalót:

* mely fájlokat módosítottad;
* mely fájlokat hoztad létre;
* mely service-ek maradtak;
* mely service-ek opcionálisak;
* mit töröltél;
* miért volt felesleges;
* mely image-ek törölhetők;
* mely volume-ok maradtak érintetlenek;
* hogyan indul a HP-demómód;
* hogyan működik a mock;
* hogyan működik a replay;
* milyen állapotban van az Aaronia backend;
* milyen állapotban van az USRP backend;
* milyen állapotban van az SDRangel-integráció;
* mi szükséges a valós SPECTRAN V6 teszthez;
* mi szükséges a valós USRP teszthez;
* hogyan költöztethető a rendszer az új szerverre.

A végeredmény egy működő, tiszta, dokumentált, migrálható rendszer legyen, amely a HP-n teljes demóként fut mock és replay forrással, később pedig ugyanebből a projektből használható Aaronia SPECTRAN V6-tal, USRP-vel és SDRangellel.

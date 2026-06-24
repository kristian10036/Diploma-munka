> **Történeti baseline audit.** A későbbi, 19–27. pont szerinti változtatások és a végső állapot a `FINAL_AUDIT.md` fájlban vannak.

# Projekt-audit

> Specifikációs státusz: `Phase.md` – legacy/original specification; `phase1.md` – current authoritative specification. A fájlnév a projektben kisbetűs. A frissebb összehasonlítás és állapotaudit: `PHASE_COMPARISON.md`, illetve `PHASE_1_11_REVIEW.md`.

Készült: 2026-06-19  
Hatókör: a `Phase.md` 1. pontja  
Projekt: `Diploma_munka5_kismet_integrated`

## Vezetői összefoglaló

A projekt működő demonstrációs alap: a FastAPI backend, a statikus frontend, a TimescaleDB/PostgreSQL, a Mosquitto, a Kismet és a spektrumszimulátor fut. A jelenlegi architektúra azonban még nem a `Phase.md` célarchitektúrája:

- egyetlen `docker-compose.yml` keveri a core, RF és AI komponenseket;
- nincs külön `spectrum-ingest` és C++ `rf-agent`;
- a replay és Aaronia forrás csak stub, USRP és SDRangel komponens nincs;
- nincs recording alrendszer, backup/restore vagy acceptance teszt;
- a backend üzleti logikájának többsége egy 3300+ soros `main.py` fájlban van;
- a hosszú életű service-ek közül csak a Kismet használ restart policy-t;
- a core indítás jelenleg az opcionális, 4,88 GB-os Ollamát is elindítja;
- a Kismet raw payload tartalmaz RSSI-t, de a futó adatbázis normalizált RSSI mezői üresek.

Az audit során nem történt törlés, volume-módosítás, adatbázis-írás vagy service-újraindítás.

## Audit módszere és korlátai

Ellenőrizve lett:

- minden projektfájl és könyvtár a vendorizált Kismet archívum tartalomjegyzékével együtt;
- Compose feloldás, service-ek, profilok és volume-definíciók;
- Dockerfile-ok, Nginx, Mosquitto és környezeti konfiguráció;
- futó/leállt konténerek, restart count, mountok, image-ek, networkök és build cache;
- backend route-ok, WebSocket, MQTT, Kismet/BLE collectorok és spektrumforrások;
- frontend oldalak, tabok és API-használat;
- mind a hét adatbázis-migráció és a tényleges PostgreSQL-táblák;
- futó health/source/import API-k és az RSSI-adatok csak olvasási SQL-lekérdezésekkel.

Korlát: a `.git` útvonal ebben a környezetben nem érvényes Git repository, ezért commit hash, tracked/untracked állapot és Git-alapú duplikációvizsgálat nem készíthető. A 2. lépés előtt valódi Git vagy fájlszintű mentési pont szükséges.

## Jelenlegi futási állapot

| Service | Kategória | Állapot | Healthcheck | Restart policy | Megjegyzés |
|---|---|---:|---|---|---|
| `database` | szükséges core | running | healthy | nincs | TimescaleDB/PostgreSQL 16, név szerinti adatvolume |
| `migrate` | szükséges core, egyszeri | exited 0 | nincs | `no` | minden induláskor újrafuttatja az idempotens SQL-eket |
| `mosquitto` | szükséges core jelenleg | running | nincs | nincs | anonim listener, backend riasztást publikál |
| `backend` | szükséges core | running | nincs | nincs | FastAPI, bind mounttal fut |
| `frontend` | szükséges core | running | nincs | nincs | statikus Nginx |
| `reverse-proxy` | szükséges core | running | nincs | nincs | host `8080`, API/WS proxy |
| `kismet` | opcionális RF | running | nincs | `unless-stopped` | `rf` profil, host network, privileged |
| `ollama` | opcionális AI | running | nincs | nincs | jelenleg core Compose része, valódi RAG nincs |

Minden vizsgált futó service restart countja `0`. A naplódriver mindenhol `json-file`, nem a célként előírt `local`.

## Komponensleltár és kategorizálás

### Compose és infrastruktúra

| Komponens | Kategória | Döntés |
|---|---|---|
| `docker-compose.yml` | szükséges jelenlegi definíció, átalakítandó | tartalma később `compose.yaml`, `compose.rf.yaml`, `compose.ai.yaml`, `compose.dev.yaml` fájlokra bontandó |
| `nginx/default.conf` | szükséges core | megtartandó; API és WebSocket proxy működik |
| `mosquitto/config/mosquitto.conf` | szükséges core jelenleg, biztonságilag javítandó | anonim hozzáférés csak izolált demo networkön elfogadható |
| `python-processor/Dockerfile` | szükséges core | megtartandó, később `docker/backend` alá rendezhető |
| `docker/kismet/Dockerfile` | opcionális RF | megtartandó; vendorizált, módosított Kismet buildet használ |
| `docker/kismet/start-kismet.sh` | opcionális RF | megtartandó; egy és több source konfigurációt kezel |
| `.env` | lokális titok/konfiguráció | nem mozgatható auditban, backupnál védetten kezelendő |
| `.env.example` | szükséges dokumentáció | elavult stub-megjegyzések és hiányzó `KISMET_SOURCES` miatt frissítendő |

### Backend és adatfolyamok

| Komponens | Kategória | Állapot |
|---|---|---|
| `python-processor/main.py` | szükséges core, modulárisítandó | API, DB, import, session, reference, spectrum broadcast és statikus mount egy fájlban |
| `app/config.py` | szükséges core | typed környezeti konfiguráció; tovább bővíthető |
| `app/services/collectors/kismet.py` | opcionális RF, aktívan használt | live polling, auth, explicit mezőlista és kompatibilitási fallback |
| `app/services/collectors/bettercap.py` | opcionális RF stub | csak elérhetőségi probe, live BLE polling nincs |
| `app/spectrum/sources/base.py` | szükséges RF alap | korai Python `SpectrumFrame`, még nem a Phase közös sémája |
| `app/spectrum/sources/simulator.py` | szükséges demókomponens | működő szimulátor, de egyszerű zaj + egy csúcs; nincs explicit `is_simulated` frame metadata |
| `app/spectrum/sources/file_replay.py` | opcionális RF stub | nem olvas fájlt; start/pause/seek/speed nincs |
| `app/spectrum/sources/aaronia_rtsa.py` | opcionális RF stub | HTTP probe, nem Aaronia Linux SDK backend; helyesen nem állít elő hamis adatot |
| `app/spectrum/manager.py` | szükséges RF alap | simulator/Aaronia HTTP/file replay választás |
| `/ws/spectrum` | szükséges core jelenleg | működő JSON pontlista; nincs frame schema, sequence vagy ingest réteg |
| MQTT publikálás | szükséges core jelenleg | csak `tscm/alerts` demo anomália; cél RF topicok nincsenek |
| `/api/ask` és Ollama config | opcionális AI, félkész | szabályalapú SQL válasz; Ollama URL látszik, de nincs modellhívás/RAG |

### Frontend

| Fájl/funkció | Kategória | Állapot |
|---|---|---|
| `static/index.html` | szükséges core | működő Spektrum, Wi‑Fi/Kismet és Bluetooth/BLE tab |
| spektrum canvas, waterfall, overview | szükséges core | zoom, pan, marker, max hold és referencia funkciók jelen vannak |
| session panel | szükséges core | start/stop/refresh jelen van |
| `static/import.html` | fejlesztői/operátori komponens | OSCOR/DDF/PR100/MESA, Kismet, BLE és reference importokhoz aktívan linkelt |
| RF Agent tab | hiányzó | létrehozandó |
| Felvételek tab | hiányzó | létrehozandó |
| Rendszerállapot tab | hiányzó | létrehozandó |

A statikus frontend két úton is kiszolgálható: külön `frontend` Nginx service-en és a backend gyökérre mountolt `StaticFiles` útvonalán. A reverse proxy ténylegesen a frontend service-t használja; a backend mount redundáns, de eltávolítás előtt közvetlen backend-hozzáférési kompatibilitást kell tesztelni.

### Adatbázis

A hét idempotens migráció ténylegesen létrehozta a várt táblákat. Timescale hypertable van többek között a spektrum-, peak-, anomália-, Wi‑Fi-, Bluetooth- és referencia-spektrum adatokhoz.

Kategóriák:

- szükséges core: `locations`, `measurement_sessions`, `measurement_sources`, `spectrum_samples`, `spectrum_peaks`, `anomalies`, `wifi_devices`, `wifi_observations`, `bluetooth_devices`, `bluetooth_observations`;
- szükséges import/reference: `csv_imports`, `uploaded_files`, `import_error_rows`, `reference_bands`, `reference_band_site_baselines`, `reference_spectrum_points`, `reference_images`;
- opcionális műszerimport: `oscor_import_rows`, `ddf_import_rows`, `pr100_import_rows`, `mesa_import_rows`, `kismet_import_rows`, `bettercap_ble_import_rows`;
- opcionális AI/előkészítés: `documents`, `document_chunks`, `embeddings`;
- hardver-előkészítés: `sdr_devices`, `downconverter_profiles`, `calibration_profiles`;
- tisztázandó/korai modell: `reference_profiles`, `reference_measurements`, `frequency_bands`, `app_users` – jelenlegi backendhasználatuk nem bizonyított, de sémafüggőség vagy későbbi funkció miatt nem törölhetők.

Hiányok:

- nincs recording/session fájlmetaadatokra dedikált tábla;
- nincs IQ/audio/PCAP/Kismet fájl-katalógus a Phase célmodellje szerint;
- nincs migrációtörténet/checksum tábla; a `migrate` service minden SQL-t újrafuttat;
- a meglévő idempotens megközelítés működik, de driftet és módosított régi migrációt nem érzékel.

### Kismet és Bluetooth/BLE

Bizonyított működés:

- a Kismet service fut, restart loop nincs;
- Wi‑Fi és Bluetooth source egyszerre látszik a raw adatokban;
- a háttérimport 15 másodpercenként fut, az utolsó ellenőrzéskor 72 Wi‑Fi és 2 Bluetooth sort importált, hiba nélkül;
- SSID/BSSID/MAC/channel/frequency/vendor/device name/source/timestamp bekerül;
- session nélkül `Kismet live background` helyszínnel elérhetők a legutóbbi adatok;
- a raw payload Wi‑Fi esetén `kismet.common.signal.last_signal=-40`, Bluetooth esetén `bluetooth.device.rssi_last=-66` értéket tartalmazott.

Kritikus eltérés:

- `wifi_observations`: 15 432 sor, normalizált RSSI/signal értékkel 0 sor;
- `bluetooth_observations`: 278 sor, normalizált RSSI értékkel 0 sor;
- a futó backend folyamat még nem bizonyítja a friss RSSI-normalizáló kód betöltését; célzott újraindítás és új sorok ellenőrzése szükséges a fejlesztési sorrend 7. pontjában;
- a lekért raw payload túl nagy és teljes Kismet objektumnak látszik, ezért ellenőrizni kell, hogy az explicit POST sikerül-e vagy a collector GET fallbackre vált;
- `.kismet` fájlok megléte az adatvolume-ban nem lett fájlrendszeri szinten auditálva, az alkalmazás `uploaded_files` táblájában 0 ilyen fájl szerepel.

### Dokumentáció és minták

| Elem | Kategória | Döntés |
|---|---|---|
| `RUNNING.md` | szükséges dokumentáció | megtartandó és az új Compose felosztással frissítendő |
| `CURRENT_STATE_REPORT.md` | fejlesztési történet | elavult részleteket tartalmaz, de audit trailként megtartandó |
| `KISMET_DOCKER_INTEGRATION.md` | opcionális RF dokumentáció | megtartandó, később `RF_AGENT.md`/RUNNING tartalmával összehangolandó |
| `codex_plan.md` | korábbi fejlesztési terv | a `Phase.md` részben felülírja; elavult, de törlés előtt felhasználói döntés kell |
| `agents.md` | fejlesztői instrukció | megtartandó |
| `Phase.md` | aktuális követelmény | megtartandó |
| `data/samples/*` | tesztkomponens | aktív importtesztekhez megtartandó |
| `data/nmhh_reference_csv_for_codex/*` | referencia/tesztadat | NMHH és baseline fejlesztéshez megtartandó |
| `vendor/kismet-master-bluetooth-rssi.zip` | opcionális RF build input | nem felesleges: a Kismet Dockerfile közvetlenül használja |

## Duplikált, elavult és eltávolítható elemek

### Bizonyítottan generált, biztonságosan eltávolítható

- `python-processor/**/__pycache__/` és `*.pyc`: Python generált cache; `.gitignore` már kizárja. Az audit során nem lett törölve.
- két dangling project image (`708 MB` és `234 MB`) és körülbelül `4,254 GB` reclaimable build cache található. Csak a későbbi, projekt-szűrt cleanup script és mentési pont után törölhető.

### Duplikált, de még nem törölhető automatikusan

- frontend statikus kiszolgálás a frontend Nginxben és a backend `StaticFiles` mountján;
- a `CURRENT_STATE_REPORT.md`, `codex_plan.md` és az új `Phase.md` részben átfedő állapotleírásokat tartalmaz;
- korai Python spectrum source architektúra és a tervezett C++ rf-agent funkcionalitása később átfedhet, de a jelenlegi UI működése miatt most mind szükséges.

### Tisztázandó

- 12 névtelen Docker volume látható a négy projekt-volume mellett. Több közülük korábbi Mosquitto vagy más container mount lehet; tulajdon és adattartalom bizonyítása nélkül nem törölhető.
- `app_users`, `reference_profiles`, `reference_measurements`, `frequency_bands` jelenlegi alkalmazáshasználata nem látható, de adatbázisobjektumként nem törölhetők audit alapján.
- a Bettercap collector csak stub, miközben a fájlimport működik; a Kismet BLE kiválthatja a live Bettercap igényt, de ezt funkcionális döntésként kell kezelni.

## Biztonsági megállapítások

1. A Compose fejlesztői alapjelszavakat tartalmaz fallbackként; productionben kötelező külső `.env` és erős titok.
2. A Mosquitto `allow_anonymous true`; csak belső Docker networkön elfogadható demóhoz.
3. A Kismet `privileged: true` és host network módban fut. Laborban indokolható, productionben dedikált adapter és minimális capability/device átadás szükséges.
4. Az image tagek egy része `latest`, a Python követelmények nincsenek verzióra rögzítve; a build nem teljesen reprodukálható.
5. A backend fejlesztői bind mountja elfedi az image-be másolt kódot; production Compose-ban nem maradhat.
6. Nincs alkalmazásszintű autentikáció/authorizáció az admin/import endpointok előtt.
7. Nincs egységes logrotáció; `json-file` korlát nélkül nőhet.

## Stabilitási megállapítások

- csak a database rendelkezik healthcheckkel;
- backend, frontend, reverse proxy, Mosquitto és Ollama restart policy nélkül fut;
- a reverse proxy csak indulási sorrendet kap, readiness feltételt nem;
- a migrate helyesen egyszer fut és `0` kóddal kilép;
- a backend startup task nincs eltárolva/leállítva a spectrum generatorhoz, míg a Kismet task szabályosan cancelre kerül;
- a hibás spectrum source nem dönti le a loopot, ami jó alap;
- erőforráslimit vagy HP-demó frame-rate profil még nincs.

## Hiányzó célkomponensek

- `compose.yaml`, `compose.rf.yaml`, `compose.ai.yaml`, `compose.dev.yaml`;
- `spectrum-ingest` service;
- C++17/20 `rf-agent`, Mock/Replay/Aaronia/USRP backendek és közös frame modellek;
- FFT/IQ pipeline;
- RF agent REST/WebSocket/MQTT API;
- SDRangel controller skeleton;
- recording formátum és fájlkezelés;
- `deploy/systemd/rf-agent.service`;
- HP demo és production hardware konfiguráció;
- docker audit/cleanup, backup/restore, migration és acceptance scriptek;
- `ARCHITECTURE.md`, `RF_AGENT.md`, `MIGRATION.md`, `BACKUP_RESTORE.md`;
- automatizált tesztkönyvtár.

## Prioritás és javasolt következő lépések

1. **P0 – mentési pont:** PostgreSQL, Kismet és uploads sértetlen mentése; valódi Git repository vagy checksum manifest létrehozása.
2. **P0 – RSSI bizonyítás:** backend kontrollált újraindítása után kizárólag új importált sorokon ellenőrizni a normalizálást és a collector `fetch_method` értékét.
3. **P1 – Compose felosztás:** core rendszerből kivenni az Ollamát és Kismetet; dev bind mount külön fájlba.
4. **P1 – stabilitás:** restart policy, healthcheck és `local` logging bevezetése.
5. **P1 – közös SpectrumFrame és rf-agent:** a meglévő UI kompatibilitás megtartásával.
6. **P2 – replay/recording/ingest:** működő HP-demó adatút.
7. **P2 – hardver skeletonok és SDRangel:** csak igazolt disabled/unavailable állapotokkal.

## Audit döntés

A jelenlegi rendszer megőrzendő és fokozatosan átalakítandó. Teljes újraírás vagy mostani könyvtármozgatás nem indokolt. Az audit alapján automatikusan törölhető üzleti komponens nincs. Elsőként a biztonsági mentési pontot kell létrehozni; csak utána következhet a Compose-rendrakás és a generált cache/dangling build elemek projekt-szűrt eltávolítása.

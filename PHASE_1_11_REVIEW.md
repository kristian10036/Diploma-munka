> **Történeti 1–11. review.** A benne jelzett hiányok egy része azóta elkészült; aktuális státusz: `PHASE_PROGRESS.md`.

# Phase 1–11 implementációs felülvizsgálat

Készült: 2026-06-19  
Irányadó specifikáció: `phase1.md`

## Auditkörnyezet és bizonyítékok

- A munkakönyvtár: `/root/Diploma_munka5_kismet_integrated`.
- A `.git` könyvtár üres/olvashatatlan metaadat-könyvtárként látszik; `git status`, `git diff` és commit hash nem áll rendelkezésre. Emiatt a változásaudit fájlszinten végezhető, Git-bizonyíték nem adható.
- `docker compose config` sikeres, de figyelmeztet a párhuzamos `compose.yaml` és legacy `docker-compose.yml` fájlra.
- `docker compose -f compose.yaml -f compose.rf.yaml config` sikeres.
- `docker run --rm <test-image> ctest --test-dir /src/build --output-on-failure`: 4/4 PASS (model, mock, replay, Aaronia `sdk_not_found`).
- A későbbi futtatás az új probe runnerrel és FFT pipeline-nal: 6/6 CTest PASS.
- Mentett runtime contract tesztek: `tests/api/test_rf_agent_rest.py` PASS és `tests/websocket/test_rf_agent_spectrum.py` PASS.
- A `127.0.0.1:8765` runtime probe sikertelen volt (`connection refused`), miközben egy korábbi `docker compose ps -a` healthy RF-agentet jelzett. Ezt runtime PASS-ként nem számítjuk.

## Státuszösszesítő

| # | Terület | Státusz | Korrekció szükséges |
|---:|---|---|---|
| 1 | Projekt-audit | PARTIAL | Igen |
| 2 | Monorepo struktúra | PARTIAL | Igen |
| 3 | Compose core/RF/AI/dev | PARTIAL | Igen |
| 4 | Monolitikus `main.py` modulokra bontása | BROKEN | Igen |
| 5 | Kismet RSSI-normalizálás | PARTIAL | Igen |
| 6 | Kismet Wi-Fi/Bluetooth megőrzése | PARTIAL | Igen |
| 7 | C++ RF agent és Aaronia backend kezdete | PARTIAL | Igen, biztonsági P0 |
| 8 | USRP backend/skeleton | NOT IMPLEMENTED | Igen |
| 9 | Közös végleges `SpectrumFrame` | DONE | Legacy frontend adapter megőrzendő |
| 10 | Mock backend | DONE | Csak sémaadaptáció |
| 11 | Replay backend | PARTIAL | Igen |

## 1. Projekt-audit — PARTIAL

Fájlok: `PROJECT_AUDIT.md`, `CURRENT_STATE_REPORT.md`, `PHASE_PROGRESS.md`.

Bizonyíték: a korábbi audit részletes leltárt, DB/Kismet és Compose megállapításokat tartalmaz. Azóta azonban létrejött a C++ agent és a Compose-felosztás, ezért több „hiányzó” állítása elavult. A jelen audit igazolta a dokumentáció, `spectrum-ingest`, `ml`, scripts és tesztstruktúra hiányait.

Hiány: nincs használható Git diff; nincs naprakész komponenslista a mostani kódra; nincs biztonságos Docker-audit script. Korrekció: a `PROJECT_AUDIT.md` frissítése szükséges, törlés nem indokolt.

Publikus API/WS változás: az új C++ RF API a legacy Python API mellett jelent meg; kompatibilitás nincs snapshot teszttel bizonyítva.

## 2. Monorepo könyvtárstruktúra — PARTIAL

Fájlok/könyvtárak: `compose*.yaml`, `python-processor/`, `rf-agent/`, `database/`, `docker/`, `config/`, `recordings/`.

Bizonyíték: a C++ agent, Dockerfile és sémák strukturáltak. Hiányzik `spectrum-ingest/`, `ml/`, `scripts/`, `tests/`, `deploy/systemd/`, több dokumentum; a backend továbbra is `python-processor` néven és főleg monolitikusan él.

Korrekció: fokozatos bővítés szükséges; vak könyvtármozgatás tilos.

Publikus API/WS változás: nincs közvetlenül, de az útvonalak mozgatása előtt karakterizáció kötelező.

## 3. Compose core/RF/AI/dev felosztás — PARTIAL

Fájlok: `compose.yaml`, `compose.rf.yaml`, `compose.ai.yaml`, `compose.dev.yaml`, legacy `docker-compose.yml`.

Bizonyíték: mindkét fő Compose-feloldás sikeres. A core nem indít RF hardvert vagy Ollamát; restart és local logrotáció nagyobbrészt be van állítva; migrate `restart: no` és DB-health függő.

Hiány/hiba: a core specifikációban kötelező `spectrum-ingest` nincs; Mosquitto healthcheck hiányzik; a legacy alapértelmezett fájl Compose-figyelmeztetést okoz; a dev/AI overlay minimális; host storage/env stratégia hiányos. A futó projektállapot nem bizonyította a teljes core stack runtime működését.

Publikus API/WS változás: a core jelenleg továbbra is a backend legacy `/ws/spectrum` endpointját szolgálja.

## 4. `main.py` modulokra bontása — BROKEN

Fájlok: `python-processor/main.py` (több mint 3300 sor), kisebb `app/config.py`, collector és spectrum source modulok.

Bizonyíték: collectorok és spectrum source-ok részben külön modulban vannak, de route-ok, DB SQL, import, session, frontend mount, spectrum loop és assistant továbbra is a monolitban található.

Hiány: `tests/api/`, `tests/websocket/`, `tests/integration/` és `tests/snapshots/openapi.json` nem létezik. Ezért a refaktor kompatibilitása nem bizonyított.

Korrekció: előbb snapshot/karakterizáció, utána inkrementális route/service szétválasztás.

Publikus API/WS változás: nem bizonyított; a legacy WS pontlistát, a C++ WS teljes frame-et küld.

## 5. Kismet RSSI-normalizálás — PARTIAL

Fájlok: `python-processor/main.py`, `python-processor/app/services/collectors/kismet.py`, `database/migrations/006_kismet_wifi_alignment.sql`, `007_bettercap_ble_alignment.sql`.

Bizonyíték: a kötelező aliasok szerepelnek a collector és normalizáló kódban, többek között `device_last_signal`, `kismet.common.signal.last_signal`, slash aliasok, `bluetooth_rssi_last/avg` és dotted Bluetooth aliasok.

Hiány: nincs dokumentált, újonnan importált sorokra futtatott Wi-Fi/Bluetooth SQL teszt. A régi audit nullás normalizált RSSI-t rögzített, ami nem bizonyítja a jelenlegi kód runtime eredményét.

Korrekció: kontrollált friss import után a specifikáció két COUNT lekérdezése és konkrét új sorok ellenőrzése szükséges.

Publikus API/WS változás: Wi-Fi/BLE response mezők kompatibilitása nincs snapshotolva.

## 6. Kismet Wi-Fi/Bluetooth integráció — PARTIAL

Fájlok: `compose.rf.yaml`, `docker/kismet/`, collector modul, backend Wi-Fi/Bluetooth endpointok, frontend tabok.

Bizonyíték: a Compose több source env-et és Kismet volume-ot ad; a backend rendelkezik status/import/device/observation/RSSI route-okkal; a frontend külön Wi-Fi és Bluetooth nézetet tartalmaz. A `docker compose ps -a` Kismet futást jelzett.

Hiány: `.kismet` fájl megléte, friss live import, session nélküli legutóbbi adatok és több source eredménye ezen auditban nem kapott végponttól végpontig bizonyítást.

Korrekció: adatot nem törlő integration teszt és SQL/API ellenőrzés.

## 7. C++ RF agent és Aaronia kezdete — PARTIAL

Fájlok: `rf-agent/`, `docker/rf-agent/Dockerfile`, `compose.rf.yaml`.

Bizonyíték: a C++17 agent buildel; REST/WS alap, mock/replay source manager létezik. A `/sources` Aaronia állapotot csak hardcoded `disabled` értékként adja.

Elkészült: külön `aaronia-probe` executable, amely `RTLD_NOW | RTLD_LOCAL` módban tölt, a dokumentált `AARTSAAPI_Init_With_Path` és `AARTSAAPI_Shutdown` szimbólumokat oldja fel, strukturált JSON-t és CPU-diagnosztikát ad. A fő agent fork/exec subprocess runnerrel, timeouttal, korlátozott stdout/stderr-rel és külön exit/`SIGILL`/`SIGSEGV` feldolgozással indítja. Elérhető a `GET/POST /aaronia/probe` és `GET /aaronia/status`; a runtime REST contract PASS. SDK nélkül is buildel; a hiány- és crash-szimulációs tesztek PASS. A tényleges HP probe izolált konténerben `library_load_failed` eredményt adott, mert a slim teszt-image-ből hiányzott a `libusb-1.0.so.0`; AVX=true, AVX2=false. Egy második, host-library mountos kísérlet glibc ABI-keverés miatt elutasítandó megoldásnak bizonyult, ezért abból SDK-következtetés nem vonható le.

Kritikus hiány: nincs `aaronia-worker`, worker PID/heartbeat/restart backoff és valódi packet adatút. A vendor library továbbra sem kerül a stabil főfolyamatba.

Korrekció: külön helper executables SDK nélküli buildképességgel; a fő agent soha nem linkelhet/tölthet vendor libraryt.

Publikus API/WS változás: hiányzik `/aaronia/probe`, `/aaronia/status`, strukturált hiba és worker státusz.

## 8. USRP backend/skeleton — NOT IMPLEMENTED

Fájl: csak `rf-agent/CMakeLists.txt` `ENABLE_USRP` opciója és hardcoded disabled source-lista.

Bizonyíték: `ENABLE_USRP=ON` fatal error; nincs source/worker, UHD discovery, konfiguráció vagy status endpoint.

Korrekció: SDK-független disabled skeleton, opcionális UHD build és lehetőleg worker izoláció.

Publikus API/WS változás: `/usrp/status` hiányzik.

## 9. Végleges közös `SpectrumFrame` — DONE

Fájlok: `rf-agent/include/rf_agent/models.hpp`, `src/models.cpp`, `src/frame_json.cpp`, `config/spectrum-frame.schema.json`.

Bizonyíték: a modell, serializer és JSON schema `step_frequency_hz`, `num_points`, `power_unit`, `powers_dbm` és `flags` mezőket használ; nincs frekvenciatömb. A validáció ellenőrzi a `stop = start + step × (num_points-1)` azonosságot, tömbméretet, ISO timestampet, sequence-t, NaN/Inf értékeket és max méretet. A 4/4 CTest PASS részeként a model/mock/replay tesztek is megfeleltek.

A frontend pontlista kompatibilitási adapter számítja a frekvenciát. A replay parser a korábbi recordingokból fallbackként képes lépésközt származtatni, de minden új kimenet az authoritative wire sémát használja.

Publikus API/WS változás: szükségszerű RF WS sémafrissítés, schema version/kompatibilitás dokumentálásával.

## 10. Mock backend — DONE

Fájlok: `rf-agent/src/mock_rf_source.cpp`, header és `tests/test_mock_rf_source.cpp`.

Bizonyíték: determinisztikus zaj, álló és mozgó keskenysávú jel, szélessávú komponens, burst, változó amplitúdó, FPS limit és szimulációs metadata látható a kódban; külön unit teszt target fordul.

Hiány: a végleges frame sémára át kell állítani, majd újrafuttatni a tesztet. Ez adaptáció, nem újraimplementálás.

Publikus API/WS változás: a végleges RF frame schema miatt változik; source label marad `mock`.

## 11. Replay backend — PARTIAL

Fájlok: `rf-agent/src/replay_rf_source.cpp`, header, `tests/test_replay_rf_source.cpp`, `config/recording-metadata.schema.json`.

Bizonyíték: NDJSON/zstd olvasás, SHA-256 ellenőrzés, max méretek, pause/resume/seek/loop és engedélyezett sebességek implementáltak; sérült recording inicializálása hibára fut; unit teszt target fordul.

Hiány: recording létrehozás nincs; `/recordings/{id}` nincs; `/recordings/start|stop` 501; metadata PostgreSQL tárolás nincs; eredeti timestamp-alapú timing és sérült egyedi frame kihagyás bizonyítása hiányos; a parser a régi frame sémát használja.

Korrekció: a meglévő olvasót megőrizve végleges schema, writer/API/DB metadata és teljes integration teszt.

Publikus API/WS változás: replay output `source_type=replay` és eredeti source metadata jelenleg jó irány, de a wire schema migrálandó.

## Következő kötelező lépés

Az 1–11. pontból következő P0 feladat az API/WS karakterizáció és az Aaronia worker/főagent felügyelet befejezése. A végleges `SpectrumFrame` és az izolált probe alapja elkészült; az FFT csak a fennmaradó baseline kompatibilitási munka után kezdhető meg.

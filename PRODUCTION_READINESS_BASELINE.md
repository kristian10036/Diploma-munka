# Production readiness baseline

Dátum: 2026-06-20 (Europe/Budapest)  
Authoritative specifikáció: `phase2.md`

## Kiindulási állapot

- A projektkönyvtárban nincs `.git`, ezért `git status`, diff és commit-alapú
  kompatibilitási baseline nem készíthető. Ez környezeti hiány, nem sikeres Git-audit.
- A Compose core, core+RF, core+RF+AI és core+dev konfigurációja parse-olható.
- Az audit idején egyetlen Compose service sem futott.
- A backend entrypoint `python-processor/main.py` 3979 soros monolit; néhány ML,
  RAG, collector, spectrum-source és RF Agent kliens modul már külön létezik.

## Szolgáltatások

| Szolgáltatás | Jelenlegi szerep | Baseline állapot |
|---|---|---|
| `database` | PostgreSQL/TimescaleDB és pgvector | konfigurálva, futás közben nem tesztelt |
| `migrate` | SQL fájlok sorrendi alkalmazása | konfigurálva; nincs alkalmazott-verzió nyilvántartás |
| `mosquitto` | MQTT broker | konfigurálva, nem futott |
| `backend` | FastAPI, DB/API, Wi-Fi/BLE, ML, RAG, RF proxy | unit részhalmaz tesztelt, élő API nem |
| `spectrum-ingest` | SpectrumFrame validáció, reconnect, bounded fan-out | kód auditálva; host dependency hiány miatt teszt nem futott |
| `frontend` | statikus magyar kezelőfelület | forrás auditálva; DOM/browser smoke nincs |
| `reverse-proxy` | egyetlen core host port és WS proxy | Compose parse PASS, runtime nincs |
| `rf-agent` | C++ mock/replay, recording, probe és control API | build + 10/10 CTest PASS |
| `kismet` | passzív Wi-Fi/BLE megfigyelés | opcionális, hardver/runtime nincs |
| `ollama` | opcionális chat/embedding | opcionális, runtime nincs |

## API- és WebSocket-baseline

- Backend: health; ML; spectrum source; Kismet; Bettercap; session; import;
  Wi-Fi/Bluetooth; reference; peak; marker create/list; audit list; RF Agent
  proxy; recording/replay; Aaronia/USRP/SDRangel proxy; system; RAG és assistant
  endpointok vannak. A marker update/archive/delete, known-signal és teljes alert
  workflow még nincs.
- Backend WebSocket: `/ws/spectrum` régi `[{x, y}]` kompatibilitási adatút.
- Spectrum ingest: `GET /health`, `/status`, `/metrics`; WebSocket
  `/ws/spectrum`, `/ws/status`.
- RF Agent REST: `/health`, `/status`, `/capabilities`, `/sources`,
  `/sources/current`, source select/start/stop/configure, recording/replay,
  Aaronia/USRP probe/status és SDRangel control endpointok.
- RF Agent WebSocket: `/ws/spectrum`, `/ws/status`.
- A publikus OpenAPI/runtime contract tesztek nem futottak, mert a stack nem fut.

## Adatbázis-migrációk

Meglévő, változatlan migrációk: `001_initial_schema.sql`–
`010_operational_metadata.sql`. A 010 marker, RF detection, system alert és audit
táblákat hoz létre. Known-signal, marker archiválás/revízió, reference verziózás,
recording type és teljes review workflow migráció még nincs.

A Compose migrátor minden induláskor minden SQL fájlt újrafuttat. A migrációk
többnyire `IF NOT EXISTS` elemeket használnak, de nincs tranzakciós migrációs
verziótábla; ez produkciós kockázat.

## Frontend-baseline

- A felső fülsor sorrendje változatlan: Spektrum; Wi-Fi / Kismet; Bluetooth / BLE;
  RF Agent; Felvételek; ML osztályozás; RAG; Rendszerállapot.
- Meglévő funkciók: spektrum, waterfall, overview, zoom/pan/marker, max hold,
  reference/diff, session, Wi-Fi/BLE panelek, RF Agent, recording, ML, RAG és
  system panelek.
- A spektrum eszköztár zsúfolt és részben angol; referencia/peak mentéshez
  böngésző `prompt()` használatos.
- A marker UI csak ideiglenes markerre épül; tartós CRUD/lista nincs kész.
- Automatikus DOM/Playwright smoke teszt nincs.

## Baseline teszteredmények

| Ellenőrzés | Tényleges eredmény |
|---|---|
| Python unit (`python-processor/tests`) | 18/18 PASS |
| C++ build, Aaronia ON / USRP OFF | PASS |
| CTest | 10/10 PASS |
| Spectrum ingest host teszt | NEM FUTOTT: `ModuleNotFoundError: fastapi` |
| Python szintaxis | PASS |
| Shell `bash -n` | PASS |
| JSON sémák parse | PASS |
| Compose: core/RF/AI/dev parse | PASS |
| Frontend Node syntax | NEM FUTOTT: `node` nincs telepítve |
| Teljes acceptance | FAIL: 15 hiba, 2 warning; a stack nem futott |
| Élő API/WS contract | NEM FUTOTT: backend/RF Agent nem futott |

Az acceptance-ben a Compose parse, orphan check és backup dry-run PASS volt.
Minden service-, HTTP- és runtime ellenőrzés a hiányzó futó stack miatt hibázott.

## Hardverfüggetlenül tesztelhető / nem tesztelhető

Tesztelhető és részben igazolt: SpectrumFrame C++ validáció, mock/replay,
recording writer, FFT, probe-runner izoláció, SDRangel kliens unit szinten, ML/RAG
unit részhalmaz, Compose és sémák.

Nem igazolt ebben a baseline-ban: élő DB/API/WS adatút, frontend DOM/rendering,
Kismet/BLE runtime, teljes recording/replay acceptance, SDRangel élő control és
IQ data plane, Aaronia/USRP valós adatút, valós ML modell.

## Észlelt szerződés- és implementációs hibák

1. **Kritikus SpectrumFrame frontend kontraktushiba:** a spectrum-ingest teljes
   `SpectrumFrame v1` objektumot küld, a frontend `normalizeIncoming()` viszont
   tömböt vár. Az objektum üres inputként teljes tartományú, mesterséges
   `-105 dBm` görbévé válik.
2. A hiányzó frekvenciatartomány `-105 dBm` értékkel van kitöltve, nem validity
   hiányként; ez hamis mérésnek látszik.
3. A natív frame és a teljes tartományú overview ugyanaz a fix 24 576 bin-es,
   10 MHz–24 GHz tömb. Keskenysávú natív részlet elveszhet.
4. Nincs frontend stale timeout, teljes frame metadata vagy sequence-gap kijelzés.
5. A marker API csak create/list; nincs teljes CRUD, archiválás és kapcsolódó UI.
6. Nincs known-signal modell és tolerancia/tulajdonság alapú matching.
7. A referencia nem teljesen verziózott/import-registry alapú; `.peak` kontrollált
   adapter még nincs.
8. Az IQ/audio recording adatmodell és mock fixture nincs kész.
9. Az SDRangel IQ data plane csak dokumentált skeleton; valósnak nem tekinthető.
10. A backend továbbra is 3979 soros monolit.
11. A Compose több ellenőrizetlen `latest` image taget használ.
12. A migrációfuttató nem tart nyilván alkalmazott verziókat.

## Módosítás előtti kompatibilitási alap

- A fenti endpointok és a nyolc felső fül megőrzendő.
- A JSON `SpectrumFrame v1` és a régi `[{x,y}]`, `[{freq,dbm}]`, valamint
  számtömb frontend formátumok kompatibilitása megőrzendő.
- Mock/replay mindenhol szimuláltként jelölendő.
- A meglévő 001–010 migrációk nem módosíthatók; minden sémafejlesztés új forward
  migration.
- A meglévő recording és volume adatok érintetlenek maradnak.

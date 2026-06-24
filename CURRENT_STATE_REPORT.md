> **Történeti állapotjelentés.** A jelenlegi implementációt a `PHASE_PROGRESS.md` és a `FINAL_AUDIT.md` írja le.

# Current State Report

Készült: 2026-06-18  
Hatókör: `CODEX_PLAN.md` — Phase 1 (projektfelmérés és biztonságos takarítás)

## Átvizsgált területek

- `docker-compose.yml`
- `nginx/default.conf`
- `python-processor/Dockerfile`
- `python-processor/.dockerignore`
- `python-processor/main.py`
- `database/init/001_apply_migrations.sql`
- `database/migrations/001_initial_schema.sql`
- `database/migrations/002_device_import_tables.sql`
- `database/migrations/003_reference_layers.sql`
- `database/migrations/004_reference_band_nmhh_fields.sql`
- `database/README.md`
- `python-processor/static/index.html`
- `python-processor/static/import.html`
- `.env.example` (csak olvasás; titok nem lett módosítva)

## Jelenlegi architektúra

A Compose-konfiguráció hat szolgáltatást ír le:

1. `reverse-proxy`: Nginx, alapértelmezetten a gazdagép 8080-as portján.
2. `frontend`: Nginx, amely a statikus HTML-fájlokat szolgálja ki.
3. `backend`: Python 3.11 + FastAPI/Uvicorn.
4. `database`: TimescaleDB/PostgreSQL 16.
5. `mosquitto`: MQTT broker.
6. `ollama`: helyi modellfuttató szolgáltatás, de a backendben még nincs valódi RAG-használat.

A reverse proxy az `/api/` útvonalat a backendre, a `/ws/` útvonalat WebSocket-támogatással a backendre, minden más kérést a frontend konténerre irányít. A backend ezen felül közvetlenül is mountolja a statikus könyvtárat, tehát jelenleg két kiszolgálási út létezik ugyanahhoz a frontendhez.

## Backend jelenlegi állapota

A backend egyetlen, körülbelül 1200 soros `main.py` modulban tartalmazza a konfigurációt, adatbázis-hozzáférést, importokat, referencia-kezelést, elemzést, statikus kiszolgálást és a spektrumszimulátort.

Jelenlegi HTTP endpointok:

| Metódus | Útvonal | Funkció |
|---|---|---|
| GET | `/api/health` | Konfigurációs állapot és támogatott funkciók |
| POST | `/api/imports/{device_type}` | Általános CSV-import |
| POST | `/api/references/bands/import` | Referenciasáv CSV-import |
| POST | `/api/references/spectrum/import` | Referenciaspektrum CSV-import |
| POST | `/api/references/images` | Referenciakép feltöltése |
| GET | `/api/references/bands` | Referenciasávok lekérdezése |
| GET | `/api/references/spectrum` | Referenciaspektrum lekérdezése |
| GET | `/api/references/images` | Referenciaképek listázása |
| GET | `/api/references/images/{image_id}/file` | Referenciakép letöltése |
| POST | `/api/spectrum/reference-captures` | Aktuális spektrum mentése referenciaként |
| POST | `/api/spectrum/peaks` | Spektrumcsúcs mentése |
| GET | `/api/analysis/repeated-macs` | Több helyszínen látott MAC-címek |
| POST | `/api/ask` | Egyetlen szabályalapú kérdéstípus, nem valódi RAG |

Jelenlegi WebSocket endpoint:

- `/ws/spectrum`: 2400–2500 MHz közötti, 100 pontos szimulált spektrumot küld körülbelül fél másodpercenként.

A szimulátor és az MQTT-riasztás a backend indulásakor automatikusan elindul. Valódi Spectran/Aaronia hardverforrás nincs bekötve. A `Kismet` és `Bettercap BLE` név már szerepel az általános CSV-import támogatott típusai között, de ez nem valódi Kismet/Bettercap kollektor vagy protokollintegráció; az 1. fázisban ez a meglévő kód változatlan maradt.

A `/api/health` jelenleg azt jelzi, hogy az adatbázis URL konfigurálva van-e, de nem végez tényleges adatbázis-, MQTT- vagy Ollama-readiness ellenőrzést.

## Adatbázis jelenlegi állapota

Négy számozott migráció található:

1. `001_initial_schema.sql`: alapfelhasználók, helyszínek, mérési források, korai mérési munkamenetek, SDR/kalibráció, spektrum, anomáliák, Wi-Fi, Bluetooth, import- és dokumentumtáblák.
2. `002_device_import_tables.sql`: OSCOR, DDF, PR100, MESA, Kismet és Bettercap BLE nyers/normalizált CSV-import sorok és importhibák.
3. `003_reference_layers.sql`: referenciasávok, referencia-spektrumpontok és referenciaképek.
4. `004_reference_band_nmhh_fields.sql`: NMHH-metaadatok és helyszínspecifikus referencia-baseline tábla.

Az inicializáló SQL mind a négy migrációt sorrendben meghívja, de csak új adatbázis-adatkötet első indulásakor fut automatikusan. Meglévő adatbázisokhoz még nincs külön migrációfuttató.

A Phase 2 szempontjából fontos eltérések:

- Már van `measurement_sessions`, de `location_id`, `source_id`, `mode`, `title`, `notes` és `metadata` mezőkkel; hiányzik többek között a tervezett `location_name`, `operator_name`, `environment_description` és `created_at`.
- Már van `measurement_sources`, de globális forráskatalógusként működik, nincs `measurement_session_id`, `device_name`, `adapter_name`, `status` és `config` mezője.
- A spektrumminták és anomáliák már képesek `session_id` tárolására.
- A `wifi_observations`, `bluetooth_observations` és az eszközimport sorok jelenleg nem tartalmaznak mérési munkamenet-azonosítót.
- A meglévő backendben még nincsenek session start/stop/list/detail/active endpointok.

## Frontend jelenlegi állapota

- `index.html`: interaktív spektrum- és waterfall-nézet, zoom/pan/marker, max hold, lokális és adatbázis-referencia, csúcsmentés, WebSocket-kapcsolat és demo fallback.
- `import.html`: általános eszköz-CSV, referenciasáv, referenciaspektrum és referenciakép feltöltése, valamint a korlátozott `/api/ask` felület.
- A frontend tisztán statikus HTML/CSS/JavaScript, külön buildlépés és csomagkezelő nélkül.
- Aktív mérési munkamenetet megjelenítő vagy indító/leállító panel még nincs.

## Phase 1 során elvégzett biztonságos változtatások

- Létrejött a Python-függőségeket központilag felsoroló `python-processor/requirements.txt`.
- A backend Dockerfile most ebből a fájlból telepíti ugyanazokat a csomagokat, amelyeket korábban közvetlenül a Dockerfile sorolt fel.
- A backend image letiltja a Python bytecode fájlok írását, így a fejlesztői bind mount újraindításkor sem hozza vissza a host oldali `__pycache__` könyvtárat; a naplózás pufferelése is ki van kapcsolva.
- Létrejött a `.gitignore`, amely kizárja a helyi titkokat, Python cache-eket, virtuális környezeteket, runtime feltöltéseket, logokat és szerkesztői fájlokat; a `.env.example` továbbra is követhető.
- A megtalált `__pycache__` és `.pyc` fájlok eltávolításra kerülnek az 1. fázis részeként.
- Endpoint és adatbázis-migráció nem változott.

## Kockázatok és későbbi teendők

- A Compose több `latest` image taget használ, ezért a build/telepítés idővel nem teljesen reprodukálható.
- A közvetlen Python-függőségek külön fájlba kerültek, de verzióik még nincsenek rögzítve; egy későbbi, külön jóváhagyott karbantartási lépésben lockolt verziók használata indokolt.
- A szolgáltatásokhoz nincs Docker healthcheck; a `depends_on` csak indulási sorrendet biztosít, readiness-t nem.
- A backend bind mount fejlesztéshez kényelmes, de futáskor elfedi az image-be másolt alkalmazásfájlokat.
- A backend fokozatos modulokra bontása indokolt, de nem része ennek a fázisnak.
- A session séma összehangolását új, előre mutató migrációval kell elvégezni; meglévő táblát vagy adatot nem szabad törölni.
- A valódi Spectran/Aaronia, Kismet, Bettercap, RAG és ML integrációk későbbi fázisok feladatai.

## Ellenőrzés

A tervben előírt ellenőrzések 2026-06-18-án lefutottak:

```powershell
docker compose down --remove-orphans
docker compose up -d --build
docker compose ps
curl.exe http://localhost:8080/api/health
```

Eredmény:

- A korábbi Compose-konfigurációból megmaradt, már leállt orphan konténerek eltávolítása sikeres volt; név szerinti volume nem lett törölve.
- A backend image sikeresen felépült a `requirements.txt` használatával.
- A `backend`, `database`, `frontend`, `mosquitto`, `ollama` és `reverse-proxy` szolgáltatás egyaránt `Up` állapotban van.
- A `http://localhost:8080/api/health` sikeres választ adott: `status=ok`, `service=tscm-backend`, `database_configured=true`.
- A konténer újraindítása után sincs `__pycache__` könyvtár vagy `.pyc` fájl a munkaterületen.

A könyvtár jelenleg nem tartalmaz elérhető `.git` mappát, ezért Git-alapú státusz vagy diff nem készíthető; a módosított fájlok listája a Phase 1 végső jelentésében szerepel.

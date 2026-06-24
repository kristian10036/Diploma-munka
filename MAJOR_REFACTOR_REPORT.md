# Major refactor report

Tracks `major_refactor_prompt.pdf` ("viselkedésmegőrző refaktor és
referencia-konszolidáció"), Fázis 0–6. One section per completed phase.
This is a separate track from the legacy `phase1.md`/`phase2.md`
A–O system tracked in `PHASE_PROGRESS.md`.

## Fázis 0 – biztonsági háló és CI (2026-06-24)

### Előzmény / kiindulási állapot

A repo nem volt verziókövetve (`.git` üres mappa). Ezt a fázist megelőzően
`git init` + egy baseline commit (`91899b4`) készült, hogy a további
fázisoknak legyen visszaforgatási pontja.

A pyproject.toml, a Dockerfile test stage (`python -m pytest -q`, 121 teszt),
a pytest markerek és `scripts/check_release_package.py` már léteztek egy
korábbi munkamenetből. Ez a fázis a hiányzó részeket zárta le.

### Módosított fájlok

- `pyproject.toml` — `addopts` kiegészítve `-m "not integration and not
  hardware and not docker"`-rel, hogy az alapértelmezett/offline pytest
  futás (és minden, ami a gyökér pyproject.toml-t használja) kihagyja a
  élő infrastruktúrát igénylő teszteket, de explicit `-m integration`-nel
  továbbra is futtathatók maradjanak.

### Új fájlok

- `tests/test_openapi_snapshot.py` + `tests/fixtures/openapi_snapshot.json`
  — az `app.openapi()` séma golden snapshotja; drift esetén elbukik,
  `UPDATE_OPENAPI_SNAPSHOT=1`-gyel regenerálható.
- `python-processor/tests/test_reference_set_export_shape.py` +
  `tests/fixtures/reference_set_export_golden.json` — `_export_payload()`
  kimeneti alakjának golden fixture tesztje, `ScriptedCursor` fake-kel
  (nincs valós DB-kapcsolat, ahogy a meglévő tesztek is hand-rolled
  fake-eket használnak, pl. `test_management_frames_and_baseline.py`).
- `tests/integration/test_reference_set_round_trip.py` — valós Postgres
  ellen futó (`@pytest.mark.integration`, `DATABASE_URL` hiányában
  `skipif`) export→import→export round-trip teszt `/api/reference-sets/
  capture` → `/export` → `/import` → `/export` láncon, FastAPI
  `TestClient`-tel. Egy `device_baselines` sort direktben szúr be SQL-lel
  (mert `capture_reference_set` csak `save_baseline()`-on keresztül írna
  ilyet, ami élő session-megfigyeléseket igényelne).

### Mi lett csak mozgatva és mi változott funkcionálisan

Nem történt forráskód-mozgatás vagy funkcionális változás az `app/`
alatt. Kizárólag teszt-/CI-infrastruktúra került hozzá, és egy
konfigurációs sor (`addopts`) változott.

### Migrációk

Nincs új migráció ebben a fázisban.

### Kritikus hiba dokumentálva (még nem javítva)

A round-trip teszt explicit módon rögzíti és bizonyítja a
major_refactor_prompt.pdf Fázis 3-ban megnevezett hibát:
`/api/reference-sets/{id}/export` visszaadja a `device_baselines`
tömböt, de `/api/reference-sets/import` figyelmen kívül hagyja –
import után a komponens elvész. A teszt jelenleg ezt mint elvárt
(hibás) viselkedést asserteli, kommenttel jelölve, hogy Fázis 3
megoldása után az assertiont meg kell fordítani.

### Teszteredmények (pontos számmal)

Mért környezet: a sandboxban a system Python `fastapi==0.135.3`-at futtat,
miközben `python-processor/requirements.txt` `fastapi==0.128.2`-t ír elő —
ez eltérést okozott az OpenAPI snapshotban, amíg a snapshotot egy pinnelt,
`requirements.txt`-ből épített scratch venv-vel nem generáltam újra.
Minden alábbi szám ebből a pinnelt venv-ből származik.

- `python -m pytest -q` (gyökérből, alapértelmezett `addopts`-szal):
  **132 passed, 8 deselected** (a 8 deselected: 7 élő `rf-agent`/backend
  szolgáltatást igénylő `tests/api`+`tests/websocket` kontraktteszt +
  az új `tests/integration/` round-trip teszt).
- `python -m pytest -q -m integration` (élő infrastruktúra nélkül):
  **7 failed** (a régi rf-agent kontrakttesztek, `ConnectionRefusedError`
  – ez várt, hiszen nincs élő szolgáltatás), **1 skipped** (az új
  round-trip teszt, `DATABASE_URL` hiányában) – ezt a stack ellen kell
  lefuttatni a valódi megerősítéshez.
- `python -m pytest -q python-processor/tests tests/frontend/
  test_ui_static.py` (a Docker test stage / `scripts/offline-
  acceptance.sh` által futtatott szűkebb kör): **121 tests, mind PASS**
  – pontosan megfelel a Fázis 0 specifikációban megadott célszámnak.
- `scripts/offline-acceptance.sh` (pinnelt venv-vel a PATH-on): **10 PASS,
  2 FAIL, 0 WARN** → Python syntax, offline pytest, spectrum-ingest
  tesztek, coverage, frontend JS syntax+fixture-ök, offline load
  fixture, static production invariants, production fail-fast, shell
  syntax mind PASS. A 2 FAIL: `ruff check` és `ruff format` (lásd alább).
- `node --check` az összes `python-processor/static/*.js` és
  `tests/frontend/*.js` fájlon: mind PASS, szintaktikailag hibátlan.
- A 4 meglévő `tests/frontend/*.js` modul saját assertion-futása
  (`node tests/frontend/test_*.js`): mind PASS.

### Coverage változás

- `python-processor/tests` + `tests/frontend/test_ui_static.py` körén:
  **40.36%** statement coverage (`coverage report`, branch=true).
- A teljes offline gyökér-suite-on (minden deselektált integration nélkül):
  **48.30%** statement coverage.
Nincs korábbi commitolt coverage-szám, amihez viszonyítani lehetne (ez az
első mérés, mivel a repo most kapott verziókövetést) – ez a baseline a
következő fázisok összevetési pontja.

### Ruff – ismert, nem javított adósság

`ruff check .`: **649 hiba** (jellemzően `E501` túl hosszú sor és `I001`
rendezetlen import) **88 fájlban**; `ruff format --check .`: **85 fájl**
igényelne átformázást. Ez a kódbázis korábbról örökölt, eddig sosem
kikényszerített állapota – a Fázis 0 célja a Ruff *futtatása és
dokumentálása* volt, nem a teljes meglévő kódbázis átformázása (az utóbbi
indokolatlanul nagy, kockázatos diffet jelentene a terv saját 7. szabálya
ellen: „Ne használj globális search/replace refaktort ellenőrzés
nélkül”). A három, ebben a fázisban hozzáadott új tesztfájl Ruff-tiszta
(`ruff check`/`format --check` mindkettő PASS rájuk szűkítve).

### Ismert korlátok

- A `tests/integration/test_reference_set_round_trip.py` tesztet nem
  sikerült élő Postgres ellen futtatni ebben a sandboxban (nincs elérhető
  DB; a `database` service TimescaleDB+pgvector image-e saját Dockerfile-t
  igényelne felépítéshez). A teszt szintaktikailag és kollekció szintjén
  ellenőrzött, `DATABASE_URL` hiányában tisztán skip-el – éles
  megerősítés a felhasználó docker stack-je ellen szükséges.
- A sandbox system Python-ja **nem** egyezik a `requirements.txt` pinnel
  (`fastapi` 0.135.3 vs 0.128.2 pinnelt) – ezért minden mérést egy
  scratch venv-ben (`requirements.txt`-ből épített) végeztem el. Érdemes
  lenne a fejlesztői dokumentációban (RUNNING.md) explicit módon jelezni,
  hogy a teszteket pinnelt venv-ből vagy a Docker `test` stage-ből kell
  futtatni, nem a system Pythonból.
- `ruff`/`coverage` nincs telepítve a Dockerfile `test` stage-en kívül
  sehol dokumentáltan (a `python-processor/Dockerfile` test stage-je
  telepíti és futtatja, de a gyökér-szintű ellenőrzéshez/CI-hez nincs
  pinnelt dev-requirements fájl).

### Következő fázis kockázatai (Fázis 1 – frontend darabolás)

- A `python-processor/static/index.html` 4307 soros; a tervezett ES
  modulokra bontás (api-client, 3 store, 5 controller, views, css) nagy,
  egyetlen lépésben kockázatos diff – érdemes inkrementálisan, minden
  modul kiemelése után a meglévő `tests/frontend/test_ui_static.py` +
  Playwright-szerű manuális ellenőrzéssel haladni.
- A helyi referencia-cache verziózott objektumra cserélése és a
  peak-preserving-vs-backend-normalizálás döntés (backend-oldali
  normalizálás mellett döntöttünk) backend API-érintést is jelenthet –
  ellenőrizni kell, hogy ez nem ütközik a Fázis 3 kanonikus
  referencia-domain munkájával.

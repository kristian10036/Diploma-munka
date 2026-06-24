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

## Fázis 1 – frontend darabolás (folyamatban, 2026-06-24)

### Live-verifikációs infrastruktúra (új, ismételten felhasználható)

A statikus tesztek (JS syntax, `test_ui_static.py`) nem fognak meg
canvas-rajzolási vagy állapotkezelési regressziót. Ezért minden további
modul kiemelése után élő böngészős ellenőrzés készül:

- Scratch venv: `/tmp/.../scratchpad/venv` (uvicorn + a `requirements.txt`
  pinnelt verziói).
- Indítás: `APP_MODE=demo AUTH_MODE=disabled LOG_LEVEL=ERROR
  uvicorn main:app --app-dir python-processor --host 127.0.0.1 --port 8099`
  (DATABASE_URL nélkül – a hálózati hívások 503-at adnak, ez elvárt és
  nem hiba).
- Scratch Node projekt + Playwright Chromium:
  `/tmp/.../scratchpad/pw` (`npm install playwright@1.61.1`,
  `npx playwright install chromium` – `--with-deps` nem megy sudo
  nélkül, de a böngésző bináris önmagában telepíthető és működik).
- `pw/smoke.js`: minden fő tabra (`spectrum`, `wifi`, `bluetooth`,
  `rfagent`, `recordings`, `ml`, `rag`, `system` – ld. valódi
  `data-tab` attribútumok) átkattint, és csak a `pageerror` (nem
  elkapott kivétel) eseményt tekinti hibának. A `console.error`-t NEM,
  mert az app szándékosan logolja oda a hálózati/DB hibákat catch
  ágban (`DATABASE_URL nincs beallitva.` stb.) – ezek a jelenlegi
  DB nélküli sandboxban várt zaj, nem bug.
- Baseline (a CSS-kiemelés után, mielőtt bármilyen JS mozgott):
  **SMOKE PASS: zero JS errors across all tabs.**

### Elkészült: app.css kiemelés

Lásd a `33b4ced` commitot. `index.html`: 4307 → 3883 sor. Pure text
move, nincs funkcionális változás. `test_ui_static.py` CSS-tartalmú
assertjei (`grid-template-rows...`, `@media(...)`, stb.) most a
`app.css`-t ellenőrzik, nem a html-t.

### Inventory a következő lépéshez: api-client.js

A megmaradt ~3460 soros inline `<script>` mélyen összekapcsolt:
globális mutable state (`viewMin`/`mode`/`cursor`/`drag`/
`activeMeasurementSession`/`viewedSession`/`staticReference`/stb.) sok
tucat függvényből írva/olvasva, canvas-rajzolás (`drawSpectrum`,
`drawWaterfall`, `drawOverview`, markerek) közvetlenül a state-re épül.

A `fetch(` hívások (41 db az inline scriptben, a `system-tabs.js`/
`rag.js` saját fetch-jei nem számolva ide) helye és funkciója:

- Session kezelés: `/api/sessions/active`, `/start`, `/{id}/stop`,
  `/api/sessions?limit=50`, `/api/sessions/{id}`.
- Legacy device-baseline: `/api/device-baseline/save|compare|deactivate`.
- Kismet/Bettercap/Wi-Fi/Bluetooth: `/api/kismet/status`,
  `/api/kismet/import/status`, `/api/wifi/devices`,
  `/api/wifi/security-events`, `/api/detections`,
  `/api/bettercap/status`, `/api/bluetooth/devices`,
  `/api/import/kismet/live`, `/api/import/kismet/alerts`.
- Spektrum-referencia rétegek: `/api/references/bands`,
  `/api/references/images`, `/nmhh-frequency-allocations.json`
  (statikus, nem API).
- Reference-sets: `/api/reference-sets/capture`,
  `/api/reference-sets/{id}`, `/api/reference-sets/{id}/spectrum`,
  `/api/reference-sets?...`, `/api/spectrum/peaks`.
- Marker/known-signal CRUD: `/api/markers` (POST/PATCH/DELETE),
  `/api/known-signals` (POST/PATCH/DELETE).
- Admin/retention: `/api/admin/retention/preview|purge`.
- Legacy spectrum reference import: `/api/references/import`,
  `/api/references/{id}?include_points=true`.
- RF Agent/SDRangel: `/api/rf-agent/source/viewport`,
  `/api/rf-agent/sdrangel/demod/update|start|stop`,
  `/api/rf-agent/sdrangel/readiness`,
  `/api/integrations/sdrangel/devicesets`,
  `/api/rf-agent/sdrangel/tune`.

Minden call site-nak saját, magyar nyelvű hibaüzenete és saját
fallback-viselkedése van (pl. `payload.detail?.message || payload.detail
|| 'Session indítás sikertelen'` mintázat, de nem egységes – van
csendesen elnyelt hiba is, ld. `archiveMarker`). Az `api-client.js`
kiemelésnek ezt call site-onként kell megőriznie, ezért ez saját,
külön lépés – nem fért bele ebbe a sessionbe.

### Pontos fetch-leltár (újraszámolva, 2026-06-24 folytatás)

A korábbi „41” becslés helyett pontos `grep -n "fetch("` számlálás:
**48 sor, 49 db `fetch(` előfordulás** (a 2628. sor egy `Promise.all`-ban
két fetch-et tartalmaz egyetlen sorban). Pontos lista sorszámmal
(mind a `python-processor/static/index.html` jelenlegi, 3883 soros
állapotára vonatkozik):

| Sor | Endpoint | Csoport |
|---|---|---|
| 543 | `/api/health/ready` | runtime policy (induláskor) |
| 796 | `/api/sessions/active` | session |
| 890 | `/api/sessions/start` | session |
| 922 | `/api/sessions/{id}/stop` | session |
| 950 | `/api/sessions?limit=50` | session |
| 965 | `/api/sessions/{id}` | session |
| 993 | `/api/spectrum/source/status` | spektrum forrás |
| 1151 | `/api/device-baseline/save` | legacy device-baseline |
| 1170 | `/api/device-baseline/compare` | legacy device-baseline |
| 1185 | `/api/device-baseline/deactivate` | legacy device-baseline |
| 1327 | `/api/kismet/status` | Wi-Fi tab |
| 1328 | `/api/kismet/import/status` | Wi-Fi tab |
| 1331 | `/api/wifi/devices` | Wi-Fi tab |
| 1332 | `/api/wifi/security-events` | Wi-Fi tab |
| 1333 | `/api/detections` (domain=wifi) | Wi-Fi tab |
| 1406 | `/api/bettercap/status` | Bluetooth tab |
| 1407 | `/api/kismet/status` | Bluetooth tab (külön call site) |
| 1410 | `/api/bluetooth/devices` | Bluetooth tab |
| 1411 | `/api/detections` (domain=bluetooth) | Bluetooth tab |
| 1453 | `/api/import/kismet/live` | Kismet import |
| 1467 | `/api/import/kismet/alerts` | Kismet import |
| 1588 | `/api/references/bands` | spektrum-referencia rétegek |
| 1589 | `/api/references/images` | spektrum-referencia rétegek |
| 1606 | `/nmhh-frequency-allocations.json` | statikus fájl, NEM REST API |
| 2395 | `/api/reference-sets/capture` | reference-sets |
| 2446 | `/api/spectrum/peaks` | reference-sets |
| 2489 | `/api/reference-sets/{id}` | reference-sets (metaResponse) |
| 2494 | `/api/reference-sets/{id}/spectrum` | reference-sets |
| 2527 | `/api/reference-sets?...` | reference-sets (lista) |
| 2550 | `/api/reference-sets/{id}` | reference-sets (kiválasztott betöltése, külön call site) |
| 2589 | `/api/markers` POST | marker/known-signal CRUD |
| 2613 | `/api/known-signals` POST | marker/known-signal CRUD |
| 2628 | `/api/markers?limit=100` + `/api/known-signals?limit=100` | marker/known-signal CRUD (2 fetch egy sorban) |
| 2633 | `/api/markers/{id}` PATCH | marker/known-signal CRUD (`editMarker`) |
| 2634 | `/api/markers/{id}` DELETE | marker/known-signal CRUD (`archiveMarker`) |
| 2635 | `/api/known-signals/{id}` PATCH | marker/known-signal CRUD (`setKnownSignalStatus`) |
| 2636 | `/api/known-signals/{id}` DELETE | marker/known-signal CRUD (`archiveKnownSignal`) |
| 3056 | `/api/admin/retention/preview` | admin/retention |
| 3084 | `/api/admin/retention/purge` | admin/retention |
| 3194 | `/api/references/import` | legacy spectrum reference import |
| 3197 | `/api/references/{id}?include_points=true` | legacy spectrum reference import |
| 3221 | `/api/rf-agent/source/viewport` | RF Agent/SDRangel |
| 3453 | `/api/rf-agent/sdrangel/demod/update` | RF Agent/SDRangel |
| 3710 | `/api/rf-agent/sdrangel/readiness` | RF Agent/SDRangel |
| 3737 | `/api/integrations/sdrangel/devicesets` | RF Agent/SDRangel |
| 3755 | `/api/rf-agent/sdrangel/tune` | RF Agent/SDRangel |
| 3765 | `/api/rf-agent/sdrangel/demod/start` | RF Agent/SDRangel |
| 3797 | `/api/rf-agent/sdrangel/demod/stop` | RF Agent/SDRangel |

### Architektúra döntés (2026-06-24, folytatás): valódi ES modul + window-bridge

A `major_refactor_prompt.pdf` szövege szerint Fázis 1 célja explicit
**ES module-okra** bontás (`import`/`export`), nem a már meglévő 4
kiemelt fájl (`demod-passband.js`, `spectrum-frame-adapter.js`,
`spectrum-view-model.js`, `maxhold-controller.js`) által használt
UMD/IIFE+`globalThis` mintázat. Mielőtt `api-client.js`-t megírtam
volna, feltártam egy valódi blocker-t: a `system-tabs.js` (korábban
kiemelt, `<script src="/system-tabs.js">`, NEM modul) közvetlenül hívja
a fő inline scriptben deklarált `openOperationModal` és `toastMsg`
függvényeket (system-tabs.js sor 200, 222, 224, 238, 249, 251) puszta
azonosítóként. Ez ma azért működik, mert a fő `<script>` classic
(nem-modul) script, és a benne lévő `function` deklarációk a globális
objektumra (`window`) kerülnek, így egy később betöltött, ugyancsak
classic script (`system-tabs.js`) el tudja érni őket. `rag.js`-nek
nincs ilyen függősége (önállóan működik).

Ha a fő scriptet egyszerűen `type="module"`-ra állítanám, ez a
függőség némán elszállna (a modul-szintű `function` deklarációk NEM
kerülnek a globális objektumra) — ReferenceError `system-tabs.js`-ben.

Felhasználói döntés (megkérdezve, jóváhagyva): **valódi ES modul +
window-bridge**, nem az UMD-mintázat újrahasznosítása. Konkrétan:

1. A fő `<script>` (index.html 392. sor) `<script type="module">`-ra
   vált.
2. `toastMsg` és `openOperationModal` definíciója után egy-egy
   `window.toastMsg = toastMsg;` / `window.openOperationModal =
   openOperationModal;` sor hidalja át a `system-tabs.js`
   függőséget — ezt a két függvényt később, a `views/*`/`controllers/*`
   fázisban kell véglegesen modulra cserélni (akkor a bridge is törölhető).
3. `python-processor/static/package.json` új fájl, `{"type":"module"}`
   tartalommal — ez **csak** a Node tooling (`node --check`) ESM/CJS
   észleléséhez kell, a böngésző viselkedését nem érinti (a böngésző a
   `<script type="module">` attribútumból dönt, nem a package.json-ból).
   A meglévő UMD-fájlok szintaktikailag ESM alatt is érvényesek
   (a `typeof module === 'object'` guard csak futásidejű check, nem
   szintaxis), úgyhogy ez nem töri el a meglévő `node --check`
   ellenőrzéseket.
4. `scripts/offline-acceptance.sh` „frontend inline JavaScript syntax”
   lépése jelenleg `re.findall(r'<script>(.*?)</script>', ...)`
   regex-szel keresi a kiemelendő inline scriptet — ez literálisan
   `<script>`-et vár, attribútum nélkül, tehát `type="module"` után
   **nem találna semmit** (néma lefedettség-vesztés, nem hibázna). A
   regexet úgy kell módosítani, hogy `<script type="module">`-t is
   felismerje, ÉS a kiírt temp fájl kiterjesztését `.mjs`-re kell
   váltani (`node --check` csak `.mjs` esetén — vagy ha van mellette
   `package.json` `"type":"module"`-lal — engedi az `import` szintaxist;
   a `/tmp` ide nem alkalmas, de a `.mjs` kiterjesztés package.json
   nélkül is működik). `node --check` csak szintaxist ellenőriz, a
   relatív `import './api/api-client.js'` útvonal fel-nem-oldása ezért
   nem gond.
5. Az új `python-processor/static/api/api-client.js` fájlt fel kell
   venni a `js_syntax_targets` tömbbe is (mint a többi külső statikus
   JS fájlt) — ez a (3) pont miatti package.json-nal már helyesen
   ESM-ként lesz ellenőrizve.
6. `tests/frontend/test_ui_static.py`-ban **4 darab** literál
   endpoint-substring assert ma az `index.html` tartalmára megy, és
   ezek a hívások az `api-client.js`-be költöznek:
   `"/api/wifi/devices" in html`, `"/api/wifi/security-events" in
   html`, `"/api/import/kismet/alerts" in html`,
   `"/api/bluetooth/devices" in html` (lásd a fájl ~85-88. sorát). Ezeket
   át kell írni úgy, hogy az `api-client.js` tartalmát ellenőrizzék —
   pontosan úgy, ahogy a CSS-kiemelés után a CSS-tartalmú assertek az
   `app.css`-re kerültek át. A negatív assertek
   (`"/api/wifi/observations?measurement_session_id" not in html` stb.)
   nem érintettek, marad `html`-en.

Ez a döntés precedens lesz a hátralévő `state/*` és `controllers/*`
modulokra is: mindegyik valódi `export`/`import`-ot fog használni, a
fő script importálja őket, és csak a `system-tabs.js`/`rag.js`-szel
való érintkezési pontoknál kell hasonló bridge-et mérlegelni (eddig
csak a fenti kettő azonosítónál van ilyen érintkezés).

### Elkészült: api-client.js kiemelés (2026-06-24, folytatás 2)

A fenti checklist mind a 8 pontja végrehajtva, módosítatlan üzleti
logikával:

- `python-processor/static/api/package.json` (`{"type":"module"}`) —
  **fontos eltérés a tervhez képest**: NEM a `static/` gyökerébe
  került, hanem az `api/` alkönyvtárba. Node a `package.json`
  `"type"` mezőjét a fájltól felfelé haladva a *legközelebbi*
  találatból olvassa ki, és ez minden `require()`/`import`
  betöltésre érvényes, nem csak a `node --check`-re. Az első próbálkozás
  (`static/package.json`) ezt félreértette: a 4 már korábban kiemelt
  UMD modult (`demod-passband.js`, `maxhold-controller.js`,
  `spectrum-frame-adapter.js`+`spectrum-view-model.js`,
  `viewport-controller.js`) a `tests/frontend/test_*.js` fixture-ök
  `require()`-rel töltik be; ESM-ként újraértelmezve a `typeof module
  === 'object'` UMD-guard csendben hamis lett (ESM-ben nincs `module`
  globális), a `require()` pedig (Node 24 natív `require(esm)`
  támogatásával) nem dobott hibát, csak egy üres namespace objektumot
  adott vissza → mind a 4 fixture elszállt (`X.createState is not a
  function` jellegű hibákkal). Ezt az `scripts/offline-acceptance.sh`
  teljes futtatása fogta meg. Megoldás: a `package.json`-t az `api/`
  alkönyvtárba mozgatva a hatókör csak az `api-client.js`-re szűkül,
  a szülő `static/` könyvtárban lévő fájlok visszaállnak az
  alapértelmezett CommonJS-interpretációra — ez a böngészőt nem
  érinti (ott a `<script type="module">` attribútum dönt), és a 4
  UMD fixture újra zöld.
- `python-processor/static/api/api-client.js` — 46 exportált
  függvény, namespace importtal hívva (`import * as apiClient from
  './api/api-client.js'`) a névkollíziók elkerülésére (több call
  site-beli wrapper-függvény neve, pl. `saveDeviceBaseline`,
  `startSdrangelDemod`, egyezik azzal, amit egy névvel ellátott export
  kapott volna). 3 függvényt (`fetchKismetStatus`, `fetchDetections`,
  `fetchReferenceSetMeta`) két különböző call site is használja,
  ezért 46 függvény fedi le mind a 49 eredeti `fetch(` előfordulást —
  ez szándékos konszolidáció, nem hiányosság.
- **Szándékos egyszerűsítés a korábbi tervhez képest**: nincs
  `ApiError` osztály, és a függvények nem parse-olják a JSON-t —
  mindegyik pontosan a `fetch(url, init)`-et helyettesíti, és a nyers
  `Promise<Response>`-t adja vissza. Indok: a call site-ok rendkívül
  vegyesek (van, ami `res.ok`-ot néz `.json()` előtt, van, ami után;
  van, ami soha nem hív `.json()`-t, pl. `archiveMarker`/`deleteMarker`
  DELETE — itt egy kényszerített JSON-parse a megosztott helperben
  egy 204-es üres body esetén ÚJ kivételt dobott volna, ahol korábban
  nem volt hiba). A `viselkedésmegőrző` elv elsőbbséget kapott a
  tervrajz szó szerinti megvalósításával szemben; minden válasz-
  kezelési/hibaüzenet-logika változatlanul az `index.html`-ben maradt.
- Fő `<script>` → `<script type="module">`, `import * as apiClient
  ...` a tetején, mind a 49 call site átírva (`grep -c
  "apiClient\."` → 48 sor / 49 előfordulás, megegyezik az eredeti
  leltárral).
- `window.toastMsg` / `window.openOperationModal` bridge bevezetve a
  `system-tabs.js` classic script-függőség miatt.
- `tests/frontend/test_ui_static.py`: `_parse_static_ui()` mostantól
  az `api-client.js`-t is visszaadja; a 4 endpoint-substring assert
  (`/api/wifi/devices`, `/api/wifi/security-events`,
  `/api/import/kismet/alerts`, `/api/bluetooth/devices`) áthelyezve
  `html`-ről `api_client`-re. A negatív assertek változatlanul
  `html`-en futnak.
- `scripts/offline-acceptance.sh`: az inline JS syntax check regexje
  felismeri a `<script type="module">`-t is, a temp fájl kiterjesztése
  `.mjs`-re váltott, `api-client.js` bekerült a `js_syntax_targets`
  tömbbe.

### Verifikáció (2026-06-24, folytatás 2)

- `node --check` mind az új, mind a meglévő statikus JS fájlokon: PASS.
- `python -m pytest -q` (system Python, nincs verzióeltérés-probléma
  ebben a futásban): **132 passed, 8 deselected** — megegyezik a
  Fázis 0 baseline-nal.
- `scripts/offline-acceptance.sh`: **0 FAIL, 2 WARN** (`coverage` és
  `ruff` nincs telepítve a system Pythonban — ugyanaz a 2 ismert
  hiányosság, mint Fázis 0-ban). Ez a futás fogta meg és igazolta a
  fenti `package.json`-elhelyezési hibát, majd a javítás után tisztán
  ment át.
- Élő böngészős smoke teszt: a korábbi session Node+Playwright
  harness-e nem perzisztens, újra kellett építeni. `npm` nem volt
  elérhető ebben a sandboxban (csak bare `nodejs`), ezért a Python
  `playwright` csomagra váltottam (ugyanaz a Chromium motor, nincs
  npm-függés) — scratch venv + `pip install playwright && playwright
  install chromium`. Demo-mód uvicorn (`APP_MODE=demo
  AUTH_MODE=disabled`, `DATABASE_URL` nélkül) + mind a 8 tab
  átkattintva: **SMOKE PASS: zero JS errors across all tabs.**
  Szerveroldali 500/503 zaj van (`/app/recordings` mkdir
  `PermissionError` — a sandboxban nem írható abszolút útvonal, és
  DB nélküli 503-ak), de ezek nem `pageerror`-ok, a frontend a meglévő
  catch-ágaiban kezeli őket, ahogy korábban is.
- Megvizsgált és igazolt, nem hiba: az `import './api/api-client.js'`
  relatív specifier `/index.html`-hez viszonyítva `/api/api-client.js`
  URL-re oldódik fel, ami egybeesik a backend REST namespace-ének
  `/api/` prefixével. Production-ban (`nginx/default.conf`) a
  `location /api/ { proxy_pass http://backend:8000/api/; }` szabály
  ezt a kérést a `backend` konténerhez irányítja, NEM a statikus
  fájlokat kiszolgáló külön `frontend` (nginx + `docker/frontend/
  Dockerfile`) konténerhez. Ez működik, mert a FastAPI backend saját
  maga is felmountolja a `static/` mappát a `/`-re fallbackként
  (`app/application.py:158`, `app.mount("/", StaticFiles(...))`),
  ami megelőzte ezt a sessiont — tehát mind a kettő konténer (saját
  fallback-mount a backendben, illetve a külön frontend konténer)
  ugyanazt a fájlt szolgálja ki ugyanarról a relatív útvonalról. Nem
  igényelt módosítást, de érdemes számon tartani: ha ez a fallback
  mount valaha eltávolításra kerülne a backendből, az `api/` alkönyvtár
  nevét érdemes lenne megváltoztatni, hogy ne essen egybe a `/api/`
  REST-prefixszel.

### Következő lépés (Fázis 1 folytatása: state/* és controllers/* modulok)

Az `api-client.js` kiemelés lezárva. A megmaradt inline script
(~3400 sor) még tartalmazza a state-kezelést (`viewMin`/`mode`/
`cursor`/`drag`/`activeMeasurementSession`/`staticReference`/stb.) és
az 5 controller-szerű felelősséget (session, spektrum-rajzolás,
Wi-Fi/Bluetooth panel, reference-sets, SDRangel/demod). A korábbi
döntés (valódi ES modul + window-bridge a `toastMsg`/
`openOperationModal`-hoz) ezekre is érvényes precedens. Ezt a
darabolást a jelen session nem kezdte el.

### Darabolási stratégia döntés (2026-06-24, Opus 4.8) – inkrementális, precedens-követő

Felhasználói döntés (Opusra váltva, megkérdezve, jóváhagyva): **nem** a
prompt szó szerinti „3 store + 5 controller" struktúráját erőltetjük rá
egyszerre, hanem a már bevált, tesztelt `spectrum-view-model.js` /
`demod-passband.js` precedenst követjük: tiszta, DOM-mentes logikát és
önálló render-klasztereket emelünk ki ES-modulokba, amelyek a state-et
**argumentumban kapják**; a megosztott mutable view-state és az
orchestration az `index.html`-ben marad. Ahol a state-nek tényleg a
logikájával kell laknia, ott mutált-property objektum-store lesz (nem
primitív `let`, mert az ES-modul import binding read-only az importáló
oldalon – `viewMin = x` egy importált bindingre dobna). Egyszerre EGY
szelet, közte élő verifikációval.

**Indok a literál „store-first" helyett:** a ~181 függvény ~40
modul-szintű `let`-et ír/olvas közvetlen azonosítóként (a rajzoló forró
út is: `drawSpectrum`/`drawMarkers` olvassa `viewMin`/`currentSpectrumFrame`/
`referenceSweep`/`cursor`/`drag`-et és írja `visiblePeak`/`maxPeak`-et).
A primitív állapot store-ba mozgatása minden hivatkozás átírását
igényelné (`viewMin` → `view.min`), ami pont a terv 7. szabálya
(„ne használj globális search/replace refaktort ellenőrzés nélkül")
ellen menne, nagy regressziós kockázattal a rajzoló úton.

### Elkészült: 1. szelet – observation-format.js (tiszta formázó-helperek)

A legkockázatmentesebb, mindkét stratégia alatt értékes első szelet: a
Wi-Fi/Bluetooth eszközmegfigyelési táblázatok tiszta (DOM-mentes,
state-mentes) formázó-/adatkinyerő-helperei kiemelve.

- Új fájl: `python-processor/static/ui/observation-format.js` (valódi ES
  modul, `export`) + `python-processor/static/ui/package.json`
  (`{"type":"module"}`, az `api/`-nál tanult scoping-szabály szerint, hogy
  a `node --check` ESM-ként kezelje, a szülő `static/` UMD-fájljait nem
  érintve).
- Kiemelt függvények (12 db, testük **szó szerint változatlan** – egy
  line-precíz Python splice + bájtra-egyező verifikációval mozgatva):
  `firstFiniteNumber`, `observationRawPayload`, `rawKismetSignal`,
  `formatRssiSummary`, `formatAge`, `formatRiskSummary`,
  `formatManagementSummary`, `formatServiceSummary`, `formatExactTime`,
  `formatReferenceStatus` (+`REFERENCE_STATUS_GLYPHS` const),
  `referenceRowClass`, és a `formatUnknownStatus`.
- **Holt kód megőrizve, nem törölve:** a `formatUnknownStatus` már a
  kiemelés előtt is használaton kívüli volt az `index.html`-ben (0 hívási
  hely, csak definíció). Viselkedésmegőrző módon változatlanul áthelyezve
  és exportálva (a tesztben lefedve), nem törölve – a holtkód-eltávolítás
  külön, explicit döntés tárgya.
- **Named import, zéró call-site churn:** az `index.html` namespace-prefix
  helyett `import { ... } from './ui/observation-format.js'`-t használ, így
  a hívási helyek bájtra azonosak maradtak; az `index.html` egyetlen
  változása az import sor + a 12 definíció törlése (3858 → 3757 sor).
  A 11 ténylegesen hívott név importálva; a két modul-belső
  (`formatUnknownStatus` holt, `REFERENCE_STATUS_GLYPHS` csak a
  `formatReferenceStatus` használja) nincs importálva.
- Ellenőrizve: e nevek sehol máshol nem szerepelnek (sem
  `system-tabs.js`/`rag.js` classic scriptben – nincs szükség
  window-bridge-re –, sem más fájlban), így a kiemelés zárt.
- Új unit teszt: `tests/frontend/test_observation_format.js` (49
  assertion, a meglévő `require()`-alapú fixture-stílusban; a Node 24
  `require(esm)` támogatásával tölti be az ES modult). Felvéve a
  `scripts/offline-acceptance.sh` `js_syntax_targets` tömbjébe és a
  futtatási listába is.
- `tests/frontend/test_ui_static.py`: `_parse_static_ui()` mostantól az
  `observation-format.js` tartalmát is visszaadja; a `formatReferenceStatus`
  definíciós assert áthelyezve `html`-ről a modul tartalmára
  (`"export function formatReferenceStatus" in observation_format`). A
  többi bare-substring assert (`"formatRssiSummary" in html` stb.)
  változatlan – ezek a megmaradt hívási helyek / import-lista miatt
  továbbra is igazak.

**Verifikáció (mind PASS):** `node --check` a modulon és az inline
scripten; az új unit teszt (49 assertion); `scripts/offline-acceptance.sh`
(0 FAIL, 2 ismert WARN: coverage/ruff nincs telepítve); teljes
`pytest -q` (132 passed, 8 deselected); élő Playwright smoke mind a 8
tabon (zero pageerror – ez egyúttal bizonyítja, hogy mind a 11 named
import feloldódik, különben a modul betöltéskor dobna). A modul
kiszolgálása élőben ellenőrizve: `GET /ui/observation-format.js` → 200,
`text/javascript`.

### Elkészült: 2. szelet – html.js (megosztott escapeHtml util)

A view-modulok közös előfeltétele: az `escapeHtml` (79 használat az
`index.html`-ben, tiszta, classic scriptek NEM használják) kiemelve egy
önálló, megosztott util-modulba. Külön, minimális szeletként – mert ez a
zéró-kockázatú, szó szerinti + named-import mozgatás (bevált precedens),
és minden jövőbeli view-modul (eszközmegfigyelési táblázatok,
spektrum-popover, retention) erre épül; külön tartva a diff tiszta és
függetlenül verifikálható marad, mielőtt a magasabb kockázatú
render-klaszter (3. szelet, függvénytest-átírással) jön.

- Új fájl: `python-processor/static/ui/html.js` (`export function
  escapeHtml`, test szó szerint változatlan); a `ui/package.json`
  (1. szeletből) már ESM-ként kezeli.
- `index.html`: új `import { escapeHtml } from './ui/html.js';` sor, a
  definíció törölve; a 78 hívási hely **bájtra azonos** (named import).
- Új unit teszt: `tests/frontend/test_html_util.js` (9 assertion),
  felvéve a `js_syntax_targets`-be és a futtatási listába.
- `test_ui_static.py` nem érintett (nem volt `escapeHtml`-definíciós
  assert benne).
- **Verifikáció (mind PASS):** `node --check` (modul + inline);
  `test_html_util.js` (9 assertion); `offline-acceptance.sh` (0 FAIL);
  teljes `pytest` (132 passed); élő Playwright smoke mind a 8 tabon
  (zero pageerror); `GET /ui/html.js` → 200.

### Elkészült: 3. szelet – device-observation-view.js (Wi-Fi/BT render-klaszter, pure/impure split)

Az első NEM-szó-szerinti szelet: a Wi-Fi/Bluetooth render-függvények
pure/impure szétválasztása. A magasabb kockázat miatt a HTML-építő
template literálokat **script-alapú verbatim kiemeléssel** mozgattam (a
map-callback testek bájtra azonosak az eredetivel, assertálva), így a
kimenet konstrukcióból adódóan változatlan.

- Új fájl: `python-processor/static/ui/device-observation-view.js` – 7
  tiszta HTML-string-építő: `referenceSummaryHtml`,
  `deviceReferenceDetailsHtml`, `missingReferenceDevicesHtml`,
  `detectionRowsHtml`, `wifiObservationsHtml`, `wifiSecurityEventsHtml`,
  `bluetoothObservationsHtml`. Importálja az `escapeHtml`-t (html.js) és a
  11 format-helpert (observation-format.js); a `WIFI_DETAIL_FIELDS` stb.
  detail-konstansok ide, modul-privátként költöztek.
- `index.html`: a 7 render-függvény **vékony wrapperré** vált – a DOM-írás
  (`*.innerHTML = builder(...)`), a state-Map-ek (`wifiItemsByIdentity`/
  `bluetoothItemsByIdentity`) és a click-listenerek az `index.html`-ben
  maradtak; a `renderReferenceSummary` továbbra is itt köti be a
  toggle-listenert a kiemelt `referenceSummaryHtml` köré. Az
  `openDetailDialog`/`toastMsg`/`detailDialog` primitívek érintetlenek.
- **Dead import takarítás:** a 3. szelet után a 11 observation-format
  helper egyetlen hívási helye sem maradt az `index.html`-ben (mind a
  view-modulba költözött, ami közvetlenül importálja őket), ezért az
  `index.html` observation-format importja törölve (a `html.js`
  escapeHtml import marad: 22 hívási hely). `index.html`: 3757 → 3634 sor.
- Új unit teszt: `tests/frontend/test_device_observation_view.js` (32
  assertion – üres állapotok pontos stringként, egy-elemű sorok, XSS-escape,
  kv-diff/baseline-osztály jelölés, reference-summary darabszámok).
- `test_ui_static.py`: `_parse_static_ui()` mostantól a
  `device-observation-view.js`-t is olvassa; a moved formatter-asserteket
  (`formatRssiSummary`/`formatAge`/`formatExactTime`/`formatRiskSummary`/
  `formatManagementSummary`/`formatServiceSummary`) `observation_format`-ra,
  a moved mező-asserteket (`previous_signal_dbm`/`previous_rssi_dbm`)
  `device_observation_view`-ra helyeztem át; a statikus `<tbody>`
  üres-állapot markup és a wrapper-függvénynevek (`renderReferenceSummary`/
  `showMissingReferenceDevices`/`openDeviceReferenceDetails`) asszertjei
  `html`-en maradtak (változatlanul igazak).
- **Verifikáció (mind PASS):** `node --check` (modul + inline);
  `test_device_observation_view.js` (32 assertion); `offline-acceptance.sh`
  (0 FAIL); teljes `pytest` (132 passed); élő Playwright smoke mind a 8
  tabon (zero pageerror); **plusz élő böngészős data-path ellenőrzés**:
  dinamikus `import('/ui/device-observation-view.js')` valós Chromiumban,
  a builderek valós adattal renderelve (wifi 2437 MHz + escape +
  row-baseline-new, bt service-uuid + row-baseline-changed, detail kv-table
  + match meta) – ez kizárja a Node-`require()` vs. böngésző-ESM eltérést.
  `GET /ui/device-observation-view.js` → 200.

### Mellékesen javítva: migrate konténer exec-bit (2026-06-24)

A `scripts/run-migrations.sh` a munkamenet elején elvesztette a futtatható
bitjét (`100755 → 100644`, working-tree drift). A `migrate` szolgáltatás
(compose.yaml) NEM-root `USER backend` (uid 10003) alatt, `read_only`
rootfs-szel, a bind-mountolt scriptet közvetlenül **entrypoint**-ként
futtatja – exec-bit nélkül „permission denied". Visszaállítva 755-re
(`git` 100755-ként követi, ezért checkout-stabil). A script a read_only fs
alatt is működik (mktemp a `/tmp` tmpfs-re, csak a ro `/migrations`-t
olvassa). Nincs image-rebuild igény, csak újrafuttatás (`docker compose up
migrate`).

### Elkészült: 4. szelet – spectrum-scale.js (konstansok + tiszta skála-math)

A „spektrum-tengely store" elemzése egy élesebb megállapítást hozott: a
`viewMin`/`viewMax` mutábilis nézet-ablaknak **egyetlen írója** van
(`setView`), és tisztán az `index.html` orchestrationjéhez kötött (a
`setView` hajtja az `updateReadouts`/`requestDraw`/`scheduleReferenceFetch`-et).
Objektum-store-rá alakítása 71 `viewMin`/`viewMax` hivatkozás átírását
jelentené a **rajzoló forró úton**, alacsony strukturális haszonért –
rossz kockázat/haszon arány. Ezt a részt **szándékosan elhalasztom** (lásd
lent), és helyette a benne rejlő alacsony-kockázatú, magas-értékű részt
emeltem ki.

- Új fájl: `python-processor/static/ui/spectrum-scale.js` – a 6 rögzített
  konstans (`FULL_MIN`, `FULL_MAX`, `NUM_BINS`, `DBM_MIN`, `DBM_MAX`,
  `MIN_SPAN`) és a 10 TISZTA, viewMin/viewMax-FÜGGETLEN segédfüggvény
  (`clamp`, `freqToBin`, `binToFreq`, `dbmToY`, `yToDbm`, `fullFreqToX`,
  `fullXToFreq`, `niceStep`, `formatFreq`, `formatSpan`). Definíciók szó
  szerint változatlanok, named importtal visszakötve → **zéró call-site
  churn** (a bevált 1–2. szeletes minta).
- **STAY az index.html-ben** (viewMin/viewMax-függő, a nézet-ablakra
  épülnek): `span`, `center`, `freqToX`, `xToFreq`, `formatAxisFreq` – és
  maga a `viewMin`/`viewMax` + `setView`/`setCenterSpan`/`zoomAt`/`panBy`
  orchestration.
- `index.html`: 3634 → 3596 sor. A `clamp` (37 hívás), a konstansok és a
  formázók mind named importtal, érintetlen hívási helyekkel.
- A `clamp` ide került (a `freqToBin` használja); a `viewport-controller.js`
  és `demod-passband.js` saját, lokális `clamp`-et definiál, ezekre nincs
  hatás.
- Új unit teszt: `tests/frontend/test_spectrum_scale.js` (44 assertion –
  konstansok, clamp határok, freqToBin/binToFreq végpontok+clamp,
  dbmToY/yToDbm inverz, fullFreqToX/fullXToFreq, niceStep, formatFreq/Span).
- `test_ui_static.py`: `_parse_static_ui()` mostantól a `spectrum-scale.js`-t
  is olvassa; a `"const FULL_MIN = 0"`/`"const FULL_MAX = 24000"` assert
  áthelyezve `html`-ről `spectrum_scale`-re (`export const ...`).
- **Verifikáció (mind PASS):** `node --check`; a 44-assertion unit teszt;
  `offline-acceptance.sh` (0 FAIL); teljes `pytest` (132 passed); élő
  Playwright smoke mind a 8 tabon (zero pageerror); **plusz canvas-tartalom
  ellenőrzés**: demo módban a spektrum-canvas valós sweepeket rajzol, a
  `getImageData` 27 különböző színt mutat (nem üres) – ez funkcionálisan
  igazolja, hogy a kiemelt konstansok/transzformációk a rajzoló forró úton
  helyesen működnek. `GET /ui/spectrum-scale.js` → 200.

### Szándékosan elhalasztva: viewMin/viewMax objektum-store

A nézet-ablak (`viewMin`/`viewMax`) objektum-store-rá alakítása
(`view.min`/`view.max`) **nem** része ennek a munkának: 71 hivatkozás a
rajzoló forró úton, egyetlen író (`setView`), és a `setView` mély
orchestration-kötése (readout/draw/fetch + `toastMsg`) miatt a haszon
(modul-globális → objektum-property) nem indokolja a kockázatot. Ha mégis
megtörténik, precíz, scriptelt szó-határos csere + teljes tesztsor +
demo-canvas vizuális ellenőrzés mellett javasolt.

### Elkészült: 5. szelet – band-popover-view.js (popover HTML-építők)

A 3. szelethez hasonló pure/impure split a spektrum-sáv és NMHH popover
tartalmára.

- Új fájl: `python-processor/static/ui/band-popover-view.js` – 3 tiszta
  HTML-építő: `popRow`, `bandPopoverHtml`, `nmhhPopoverHtml` (template
  literálok script-alapú verbatim kiemeléssel, bájtra azonosak).
  Importálja az `escapeHtml`-t (html.js) és a `formatFreq`-et
  (spectrum-scale.js).
- `index.html`: a `showBandPopover`/`showNmhhPopover` vékony wrapperré vált
  (`bandPopover.innerHTML = bandPopoverHtml(band); placeBandPopover(...)`);
  a DOM-pozicionálás (`placeBandPopover`), a hide és a hit-test
  (`referenceBandAt`/`nmhhBandAt`) az `index.html`-ben maradtak. A `popRow`
  egyetlen hívója a két builder volt → modul-privát lett (nincs importálva
  vissza). A `formatFreq` továbbra is importált (14 hívási hely marad).
  `index.html`: 3596 → 3570 sor.
- Új unit teszt: `tests/frontend/test_band_popover_view.js` (18 assertion –
  popRow escape, band frekvencia-formázás/forrás-összefűzés/escape/default
  mezők, nmhh use-lista escape + üres placeholder).
- `test_ui_static.py` nem érintett (nem volt popover-tartalmú assert).
- **Verifikáció (mind PASS):** `node --check`; 18-assertion unit teszt;
  `offline-acceptance.sh` (0 FAIL); teljes `pytest` (132 passed); élő
  Playwright smoke (zero pageerror); **plusz élő böngészős data-path**:
  dinamikus `import('/ui/band-popover-view.js')` valós Chromiumban, a két
  builder valós sávval renderelve (frekvencia-formázás + escape) PASS.
  `GET /ui/band-popover-view.js` → 200.

### Összegzés – Fázis 1 frontend modularizáció státusza (5 szelet)

| Szelet | Modul | Jelleg | Unit assert |
|---|---|---|---|
| 1 | `ui/observation-format.js` (12 formázó) | verbatim | 49 |
| 2 | `ui/html.js` (`escapeHtml`) | verbatim | 9 |
| 3 | `ui/device-observation-view.js` (7 építő) | pure/impure split | 32 |
| 4 | `ui/spectrum-scale.js` (6 konst + 10 helper) | verbatim | 44 |
| 5 | `ui/band-popover-view.js` (3 építő) | pure/impure split | 18 |

`index.html`: a `b1abb31` commit óta a `<script>` ~288 sorral rövidebb. 5
ES-modul, 152 új unit assertion, mind a `node --check` + offline-acceptance
+ 132 pytest + élő Playwright (smoke + canvas-render + data-path) zöld. A
`viewMin`/`viewMax` store szándékosan elhalasztva (lásd fent).

### Következő lehetséges szeletek (sorrend még nyitott)

(a) a reference store (`referenceBands`/`referenceImages`/`nmhhBands` +
lekérő/rajzoló logika); (b) a session-controller
(`activeMeasurementSession`/`viewedSession` + `refreshMeasurementSession`/
`startMeasurementSession`/stb.); (c) opcionálisan az elhalasztott
viewMin/viewMax store, ha külön döntés születik róla.

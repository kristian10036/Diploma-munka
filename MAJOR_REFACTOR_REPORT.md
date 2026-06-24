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

### Következő lépés (megszakítva felhasználói kérésre — pontos folytatási checklist)

A munka **itt állt meg, kód még nem módosult** ebben a folytatott
sessionben (csak feltárás + a fenti döntés történt). A következő
sessionnek ebben a sorrendben kell haladnia:

1. `python-processor/static/package.json` létrehozása (`{"type":
   "module"}`).
2. `python-processor/static/api/api-client.js` megírása: `export class
   ApiError extends Error` (mezők: `status`, `payload`) + egy
   alacsony szintű, megosztott `request(url, init)` helper, ami
   elvégzi a fetch-et és a JSON parse-ot, majd **vagy** visszaadja
   `{response, payload}`-ot (ha a call site maga dönt `res.ok`
   alapján — ez a jelenlegi minták többségénél így van), **vagy**
   dob egy `ApiError`-t a call site által átadott fallback-szöveggel,
   a jelenlegi `payload.detail?.message || payload.detail ||
   fallback` mintázat egységesítésével. Minden fenti 49 call site-hoz
   egy dedikált, névvel ellátott export függvény (pl.
   `startSession(body)`, `stopSession(id)`, `fetchWifiDevices(params)`
   stb.) — a pontos lista a fenti táblázat.
3. Fő `<script>` tag → `type="module"`; `import {...} from
   './api/api-client.js';` a tetejére; mind a 49 fetch call site
   átírása az új függvényekre, a call site-specifikus magyar
   hibaüzenetek/fallback-ek és vezérlési logika **változatlanul**
   hagyva.
4. `window.toastMsg = toastMsg;` / `window.openOperationModal =
   openOperationModal;` bridge bevezetése.
5. `tests/frontend/test_ui_static.py` 4 assert-jének átírása
   `api-client.js`-re (lásd fent).
6. `scripts/offline-acceptance.sh`: regex `<script type="module">`
   felismerésre bővítése, temp fájl `.mjs` kiterjesztésre váltása,
   `api-client.js` felvétele a `js_syntax_targets` tömbbe.
7. Teljes ellenőrzés: `node --check` az új és módosított fájlokon,
   `tests/frontend/test_ui_static.py`, teljes `pytest`,
   `scripts/offline-acceptance.sh`, majd a meglévő Playwright
   smoke-harness (`pw/smoke.js`, lásd fent — scratch venv + Chromium
   újraindítása szükséges, ezek nem perzisztens állapotok) mind a 8
   tabra.
8. Jelentés + memória frissítése, commit.

A live-verifikációs harness (scratch venv + Playwright Chromium)
**nem perzisztens** — egy korábbi sessionben épült fel a
`/tmp/.../scratchpad`-ben, ami sessionek között elveszhet; a
folytatásnál újra kell építeni, ha már nincs ott (lásd a fenti
„Live-verifikációs infrastruktúra” szakasz pontos parancsait).

# REFACTOR_BASELINE.md — jelenlegi (szétbontás ELŐTTI) referencia-állapot

> Csak elemzés/futtatás, forrás nem módosult. `git status --porcelain` a
> futtatások előtt és után is tisztát mutatott a forrásfájlokra (csak ez a
> három `REFACTOR_*.md` jött létre). Rögzítve: 2026-06-25, HEAD `9cc8023`.

## 0. Környezet, amiben futtattam

- OS: Linux (Kali), shell: zsh.
- Python: **3.13.12**, pytest **9.0.3**.
- Node — **két különböző verzió van elérhető, ez kritikus a reprodukáláshoz:**
  - `nvm` alapértelmezett / `node` a PATH-on bash-indításkor: **v18.20.8**
    (`/home/kk/.config/nvm/versions/node/v18.20.8/bin/node`).
  - Rendszer Node (`/usr/bin/node`, apt `nodejs` pakettből): **v24.16.0**.
  - A repó `.nvmrc` **`24`**-et ír elő, és a `scripts/offline-acceptance.sh`
    pontosan ezért tartalmazza ezt a logikát (19–26. sor):
    ```
    if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
      . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
      nvm use --silent >/dev/null 2>&1 || nvm use system --silent >/dev/null 2>&1 || true
    fi
    ```
    Mivel a Node 24 NINCS telepítve nvm alá ebben a környezetben, az első
    `nvm use` hibázik, és a script a **`nvm use system`** ágra esik, ami
    a `/usr/bin/node` v24.16.0-t választja. **Tehát a script maga
    helyesen v24-re vált**, de ha valaki kézzel, a script futtatása
    nélkül, sima `node ...`-tal próbál tesztelni egy friss shellben,
    csendben a hibás v18.20.8-at kapja.
  - **Bizonyított hatás (ld. 2. pont):** 7 db `tests/frontend/*.js` fixture
    `require()`-rel tölt be `python-processor/static/ui/*.js` ESM
    modulokat (azok package.json-ja `"type":"module"`) — ez Node 18 alatt
    `ERR_REQUIRE_ESM`-mel elhasal, Node 24 alatt simán lefut. **Ez egy
    MEGLÉVŐ, a szétbontástól független környezeti csapda**, nem a mai
    munka okozta — de a holnapi végrehajtónak tudnia kell róla, különben
    feleslegesen a saját kódváltozására gyanakodna.
  - Minden alábbi futtatást a helyes (`nvm use --silent || nvm use system
    --silent`) váltás UTÁN, Node **v24.16.0**-val végeztem el, hogy a
    valódi "zöld most" állapotot rögzítsem.

## 1. `node --check` — szintaxis-ellenőrzés

Az `offline-acceptance.sh` `js_syntax_targets` tömbjében szereplő összes
fájlra (15 statikus modul + 12 teszt-fixture), egyetlen `node --check`
hívásban:

```
node --check \
  python-processor/static/api/api-client.js \
  python-processor/static/demod-passband.js \
  python-processor/static/maxhold-controller.js \
  python-processor/static/rag.js \
  python-processor/static/spectrum-frame-adapter.js \
  python-processor/static/spectrum-view-model.js \
  python-processor/static/system-tabs.js \
  python-processor/static/ui/band-popover-view.js \
  python-processor/static/ui/canvas-util.js \
  python-processor/static/ui/device-observation-view.js \
  python-processor/static/ui/html.js \
  python-processor/static/ui/observation-format.js \
  python-processor/static/ui/spectrum-data.js \
  python-processor/static/ui/spectrum-scale.js \
  python-processor/static/viewport-controller.js \
  tests/frontend/test_*.js   # mind a 12
```

**Eredmény: EXIT 0, nincs kimenet (nincs hiba).** ✅ Ez Node 18.20.8 alatt
IS lefut hiba nélkül (a `node --check` csak parse-ol, nem futtat
`require()`-t, ezért az ESM/CJS interop-probléma itt nem jön elő).

## 2. Inline `<script>` szintaxis-ellenőrzés (offline-acceptance.sh minta)

Az `offline-acceptance.sh` 101–109. sorában lévő Python snippet pontos
megismétlése: az `index.html` minden `<script>` / `<script type="module">`
blokkját kivonja (a `src`-attribútumos `<script src="...">` tag-eket a
regex NEM találja meg, csak az inline tartalmút), ideiglenes `.mjs`
fájlba írja, és `node --check`-eli.

```
talált <script> blokk (src nélküli): 1
blokk #0: 3162 sor, node --check exit=0
```

**Eredmény: a 3162 soros inline ES modul jelenleg szintaktikailag hibátlan.** ✅
(A `1` darabszám helyes: a fejben/végén lévő összes `<script src="...">`
tag-et — a 6 db globálisra kötő modult, a `system-tabs.js`-t és a
`rag.js`-t — a regex kihagyja, mert azoknak nincs inline tartalmuk.)

## 3. `tests/frontend/*.js` fixture-ök egyenként, Node v24.16.0-val

| Teszt | Eredmény | Részlet |
|---|---|---|
| `test_band_popover_view.js` | ✅ PASS | `band popover view: PASS (18 assertions)` |
| `test_canvas_util.js` | ✅ PASS | `canvas util: PASS (18 assertions)` |
| `test_demod_passband.js` | ✅ PASS | `demod passband module: PASS (35 assertions)` |
| `test_device_observation_view.js` | ✅ PASS | `device observation view: PASS (32 assertions)` |
| `test_html_util.js` | ✅ PASS | `html escape util: PASS (9 assertions)` |
| `test_maxhold_controller.js` | ✅ PASS | `maxhold controller: PASS` |
| `test_observation_format.js` | ✅ PASS | `observation format helpers: PASS (49 assertions)` |
| `test_spectrum_data.js` | ✅ PASS | `spectrum data: PASS (15 assertions)` |
| `test_spectrum_model.js` | ✅ PASS | `spectrum frame/view model: PASS` |
| `test_spectrum_scale.js` | ✅ PASS | `spectrum scale: PASS (47 assertions)` |
| `test_viewport_controller.js` | ✅ PASS | `viewport controller: PASS` |
| `test_viewport_wiring.js` | ✅ PASS | `viewport wiring integration: PASS` |

**12/12 zöld, mind exit code 0.**

Ugyanezen 7 fixture (`test_band_popover_view`, `test_canvas_util`,
`test_device_observation_view`, `test_html_util`, `test_observation_format`,
`test_spectrum_data`, `test_spectrum_scale`) **Node v18.20.8 alatt**
`ERR_REQUIRE_ESM`-mel elhasal (`require()` natívan nem tud ESM-et
betölteni Node 18-on) — ezt külön is lefuttattam, dokumentálva a 0. pont
alatt, csak hogy a csapda reprodukálható legyen, ha valaki véletlenül a
rossz Node-dal próbálkozik. A maradék 5 (`test_demod_passband`,
`test_maxhold_controller`, `test_spectrum_model`, `test_viewport_controller`,
`test_viewport_wiring`) `require()`-rel UMD-wrappelt (nem ESM) fájlokat tölt
be a `python-processor/static/` gyökérből, ezért Node-verziófüggetlenül
lefutnak.

## 4. `tests/frontend/test_ui_static.py` (pytest)

```
PYTHONPATH=python-processor python -m pytest -q tests/frontend/test_ui_static.py
.                                                                        [100%]
1 passed in 0.02s
```

**Eredmény: 1/1 PASS.** ✅ Ez a teszt — ahogy a `REFACTOR_CUTMAP.md` 3.
pontja részletezi — **literális szövegillesztéssel** ellenőrzi az
`index.html` tartalmát (nem csak markupot, hanem konkrét JS-kulcsszavakat
és függvényneveket is, pl. `"function setViewedSession" in html`). Ez
**MA zöld**, de a jellegéből adódóan ez lesz az első teszt, amely
**hamis pirosra vált** a holnapi kivágás során, méghozzá NEM azért, mert
valami elromlik, hanem mert a szöveg, amit keres, fizikailag másik
fájlba kerül. Lásd `REFACTOR_CUTMAP.md` 3. pontjának táblázatát a pontos
sorhivatkozásokkal.

## 5. Mit NEM fed le automatizált teszt — ezeket kézzel kell ellenőrizni a kivágás után

A repóban **nincs becsekkelt böngésző-szintű (DOM/canvas) automatizált
teszt** (nincs Playwright/Puppeteer/jsdom/Cypress/Selenium konfiguráció
vagy tesztfájl a repóban; a `.claude/settings.local.json` engedélylistájában
látható Playwright-/Puppeteer-hivatkozás korábbi, ad hoc, kézi
ellenőrzési munkamenetekből származik, nem a repó tesztkészletéből).
Emiatt a következő viselkedéseket a jelenlegi tesztfutás **egyáltalán nem
fedi le** — ezek mind a `index.html` inline kódjában élnek, és csak
böngészőben (vagy a `/run`, `/verify` skillekkel) ellenőrizhetők manuálisan
a holnapi szétbontás UTÁN, modulonként:

1. **Tényleges canvas-rajzolás** — `drawAll`/`drawSpectrum`/`drawWaterfall`/
   `drawOverview`/`drawDemodPassband`/`drawMarkers`/`drawCursorAndSelection`/
   `drawReferenceBands`/`drawNmhhBands`. A `test_canvas_util.js` csak a
   `ui/canvas-util.js` SEGÉDFÜGGVÉNYEIT (`inPlot`,`roundRect`,`dbmToColor`)
   teszteli, nem a tényleges Canvas2D kimenetet.
2. **WebSocket-kezelés végponttól-végpontig** — `connectWS`/`onmessage`/
   `onclose`/újracsatlakozás, `fallbackToDemo`/`startDemo` demo-hurok. Nincs
   szimulált WS szerver teszt ehhez a kódhoz.
3. **Egér-/billentyű-interakció maga az `index.html`-ben** — drag/pan/zoom/
   select/marker/demod-passband egérkezelők, context-menü, billentyű-
   parancsok. A `test_viewport_wiring.js` egy MINTÁT (debounce, begin/end
   interaction, observeFrame staleness) szimulál egy fake harness-szel a
   valódi `ViewportController.Controller`-rel — NEM importálja és NEM
   futtatja az `index.html` tényleges DOM-event listenereit.
4. **Session-életciklus UI** — session indítás/leállítás/felfedezés/
   korábbi megnyitás, Wi-Fi/Bluetooth panel frissítés, device-baseline
   mentés/összehasonlítás/deaktiválás, Kismet live/alert import. Az
   `ui/device-observation-view.js` HTML-generáló segédfüggvényei
   tesztelve vannak (`test_device_observation_view.js`), de az ezeket
   hívó orchestrátor-kód (`refreshWifiPanel`, `refreshBluetoothPanel`,
   `startMeasurementSession`, stb.) nincs.
5. **Referencia-kezelés UI-folyama** — pillanatkép/Max Hold rögzítés, DB
   referencia mentés/betöltés/export, `localStorage` import.
6. **SDRangel demoduláció indítás/leállítás + böngészőhang lejátszás** —
   Web Audio API, `AudioContext`, bináris PCM WebSocket stream. Hardver-
   és böngésző-API-függő, nem unit-tesztelhető Node alatt.
7. **Adatkarbantartás (retention) előnézet/törlés UI-folyam.**
8. **Panel összecsukás/kibontás perzisztencia** (`localStorage` round-trip
   a `spectrumControlPanelCollapsed`/`waterfallPanelCollapsed` kulcsokkal).
9. **Tab-váltás (`activateTab`) és a két `setInterval`** (stale-figyelő,
   5 másodperces periodikus `refreshActiveDataTab`).
10. **Marker/ismert jel CRUD UI-folyama** (`saveMarkerAt`,
    `saveKnownSignalAt`, `editMarker`, `archiveMarker`, stb.).
11. **A demod-passband egér-hitbox és kétirányú szinkron GLUE kódja**
    (`demodHitAt`, `handleDemodMouseDown`/`Move`, `syncDemodStateToPanel`/
    `syncPanelToDemodState`) — a `test_demod_passband.js` a TISZTA logikát
    (`demod-passband.js`: `computePixelGeometry`, `hitTestPassband`, stb.)
    teszteli, nem az `index.html`-ben élő bekötést.

## 6. Összefoglalás — a holnapi végrehajtás sorrendje és a top 3 kockázat

**Javasolt sorrend (a `REFACTOR_CUTMAP.md` részletes indoklásával):**

1. `view-state.js` kiemelése elsőként (ezen áll majd minden más modul —
   nem önálló kivágás, hanem előfeltétel).
2. `viewport-glue.js` — a feladat által is jelzett legönállóbb egység;
   figyelni kell a `window.refreshRfAgentCapabilities` explicit
   globális-export megtartására (`system-tabs.js` rá támaszkodik).
3. `retention.js` és `sdrangel-audio.js` — alacsony kockázatú, egyirányú
   függésű egységek, jó "bemelegítés" a nehezebbek előtt.
4. `source-status.js`, `entities.js`, `panel-toggles.js` — közepes
   kockázat, kevés és jól látható külső függéssel.
5. `spectrum-render.js` + `demod-glue.js` EGYÜTT (a köztük lévő
   körfüggés miatt egyszerre kell mozgatni, ld. CUTMAP 2.2–2.3), majd
   `interaction.js` (a demod-glue-val való harmadik körfüggés miatt
   ugyanebben a körben).
6. `ws-ingest.js` (a `spectrum-render.js`/`demod-glue.js` már a helyén
   van, ezért most már csak egyirányú importokkal megoldható).
7. `spectrum-reference.js` és `session-and-data-tabs.js` UTOLJÁRA,
   EGYÜTT, és EBBEN a körben kell frissíteni a
   `tests/frontend/test_ui_static.py` 12 érintett szövegillesztését is
   (ld. CUTMAP 3. pont) — ezt a kört NEM lehet "csak mozgatás"-ként
   kezelni, mert ismert, tervezett tesztváltozással jár.

**Top 3 kockázat:**

1. **A `selectedReferenceSetId` körfüggés** (`spectrum-reference.js` ↔
   `session-and-data-tabs.js`) — ha ezt nem oldjuk fel egy neutrális
   megosztott állapottal/eseménnyel ELŐRE, a két modult gyakorlatilag
   lehetetlen lesz egymástól függetlenül kivágni anélkül, hogy az egyik
   a másikat azonnal vissza-importálja.
2. **Néma (hibaüzenet nélküli) viselkedésvesztés a `maxHoldEnabled`/
   `waterfallBuffer`/`overviewAccumulator` keresztmodul-íráson** — ezek
   olyan esetek, ahol egy másik modul KÖZVETLENÜL ír egy állapotot, amit
   nem ő birtokol (pl. `setView`/`resizeAll` nullázza a
   `waterfallBuffer`-t). Ha a kivágás után ez csak export-import lesz
   ahelyett, hogy egy explicit függvényhívássá válna, a fordító/`node
   --check` NEM jelez hibát, csak futásidőben, böngészőben látható meg a
   hibás viselkedés (pl. a vízesés nem törlődik nézetváltáskor) — ezért
   ez kifejezetten a 5. pontban felsorolt MANUÁLIS ellenőrzést igényli.
3. **`tests/frontend/test_ui_static.py` 12 literális szövegillesztése** —
   ezek ma zöldek, és automatikusan, MAGUKTÓL pirosra váltanak, amint a
   `session-and-data-tabs.js`/`sdrangel-audio.js`/`panel-toggles.js`/
   `loadRuntimePolicy` kód kikerül `index.html`-ből, FÜGGETLENÜL attól,
   hogy a funkcionalitás helyesen működik-e. Ezt ELŐRE be kell tervezni
   (a teszt frissítése ugyanabban a commit-ban, amelyik a kivágást
   végzi), különben a holnapi CI/offline-acceptance lépés hamis riasztást
   ad egy egyébként helyes refaktorra.

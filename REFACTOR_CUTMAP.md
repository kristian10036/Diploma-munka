# REFACTOR_CUTMAP.md — index.html inline modul szétbontási terve

> Csak elemzés. Semmilyen forrásfájl nem módosult ennek a dokumentumnak az
> elkészítése során. Minden sorszám a `python-processor/static/index.html`
> jelenlegi állapotára vonatkozik (2026-06-25, `git status` clean, HEAD
> `9cc8023`).

## 0. Alapadatok

- `index.html` teljes hossza: **3560 sor**.
- Inline `<script type="module">` blokk: **394–3556** (`</script>` a 3556.
  sorban) → **3163 sor**, ez a bontandó kód.
- A `<head>`-ben (10–14. sor) és a `</body>` előtt (3557–3558. sor) már most
  is külön fájlból töltött, globálisra kötő (UMD-szerű) modulok futnak, ebben
  a sorrendben:
  1. `spectrum-frame-adapter.js` → `window.SpectrumFrameAdapter`
  2. `spectrum-view-model.js` → `window.SpectrumViewModel`
  3. `maxhold-controller.js` → `window.MaxHoldController`
  4. `demod-passband.js` → `window.DemodPassband`
  5. `viewport-controller.js` → `window.ViewportController`
  6. *(inline modul, type="module")*
  7. `system-tabs.js` (sima script, **a `window.toastMsg`,
     `window.openOperationModal`, `window.refreshRfAgentCapabilities`
     globálisra támaszkodik** — ld. 4. pont)
  8. `rag.js` (sima script, nem nyúl az inline modul globáljaihoz)
- Az inline modul már ma is importál kész, tisztán logikai ES modulokat:
  `api/api-client.js` (44 export, REST hívások), és a `ui/` alatt
  `html.js`, `spectrum-scale.js`, `device-observation-view.js`,
  `band-popover-view.js`, `spectrum-data.js`, `canvas-util.js`. Ezeket NEM
  kell még egyszer kivágni, már jó helyen vannak — az új modulok ezekből is
  importálnak majd.

A kódban már most is jól látható 11 banner-szakasz van (`// --- NÉV ---`):
`CONFIG`(405) `DOM`(411) `RF AGENT VIEWPORT CONTROLLER`(491)
`STATE`(538) `UTILS`(693) `RESIZE`(1447) `DRAWING`(1469) `DATA`(1993)
`INTERACTION`(2503) `BUTTONS / KEYBOARD`(2716)
`DEMODULÁCIÓS PASSBAND`(2969) `START`(3536). Ez NEM egyezik 1:1 a célmodul-
határokkal — több banner-szakasz belsőleg több, egymástól jól elkülöníthető
felelősségi kört tartalmaz (pl. `UTILS` 752 sor, és session-kezelés,
Wi-Fi/Bluetooth panel, baseline, band-popover, view-state mind benne van).

## 1. Célmodul-térkép

A feladatban javasolt induló határokat (`viewport-glue`, `spectrum-render`,
`interaction`, `source-status`) a valós kódhoz igazítva pontosítottam, és
felvettem további, a kódban ténylegesen elkülönülő egységeket is
(`view-state`, `demod-glue`, `sdrangel-audio`, `session-and-data-tabs`,
`spectrum-reference`, `entities`, `ws-ingest`, `retention`,
`panel-toggles`). A javasolt betöltési sorrend balról jobbra, fentről
lefelé követi a listát (a meglévő `<script src>` minta szerint, plain
globális scriptként VAGY `type="module"`-ként — ld. 5. pont a döntésről).

### 1.1 `view-state.js` — **alapréteg, mindenki ebből importál**

A feladat nem nevezte meg külön, de a kód feltérképezése azt mutatja, hogy
ez nélkül NINCS tiszta szétbontás: `viewMin`/`viewMax` és az ebből
származtatott `freqToX`/`xToFreq`/`span`/`center` függvényeket gyakorlatilag
minden javasolt modul olvassa.

| Funkció | Sor |
|---|---|
| `span`, `center`, `freqToX`, `xToFreq` | 695–698 |
| `applyFrameFrequencyDomain` | 699–706 |
| `measuredRangeMhz` | 707–715 |
| `setMode` | 1299–1308 |
| `setView` | 1310–1337 |
| `setCenterSpan` | 1338–1341 |
| `zoomAt`, `panBy` | 1391–1400 |
| `updateReadouts` | 1402–1433 |
| `sampleReferenceAtFreq`, `sampleAtFreq` | 1434–1438 |
| `requestDraw` | 1439–1444 |
| állapot: `viewMin`, `viewMax`, `mode`, `markerFreq`, `cursor`,
  `rangeInputsDirty`, `animationPending` | 541–569, 679, 686 |

**Importál:** `FULL_MIN/FULL_MAX/MIN_SPAN/clamp/freqToBin/binToFreq/...`
(`ui/spectrum-scale.js`), `viewportController.schedule` +
`currentRfViewport` (→ `viewport-glue.js`), `toastMsg` (→ közös util),
`drawAll`/`resizeAll` hívás csak közvetve (`requestDraw` ütemez
`requestAnimationFrame(drawAll)`-t, tehát **importálnia kell
`drawAll`-t a render-modulból**).
**Exportál:** minden fent felsorolt függvényt + a `viewMin`/`viewMax`
gettereket (ne nyers `let`-eket exportáljunk ES modulból, mert az élő
binding bár működik, de a meglévő kód mindenhol simán hozzáférne; inkább
`getViewRange()/setViewRange()` getter/setter-stílust javaslok — ld.
SHARED_STATE doc 2. pont).
**Betöltési hely:** rögtön a meglévő globális controllerek (1–5. tétel)
UTÁN, minden más célmodul ELŐTT.

### 1.2 `viewport-glue.js` — **1. kivágandó, legönállóbb**

| Funkció | Sor |
|---|---|
| `sendRfAgentViewportRequest` | 496–504 |
| `handleViewportStateChange` | 505–529 |
| `viewportController` (a `ViewportController.Controller` egyetlen
  példánya) | 530–533 |
| `currentRfViewport` | 534–536 |
| `refreshRfAgentCapabilities` (+ `window.refreshRfAgentCapabilities =`) | 1008–1017 |

**Importál:** `apiClient.updateRfAgentViewport`,
`apiClient.fetchRfAgentCapabilities`, `formatSpan` (`ui/spectrum-scale.js`),
`window.ViewportController` (globális), `center()`/`span()`
(→ `view-state.js`), `sourceMessageValue` DOM-referencia.
**Exportál:** `viewportController` (a `view-state.js`,
`interaction.js` és `ws-ingest.js` mind ezt hívják:
`.schedule()`, `.beginInteraction()`, `.endInteraction()`,
`.observeFrame()`, `.setCanvasPhysicalWidth()`), `currentRfViewport`.
**Muszáj globálisra tenni:** `refreshRfAgentCapabilities`-t a
`system-tabs.js` `window.refreshRfAgentCapabilities?.()` formában hívja
(ld. `system-tabs.js:82`) — ha ES modulba kerül, az exportot **explicit
`window.refreshRfAgentCapabilities = ...`-ként is be kell kötni**, különben
a Rendszerállapot fül RF Agent kártyája eltörik.
**Betöltési hely:** közvetlenül `view-state.js` után — ez önmagában a
legkevesebb belső függéssel rendelkező egység, ezért ez az első valódi
kivágási kísérlet.
**Megjegyzés:** `tests/frontend/test_viewport_wiring.js` NEM importálja ezt
a kódot — egy szimulált huzalozási mintát tesztel a valódi
`ViewportController.Controller`-rel. A kivágás nem futtatja újra ezt a
tesztet automatikusan zöldre/pirosra, de a benne dokumentált viselkedési
szerződést (debounce, beginInteraction/endInteraction, observeFrame
staleness) az új modulnak is be kell tartania.

### 1.3 `source-status.js`

| Funkció | Sor |
|---|---|
| `renderSpectrumSourceStatus` | 993–1007 |
| `refreshSpectrumSourceStatus` | 1018–1031 |

**Importál:** `apiClient.fetchSpectrumSourceStatus`,
`refreshRfAgentCapabilities` (→ `viewport-glue.js`, mert
`refreshSpectrumSourceStatus` az első sorában meghívja), `toastMsg`.
**Megosztott DOM-sink:** `sourceMessageValue.textContent`-et **mindkét**
modul írja (`renderSpectrumSourceStatus` ÉS `handleViewportStateChange` a
`viewport-glue.js`-ben) — ez nem JS-állapot ütközés, de tényleges
versenyhelyzet: amelyik utoljára fut, az nyer. Ezt a SHARED_STATE
dokumentum is felveszi.
**Betöltési hely:** `viewport-glue.js` után.

### 1.4 `spectrum-render.js` (rajzolás + resize)

A feladat ezt `spectrum-render.js` néven, `drawAll`+resize köré javasolta —
ez stimmel, de **körfüggést** tartalmaz a demod-glue-val (ld. 2.3 pont).

| Funkció | Sor |
|---|---|
| `resizeCanvas`, `resizeAll` (+ `window.addEventListener('resize', ...)`) | 1449–1467 |
| `drawAll`, `setPlotDims` | 1472–1491 |
| `drawBackground`, `drawGrid`, `formatAxisFreq` | 1492–1546 |
| `visibleBinRange` | 1547–1551 |
| `maybeResetMaxHoldFromFrame` | 1552–1561 |
| `drawReferenceTrace`, `drawReferenceBands`, `drawNmhhBands`,
  `nmhhBandAt`, `showNmhhPopover`, `referenceBandAt` | 1562–1654 |
| `drawSpectrum` | 1655–1723 |
| `drawMaxHoldTrace`, `drawMarkers`, `drawCursorAndSelection` | 1724–1872 |
| `ensureWaterfallBuffer`, `addWaterfallRow`, `drawWaterfall` | 1873–1931 |
| `drawOverview` | 1932–1991 |
| (UTILS-ből idekerül, mert csak rajzolás hívja:)
  `drawUnmeasuredOverlay` | 716–739 |

**Importál:** `ui/spectrum-scale.js` (sok függvény), `ui/canvas-util.js`
(`inPlot`, `roundRect`, `dbmToColor`), `ui/band-popover-view.js`
(`nmhhPopoverHtml` csak a `showNmhhPopover`-hez), `SpectrumViewModel`
globális (`minMaxEnvelope`, `peakInRange`), `view-state.js`
(`viewMin/viewMax/span/center/freqToX/xToFreq`), **`drawDemodPassband`
a `demod-glue.js`-ből** (a `drawSpectrum` 1720. sorában hívja!).
**Exportál:** `drawAll`, `resizeAll`, és a hit-test segédeket
(`nmhhBandAt`, `referenceBandAt`) az `interaction.js` számára.
**Megjegyzés:** a `maxHoldController`/`maxHoldState`/`hasMaxHold` triót
ez a modul OLVASSA (rajzoláshoz) és ÍRJA (`maybeResetMaxHoldFromFrame`),
de a `ws-ingest.js` (`acceptSweep`) is hívja a
`maybeResetMaxHoldFromFrame`-et — ez egy második körfüggés
(ld. 2.4 pont).

### 1.5 `interaction.js`

| Funkció | Sor |
|---|---|
| `canvasPoint`, `hideContext` | 2505–2510 |
| `cancelDrag`, `cancelDemodDrag` (+ `window.blur` listener) | 2517–2533 |
| `spectrumCanvas` mousemove/mouseleave/mousedown/wheel/dblclick/
  contextmenu | 2535–2665 |
| `document.click` (context+popover elrejtés) | 2666–2669 |
| `overviewCanvas` mousedown/mousemove/wheel | 2671–2695 |
| `waterfallCanvas` mousemove/mouseleave/wheel | 2697–2713 |
| `window.mouseup` (a select/pan/overview-drag lezárása) | 2604–2639 |

**Importál:** `view-state.js` (`setView`, `setCenterSpan`, `zoomAt`,
`panBy`, `xToFreq`, `span`), `viewport-glue.js`
(`viewportController.beginInteraction/endInteraction`,
`currentRfViewport`), `spectrum-render.js`
(`nmhhBandAt`, `referenceBandAt`, hogy a kattintás találjon-e sávot),
`ui/canvas-util.js` (`inPlot`), band-popover megjelenítés
(`showBandPopover`/`hideBandPopover`/`showNmhhPopover` — ezek jelenleg a
UTILS-ben vannak, 1276–1298, és ide, az `interaction.js`-be valók, mert
csakis itt hívják őket), **`demodHitAt`/`handleDemodMouseDown`/
`handleDemodMouseMove` a `demod-glue.js`-ből** (mousemove/mousedown ágban).
**Exportál:** semmi mást nem hív kívülről ezen a körön, ez egy "levél"
modul lehetne, HA nem lenne a demod körfüggés.
**Megjegyzés — DOM-állapot mutáció máshol definiált elemen:**
`document.body.classList.add/remove('no-select')`-et ez a modul ÉS a
`demod-glue.js` is hívja (`handleDemodMouseDown`) — finom, de valós
ütközési pont, ha a két modul független timing-gal fut.

### 1.6 `demod-glue.js`

A bannerkommentár (2970–2972. sor) maga is megfogalmazza, hogy ez egy önálló
"glue" réteg a kész `DemodPassband` logikai modul és az UI között — érdemes
külön fájlnak venni, NEM az `interaction`/`spectrum-render` részének.

| Funkció | Sor |
|---|---|
| `freqHzToSpectrumX`, `spectrumXToFreqHz` | 2976–2977 |
| `demodCapability` | 2981–2989 |
| `drawDemodPassband` | 2991–3064 |
| `renderDemodReadout` | 3069–3092 |
| `syncDemodStateToPanel` | 3095–3104 |
| `syncPanelToDemodState` | 3108–3126 |
| `demodUpdateScheduler` (`DemodPassband.createUpdateScheduler(...)`) | 3130–3162 |
| `scheduleDemodUpdateIfActive` | 3164–3191 |
| `demodHitAt`, `handleDemodMouseDown`, `handleDemodMouseMove`,
  `setDemodFrequencyFromX`, `initDemodFromContext` | 3195–3256 |
| panel input bindings (`sdrangelMode`/`Bandwidth`/`Squelch`/`Volume`
  change/input → `syncPanelToDemodState`) | 3496–3505 |
| `demodBandwidthDefaults` | 3495 |
| `modeDemod` gomb + `ctxDemodulate` context-menü kötés | 2946–2955, 3492 |

**Importál:** `window.DemodPassband` (globális), `demodState`
(→ `view-state.js`-szel azonos szintű megosztott állapot, ld.
SHARED_STATE), `spectrum-render.js` (`sCtx`, `spectrumPlot`, `freqToX`/
`xToFreq` becsomagolva), `apiClient.updateSdrangelDemod`, `requestDraw`
(→ `view-state.js`).
**Exportál:** `drawDemodPassband` (→ `spectrum-render.js` hívja!),
`demodHitAt`/`handleDemodMouseDown`/`handleDemodMouseMove`
(→ `interaction.js` hívja!), `initDemodFromContext`
(→ a context-menü kötés és a `sdrangel-audio.js` `startSdrangelDemod`
végén is hív rá hasonlót).
**Ez a modul a két legélesebb körfüggés metszéspontja** — ld. 2.2/2.3 pont.

### 1.7 `sdrangel-audio.js`

Egyirányú függés a `demod-glue.js` felé (NEM körkörös) — biztonságosabb
kivágás, mint a demod-glue maga.

| Funkció | Sor |
|---|---|
| böngészőhang állapota (`browserAudioContext`, …, `browserAudioSources`) | 3258–3267 |
| `setBrowserAudioStatus`, `scheduleBrowserAudio`, `appendBrowserPcm`,
  `prepareBrowserAudio`, `stopBrowserAudio` | 3269–3369 |
| `sdrangelReasonText`, `refreshSdrangelReadiness` | 3371–3410 |
| `createSdrangelDeviceSet`, `startSdrangelDemod`, `stopSdrangelDemod` | 3411–3482 |
| gombkötések (`btnSdrangelRefresh/CreateDeviceSet/Start/Stop`),
  `beforeunload` listener | 3507–3511 |
| `sdrangelReadiness`, `activeSdrangelChannel` állapot | 2966–2967 |

**Importál:** `apiClient.{createSdrangelDeviceSet,tuneSdrangel,
startSdrangelDemod,stopSdrangelDemod,fetchSdrangelReadiness}`,
`AUDIO_WS_URL` (→ CONFIG/bootstrap), `demodState`,
`syncDemodStateToPanel` (→ `demod-glue.js`, a `startSdrangelDemod` végén
hívja), `toastMsg`.
**Exportál:** nincs visszafelé hívás — ez teszi alacsony kockázatúvá.

### 1.8 `entities.js` (markerek + ismert jelek)

| Funkció | Sor |
|---|---|
| `saveMarkerAt` | 2311–2327 |
| `saveKnownSignalAt` | 2329–2353 |
| `entityAction`, `refreshSpectrumEntities` | 2355–2362 |
| `editMarker`, `archiveMarker`, `setKnownSignalStatus`,
  `archiveKnownSignal` | 2363–2366 |
| gombkötések (`btnRefreshMarkers/KnownSignals`, context-menü
  `ctxSaveMarker/ctxKnownSignal/ctxSuppressSignal`) | 2811–2812, 3488–3490 |

**Importál:** `apiClient.{createMarker,createKnownSignal,fetchMarkers,
fetchKnownSignals,updateMarker,deleteMarker,updateKnownSignalStatus,
deleteKnownSignal}`, `openOperationModal`/`toastMsg` (közös util),
`sampleAtFreq`/`setCenterSpan`/`span` (→ `view-state.js`),
`activeMeasurementSession`/`currentSpectrumFrame` (olvasás).
**Exportál:** `refreshSpectrumEntities` (→ az `activateTab` és a
`saveMarkerAt`/`saveKnownSignalAt` is hívja belsőleg, kívülről az
`activateTab('spectrum')` ág hívja, ami a tab-kezelésben él).

### 1.9 `spectrum-reference.js`

| Funkció | Sor |
|---|---|
| `normalizeIncoming`, `currentSpectrumSnapshot` | 1996–2027 |
| `updateReferenceStatus` | 2028–2041 |
| `setReferenceFromSweep`, `setReferenceFromCurrentFrame`,
  `setReferenceFromMaxHold` | 2042–2092 |
| `referencePointsForSave`, `saveCurrentViewReference`, `saveMaxPeak` | 2093–2200 |
| `renderReferenceBar`, `selectReferenceSet`, `openReferenceSetPicker`,
  `openReferenceBarDetails`, `exportSelectedReference` | 2202–2309 |
| `clearReference`, `loadReferenceFromLocalStorage` | 2367–2405 |
| gombkötések (DB referencia gombok, `btnDbReference`,
  `referenceFile` import) | 2845–2861, 2868–2887, 2895–2919 |

**Importál:** `apiClient.{captureReferenceSet,saveSpectrumPeak,
fetchReferenceSetMeta,fetchReferenceSetSpectrum,fetchReferenceSets,
importReferenceFile,fetchReferenceDetail}`,
`ui/spectrum-scale.js` (`freqToBin`,`binToFreq`,…), `ui/spectrum-data.js`
(`peakOfArray`), `SpectrumFrameAdapter` (nem direkt, csak transzitíven a
`normalizeIncoming` az `acceptSweep`-pel közös logikát másol),
`view-state.js` (`viewMin/viewMax`).
**Exportál — KÖRFÜGGÉS:** `clearReference` és `selectReferenceSet` is
hívja a `refreshWifiPanel`/`refreshBluetoothPanel`-t
(`session-and-data-tabs.js`), miközben az utóbbi modul olvassa az itt
élő `selectedReferenceSetId`-t. Ld. 2.1 pont.
**Megjegyzés:** `normalizeIncoming`-ot az `acceptSweep` (→ `ws-ingest.js`)
IS hívja — ez egy önálló, állapotmentes függvény, érdemes lehet egy
közös, még kisebb segédmodulba (`spectrum-frame-normalize.js`) tenni,
hogy a `ws-ingest.js` ne kelljen a teljes `spectrum-reference.js`-t
importálnia csak ezért az egy függvényért.

### 1.10 `ws-ingest.js`

| Funkció | Sor |
|---|---|
| `acceptSweep` | 2406–2444 |
| `connectWS` | 2445–2468 |
| `fallbackToDemo`, `startDemo` | 2469–2491 |
| stale-figyelő `setInterval` | 2492–2497 |
| periodikus `refreshActiveDataTab` `setInterval` | 2498–2500 |

**Importál:** `SpectrumFrameAdapter.parseSpectrumFrame`,
`viewportController.observeFrame` (→ `viewport-glue.js`),
`normalizeIncoming` (→ `spectrum-reference.js` vagy a kiemelt
`spectrum-frame-normalize.js`), `maybeResetMaxHoldFromFrame`,
`addWaterfallRow`, `requestDraw` (→ `spectrum-render.js` /
`view-state.js`), `refreshActiveDataTab` (→
`session-and-data-tabs.js`), `WS_URL`/`allowSyntheticFallback`
(→ CONFIG/bootstrap).
**Ez importálja a legtöbb más modult** — ténylegesen ez az adatfolyam
"motorja", nem egy levél-modul.

### 1.11 `session-and-data-tabs.js` — **legnagyobb, legkockázatosabb darab**

A feladat ezt csak "referencia/anomália/session blokkok – külön
szakaszként, ha elkülöníthetők" szintjén jelezte előre; a feltérképezés
azt mutatja, hogy ez ~460 sornyi, sűrűn összekötött kód, ÉS ez az a blokk,
amelyik a legtöbb `tests/frontend/test_ui_static.py` szövegillesztést
megtöri (ld. 3. pont) — ezért ezt javaslom utolsónak kivágni, és csak a
teszt frissítésével együtt.

| Funkció | Sor |
|---|---|
| `activateTab` | 793–814 |
| `discoverActiveMeasurementSession`, `refreshActiveDataTab`,
  `renderMeasurementSession`, `updateSessionEmptyState`,
  `clearSessionScopedFrontendState`, `setViewedSession`,
  `refreshMeasurementSession`, `startMeasurementSession`,
  `stopMeasurementSession`, `startSessionFromModal`,
  `openPreviousSessionPicker` | 815–992 |
| `activeSessionLocationNameForBaseline`,
  `lastWifiBluetoothBaselineLocationName`,
  `currentLocationNameForBaseline` | 1032–1044 |
| `renderReferenceSummary`, `resolveBaselineLocationName`,
  `saveDeviceBaseline`, `compareDeviceBaseline`,
  `deactivateDeviceBaseline` | 1045–1111 |
| `openDetailDialog`, `openDeviceReferenceDetails`,
  `showMissingReferenceDevices`, `renderDetectionRows`,
  `renderWifiAnomalies`, `renderBluetoothAnomalies` | 1112–1132 |
| `wifiItemsByIdentity`, `renderWifiObservations` (+ click listener),
  `renderWifiSecurityEvents`, `refreshWifiPanel` | 1133–1187 |
| `bluetoothItemsByIdentity`, `renderBluetoothObservations`
  (+ click listener), `refreshBluetoothPanel` | 1188–1243 |
| `importKismetLive`, `importKismetAlerts` | 1244–1275 |
| ~30 gombkötés (session/source/wifi/bluetooth export, baseline,
  kismet import) | 2722–2744, 2862–2867 |

**Importál:** `apiClient` (kismet/bettercap/wifi/bluetooth/session/
baseline végpontok — kb. 20 funkció), `openOperationModal`/`toastMsg`,
`ui/device-observation-view.js` (`referenceSummaryHtml`,
`deviceReferenceDetailsHtml`, `missingReferenceDevicesHtml`,
`detectionRowsHtml`, `wifiObservationsHtml`, `wifiSecurityEventsHtml`,
`bluetoothObservationsHtml`), `ui/html.js` (`escapeHtml`),
`entities.js` (`refreshSpectrumEntities`, az `activateTab` hívja),
`spectrum-render.js`/`view-state.js` (`resizeAll`, `requestDraw`),
`spectrum-reference.js` (`selectedReferenceSetId` olvasása).
**Körfüggés `spectrum-reference.js`-szel:** ld. 2.1 pont.
**Megjegyzés:** ez a blokk önmagában tovább bontható (pl.
`session-lifecycle.js` + `wifi-bluetooth-panels.js` +
`device-baseline.js`), de a `viewedSession`/`activeMeasurementSession`/
`selectedReferenceSetId` hármas mindhárom darabot átszövi — egy ilyen
belső bontás csak akkor ér valamit, ha előbb a 2.1 körfüggést egy
state.js-stílusú megosztott modullal feloldjuk.

### 1.12 `retention.js` — alacsony kockázat, jól elkülönül

| Funkció | Sor |
|---|---|
| `formatRetentionDate`, `retentionResetPreview` + preview/purge gomb
  handlerek | 2747–2810 |

**Importál:** `apiClient.{fetchRetentionPreview,purgeRetention}`,
`openOperationModal`/`toastMsg`.
**Exportál:** semmit, levél-modul.

### 1.13 `panel-toggles.js` — alacsony-közepes kockázat

| Funkció | Sor |
|---|---|
| `getSpectrumControlPanelCollapsed`, `setSpectrumControlPanelCollapsed`,
  `toggleSpectrumControlPanel`, `initSpectrumControlPanel` | 607–639 |
| `getWaterfallPanelCollapsed`, `setWaterfallPanelCollapsed`,
  `toggleWaterfallPanel`, `initWaterfallPanel` | 640–674 |
| `initPanelToggles` | 2961–2964 |

**Importál:** `resizeAll` (→ `spectrum-render.js`).
**Kockázat:** a `spectrumControlPanelCollapsed`/`waterfallPanelCollapsed`
`localStorage`-kulcsok CSAK ebben a kódban szerepelnek szövegszerűen — ha
a kulcsneveket tartalmazó konstansok kikerülnek `index.html`-ből, a
`test_ui_static.py:112` sora megbukik (ld. 3. pont).

### 1.14 Bootstrap/init script (amit NEM viszünk ki)

| Tartalom | Sor |
|---|---|
| `CONFIG` (`WS_URL`, `AUDIO_WS_URL`) | 408–409 |
| összes `DOM` `getElementById`/`querySelector` cache | 414–489 |
| canvas kontextusok (`sCtx`/`wCtx`/`oCtx`) | 487–489 |
| `toastMsg` (+ `window.toastMsg =`), `openOperationModal`
  (+ `window.openOperationModal =`) | 740–792 |
| `cssVar` | 1298 |
| `document.addEventListener('keydown', ...)` | 3513–3530 |
| `auxclick` preventDefault | 3533 |
| `START` szekció (init hívások sorrendje) | 3538–3555 |

**Ez NEM tehető külön "üres" modullá** — ez az orchestrator, amely import-
sorrendben mindenkit összekapcsol, és ez fut a `<script type="module">`
maradék tartalmaként (vagy egy `main.js` entry pointként). A `toastMsg`/
`openOperationModal` itt marad, mert ezt szó szerint MINDEN javasolt
modul használja (cross-cutting, nem érdemes szétszedni), és mert
`system-tabs.js` ezekre globálisként támaszkodik.
**Nyitott kérdés (nem döntöm el, csak jelzem):** a `keydown` handler
inkább az `interaction.js`-be illene tartalmilag (zoom/pan
billentyűparancsok), de oldalgörgetést (`ArrowUp/Down`, `PageUp/Down`)
is végez, ami nem canvas-specifikus — holnap el kell dönteni, hogy
marad-e a bootstrapban vagy megy az `interaction.js`-be.

## 2. Körkörös függések (a legfontosabb töréspontok)

ES modulok között a körkörös `import` önmagában NEM crash-el, amíg a
kölcsönös hívás csak FÜGGVÉNYTESTBEN (eseménykezelőben, callback-ben)
történik, nem a modul tetején azonnal kiértékelve — itt pontosan ez a
helyzet mind a négy felsorolt esetben, tehát futásidőben működne. A
valódi probléma: ezek a modulok NEM tesztelhetők/érthetők egymástól
függetlenül, mindkét oldalt együtt kell importálni és karbantartani.

1. **`spectrum-reference.js` ↔ `session-and-data-tabs.js`**
   `clearReference` (2378–2379) és `selectReferenceSet` (2250) hívja a
   `refreshWifiPanel`/`refreshBluetoothPanel`-t; ezek viszont olvassák a
   `selectedReferenceSetId`-t (1156, 1208), amit a
   `spectrum-reference.js` ír. **Legnehezebb feloldani** — vagy egy
   közös `reference-state.js` birtokolja a `selectedReferenceSetId`-t és
   egy esemény/callback jelzi a panel-frissítést, vagy a hívó kódot
   (UTILS/bootstrap szint) kell megbíznia mindkét frissítéssel.
2. **`spectrum-render.js` ↔ `demod-glue.js`**
   `drawSpectrum` (1720) hívja `drawDemodPassband`-ot; a
   `drawDemodPassband` viszont a `spectrum-render.js` `sCtx`/
   `spectrumPlot`/`freqToX`-jét használja (`freqHzToSpectrumX` wrapper).
3. **`interaction.js` ↔ `demod-glue.js`**
   `spectrumCanvas` mousedown/mousemove (2581, 2543–2548) hívja
   `handleDemodMouseDown`/`handleDemodMouseMove`/`demodHitAt`-ot; ezek a
   függvények viszont `interaction.js`-ben élő `demodDrag`-et247 és
   `mode`-ot olvasnak (a mód-állapot ÉS a drag-állapot megosztott — ld.
   SHARED_STATE).
4. **`spectrum-render.js` ↔ `ws-ingest.js`**
   `acceptSweep` (2437–2443) hívja a `spectrum-render.js`-ben élő
   `maybeResetMaxHoldFromFrame`/`addWaterfallRow`/`requestDraw`-t; a
   `spectrum-render.js` viszont a `currentSpectrumFrame`-et (amit a
   `ws-ingest.js` ír) olvassa minden `drawSpectrum`/`drawWaterfall`
   hívásban.

Ezen négy közül **az 1. a legkockázatosabb** (ezért is utolsó a
`session-and-data-tabs.js` kivágása), a 2–4. kezelhető úgy, hogy a
hívott függvényt egyszerűen importáljuk a másik modulból — ezek nem
crashelnek, csak dokumentálni kell, hogy "ez a két fájl együtt mozog".

## 3. `tests/frontend/test_ui_static.py` — szöveg-egyezés kockázatok

Ez a teszt **literálisan** keres szövegrészleteket a teljes
`index.html`-ben (`html` változó = a teljes fájl szövege, nem a
renderelt DOM). A markup-szövegek (gombfeliratok, `<th>`, `id="..."`)
NEM törnek el, mert azok a HTML-ben maradnak függetlenül attól, hova
kerül a JS. De a következő assertek **kizárólag JS-forráskódot**
keresnek `index.html`-ben, és megbuknak, ha az adott függvény/kulcsszó a
teljes deklarációjával (definíció + minden hívás) kikerül egy külön
fájlba:

| Sor | Assert | Mit tör el |
|---|---|---|
| 108 | `"prepareBrowserAudio" in html and "appendBrowserPcm" in html` | `sdrangel-audio.js` kivágása |
| 109 | `"synthetic_fallback_allowed" in html and "loadRuntimePolicy" in html` | `loadRuntimePolicy` kivágása a bootstrapból |
| 112 | `"spectrumControlPanelCollapsed" in html and "waterfallPanelCollapsed" in html` | `panel-toggles.js` kivágása (a storage-key csak JS-ben él) |
| 183 | `"renderWifiSecurityEvents" in html` | `session-and-data-tabs.js` kivágása |
| 184 | `"importKismetAlerts" in html` | ua. |
| 206 | `"let viewedSession" in html` | ua. |
| 207 | `"function setViewedSession" in html` | ua. |
| 208 | `"reference_set_id" in html` | ua. (csak a wifi/bluetooth paraméter-összeállításban él) |
| 209 | `"require_session" in html` | ua. |
| 211 | `"function renderReferenceSummary" in html` | ua. |
| 212 | `"function showMissingReferenceDevices" in html` | ua. |
| 213 | `"function openDeviceReferenceDetails" in html` | ua. |

**Megfigyelés:** ez a 12 assert mind a `session-and-data-tabs.js` (8 db)
és a `sdrangel-audio.js`/`panel-toggles.js`/bootstrap (4 db) tervezett
kivágását érinti. A `viewport-glue.js`, `spectrum-render.js`,
`interaction.js`, `source-status.js`, `entities.js`, `retention.js`,
`spectrum-reference.js`, `ws-ingest.js`, `demod-glue.js` kivágása **nem**
sért semmilyen ilyen assertet (a `view-state.js` sem — `viewMin`/`mode`
szavak nem szerepelnek külön ellenőrzésben).
**Következmény a sorrendre:** a holnapi végrehajtásnak VAGY együtt kell
frissítenie `test_ui_static.py`-t a `session-and-data-tabs.js` /
`sdrangel-audio.js` / `panel-toggles.js` / `loadRuntimePolicy` kivágásával
(a teszt asszertjeit "X in html" helyett "X in html or X in
<új fájl>"-ra módosítva), VAGY ezeket a köröket legutoljára kell csinálni,
külön commit-ban, ami a tesztfrissítést is tartalmazza. Ez NEM ennek a
dokumentumnak a feladata (csak elemzés), de a holnapi sorrendet ez erősen
befolyásolja (ld. összefoglaló).

Az `offline-acceptance.sh` (58–112. sor) egy MÁSIK, kódolt
`js_syntax_targets` tömbböt használ `node --check`-hez, és egy Python
snippet (101–109. sor) az `index.html` MINDEN `<script>`/
`<script type="module">` blokkját kivonja és `node --check`-eli — ez
viszont **automatikusan lefedi** az inline modul maradékát bármilyen
bontás után is, de **NEM fedi le automatikusan az újonnan létrehozott
külön `.js` fájlokat** — azokat kézzel kell hozzáadni a
`js_syntax_targets` tömbhöz, különben szintaktikai hibájuk észrevétlen
maradna ebben a scriptben (bár az alkalmazás böngészőben futtatva
amúgy is azonnal jelezné).

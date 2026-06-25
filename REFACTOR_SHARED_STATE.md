# REFACTOR_SHARED_STATE.md — megosztott állapot leltár

> Csak elemzés, forrás nem módosult. A modulnevek a `REFACTOR_CUTMAP.md`-ben
> javasolt célmodulokra hivatkoznak (`view-state.js`, `viewport-glue.js`,
> `spectrum-render.js`, `interaction.js`, `demod-glue.js`,
> `sdrangel-audio.js`, `spectrum-reference.js`, `ws-ingest.js`,
> `session-and-data-tabs.js`, `entities.js`, `retention.js`,
> `panel-toggles.js`, `source-status.js`, bootstrap). A sorszámok az
> `index.html` jelenlegi állapotára vonatkoznak.

Minden táblázat oszlopai: **Állapot** | **Deklaráció (sor)** | **Olvassa**
| **Írja** | **Célmodul** | **Kívülről hivatkozza** | **Javaslat**.
"Kívülről hivatkozza" = melyik MÁSIK célmodulnak is hozzá kell férnie —
ezek a tényleges töréspontok.

## 1. Nézet-állapot (view/zoom/pan/marker/cursor)

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `viewMin`, `viewMax` | 541–542 | `span`,`center`,`freqToX`,`xToFreq`,`updateReadouts`,`sampleAtFreq`,`drawSpectrum`,`drawGrid`,`drawWaterfall`,`drawOverview`,`addWaterfallRow`,`fetchReferenceLayers`,`referenceQueryParams`,`acceptSweep`(közvetve `requestDraw`-n át) | csak `setView` | `view-state.js` | `spectrum-render.js` (rajzolás minden frame-ben), `interaction.js` (drag/zoom számítás), `spectrum-reference.js` (`referenceQueryParams`) | Getterrel exportálni (`getViewMin()/getViewMax()` vagy egy `{min,max}` snapshot), NE nyers `let`-et — élő binding működne ES modulnál is, de a meglévő kód mindenhol direkt változóként olvas, a tiszta API a karbantarthatóbb. |
| `mode` (`select\|pan\|marker\|demod`) | 569 | `setMode`,`spectrumCanvas` mousemove/mousedown,`drawCursorAndSelection`(`drag.target==='spectrum'`-en át nem, de `mode==='demod'` ágban igen) | `setMode`, és a `modeDemod`/`modeMarker` gombkezelő közvetve | `view-state.js` (vagy `interaction.js`, ld. alább) | `demod-glue.js` (`handleDemodMouseDown` ellenőrzi `mode!=='demod'`-ot) | Mivel `setMode` a `spectrumCanvas.style.cursor`-t is állítja és a demod-bekapcsolást (`demodState.enabled=true`) is elindítja, **ez valójában már ma is összeköti a view-state-et és a demod-glue-t** — a kivágás után a `setMode`-nak importálnia kell a demod modult, vagy a demod-engedélyezést egy callback/esemény mögé kell tenni. |
| `markerFreq` | 567 | `updateReadouts`,`drawMarkers`,`sampleAtFreq` hívásban | `setMode`(`modeMarker` ág null-ra), `spectrumCanvas mousedown`(marker mód), `ctxMarker` | `view-state.js` | `interaction.js`, `spectrum-render.js` | Marad egyszerű mutable export, kevés író van. |
| `cursor` (`{x,y,freq,dbm,inside,target}`) | 568 | `drawCursorAndSelection`,`drawWaterfall`(cursor vonal) | `spectrumCanvas`/`waterfallCanvas` mousemove/mouseleave | `interaction.js` | `spectrum-render.js` (rajzolás olvassa) | `interaction.js` írja, `spectrum-render.js` csak olvas — tiszta egyirányú export. |
| `drag`, `dragViewChanged` | 570–571 | `drawCursorAndSelection`,`drawOverview`(kijelölés rajzolása) | `spectrumCanvas`/`overviewCanvas` mousedown/mousemove/mouseup, `cancelDrag` | `interaction.js` | `spectrum-render.js` (a kijelölő téglalapot rajzolja a `drag` mezőiből) | Ua. mint `cursor`: `interaction.js` írja, `spectrum-render.js` olvas. |
| `rangeInputsDirty` | 679 | `updateReadouts` | `startInput`/`stopInput` `input` listener, `btnApply` | `view-state.js`/bootstrap | — | Kis hatókörű, nincs körfüggés. |
| `animationPending` | 566 | `requestDraw` | `requestDraw`, `drawAll`(reset) | `view-state.js` | `spectrum-render.js`(`drawAll` állítja vissza) | `requestDraw` és `drawAll` ketten írják ugyanazt a flaget — ha külön fájlban vannak, ez egy explicit export/import pár, nem hallgatólagos closure. |
| `activeTab` | 584 | `requestDraw`(csak `'spectrum'`-nél rajzol), `acceptSweep`(csak `'spectrum'`-nél frissít waterfallt/overview-t) | `activateTab` | `session-and-data-tabs.js` | `view-state.js` (`requestDraw`), `ws-ingest.js` (`acceptSweep`) | Egyirányú olvasás máshonnan, írás csak egy helyen — alacsony kockázat, de jelzi, hogy a `session-and-data-tabs.js` kivágása előtt ezt is exportálnia kell. |

## 2. Spektrum geometria (canvas plot téglalapok)

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `spectrumPlot`, `waterfallPlot`, `overviewPlot` (`{left,right,top,bottom,width,height}`) | 688–690 | minden rajzoló függvény + `freqToX`/`xToFreq` paraméterként + `interaction.js` `inPlot`/`canvasPoint` hívásokban | `setPlotDims`(`width`/`height`) | `spectrum-render.js` | `interaction.js` (hit-test: `inPlot(p.x,p.y,spectrumPlot)`), `view-state.js` (`freqToX(freq, plot)` mindig paraméterül kapja) | Ezek már most is paraméterátadással "lazán kötöttek" (nem globális oldschool singleton-mintázat) — ez a LEGKÖNNYEBB rész, csak exportálni kell az objektumokat `spectrum-render.js`-ből. |

## 3. Spektrum adatfolyam (WS / frame állapot)

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `currentSpectrumFrame` | 676 | `measuredRangeMhz`,`sampleAtFreq`,`drawSpectrum`,`addWaterfallRow`,`demodCapability`,`saveMarkerAt`,`saveKnownSignalAt`,`setReferenceFromCurrentFrame`,`snapFrequencyToSpectrumBin` hívásokban (demod-glue) | csak `acceptSweep` | `ws-ingest.js` | `view-state.js`(`measuredRangeMhz`,`sampleAtFreq`), `spectrum-render.js`(rajzolás), `demod-glue.js`(snap/capability), `entities.js`(marker/known-signal mentés), `spectrum-reference.js`(pillanatkép referencia) | **A legszélesebben olvasott állapot.** Egyetlen író (`acceptSweep`), sok olvasó — tiszta export, írás-oldali körfüggés nincs, csak sok importáló modul. |
| `lastSweep` | 543 | `sampleAtFreq`(fallback),`currentSpectrumSnapshot` | `acceptSweep`(`if (activeTab==='spectrum' \|\| maxHoldEnabled)`) | `ws-ingest.js` | `view-state.js`,`spectrum-reference.js` | Ua., egy író, pár olvasó. |
| `lastFrameReceivedAt` | 677 | `fallbackToDemo`, stale-figyelő `setInterval` | `acceptSweep` | `ws-ingest.js` | — | Belső, nincs külső iró/olvasó konfliktus. |
| `reconnectTimer` | 678 | `connectWS` | `connectWS` | `ws-ingest.js` | — | Tisztán belső. |
| `demoMode` | 564 | `acceptSweep`,`fallbackToDemo`,`startDemo`,`connectWS` | ua. négy függvény | `ws-ingest.js` | — | Tisztán belső. |
| `allowSyntheticFallback` | 565 | `acceptSweep`,`fallbackToDemo` | `loadRuntimePolicy` | bootstrap (`loadRuntimePolicy`) / `ws-ingest.js` | `ws-ingest.js` olvassa, de bootstrap írja | **Töréspont:** `loadRuntimePolicy` jelenleg a `STATE` szekcióban van (594–606), nem a `ws-ingest.js`-ben — ha külön fájlba kerül, ennek a flagnek exportált/importált binding-ként kell léteznie a `ws-ingest.js` és a bootstrap között. |
| `sequenceTracker` | 680 | `acceptSweep` | csak `.observe()` belső mutáció | `ws-ingest.js` | — | `SpectrumFrameAdapter.createSequenceTracker()` singleton, tisztán belső. |
| `overviewAccumulator` | 681–686 | `drawOverview` | `acceptSweep`(`.update()`) | megosztott `spectrum-render.js` ÉS `ws-ingest.js` között | mindkét irány | **Töréspont:** ezt VAGY a `spectrum-render.js` birtokolja és a `ws-ingest.js` importálja (`updateOverview(frame, now)` export-függvényen át), VAGY egy harmadik, neutrális helyen (`view-state.js`) kell létrehozni. Jelenleg egyetlen objektum, amit egy modul ír (`.update`) és egy másik olvas (`.at`/`.frequencyFor`) — klasszikus "ki birtokolja" döntés. |
| `waterfallBuffer`, `offscreenSupported` | 578–579 | `drawWaterfall`,`ensureWaterfallBuffer` | `setView`(nullázza nézetváltáskor!),`resizeAll`(nullázza átméretezéskor!),`ensureWaterfallBuffer`,`addWaterfallRow` | `spectrum-render.js` | `view-state.js`(`setView` nullázza), `spectrum-render.js`(`resizeAll` nullázza) | **Töréspont:** a `setView` (view-state.js) és a `resizeAll` (spectrum-render.js) MINDKETTŐ közvetlenül null-ra állítja a `waterfallBuffer`-t view-/méretváltáskor. Ha `view-state.js` külön fájl, importálnia kell egy `invalidateWaterfallBuffer()` export-függvényt a `spectrum-render.js`-ből, NEM állíthatja a változót direktben. |
| `visiblePeak` | 580 | `updateReadouts`,`drawMarkers` | `drawSpectrum` | `spectrum-render.js` | `view-state.js`(`updateReadouts` olvassa) | `drawSpectrum` írja minden frame-nél, `updateReadouts` (másik modul) csak olvas utána — sorrendfüggő (`drawAll` hívja előbb `drawSpectrum`-ot, utána `updateReadouts`-ot), ez a hívási sorrend a kivágás után is megőrzendő. |

## 4. Referencia-állapot

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `referenceSweep`, `hasReference`, `referenceSource`, `staticReference` | 544–547 | `drawReferenceTrace`,`drawOverview`,`sampleReferenceAtFreq`,`updateReferenceStatus`,`referencePointsForSave` | `setReferenceFromSweep`,`clearReference`,`loadReferenceFromLocalStorage`,`btnDbReference` handler(`spectrum-render.js`-ben él, ha `dbReferenceEnabled` kikapcsol DB-forrású referenciát) | `spectrum-reference.js` | `spectrum-render.js`(rajzolás),`view-state.js`(`sampleReferenceAtFreq`) | A `btnDbReference` gombkezelő (2868–2887) **közvetlenül írja** a `referenceSweep`/`hasReference`/`referenceSource`-t, holott ez a kód a `BUTTONS/KEYBOARD` szekcióban van — ezt a logikát exportált függvényen (`disableDbReference()`) keresztül kellene hívnia, ha a referencia-állapot külön fájlba kerül. |
| `selectedReferenceSetId`, `selectedReferenceSet` | 548–549 | `refreshWifiPanel`,`refreshBluetoothPanel`(`reference_set_id` query param),`renderReferenceBar`,`openReferenceBarDetails` | `setReferenceFromSweep`,`selectReferenceSet`,`clearReference` | `spectrum-reference.js` | `session-and-data-tabs.js`(`refreshWifiPanel`/`refreshBluetoothPanel` OLVASSA) | **Legélesebb körfüggés** (ld. CUTMAP 2.1 pont): ez az állapot köti össze a spektrum-referenciát és a Wi-Fi/Bluetooth panelt. Javaslat: `selectedReferenceSetId`-t emeljük egy neutrális, mindkét modul által importált `reference-state.js`-be (csak ezt az egy mezőt + egy `onReferenceSetChanged` callback-listát), így `spectrum-reference.js` és `session-and-data-tabs.js` egymástól függetlenül importálhatja, körfüggés nélkül. |
| `dbReferenceEnabled` | 550 | `scheduleReferenceFetch`,`fetchReferenceLayers`,`drawReferenceBands` | `btnDbReference` handler | megosztott `spectrum-reference.js`/`spectrum-render.js` | mindkét irány | Kisebb töréspont: a flag-et az egyik modulnak birtokolnia kell, a másiknak importálnia. |
| `referenceBands`, `referenceImages` | 551–552 | `drawReferenceBands`,`referenceBandAt` | `fetchReferenceLayers`,`btnDbReference` handler(törlés) | megosztott `spectrum-reference.js`(fetch)/`spectrum-render.js`(rajzolás+hit-test) | mindkét irány | `referenceBandAt` (hit-test, `spectrum-render.js`) és `fetchReferenceLayers` (adatbetöltés, `spectrum-reference.js`) közös tömbön dolgozik — export/import pár kell. |
| `nmhhBands`, `nmhhBandsEnabled` | 553–554 | `drawNmhhBands`,`nmhhBandAt` | `loadNmhhBands`(bootstrap-szintű hívás),`btnNmhhBands` handler | `spectrum-render.js` (rajzolás+hit-test) / bootstrap (`loadNmhhBands` betöltés, jelenleg UTILS-ban, 1379–1390) | `interaction.js`(`nmhhBandAt` hívás a mousedown-ban) | Kisebb kockázat, de `loadNmhhBands`-ot is el kell helyezni — leginkább `spectrum-render.js`-be illik (mellette él `drawNmhhBands`). |
| `referenceFetchTimer`, `referenceFetchKey` | 555–556 | `scheduleReferenceFetch`,`fetchReferenceLayers` | ua. | `spectrum-reference.js` | `spectrum-reference.js`(`saveCurrentViewReference` nullázza a key-t mentés után) | Belső, nincs külső függés. |
| `referencePeak` | 557 | `updateReadouts`,`drawMarkers` | `drawSpectrum`,`setReferenceFromSweep`,`clearReference` | megosztott `spectrum-render.js`(ír)/`view-state.js`(olvas) | — | Hasonló mintázat, mint `visiblePeak`. |

## 5. Max Hold

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `maxHoldController`, `maxHoldState` | 560–561 | `drawMaxHoldTrace`,`drawSpectrum`(peak),`maybeResetMaxHoldFromFrame`,`setReferenceFromMaxHold`,`btnResetMaxHold`/`btnMaxHold` handlerek | `maybeResetMaxHoldFromFrame`(`.updateFromFrame`),`btnResetMaxHold`(`.resetFromFrame`) | `spectrum-render.js`(a `maybeResetMaxHoldFromFrame` itt él) | `ws-ingest.js`(`acceptSweep` hívja `maybeResetMaxHoldFromFrame`-et), `spectrum-reference.js`(`setReferenceFromMaxHold` olvassa) | Singleton, globális `MaxHoldController`-re épül (már külön fájl) — az ÁLLAPOT (`maxHoldState`) az, ami megosztott, nem a logika. |
| `hasMaxHold`, `maxHoldEnabled` | 559, 563 | `drawSpectrum`,`updateReadouts`,`acceptSweep`(`if (maxHoldEnabled) lastSweep=...`) | `maybeResetMaxHoldFromFrame`,`btnMaxHold` handler | `spectrum-render.js` | `ws-ingest.js`(`acceptSweep` olvassa `maxHoldEnabled`-et a `lastSweep` frissítés feltételéhez!) | **Finom töréspont:** `acceptSweep` 2435. sora: `if (activeTab === 'spectrum' || maxHoldEnabled) lastSweep = normalizeIncoming(parsed);` — ez azt jelenti, hogy a `ws-ingest.js`-nek importálnia kell a `maxHoldEnabled` flaget a `spectrum-render.js`-ből/gombkezelőből, különben a Max Hold "más fülön is frissül a lastSweep" viselkedése elveszik. |
| `maxPeak` | 558 | `updateReadouts`,`drawMarkers`,`saveMaxPeak` | `drawSpectrum` | megosztott `spectrum-render.js`(ír)/`view-state.js`+`spectrum-reference.js`(olvas, `saveMaxPeak`) | — | `saveMaxPeak` jelenleg a `spectrum-reference.js`-be sorolt DATA-blokkban van (2167–2200) — importálnia kell a `maxPeak`-et `spectrum-render.js`-ből. |
| `hold` | 562 | `addWaterfallRow`(`if (hold) return`),`acceptSweep`(`if (hold) return`) | `btnHold` handler | megosztott bootstrap/BUTTONS(gomb)/`spectrum-render.js`+`ws-ingest.js`(olvasás) | mindkét irány | Egyszerű boolean, de KÉT különböző adatfolyam-függvény (`addWaterfallRow` a rajzolásban, `acceptSweep` az ingestben) korai-return feltétele — mindkettőnek látnia kell. |

## 6. Demoduláció (UI-glue réteg, nem a `DemodPassband` logikai modul)

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `demodState` | 572–575 | csaknem minden demod-glue függvény + `drawSpectrum`(`drawDemodPassband` hívás feltétele) + `setMode`(`demodState.enabled=true`) + `modeDemod` gomb(`demodState.enabled=false`) | `syncPanelToDemodState`,`handleDemodMouseMove`,`setDemodFrequencyFromX`,`initDemodFromContext`,`startSdrangelDemod`,`stopSdrangelDemod`,`demodUpdateScheduler` callbackek | `demod-glue.js` | `spectrum-render.js`(`drawSpectrum` ellenőrzi `demodState.enabled`-et a `drawDemodPassband`hívás előtt — bár ez maga is a demod-glue-ban van), `view-state.js`(`setMode`), `sdrangel-audio.js`(`startSdrangelDemod`/`stopSdrangelDemod`) | A `DemodPassband.createDemodState()` által létrehozott objektum, de a MEZŐIT (frequencyHz, bandwidthHz, mode, active, pendingUpdate, lastError, …) sok modul írja közvetlenül — ez egy klasszikus megosztott mutable struct. Mivel a `DemodPassband` logikai modul már tiszta (state-mentes) függvénykönyvtár, a `demodState` objektumot magát érdemes a `demod-glue.js` exportjának tekinteni, amit a `sdrangel-audio.js` és a `view-state.js`/`interaction.js` importál. |
| `demodDrag` | 576 | `handleDemodMouseMove`,`cancelDemodDrag` | `handleDemodMouseDown`,`cancelDemodDrag` | megosztott `demod-glue.js`(író)/`interaction.js`(`spectrumCanvas mousemove`/`window blur` is hívja `cancelDemodDrag`-et!) | mindkét irány | Az `interaction.js` mousemove-ja (2536. sor: `if (e.buttons === 0) { cancelDrag(); cancelDemodDrag(); }`) és a `window blur` listener (2531) is hívja a demod-glue `cancelDemodDrag`-jét — egyirányú importtal megoldható (`interaction.js` → `demod-glue.js`), de a `demodDrag` magát csak a demod-glue írja. |
| `lastContextFreq` | 577 | összes `ctx*` context-menü handler (`ctxCenter`,`ctxZoomIn`,…,`ctxDemodulate`) | `spectrumCanvas contextmenu` handler | `interaction.js` | `entities.js`(`ctxSaveMarker`/`ctxKnownSignal`/`ctxSuppressSignal`), `demod-glue.js`(`ctxDemodulate`), `view-state.js`(`ctxCenter`/`ctxZoomIn`/`ctxZoomOut`/`ctxReset`) | A context-menü gombkötések (3484–3493) MAGUK is szétszóródnak a célmodulok között funkció szerint, mind ugyanazt az `interaction.js`-ben élő `lastContextFreq`-et olvassák — export kell. |
| `demodHandlePx` | 2979(2586 a régi számozásban, ténylegesen ~2979) | `demodHitAt` | konstans, nem változik | `demod-glue.js` | — | Tisztán belső konstans. |
| `demodUpdateScheduler` | 3130–3162 | `scheduleDemodUpdateIfActive` | maga a `DemodPassband.createUpdateScheduler` hozza létre | `demod-glue.js` | — | Singleton, a `send` callback-je `apiClient.updateSdrangelDemod`-ot hívja — ha `demod-glue.js` külön fájl, ezt is importálnia kell az `api/api-client.js`-ből (ma is megteszi). |
| `sdrangelReadiness`, `activeSdrangelChannel` | 2966–2967 | `startSdrangelDemod`,`stopSdrangelDemod`,`refreshSdrangelReadiness` | ua. | `sdrangel-audio.js` | — | Tisztán belső a `sdrangel-audio.js`-nek. |
| `demodBandwidthDefaults` | 3495 | `sdrangelMode` `change` handler | konstans | `sdrangel-audio.js` (vagy `demod-glue.js`) | — | Duplikált adat: a `DemodPassband.DEFAULT_BANDWIDTHS` (a logikai modulban) UGYANEZEKET az értékeket tartalmazza máshogy elnevezve (`demod-passband.js:25-29`) — ez már MA is egy apró inkonzisztencia (két forrás, egy adat), érdemes lenne a kivágás során `DemodPassband.DEFAULT_BANDWIDTHS`-re cserélni `demodBandwidthDefaults` helyett, bár ez már nem "pusztán mozgatás", hanem tartalmi módosítás — jelzem, de NEM hajtom végre. |

## 7. Böngészőhang (browser audio)

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `browserAudioContext`, `browserAudioGain`, `browserAudioSocket`, `browserAudioNextTime`, `browserAudioSampleRate`, `browserAudioChunks`, `browserAudioPendingSamples`, `browserAudioClosing`, `browserAudioReceivedPacket`, `browserAudioSources` | 3258–3267 | egymás között, a `sdrangel-audio.js`-en belül | ua. | `sdrangel-audio.js` | `demod-glue.js` NEM nyúl hozzá direktben (csak a `startSdrangelDemod` hívja a `prepareBrowserAudio`-t, ami már a `sdrangel-audio.js` saját függvénye) | Tisztán belső állapot-csoport, nincs külső töréspont — ez támasztja alá, hogy a `sdrangel-audio.js` valóban a legbiztonságosabb kivágások közé tartozik a `viewport-glue.js`/`retention.js` mellett. |

## 8. Session / mérési munkamenet + Wi-Fi/Bluetooth panel cache

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `activeMeasurementSession` | 581 | `activeSessionLocationNameForBaseline`,`saveDeviceBaseline`,`compareDeviceBaseline`,`importKismetLive`,`importKismetAlerts`,`saveMarkerAt`,`saveKnownSignalAt`,`saveCurrentViewReference`,`exportObservationsCsv` | `renderMeasurementSession` | `session-and-data-tabs.js` | `entities.js`(marker/known-signal mentés), `spectrum-reference.js`(`saveCurrentViewReference`), bootstrap(`exportObservationsCsv`, BUTTONS szekcióban) | Sok olvasó, de mindegyik csak `?.id`-t kér ki — alacsony kockázatú, egyszerű export. |
| `viewedSession`, `viewedSessionReadOnly` | 582–583 | `refreshWifiPanel`,`refreshBluetoothPanel`,`updateSessionEmptyState` | `setViewedSession` | `session-and-data-tabs.js` | — | Tisztán belső a session-modulnak. |
| `wifiItemsByIdentity` | 740 | a `wifiObservationRows` click listener | `renderWifiObservations` | `session-and-data-tabs.js` | — | Belső. |
| `bluetoothItemsByIdentity` | 795 | a `bluetoothObservationRows` click listener | `renderBluetoothObservations` | `session-and-data-tabs.js` | — | Belső. |
| `retentionPreviewState` | 2359(eredeti),tényl. ~2752 | `btnRetentionPurge` handler | `retentionResetPreview`,`btnRetentionPreview` handler | `retention.js` | — | Belső, nincs külső függés — megerősíti, hogy `retention.js` biztonságos kivágás. |

## 9. Panel-toggle UI állapot

| Állapot | Sor | Olvassa | Írja | Célmodul | Kívülről hivatkozza | Javaslat |
|---|---|---|---|---|---|---|
| `spectrumControlPanel`, `spectrumControlPanelToggle`, `spectrumControlPanelStorageKey`, `mainElement`, `waterfallShell`, `waterfallPanel`, `waterfallPanelToggle`, `waterfallPanelStorageKey` | 585–592 | a toggle get/set/init függvények | ua. | `panel-toggles.js` | `spectrum-render.js`(mindkét toggle `resizeAll()`-t hív átméretezéskor) | Egyirányú függés (`panel-toggles.js` → `spectrum-render.js`), nem körkörös — biztonságos kivágás, leszámítva a 3. pontban (CUTMAP) jelzett `test_ui_static.py` szövegegyezést a storage-key-ekre. |

## 10. Konstansok (NEM megosztott mutable állapot, csak széles importigény)

`FULL_MIN`, `FULL_MAX`, `NUM_BINS`, `DBM_MIN`, `DBM_MAX`, `MIN_SPAN` —
ezek MÁR MA `ui/spectrum-scale.js`-ből importált `const`-ok (lásd
`index.html:399`), nem az inline modul saját állapota. Minden javasolt
célmodulnak ugyanúgy importálnia kell őket az `ui/spectrum-scale.js`-ből,
ahogy az inline modul is teszi — ez nem új töréspont, csak egy meglévő,
jól működő minta megismétlése minden új fájlban.

## 11. DOM-referencia cache (a `*Value`, `*Row`, `*Input`, `*Canvas` konstansok)

A 414–489. sorban ~75 `document.getElementById`/`querySelector` hívás
történik egyetlen helyen, és a kapott referenciákat csaknem minden
célmodul használja (pl. `sourceMessageValue` egyszerre kell a
`source-status.js`-nek ÉS a `viewport-glue.js`-nek, ld. CUTMAP 1.3).
**Ez nem állapot-ütközés, hanem egy közös erőforrás-gyorsítótár** — két
ésszerű megoldás:
1. A bootstrap/entry script továbbra is egy helyen kérdezi le MIND a
   DOM-elemeket, és paraméterként/objektumként adja át minden modul
   inicializáló függvényének (`initSpectrumRender({ spectrumCanvas, ... })`
   mintázat) — ez explicit, tesztelhető, de minden modulnak init-fázist
   igényel.
2. Minden modul maga hívja a saját `document.getElementById(...)`-jét a
   saját DOM-id-jeire — egyszerűbb, kevesebb boilerplate, de elszórja a
   DOM-szerződést sok fájlba, és duplikált lekérdezéseket eredményez
   (elhanyagolható teljesítményköltség, mert egyszer fut induláskor).
Ez egy holnapi döntés, ezt a dokumentum nem dönti el — csak jelzi, hogy
MINDEN célmodulnak szembe kell néznie vele, nem csak egynek-kettőnek.

## 12. Összefoglaló — körfüggés-rangsor

1. **`selectedReferenceSetId`/`selectedReferenceSet`** —
   `spectrum-reference.js` ↔ `session-and-data-tabs.js`. Súlyos, mert
   mindkét irányban van hívás (függvényhívás ÉS állapotolvasás).
2. **`mode` + `demodState.enabled`** — `view-state.js`/`interaction.js` ↔
   `demod-glue.js`. A `setMode('demod')` és a `modeDemod` gomb mindkét
   oldalt érinti.
3. **`waterfallBuffer`** — `view-state.js` és `spectrum-render.js` is
   közvetlenül null-ra állítja; export-függvénnyel (nem nyers írással)
   oldható fel.
4. **`maxHoldEnabled`** — a `ws-ingest.js` `acceptSweep`-je olvassa, de a
   `spectrum-render.js`/BUTTONS birtokolja; ha ez kimarad az exportból,
   a Max Hold "minden fülön frissül" viselkedés csendben elromlik
   (nincs hibaüzenet, csak hibás működés — ezért magas a néma-törés
   kockázata).
5. **`overviewAccumulator`** — ki birtokolja, `spectrum-render.js` vagy
   `ws-ingest.js`? Jelenleg egy harmadik, neutrális hely (a mai `STATE`
   szekció) tartja, ami a kivágás után is jó megoldás lehet
   (`view-state.js` vagy egy dedikált `spectrum-overview.js`).

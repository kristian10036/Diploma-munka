# Projekttörténet — korábbi riportok és fázis-promptok vázlatos összefoglalója

> Ez a fájl 16, mára lezárt/elavult riport- és specifikáció-dokumentumot
> vált fel egy rövid, vázlatos összefoglalóval (2026-06-25). A részletes
> eredeti szöveg a git history-ban megtalálható. Az AKTÍV, jelenleg is
> folyó refaktor állapotát a `MAJOR_REFACTOR_REPORT.md` követi —
> az nem ide tartozik. A holnapi `index.html`-szétbontás előkészítését a
> `REFACTOR_CUTMAP.md` / `REFACTOR_SHARED_STATE.md` / `REFACTOR_BASELINE.md`
> tartalmazza, azok sem ide tartoznak.

A projekt 2026-06-18 és 2026-06-25 között több, egymásra épülő
audit→specifikáció→implementáció→ellenőrzés körön ment át. Az alábbi lista
időrendben követi ezt; a legtöbb pontban leírt hiányosság és teendő mára
megvalósult (ahogy azt az aktuális kód és a mai `index.html`-elemzés is
megerősítette — pl. session-panel, Wi-Fi/Bluetooth/RF Agent/Felvételek/ML/
RAG/Rendszerállapot fülek, viewport controller, max hold, mind éles kódban
vannak, nem csak terv szinten).

## 1. `Phase.md` — eredeti projektspecifikáció (legacy)

A `Diploma_munka5_kismet_integrated` projekt eredeti, teljes átalakítási
prompt-ja: HP demógépen futó, később erősebb szerverre migrálható
architektúra, saját C++ RF agent, mock/replay/Aaronia/USRP backendek,
közös `SpectrumFrame` modell, Kismet/Bluetooth integráció, SDRangel,
Docker-rendrakás, backup/migráció, acceptance tesztek — 27 számozott pontban.
Ezt később a `phase1.md` több helyen korrigálta és felülírta (pl. az Aaronia
vendor library főfolyamatban való betöltését, az AVX2-alapú előzetes
blokkolást és a frekvenciatömbös `SpectrumFrame`-et). A `PHASE_COMPARISON.md`
pontonkénti döntési mátrixa szerint a hasznos célok megmaradtak, csak a
hibás részletek lettek elvetve.

## 2. `PROJECT_AUDIT.md` — kiindulási állapot-audit (2026-06-19)

A `Phase.md` 1. pontja (teljes projektfelmérés) alapján készült baseline
audit: futó szolgáltatások, komponensleltár, adatbázis-séma, Kismet/BLE
RSSI-normalizálási hiba (15 432 Wi-Fi sorból 0 normalizált RSSI-vel),
biztonsági és stabilitási hiányok, célarchitektúrától való eltérések.
Saját megjegyzése szerint elavult, a végállapotot a `FINAL_AUDIT.md` írja le.

## 3. `phase1.md` — korrigált, irányadó specifikáció (2026-06-19)

A `Phase.md` hibáit javító, akkor "current authoritative specification"
dokumentum: kötelező Aaronia-folyamatizoláció (`aaronia-probe`/
`aaronia-worker`, a vendor library soha nem fut a stabil főfolyamatban),
végleges (frekvenciatömb nélküli, számított tengelyű) `SpectrumFrame`-séma,
USRP-architektúra, FFT pipeline, `spectrum-ingest` service, RF agent REST/
WS API, recording/replay formátum, CNN-alapú RF-osztályozás, context-grounded
assistant vs. valódi RAG megkülönböztetés, SDRangel control/data plane
szétválasztás, stabilitási és biztonsági követelmények.

## 4. `PHASE_COMPARISON.md` — a két spec összehasonlítása (2026-06-19)

Pontonkénti döntési mátrix arról, mi marad meg a `Phase.md`-ből és mit ír
felül a `phase1.md`. Ez rögzítette, hogy ütközés esetén mindig a `phase1.md`
az érvényes, és hogy melyik régi követelmény (pl. opcionális RF MQTT
topicok, `deploy/systemd/rf-agent.service` minta) maradt érvényben
korrekció nélkül.

## 5. `PHASE_1_11_REVIEW.md` — az 1–11. pont implementációs felülvizsgálata (2026-06-19)

A `phase1.md` első 11 pontjának státusza akkori állás szerint: projekt-audit
és monorepo-struktúra `PARTIAL`, `main.py` modulokra bontása `BROKEN`,
végleges `SpectrumFrame` és mock backend `DONE`, USRP `NOT IMPLEMENTED`,
Aaronia C++ izoláció (probe/worker) `PARTIAL`. Saját megjegyzése szerint a
leírt hiányok egy része azóta elkészült, aktuális státusz a
`PHASE_PROGRESS.md`-ben.

## 6. `phase2.md` — "CODEX MASTER PROMPT", hardverfüggetlen véglegesítés (2026-06-19/20)

A következő nagy fázis specifikációja, A–O pontokban: backend
modularizálás, `SpectrumFrame`-kontraktus javítás, natív+overview spektrum,
spektrum UI rendrakás, tartós marker/ismert jel, referenciakezelés,
recording (spectrum/IQ/audio), SDRangel hardverfüggetlen előkészítés,
anomáliapipeline, alert/audit workflow, megfigyelhetőség, production
security, DB/teljesítmény, migráció, acceptance.

## 7. `PHASE2_IMPLEMENTATION_REPORT.md` — a phase2 A–O végrehajtási jelentése (2026-06-20)

A fenti A–O fázisok tényleges, hardverfüggetlen végrehajtásának összegzése:
a 4332 soros `main.py` 5 soros kompatibilis belépőpontra csökkent, a
legtöbb pont `implemented_tested` vagy `implemented_mock_tested` státuszú;
a valós Aaronia/USRP/SDRangel adatút végig `hardware_not_tested` maradt.
Backend unit: 49/49 PASS, offline acceptance: 0 failure.

## 8. `PHASE_PROGRESS.md` — konszolidált A–O állapottábla (2026-06-20)

A `PHASE2_IMPLEMENTATION_REPORT.md` és a `FINAL_AUDIT.md` állapotát egyetlen
táblába összesítő, "authoritative spec: phase2.md" jelzéssel ellátott
összefoglaló — ugyanazok a státuszok, kiegészítve a fő fülsor és az
automata ellenőrzések listájával, valamint a hardverfüggő nyitott
feladatokkal (Aaronia worker, USRP UHD, SDRangel valós adatút, ML tréning).

## 9. `FINAL_AUDIT.md` — végső implementációs audit (2026-06-20)

A phase2 hardver nélkül elvégezhető részeinek lezárását rögzítő audit:
részletes tesztállapot-tábla (backend 49/49, C++ CTest configure PASS, stb.)
és komponens-állapotmátrix (`implemented_tested` / `implemented_mock_tested`
/ `hardware_not_tested` / `not_trained` kategóriákkal). Felsorolja a
célgépen még kötelező lépéseket (Docker build/runtime, élő PostgreSQL,
C++ teljes build, valós hardver-aktiválás).

## 10. `PRODUCTION_READINESS_BASELINE.md` — produkciós baseline (2026-06-20)

A `phase2.md`-hez tartozó, Git nélküli könyvtárban felvett baseline:
szolgáltatás- és API-leltár, adatbázis-migrációk (001–010), észlelt
szerződéshibák (pl. a frontend `normalizeIncoming()` és a SpectrumFrame v1
objektum eltérése, amely hamis `-105 dBm` zajpadlót okozott volna),
módosítás előtti kompatibilitási alap (megőrzendő endpointok, 8 fő fül,
frame-formátumok).

## 11. `PRODUCTION_READINESS_REPORT.md` — produkciós készenléti jelentés (2026-06-20)

A `PRODUCTION_READINESS_BASELINE.md` után elkészült állapot: a SpectrumFrame-
kontraktushiba javítva, marker CRUD/ismertjel/referencia/recording/SDRangel-
mock/anomáliapipeline/megfigyelhetőség/security/migráció/backup mind
hardverfüggetlenül `implemented_tested` vagy `implemented_mock_tested`.
Listázza a célgépen még kötelező lezáró lépéseket.

## 12. `LIVE_STABILIZATION_BASELINE.md` — élő Aaronia-baseline (2026-06-22)

Az első valódi Git-repóval és élesben futó Aaronia SPECTRAN V6 hardverrel
felvett baseline: konkrét élő SpectrumFrame-mérések (RBW ~361.6 kHz, 16 384
pont, FPS ~5–6.5, drop/sequence-gap statisztikák), API-kompatibilitási
baseline (104 path/113 művelet), és a következtetés, hogy a hardveres
viewport ekkor még csak kézi tartományalkalmazáskor retune-olt (wheel/pan/
dblclick/select/overview még nem) — ez a hiány indította el a viewport
controller munkát, amely mára (ld. `viewport-controller.js` +
`tests/frontend/test_viewport_wiring.js`) elkészült.

## 13. `LIVE_STABILIZATION_CHECKPOINT.md` — biztonsági visszaállási pont (2026-06-23)

Egy konkrét live-stabilizálási munkamenet közbeni checkpoint: az Aaronia
hardveres retune-kísérletek a worker leállását okozták, ezért a kód
visszaállt az utolsó ismert stabil élő állapotra, és a checkpoint
rögzítette a biztonságos folytatási sorrendet (előbb production-only
synthetic-fallback gating, csak utána újabb retune-diagnosztika, és csak
azután a frontend viewport controller bekötése).

## 14. `codex_plan.md` — Wi-Fi/Bluetooth session és referencia UI-egyszerűsítés (lezárva)

Specifikáció a session- és referencia-fogalom szétválasztására: új session
indításakor ürüljenek a listák, helyszínnév önmagában soha ne indítson
automatikus baseline-összehasonlítást, csak explicit kiválasztott
`reference_set_id` vagy importált fájl adhat referenciajelölést, 13
elfogadási teszttel. Ez a terv a memória-feljegyzés és a mai `index.html`-
elemzés szerint mindkét fázisában elkészült és élesben ellenőrzött (ld.
`viewedSession`, `selectedReferenceSetId`, `requireSession`,
`missingReferenceDevicesHtml` a jelenlegi kódban).

## 15. `modositasok.md` — viewport-bekötés utómunkái (lezárva)

Három apró csiszolási feladat (P1.1–P1.3) a már kész viewport-bekötéshez:
üres select-kattintás ne indítson retune-t (ez a mai
`tests/frontend/test_viewport_wiring.js`-ben tesztelt eset), dedikált
felbontás-readout (a mai `resolutionReadout` elem), és a capabilities
frissítése forrásváltáskor. A P1.1 eset bizonyíthatóan implementálva és
tesztelve van a jelenlegi kódban.

# Phase megvalósítási állapot

Utolsó frissítés: 2026-06-20

Az authoritative specifikáció a `phase2.md`. A korábbi phase1 eredmények
megmaradtak; az alábbi állapot a tényleges forráskódot és a jelenlegi teszteket
követi.

## Phase2 A–O

| Fázis | Állapot | Eredmény |
|---|---|---|
| A – backend modularizálás | `implemented_tested` | A korábbi 4332 soros `main.py` 5 soros kompatibilis entrypoint. Route, runtime, DB, schema, monitoring, recording, reference, SDRangel és anomaly modulok külön fájlokban; legnagyobb Python modul 800 sor alatt. |
| B – SpectrumFrame kontraktus | `implemented_tested` | v1 és legacy adapter, Hz belső tengely, invalid/non-finite elutasítás, sequence-gap és stale kezelés; nincs hamis `-105 dBm` kitöltés. |
| C – natív detail + overview | `implemented_mock_tested` | natív frame, peak-preserving min/max envelope, külön timestampelt overview és mock viewport-szerződés. Valós Aaronia/USRP ROI: `hardware_not_tested`. |
| D – spektrum UI | `implemented_tested` | Csoportosított magyar toolbar, egységes modalok, context menü; a felső nyolc fő fül változatlan. |
| E – marker/ismert jel | `implemented_tested` | CRUD, archiválás, audit, profilalapú egyezés és csak megfelelő egyezésnél alert suppression. |
| F – referencia | `implemented_tested` | Verziózott JSON/CSV inspect/import/list/detail/activate/deactivate/export, checksum és peak-preserving resampling. Direkt `.peak`: `unsupported`. |
| G – recording | `implemented_mock_tested` | Spectrum kompatibilis; SigMF IQ és WAV audio atomikus writer/reader, checksum, tárhelyvédelem, dry-run retention és orphan audit. |
| H – SDRangel | `implemented_mock_tested` / `configured_not_tested` | REST control, biztonságos UI gating, bounded IQ data-plane absztrakció és mock source/sink. Valós plugin/adatút: `not_configured` vagy `hardware_not_tested`. |
| I – anomaly/ML | `implemented_tested` | Bounded online median/MAD pipeline, technikai és RF szabályok, Wi-Fi/BLE passzív szabályok, review. Valós klasszikus/CNN modell: `not_trained`. |
| J – alert/audit | `implemented_tested` | open/acknowledged/resolved életciklus, deduplikáció, megjegyzés és audit API/UI. |
| K – megfigyelhetőség | `implemented_tested` | liveness/readiness/status, JSON log, request ID, Prometheus metrikák és saját UI. Grafana nincs. |
| L – production security | `implemented_tested` | demo/production profil, fail-fast, viewer/operator/admin token mód, írásaudit, proxy headerek, korlátozott feltöltés, fájlszignatúra-validáció és belső service-portok. |
| M – DB/teljesítmény | `implemented_mock_tested` | checksumos migrációfuttató, forward migrációk, stabil cursor pagination, fő indexek, orphan audit és reprodukálható mock load fixture. Élő DB terhelés: `configured_not_tested`. |
| N – migráció | `implemented_tested` | kibővített preflight, systemd minták, offline image/backup/restore folyamat és jogosultság-ellenőrzés. |
| O – acceptance | `implemented_tested` | Egy fő offline/online belépési pont, backend/ingest/frontend/security/load/static invariant tesztek. Docker runtime ebben a környezetben nem futott. |

## Fontos változatlan elemek

- A fő fülsor sorrendje és jelentése változatlan:
  **Spektrum, Wi-Fi / Kismet, Bluetooth / BLE, RF Agent, Felvételek,
  ML osztályozás, RAG, Rendszerállapot**.
- Működő endpoint, recording, volume, dokumentáció és hardverintegrációs váz nem
  lett törölve.
- Törlés csak generált cache-re (`__pycache__`, `.pyc`, ideiglenes build/cache)
  vonatkozik.
- `.peak` fájlhoz nincs kitalált parser; OSCOR-exportból CSV/JSON használható.
- Mock/replay mindenhol egyértelműen szimuláltként jelölt.

## Automata ellenőrzések

- backend Python unit: **49/49 PASS**;
- spectrum-ingest unit: **PASS**;
- Python compile: **PASS**;
- SpectrumFrame/view-model Node fixture: **PASS**;
- frontend inline/külső JavaScript syntax: **PASS**;
- statikus UI smoke és fő fülsor invariant: **PASS**;
- offline mock load fixture: **PASS**;
- shell syntax és production fail-fast: **PASS**;
- offline acceptance: **PASS, 0 failure**.

A teljes Docker runtime, élő PostgreSQL-migráció és C++ rebuild nem volt
elérhető ebben a szerkesztési környezetben; ezeket a célgépen kell lefuttatni.

## Hardverfüggő nyitott feladatok

- Aaronia SPECTRAN V6 folyamatos worker és hitelesített adatút;
- USRP UHD RX/FFT worker, overflow és többeszközös PPS/GPSDO szinkron;
- SDRangel kiválasztott input/plugin és valós IQ/audio adatút;
- valós, címkézett RF recordingokon modelltréning;
- hardveres teljesítmény- és acceptance mérés.

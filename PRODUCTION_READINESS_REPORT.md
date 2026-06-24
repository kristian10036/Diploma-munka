# Production readiness jelentés

Dátum: 2026-06-20

## Összegzés

A rendszer hardver nélkül produkcióközeli, migrálható alkalmazási alapra lett
rendezve. A működő funkciók és a felső Spektrum / Wi‑Fi / Bluetooth / RF Agent /
Felvételek / ML / RAG / Rendszerállapot fülsor megmaradt. A korábbi több mint
4000 soros backend entrypoint 5 soros kompatibilitási belépőpont lett; a domain
route-ok, sémák, adatbázis, runtime, import, recording, SDRangel és anomália
rétegek külön modulokban vannak. A legnagyobb Python modul 800 sor alatt van.

## Hardverfüggetlenül elkészült

- SpectrumFrame v1/legacy adapter, hiányzó pontok `NaN` szemantikával;
- natív detail és külön overview adatmodell, peak-preserving decimálás;
- marker CRUD, ismertjel-profil és tulajdonság-alapú suppression;
- verziózott JSON/CSV referenciaimport/export;
- kontrollált `.peak` unsupported válasz;
- spectrum recording kompatibilitás, SigMF IQ és WAV audio mock writer/reader;
- SDRangel control UI és verziózott IQ data-plane absztrakció/mock;
- bounded online spektrumanomália pipeline;
- Wi‑Fi/BLE passzív anomáliaszabályok;
- detection review, alert lifecycle és audit;
- liveness/readiness/status;
- strukturált JSON log és request ID;
- offline Prometheus, saját Rendszerállapot UI, Grafana nélkül;
- production fail-fast és tokenes operator/admin írásvédelem;
- verziózott migrációfuttató, checksum-ellenőrzés, cursor pagination és destruktív védelem;
- backup/restore, orphan audit és kibővített célgép-preflight;
- offline acceptance belépési pont és reprodukálható mock terhelési fixture.

## Teszteredmény

- backend Python unit: **49/49 PASS**;
- spectrum-ingest unit: **PASS**;
- Python compile: **PASS**;
- külső és inline frontend JavaScript syntax: **PASS**;
- Compose YAML statikus parse: **PASS**;
- shell syntax: **PASS**;
- production hibás kritikus konfiguráció fail-fast: **PASS**;
- offline acceptance: **PASS, 0 failure**.

A teljes Docker runtime acceptance és élő PostgreSQL-migráció ebben a szerkesztési
környezetben nem futott, ezért ezt nem állítjuk igazoltnak. A C++ forrás CMake/
Docker buildje a célgépen vagy megfelelő fejlécekkel külön futtatandó.

## Állapotmátrix

| Komponens | Állapot |
|---|---|
| Backend modulárisítás | `implemented_tested` |
| SpectrumFrame/overview/frontend | `implemented_tested` |
| Marker/known signal | `implemented_tested` |
| Reference JSON/CSV | `implemented_tested` |
| `.peak` direkt parser | `unsupported` |
| Spectrum recording/replay | `implemented_mock_tested` |
| IQ SigMF/audio WAV | `implemented_mock_tested` |
| Prometheus offline monitoring | `implemented_tested` kódszinten |
| Grafana | szándékosan nincs használatban |
| SDRangel control | `configured_not_tested` vagy `disabled` |
| SDRangel IQ data plane | `implemented_mock_tested`, valós plugin `not_configured` |
| Aaronia/USRP valós data plane | `hardware_not_tested` |
| Statisztikai anomáliadetektor | `implemented_tested` |
| Klasszikus ML/CNN valós modell | `not_trained` |
| RAG/Ollama | konfigurációtól függően `disabled`, `ready_empty` vagy `ready` |
| Production auth | `implemented_tested` konfigurációs szinten |
| Teljes hardveres acceptance | `hardware_not_tested` |

## Kötelező célgépes lezárás

1. `bash scripts/pre-migration-check.sh`
2. `bash scripts/acceptance-test.sh --offline`
3. `docker compose ... config`
4. backup és checksum;
5. teljes image build és CTest;
6. stack indítás, migráció, online acceptance;
7. Aaronia/USRP/SDRangel egyenkénti hardveres aktiválás;
8. terhelési mérés valós frame-mérettel;
9. valós, címkézett recordingokon ML tréning.

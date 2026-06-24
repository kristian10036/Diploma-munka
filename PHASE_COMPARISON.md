# Fejlesztési specifikációk összehasonlítása

Készült: 2026-06-19

## Elsőbbség és fájlazonosítás

- `Phase.md` – legacy/original specification.
- `phase1.md` – current authoritative specification (a feladatban említett `Phase1.md` a fájlrendszerben kisbetűs néven található).

Érvényes sorrend: `phase1.md` → működő kód és tesztek → `Phase.md` → egyéb régi dokumentáció. Ütközésben mindig a `phase1.md` érvényes. A `Phase.md` auditcélból a projekt gyökerében marad; archiválására ebben a fázisban nincs elegendő alap.

## Összefoglaló

A két specifikáció közös célja egy hardver és AI nélkül is működő HP-demó, valamint ugyanabból a monorepóból migrálható hardveres rendszer. A `phase1.md` megtartja ezt a célt, de biztonsági és adatmodell-korrekciókat ír elő: az Aaronia vendor library kizárólag izolált probe/worker folyamatban tölthető be; az AVX2 hiánya csak diagnosztika; a `SpectrumFrame` nem visz frekvenciatömböt; a Kismet RSSI nem CNN-spektrogram; az SQL-kontextus nem nevezhető RAG-nak; az SDRangel REST control plane és az IQ data plane külön állapot.

## Egyező követelmények

| Terület | Közös követelmény | Jelenlegi állapot |
|---|---|---|
| Alapelv | Meglévő rendszert fokozatosan javítani, működő részeket megőrizni | Követendő; újraírás nem történt |
| Platform | HP Debian demó, későbbi erős Linux szerverre konfiguráció-alapú migráció | Dokumentált cél, migráció még nincs implementálva |
| Modularitás | Core/RF/AI/dev Compose szétválasztás; RF és AI ne legyen core-függőség | Fájlok és a core `spectrum-ingest` léteznek; RF/AI opcionális |
| RF agent | C++17/20 agent, közös source absztrakció, mock/replay/Aaronia/USRP | C++ agent, mock és replay van; hardveres backends hiányosak |
| Mock | Szimulált zaj és jelek, egyértelmű `is_simulated`, soha ne legyen hardvernek címkézve | Implementált és unit tesztelt a végleges sémával |
| Replay | Verziózott recording, pause/resume/seek/loop és engedélyezett sebességek | Részben implementált és unit tesztelt; recording írás/API hiányzik |
| IQ | Ne kerüljön nagysebességű IQ PostgreSQL-be; közös modell és opcionális stream | Modell van; recording/data plane nincs |
| Kismet | Wi-Fi/Bluetooth funkció és RSSI megőrzése, több source | Kód létezik; új sorokra vonatkozó SQL-bizonyítás hiányzik |
| Tárolás | Metadata PostgreSQL-ben, nagy bináris/recording fájlrendszerben | Korai DB-séma van; recording/ML metadata hiányos |
| Stabilitás | `unless-stopped`, healthcheck, egyszeri migrate, logrotáció | A jelenlegi Compose nagyrészt megfelel; teljes health coverage nincs |
| Adatvédelem | Volume, PostgreSQL, Kismet, upload és recording nem törölhető | Megőrzendő; cleanup script még nincs |
| Backup/migráció | Védett backup/restore és forrásátírás nélküli költözés | Nem implementált |
| Hardverstátusz | Hiányzó hardver ne tegye unhealthyvé a mock/replay rendszert | Izolált probe és státusz API van; worker még nincs |
| Dokumentáció | Implementált, tesztelt, skeleton és nem tesztelt állapotok elkülönítése | Részben teljesül; több kötelező dokumentum hiányzik |

## A `phase1.md` által módosított vagy felülírt követelmények

| Régi követelmény | Aktuális korrekció | Döntés |
|---|---|---|
| Az AVX2 runtime ellenőrzés megakadályozhatja az Aaronia indulását; HP-n `unsupported_cpu` várható | Az AVX2 csak diagnosztika. Az SDK-t izolált `aaronia-probe` folyamatban ténylegesen ki kell próbálni, eredménye lehet például `library_sigill` vagy `sdk_ready` | Régi előzetes blokkolás elvetve |
| `AaroniaRfSource` közvetlenül linkelheti/töltheti a vendor SDK-t | A stabil `rf-agent` nem töltheti be; külön `aaronia-probe` és felügyelt `aaronia-worker` kötelező | Régi architektúra tiltott |
| C++ exception és egyszerű `dlopen()` elegendő lehet hibakezeléshez | `SIGILL`, `SIGSEGV` és más natív crash csak processzhatárral izolálható; timeout/signal/exit/stdout/stderr feldolgozás kell | `phase1.md` az irányadó |
| `ENABLE_AARONIA=ON` esetén SDK hiánya CMake fatal error | A helper/probe build működjön SDK nélkül is, a probe adjon `sdk_not_found` állapotot; hardver auto-start ettől független | Régi kötelező linkerhiba elvetve |
| `SpectrumFrame` tartalmazza a `frequencies_hz` tömböt | Végleges séma: `step_frequency_hz`, `num_points`, `power_unit`, `flags`; frekvencia számítható, csak `powers_dbm` tömb van | Régi séma felülírva |
| FFT a régi terv 10. pontja | Az auditált 1–11 után a következő fejlesztési pont; részletes komponensekkel és generált jel/zaj tesztekkel | Aktuális sorrend követendő |
| SDRangel „integráció” egységes funkció | Control plane REST és data plane IQ külön; egyik sikere nem bizonyítja a másikat | Régi összemosás elvetve |
| HP demo `ENABLE_AARONIA=false` | `ENABLE_AARONIA=true` lehet azért, hogy a probe elérhető legyen; `AARONIA_AUTO_START=false` | Aktuális demo-konfiguráció az irányadó |
| Ollama/AI előkészítés általánosan | Strukturált SQL kontextus = context-grounded assistant; valódi RAG csak embeddinggel, indexszel, chunkinggal és retrievallel | Pontos elnevezés kötelező |
| Kismet RSSI használható általános RF ML-adatként | Kismet RSSI nem spektrogram és nem közvetlen CNN-bemenet; csak kontextus/weak label/validáció | Régi implicit értelmezés tiltott |
| USRP közvetlen backend megfelelő | Worker processz megengedett/ajánlott, hogy UHD-hiba ne döntse be az agentet | Izoláltabb aktuális architektúra előnyben |
| Általános logging `driver: local` | Kötelező `max-size: 10m`, `max-file: 3` opciókkal | Új követelmény pontosít |
| Régi fejlesztési sorrend szerint a hardver skeleton későbbi | Előbb 1–11 audit és javítás, majd Aaronia izoláció, FFT, ingest, API, recording, ML és további integrációk | `phase1.md` sorrend kötelező |

## Kizárólag a `Phase.md` fájlban szereplő követelmények

Az alábbi régi pontok nem ütköznek az új specifikációval, ezért megőrzendők, hacsak a megvalósítás során a működő rendszer mást nem bizonyít.

| Követelmény | Miért hasznos | Komponens | Ütközés | Illeszkedés | Új implementáció |
|---|---|---|---|---|---|
| Opcionális RF MQTT topicok (`rf/spectrum/frame`, peak/status/error/recording/SDRangel) | Aszinkron integráció és monitorozás | RF agent, Mosquitto | Nincs | Opcionális adapterként, a WS mellett | Igen |
| Bináris/tömörített spectrum transport előkészítése | Sávszélesség és CPU skálázás | RF agent, ingest | Nincs | Verziózott transport negotiation | Igen, később |
| `deploy/systemd/rf-agent.service` minta | Natív hardveres telepítés | Deployment | Nincs | Ugyanazt az env-alapú agentet indítja | Igen |
| HP erőforráskorlátok dokumentálása | Régi gép stabilitása | Compose/docs | Nincs | Profilhoz kötött ajánlások, nem irreális hard limit | Igen |
| Exportok, audio, PCAP és `.kismet` fájlok explicit fájlrendszeres kezelése | DB növekedés és visszaállíthatóság | Storage/backup | Nincs | Host-path/env és metadata katalógus | Részben/igen |
| `scripts/export-diagnostics.sh` | Hibajegyhez reprodukálható állapot | Operations | Nincs | Read-only diagnosztikai export, titokszűréssel | Igen |
| Peak/marker/zoom/pan/max-hold UI megőrzése | Meglévő demóérték | Frontend | Nincs | Aktuális UI kompatibilitási követelmény | Többsége már van; regresszióteszt kell |
| MQTT ellenőrzése acceptance tesztben | A broker tényleges readinessét bizonyítja | Acceptance | Nincs | Opcionális feature-státusz szerint | Igen |
| Kismet `.kismet` fájl mentésének és több source-nak ellenőrzése | Forenzikus nyersadat-megőrzés | Kismet | Nincs | Meglévő volume és collector mellett | Teszt/dokumentáció kell |
| Docker image/network/cache tételes auditja | Biztonságos tárhelykezelés | Operations | Nincs | Projektcímkék és dry-run alapján | Igen |

## Kizárólag a `phase1.md` fájlban szereplő követelmények

- Kötelező `PHASE_1_11_REVIEW.md`, státuszokkal és API/WS változáskövetéssel.
- API OpenAPI snapshot, WebSocket karakterizáció és `tests/api`, `tests/websocket`, `tests/integration` struktúra.
- Kismet RSSI bizonyítása kizárólag újonnan importált sorokon és konkrét aliaslista támogatása.
- `rf-agent` / `aaronia-probe` / `aaronia-worker` processzarchitektúra, signal- és timeout-feldolgozással.
- Aaronia dokumentált híváslánc, RAII, idempotens shutdown és saját error mapping.
- Végleges tömörített `SpectrumFrame`, `flags`, `num_points`, `step_frequency_hz`, `power_unit`.
- Részletes FFT komponensek, dropped-frame statisztika és sinus/zaj/DC/NaN tesztek.
- Ingest bounded queue, slow-client policy, reconnect backoff és kötelező metrikák.
- Strukturált RF API hibaobjektum, Aaronia/USRP státusz és `/ws/status`.
- Recording checksum, zstd, eredeti timestamp-időzítés és sérült frame kihagyás.
- RF ML baseline + klasszikus ML + kis CNN, session/recording szintű split és mérőszámok.
- Context-grounded assistant és valódi RAG szigorú megkülönböztetése.
- SDRangel control/data plane külön dokumentuma és frontend aktiválási kapuja.
- ML modellek/dataset backupja és migrationje.
- RF Agent, Recordings és ML frontend tab részletes operációs állapotokkal.
- Végső `IMPLEMENTATION_REPORT.md`, állításonként bizonyítékkal.

## Ellentmondások és feloldásuk

1. **Aaronia CPU-kezelés:** a régi terv AVX2 hiányából `unsupported_cpu` állapotot vezetne le; az új terv izolált valós probe-ot követel. Feloldás: CPUID csak diagnosztika, a subprocess probe eredménye dönt.
2. **Vendor library betöltés:** a régi backend közvetlen SDK-integrációja összeegyeztethetetlen a főfolyamat crash-biztonságával. Feloldás: kizárólag helper processz tölti be.
3. **Spectrum schema:** a régi specifikáció frekvenciatömböt használ, az új végleges séma számított tengelyt. Feloldás: a C++ wire schema már migrált; a frontend adapter őrzi a régi pontlistát.
4. **HP Aaronia alapérték:** régi `false`, új `true` probe-célból. Feloldás: build/probe engedélyezett, auto-start tiltott.
5. **AI/RAG:** a régi dokumentáció korai embedding táblái vagy keyword endpointja nem bizonyít RAG-ot. Feloldás: jelenleg nem implementált context-grounded assistantként sem tekinthető késznek.
6. **SDRangel:** REST vezérlés nem IQ továbbítás. Feloldás: külön readiness és dokumentált data-plane skeleton.
7. **Pontszámozás:** a régi FFT/IQ a 10–11. pont, az új 1–11 auditlista más bontást használ és az FFT az új munka első következő pontja. Feloldás: a `phase1.md` számozása és kötelező munkasorrendje érvényes.

## Régi követelmények megtartása vagy elvetése

### Teljes legacy követelmény-döntési mátrix

Az alábbi mátrix a `Phase.md` összes számozott fejezetét lefedi. A „megtartás” nem jelenti a régi megoldás változatlan átvételét: csak a szakmailag hasznos cél marad meg, a megvalósítás minden esetben a `phase1.md` korrekciói szerint történik.

| Phase.md pont és átvett követelmény | Miért hasznos | Komponens | Ütközik a Phase1.md-vel? | Illeszkedés a jelenlegi architektúrába | Új implementáció szükséges? | Döntés |
|---|---|---|---|---|---|---|
| Bevezetés: HP-demó és konfigurációval migrálható monorepo, meglévő működés megőrzése | Kizárja a költséges újraírást és a hardverfüggő core-t | Teljes rendszer | Nem; a Phase1 megerősíti | Core + opcionális RF/AI overlay | Részben | Megtartandó |
| Hardverkörnyezet: i5-2540M, Debian, AVX2 nélkül; későbbi modern RF gép | Reális teljesítmény- és kompatibilitási korlát | Deployment/RF | Részben: az „RTSA biztosan nem fut” állítás ütközik | CPU feature csak diagnosztika, izolált probe dönt | Probe elkészült; valós init teszt kell | Cél megtartandó, előzetes ítélet elvetendő |
| 1. Teljes projekt-audit és komponenskategorizálás | Megelőzi a hasznos vagy perzisztens elemek törlését | Operations/docs | Nem | `PROJECT_AUDIT.md`, `PHASE_1_11_REVIEW.md` | Folyamatos frissítés kell | Megtartandó |
| 1. Csak bizonyítottan duplikált/nem használt elem törölhető | Adat- és regresszióvédelem | Operations | Nem | Cleanup kizárólag projekt-szűrt dry-run/apply lehet | Cleanup script még kell | Megtartandó |
| 2. Ajánlott monorepo-struktúra és kontrollált mozgatás | Átlátható build/deploy határok | Repo/build | Nem | Meglévő `rf-agent`, `database`, `docker`, `config`, `tests`; további könyvtárak fokozatosan | Igen, hiányzó modulokhoz | Megtartandó |
| 3. Core/RF/AI/dev Compose-felosztás | A core hardver és AI nélkül indul | Compose | Nem | A négy Compose fájl létezik; ingest még hiányzik | Részben | Megtartandó |
| 3. Core service-lista spectrum-ingesttel | Stabil egységes frontend adatút | Compose/ingest | Nem | Az ingest a core-ban van, RF agent opcionális upstream | Nem; implementált | Megtartandó |
| 4. C++17/20 `rf-agent`, közös `IRfSource`, env source-választás | Hardverfüggetlen üzleti felület | RF agent | Nem | `IRfSource`, mock/replay és manager létezik | Aaronia/USRP worker adapter kell | Megtartandó |
| 4. REST/WebSocket/MQTT, recording és diagnosztika az agentben | Egységes RF control/data felület | RF agent | Nem; Phase1 részletezi | REST/WS részleges, MQTT/recording hiányzik | Igen | Megtartandó |
| 5. Gazdag mock jelgenerátor, explicit szimulációs címkézés | Hardver nélküli reprodukálható demó és teszt | Mock backend | Nem | Implementált, végleges frame sémával | Nem, csak további regresszióteszt | Megtartandó |
| 6. Replay lifecycle, sebességek, verziózott zstd/NDJSON/checksum formátum | Reprodukálható HP-demó és offline elemzés | Replay/recording | Nem | Reader és lifecycle részben kész | Writer, DB metadata, timestamp timing kell | Megtartandó |
| 7. Opcionális Aaronia támogatás, dokumentált SDK-források, hamis adat tiltása | Biztonságos későbbi SPECTRAN integráció | Aaronia | Részben | Csak probe/worker processz tölthet vendort | Worker és packet út kell | Korrigálva megtartandó |
| 7. AVX2 runtime ellenőrzés és `unsupported_cpu` előzetes blokkolás | Diagnosztikai információ hasznos | Aaronia | Igen: Phase1 szerint a probe-ot nem blokkolhatja | CPUID a probe JSON része, de nem dönt önmagában | Diagnosztika kész | Diagnosztika megtartandó, blokkolás elvetendő |
| 7. `ENABLE_AARONIA=ON` esetén SDK-hiányos teljes CMake hiba | Korábban buildhibával jelezte volna a hiányt | Build | Igen | Core/mock/replay és probe SDK nélkül is buildeljen | Már korrigálva | Elvetendő |
| 7. Közvetlen `AaroniaRfSource` vendor betöltés | Egyszerű adapter lett volna | Aaronia | Igen, natív crash miatt veszélyes | Főfolyamat helyett probe/worker IPC | Worker kell | Elvetendő architektúra |
| 8. Modellfüggetlen UHD/USRP discovery, konfiguráció, IQ és FFT | Több Ettus eszköz támogatása | USRP worker | Nem; Phase1 izolációt is enged | Opcionális worker + közös IQ/FFT | Igen | Megtartandó |
| 9. Közös spektrum wire modell és szigorú validáció | Backendfüggetlen ingest/front-end | Data model | Igen, a régi frekvenciatömböt Phase1 felülírja | Végleges számított tengelyű séma implementált | Nem | Cél megtartandó, régi séma elvetendő |
| 10. FFT size/window/DC/dBFS/calibration/average/max hold/peak/FPS | Közös és tesztelhető IQ→spektrum feldolgozás | DSP | Nem; Phase1 részletezi | `rf_agent::dsp` pipeline implementált | IQ source bekötés kell | Megtartandó |
| 11. IQ ne kerüljön PostgreSQL-be; fájl/stream opcionális, metadata DB-ben | Megakadályozza a DB túlterhelését | IQ/storage | Nem | Közös `IqFrame`; filesystem data plane lesz | Recording/stream metadata kell | Megtartandó |
| 12. SDRangel REST vezérlési előkészítés és disabled HP mód | Későbbi demoduláció | SDRangel | Részben: data plane nem azonos a REST-tel | Külön control service és dokumentált IQ data-plane skeleton | Igen | Control cél megtartandó, összemosás elvetendő |
| 13. RF REST endpointok és `/ws/spectrum` | Operálható, forrásfüggetlen agent | RF API | Nem; Phase1 bővíti | Teljes route-felület, `/ws/spectrum`, `/ws/status` és strukturált hibák contract tesztelve | Recording control mögötti writer még kell | Megtartandó |
| 13. Opcionális MQTT RF topicok | Aszinkron monitorozás és integráció | MQTT | Nem | Mosquitto opcionális publisher adapter | Igen | Megtartandó |
| 13. Bináris/tömörített transport előkészítése | Nagyobb FPS és kisebb hálózati költség | RF/ingest | Nem | JSON v1 után verziózott opcionális codec | Igen, később | Megtartandó |
| 14. Külön spectrum-ingest reconnecttel, validációval, gap/FPS/latency méréssel | Leválasztja az upstream RF hibákat a frontendről | Spectrum ingest | Nem; Phase1 bounded queue-val bővíti | Core service, egységes frontend WS; mockkal tesztelt | Recording integráció még kell | Megtartandó |
| 15. Metadata PostgreSQL-ben, teljes RF/IQ/audio/PCAP/Kismet fájlrendszerben | Skálázható és menthető tárolás | DB/storage | Nem; Phase1 ML elemekkel bővíti | Env-alapú host rootok + metadata migráció | Részben | Megtartandó |
| 16. Kismet Wi-Fi/Bluetooth, RSSI, több source és meglévő frontend megőrzése | Megőrzi a működő adatgyűjtést | Kismet/backend/frontend | Nem | Collector és endpointok léteznek; contract/regresszió kell | Részben | Megtartandó |
| 16. Kismet RSSI implicit RF-adatként való használata | — | ML | Igen, nem spektrogram | Csak kontextus/weak label/validáció | ML pipeline kell | Közvetlen CNN-bemenetként elvetendő |
| 17. Ugyanaz az agent Dockerben és natívan, env-konfigurációval | Migrálhatóság és hardverhozzáférés | Deployment | Nem | Dockerfüggetlen C++ logika | Natív build/docs kell | Megtartandó |
| 17. systemd service minta | Stabil natív production futtatás | Deployment | Nem | `deploy/systemd` alatt env file-lal | Igen | Megtartandó |
| 18. Read-only Docker audit és dry-run cleanup, volume törlés tiltása | Perzisztens adatok védelme | Operations | Nem | Projekt label/name szűrés; `--apply` explicit | Igen | Megtartandó |
| 19. Restart/health/dependency/migrate/logrotáció | Megakadályozza a restart loopot és végtelen logot | Compose | Nem; Phase1 pontosítja a kivételeket és logméretet | Compose extension és service-specifikus health | Részben | Megtartandó |
| 19. HP erőforrásajánlások, nem irreális limitek | Stabil demó régi gépen | Ops/docs | Nem | Dokumentált profil; FFT 2048/5 FPS | Igen, dokumentáció | Megtartandó |
| 20. HP demo env és teljes mock/replay webes funkció | Egyparancsos iskolai bemutató | Config/demo | Részben: Aaronia false helyett probe true, autostart false | `config/hp-demo.env`, opcionális probe | Igen | Korrigálva megtartandó |
| 21. Titokmentes production hardware env | Biztonságos migrációs kiindulás | Config | Nem; Phase1 AI/ML értékeket bővít | Példakonfig, valódi secret nélkül | Igen | Megtartandó |
| 22. PostgreSQL/Kismet/uploads/recording/export/config backup checksumokkal | Katasztrófa utáni helyreállítás | Backup | Nem; Phase1 ML-t is hozzáad | Read-only gyűjtés, védett `.env` | Igen/részben | Megtartandó |
| 22. Git commit hash kötelező backup mező | Reprodukálhatóság | Backup | Nem tartalmi ütközés, de Git kihagyását kérte a felhasználó | `unavailable`/opcionális provenance mezővel | Dokumentációs korrekció | Feltételesen megtartandó, nem blokkoló |
| 23. Forrásátírás nélküli HP→szerver migráció | Csökkenti az átállási kockázatot | Migration | Nem | Env/native deps/build flags/restore | Igen | Megtartandó |
| 24. Nem destruktív acceptance teszt teljes stack és opcionális hardver státuszokra | Bizonyítható átadás | QA | Nem; Phase1 ML/probe-val bővíti | Feature-aware PASS/SKIP/FAIL | Igen | Megtartandó |
| 25. Operációs dokumentáció és indítási parancsok | Megismételhető üzemeltetés | Docs | Nem | Aktuális Compose és státuszcímkék szerint | Igen/részben | Megtartandó |
| 26. Inkrementális fejlesztési sorrend, minden nagy lépés után teszt | Regressziók korai felismerése | Process | Igen a pontos sorrendben | A Phase1 kötelező sorrendje érvényes | Nem kód | Régi sorrend elvetendő, elv megtartandó |
| 27. Volume/adat/hardver/AI/UI biztonsági tiltások | Kritikus adat- és hitelességvédelem | Teljes rendszer | Nem; Phase1 bővíti | Minden script/API/Compose döntés kapuja | Folyamatos | Megtartandó |
| 28. Bizonyíték-alapú végső jelentés | Auditálható átadás | Docs/QA | Nem; Phase1 részletesebb reportot kér | `IMPLEMENTATION_REPORT.md` fájlút/parancs/teszt bizonyítékokkal | Igen | Megtartandó |

### Összevonási kapu alkalmazása

Minden „megtartandó” sor ellenőrzése ugyanazon hét kapun ment át:

1. nincs feloldatlan ütközése a `phase1.md` fájllal;
2. kompatibilitási teszt vagy adapter nélkül nem változtatja meg a működő publikus viselkedést;
3. nem hozza vissza a főfolyamatos vendor-betöltést, frekvenciatömbös végleges sémát, RSSI-spektrogramot, ál-RAG-ot vagy SDRangel-plane összemosást;
4. RF hardver és AI továbbra is opcionális;
5. volume, PostgreSQL, Kismet, upload, recording, ML modell és dataset törlése tiltott;
6. a követelmény jelenleg is szakmailag indokolt;
7. env-konfigurálható, migrálható monorepo-komponensként megvalósítható.

Ha egy sor csak korrekcióval teljesíti ezeket, kizárólag a korrigált cél tartható meg; a régi megvalósítási mód elvetendő.

### Megtartandó

A fenti „kizárólag `Phase.md`” táblában szereplő követelmények megtartandók, mert opcionálisak, nem teszik kötelezővé a hardvert/AI-t, nem veszélyeztetnek volume-ot, és illeszkednek a monorepóhoz. Ugyancsak megtartandó minden közös követelmény: mock/replay demó, Kismet/BLE, fájl/DB tárolási határ, systemd-képesség, biztonságos cleanup, backup és migráció.

### Elavultként elvetendő

- Főfolyamatban betöltött Aaronia vendor library.
- AVX2 hiányára alapozott probe-kihagyás vagy bizonyítatlan SSE4.2 fallback.
- A `frequencies_hz` tömböt kötelező wire mezővé tevő régi `SpectrumFrame`.
- Kismet RSSI spektrogramként/CNN-bemenetként kezelése.
- Keyword vagy SQL-only kontextus „RAG” megnevezése.
- SDRangel REST API IQ data plane-ként kezelése.
- SDK hiánya miatt az egész core/mock/replay build leállítása.
- Olyan UI vagy API állítás, amely valós hardverteszt nélkül késznek nevezi a hardverintegrációt.

## Implementációs állapot

### Már megvalósult a kódban

- Core/RF/AI/dev Compose fájlok és a core hosszú életű service-ek restart/logging alapjai (`compose*.yaml`).
- C++17 RF agent, `IRfSource`, mock és replay backend (`rf-agent/`).
- A `phase1.md` szerinti tömörített `SpectrumFrame` modell, schema és frontend adapter.
- Izolált `aaronia-probe` és főagent subprocess runner timeout/exit/`SIGILL`/`SIGSEGV` feldolgozással; worker még hiányzik.
- Mock jelgenerálás, szimulációs metadata és frame validation a végleges sémára.
- Replay zstd/NDJSON olvasás, checksum, pause/resume/seek/loop/0.5×/1×/2×/5×.
- RF REST route-felület, specifikus strukturált hibák, `/ws/spectrum` és `/ws/status`; recording control writer még nincs mögötte.
- Mentett és futtatott RF REST/WebSocket contract tesztek.
- Közös FFT pipeline és unit teszt sinus, két jel, zaj, DC, window, dBFS és NaN/Inf esetekre.
- Külön `spectrum-ingest` bounded queue-val, reconnect backoffkal, validációval, status WebSockettel és kötelező metrikákkal; mock upstreammel élőben tesztelt.
- Kismet Wi-Fi/Bluetooth collector aliasok és DB lekérdezések.
- PostgreSQL/TimescaleDB alap-, session-, Wi-Fi- és BLE-migrációk.
- Meglévő frontend spektrum/Kismet/BLE, zoom/pan/marker/max-hold funkciók.

### Csak dokumentált vagy részleges, de nincs kész implementáció

- Aaronia worker felügyelet; az izolált probe főagent-felügyelete már létezik, de a valós SDK-init a tesztkonténer hiányzó runtime függősége miatt még nem volt elérhető. USRP backend/worker továbbra sincs.
- Backend OpenAPI snapshot és teljes legacy API karakterizáció; az RF REST/WS contract tesztek már elkészültek.
- FFT IQ-source bekötés és IQ recording; maga a közös FFT pipeline elkészült.
- Spectrum-ingest recording integráció és tartós metrikaexport; a service és runtime metrikák elkészültek.
- Recording start/stop tényleges működése; az API route jelenleg korrekt `RECORDING_NOT_IMPLEMENTED` választ ad.
- Recording létrehozás és metadata PostgreSQL-ben.
- RF Agent/Recordings/ML frontend tabok.
- ML baseline/CNN/API és helyes dataset pipeline.
- Context-grounded assistant és valódi RAG.
- SDRangel control plane implementáció és data plane választás.
- Docker audit/cleanup, backup/restore, migration és teljes acceptance scriptek.
- Kötelező README/architecture/integration/ML/report dokumentumok.

Részletes, pontonkénti bizonyíték: `PHASE_1_11_REVIEW.md`.


---

## 2026-06-19 – végrehajtási státusz a 18. pont után

Az aktuális megvalósítási igazságforrás a `PHASE_PROGRESS.md` és a
`FINAL_AUDIT.md`. A RAG elkészült; a korábbi `not_implemented` státusz javítva.
A 19–27. folytatásból a hardver nélkül megvalósítható adattárolási/audit,
SDRangel control, data-plane skeleton, USRP probe skeleton, service-stabilitás,
Docker audit/cleanup, backup/restore, migráció, frontend és dokumentáció elkészült.
A valós Aaronia/USRP/SDRangel adatút továbbra is hardverfüggő és nincs késznek
jelölve.

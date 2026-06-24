# CODEX MASTER PROMPT – DM projekt hardverfüggetlen produkciós véglegesítése

Te egy meglévő, Docker-first RF/TSCM mérő- és elemzőrendszert fejlesztesz tovább. A projekt nem egyszerű UI-demó: C++ RF Agentet, SpectrumFrame adatfolyamot, spectrum-ingest szolgáltatást, FastAPI backendet, PostgreSQL/TimescaleDB-t, Kismet Wi-Fi és Bettercap BLE integrációt, recording/replay réteget, ML előkészítést, RAG-ot és SDRangel control-plane kezdeményt tartalmaz.

A jelenlegi gépen még nincs valódi Aaronia vagy USRP hardver. A cél nem az, hogy hardver nélkül hamisan „késznek” minősítsd a hardverintegrációt, hanem hogy minden hardverfüggetlen komponens, interfész, adatmodell, teszt, hibatűrés, UI, migráció és üzemeltetési folyamat produkciós minőségben elő legyen készítve. A rendszer később egy erősebb gépre kerüljön át forráskód-módosítás nélkül, kizárólag konfigurációval, natív driverek/SDK-k telepítésével és újrabuildeléssel.

## 0. Kötelező első lépések

Mielőtt bármit módosítasz, olvasd el legalább ezeket:

- `agents.md`
- `phase1.md`
- `PHASE_PROGRESS.md`
- `FINAL_AUDIT.md`
- `ARCHITECTURE.md`
- `RUNNING.md`
- `MIGRATION.md`
- `BACKUP_RESTORE.md`
- `RF_AGENT.md`
- `SDRANGEL_INTEGRATION.md`
- `AARONIA_INTEGRATION.md`
- `USRP_INTEGRATION.md`
- `ML_CLASSIFIER.md`
- `RAG.md`
- `config/spectrum-frame.schema.json`
- `config/iq-frame.schema.json`
- `config/recording-metadata.schema.json`

Ezután vizsgáld meg ténylegesen a forráskódot és a jelenlegi teszteket. Ne kizárólag a dokumentáció állításaira hagyatkozz.

Készíts egy új, rövid auditfájlt:

- `PRODUCTION_READINESS_BASELINE.md`

Ebben rögzítsd:

- az aktuális szolgáltatásokat;
- API- és WebSocket-végpontokat;
- adatbázis-migrációkat;
- frontend funkciókat;
- jelenlegi teszteredményeket;
- a hardver nélkül tesztelhető és nem tesztelhető részeket;
- az észlelt szerződés- vagy implementációs hibákat;
- a módosítás előtti kompatibilitási alapállapotot.

Futtasd le az összes elérhető baseline ellenőrzést. Ha valamelyik környezeti ok miatt nem futtatható, ezt pontosan dokumentáld, de ne nevezd sikeresnek.

## 1. Megváltoztathatatlan szabályok

1. Ne törölj működő funkciót vagy API-végpontot.
2. A meglévő API-khoz lehetőleg maradjon visszafelé kompatibilis adapter.
3. Adatbázis-módosítás kizárólag új, előre mutató migrációval történhet. Meglévő migrációt ne írj át.
4. Ne törölj adatbázis-volume-ot, recordingot, feltöltést vagy felhasználói adatot.
5. A `.env` valódi titkait ne olvasd ki jelentésbe, ne írd át és ne commitold. Az `.env.example` és a konfigurációs sablonok viszont legyenek naprakészek.
6. Hardverprotokollt, `.peak` fájlformátumot vagy SDRangel adatkapcsolatot ne találj ki. Ismeretlen formátumhoz tiszta adapter/interfész és egyértelmű `not_configured`, `unsupported` vagy `hardware_not_tested` állapot kell.
7. Ne állítsd egy komponensről, hogy kész vagy tesztelt, ha csak mock, replay, skeleton vagy konfigurációs előkészítés létezik.
8. A rendszerben minden hardverhiány kontrollált, jól látható állapot legyen, ne általános 500-as hiba.
9. Ne implementálj támadó Wi-Fi/Bluetooth funkciót. A Kismet és BLE rész kizárólag passzív, engedélyezett környezetben történő megfigyelésre szolgáljon.
10. Ne végezz egyszerre óriási, ellenőrizhetetlen átírást. Dolgozz az alábbi fázisokban, és minden fázis után futtasd a releváns teszteket.
11. A frontend maradhat statikus HTML/CSS/JavaScript. Ne vezess be Reactet vagy más frameworköt csak azért, hogy modernebbnek tűnjön.
12. A felhasználói felület magyar maradjon.
13. A felső fő választósávot tartsd meg. Különösen maradjon meg és ne változzon meg a logikája:
    - `Spektrum`
    - `Wi-Fi / Kismet`
    - `Bluetooth / BLE`
    - `RF Agent`
    - `Felvételek`
    - `ML osztályozás`
    - `RAG`
    - `Rendszerállapot`
14. A fenti fő füleket ne töröld, ne rendezd át, és ne olvaszd össze. Új felső szintű fület csak akkor adj hozzá, ha bizonyíthatóan nincs megfelelő hely a meglévő nézetekben; elsődlegesen a meglévő füleken belül alakíts ki új paneleket.
15. A kód ne tartalmazzon elhallgatott kivételeket, hamis fallback adatot vagy olyan demómódot, amely élő adatnak látszik.
16. Minden új tartós állapothoz legyen auditálás, validáció és dokumentáció.

---

# 2. Fázis A – Backend fokozatos modulárisítása

A `python-processor/main.py` jelenleg több ezer soros monolit. Fokozatosan bontsd modulokra, de tarts meg kompatibilis belépési pontot, hogy a Docker- és Uvicorn-indítás ne törjön el.

Célstruktúra legalább:

```text
python-processor/
  main.py                       # vékony kompatibilis entrypoint
  app/
    application.py              # FastAPI app factory/lifespan
    config.py
    db.py
    dependencies.py
    errors.py
    logging_config.py
    schemas/
    routers/
      health.py
      sessions.py
      spectrum.py
      references.py
      markers.py
      known_signals.py
      recordings.py
      rf_agent.py
      sdrangel.py
      wifi.py
      bluetooth.py
      ml.py
      rag.py
      system.py
    services/
      spectrum/
      references/
      recordings/
      anomaly/
      known_signals/
      collectors/
      sdrangel/
      ml/
      rag/
    repositories/
```

Követelmények:

- Domainenként, kis lépésekben emeld ki a kódot.
- Minden kiemelés után futtasd az API contract teszteket.
- Ne hozz létre körkörös importot.
- A DB tranzakciókezelés és kapcsolatkezelés legyen központosított.
- Legyen egységes Pydantic request/response séma.
- Legyen egységes hibaformátum, például `code`, `message`, `details`, `request_id`.
- A hardver- és külső szolgáltatásproblémák ne blokkolják a teljes backend indulását.
- A meglévő `main.py` végül csak az appot exportálja.

A refaktor önmagában nem változtathatja meg a felhasználó által látható működést.

---

# 3. Fázis B – SpectrumFrame adatkontraktus hibájának javítása

Jelenleg a `spectrum-ingest` teljes `SpectrumFrame v1` objektumot továbbít, a frontend viszont a WebSocket payloadot közvetlenül olyan normalizálónak adja, amely elsősorban tömböt vár. Emiatt egy érvényes frame könnyen üres vagy hamis, teljes tartományú `-105 dBm` görbévé válhat.

Ezt end-to-end javítsd.

## Kötelező frontend adapter

Hozz létre egy egyértelmű `parseSpectrumFrame()` / `SpectrumFrameAdapter` réteget, amely felismeri és validálja:

1. `SpectrumFrame v1` objektumot:
   - `schema_version`
   - `start_frequency_hz`
   - `stop_frequency_hz`
   - `step_frequency_hz`
   - `num_points`
   - `powers_dbm`
   - `timestamp`
   - `sequence`
   - `source_type`
   - `source_device`
   - `session_id`
   - `rbw_hz`
   - `metadata`
2. korábbi kompatibilitási formátumokat:
   - `[{x, y}]`
   - `[{freq, dbm}]`
   - egyszerű számtömb

A belső frekvenciaegység legyen Hz. MHz-re csak a megjelenítésnél alakíts.

## Fontos adatszemantika

- A hiányzó adat nem azonos `-105 dBm` méréssel.
- Hiányzó tartomány legyen `NaN`, `null` vagy külön validity mask, és a grafikonon legyen rés/„nincs adat”.
- A `-105 dBm` kizárólag megjelenítési padló vagy valódi mért érték lehet.
- Hibás frame ne kerüljön kirajzolásra.
- A UI jelenítse meg: forrás, sequence, timestamp, RBW, center/span, frame pontszám, frissesség és sequence gap.
- Ha az adatfolyam elavult, a státusz legyen `STALE`, ne maradjon megtévesztően `ONLINE`.

## Kötelező tesztek

Legyen teszt legalább ezekre:

- 100 pontos SpectrumFrame;
- 65 536 pontos SpectrumFrame;
- részleges frekvenciatartomány;
- eltérő step;
- sequence gap;
- hibás `num_points`;
- hibás `stop_frequency_hz`;
- NaN/Infinity elutasítása;
- korábbi tömbformátum kompatibilitása;
- élő WS frame frontend-adapterének fixture tesztje.

---

# 4. Fázis C – Natív felbontású spektrum és külön overview

A jelenlegi fix, teljes 10 MHz–24 GHz tartományra húzott `NUM_BINS = 24576` tömb nem lehet az egyetlen adatmodell. Körülbelül 1 MHz/bin szintű overview hasznos, de keskenysávú RF-elemzésre alkalmatlan. A zoom nem nagyíthat kizárólag egy már lebutított görbét.

Alakíts ki két elkülönített réteget:

## 4.1 Aktuális natív frame

- Az utolsó élő SpectrumFrame maradjon meg a saját natív frekvenciatengelyével és teljes pontosságával.
- A fő spektrumgrafikon a látható tartományban ebből dolgozzon.
- A böngésző pixelszámához történő csökkentés peak-preserving min/max vagy min-max envelope algoritmussal történjen.
- Egyszerű átlagolás vagy olyan interpoláció ne tüntessen el keskeny csúcsot.
- A marker és peak számítás az eredeti natív adaton történjen, ne a kirajzolt, ritkított pixeleken.
- A waterfall az aktuális center/span és natív frame adatait használja.

## 4.2 Teljes tartományú overview accumulator

- Az overview külön adatszerkezet legyen, amely a különböző sweep/frame tartományokból idővel tölti fel a teljes frekvenciatartományt.
- Minden buckethez legyen érték, utolsó frissítési idő és validity állapot.
- A régi bucket vizuálisan halványodjon vagy kapjon „stale” jelölést.
- Nem mért tartomány ne nézzen ki zajpadlónak.
- A teljes tartomány, bucketméret és időablak konfigurálható legyen.

## 4.3 Viewport/ROI szerződés

Készíts hardverfüggetlen, verziózott szerződést arra, hogy a frontend vagy backend egy kiválasztott center/span/ROI igényt küldhessen az RF Agentnek. Valódi hardver nélkül ezt mock és replay implementációval igazold.

A szerződés kezelje legalább:

- center frequency;
- span;
- kívánt RBW vagy maximális pontszám;
- sweep mód vagy fixed-tune mód;
- source capability ellenőrzés;
- elfogadott, korlátozott vagy elutasított konfiguráció;
- request ID és visszajelzett tényleges beállítás.

Ne állítsd, hogy a valódi Aaronia/USRP ezt már végrehajtja. A forrásdriver capability objektuma mondja meg, mit támogat.

## 4.4 Hatékony továbbítás

A kompatibilis JSON WebSocket maradjon meg. Emellett tervezz és – ha biztonságosan megvalósítható – implementálj opcionális verziózott bináris továbbítást a nagy frame-ekhez, JSON fallbackkel. Ne találj ki dokumentálatlan formátumot: a saját protokollt teljesen dokumentáld, legyen benne magic/version/header/payload type/endianness/pontszám és teszt.

Ha a bináris protokoll túl nagy kockázatot okozna ebben a fázisban, hagyj tiszta interfészt és mérési dokumentumot, de a JSON útvonal teljesen működjön és legyen méretkorlátos.

---

# 5. Fázis D – Spektrum UI rendbetétele duplikáció nélkül

A felső fő fülsor változatlanul maradjon.

A spektrum eszköztár jelenleg túlzsúfolt. A látható gombokat logikai csoportokba rendezd, de a funkciókat ne töröld.

Javasolt csoportok:

- **Nézet**: Teljes tartomány, Ugrás csúcsra, Overview
- **Navigáció**: Zoom +, Zoom −, pan/marker mód
- **Elemzés**: Max hold, referenciaeltérés
- **Referencia**: Aktuális beállítása, Mentés DB-be, Import, Törlés, DB-réteg
- **Mentés**: Csúcs mentése, marker mentése

A jobb kattintásos menü és a billentyűparancsok maradhatnak alternatív vezérlésként. Ezek nem számítanak hibás duplikációnak, de a képernyőn ne legyen két azonos jelentésű látható gomb.

Ne használj böngésző `prompt()` és `confirm()` ablakokat üzemi adatbevitelre. Készíts egységes, akadálymentes modal formokat validációval.

A gombnevek legyenek egyértelmű magyar kifejezések, például:

- `Peak` → `Ugrás csúcsra`
- `Save Peak` → `Csúcs mentése`
- `Ref = Current` → `Aktuális mint referencia`
- `Save Ref DB` → `Referencia mentése`
- `Load Ref` → `Referencia importálása`
- `Clear Ref` → `Referencia törlése`
- `DB Ref` → `DB referencia-réteg`

A kis kijelzőn a ritkábban használt műveletek kerülhetnek overflow menübe, de ne tűnjenek el.

---

# 6. Fázis E – Tartós markerek és „ismert jel” rendszer

A marker ne csak ideiglenes vonal legyen. A meglévő marker API-ra építve készíts teljes CRUD működést és UI-t:

- marker létrehozása;
- megtekintése;
- szerkesztése;
- törlés helyett lehetőség szerint archiválása;
- markerre ugrás;
- sessionhöz/recordinghoz/helyszínhez kapcsolás;
- címke, megjegyzés, szín/kategória és metadata;
- audit esemény minden változtatásról.

## 6.1 Új ismert jelek adatmodell

Készíts új előre mutató migrációt, például:

- `011_known_signals.sql`

Az `known_signals` vagy hasonló tábla legalább ezt tartalmazza:

- `id`
- opcionális `location_id`
- opcionális `measurement_session_id`
- `center_frequency_hz`
- `frequency_tolerance_hz`
- opcionális `bandwidth_hz`
- opcionális `expected_power_min_dbm`
- opcionális `expected_power_max_dbm`
- opcionális `modulation`
- opcionális `protocol`
- opcionális `source_type`
- `label`
- `notes`
- `status`: active/disabled/expired
- `suppress_alerts` boolean
- opcionális `valid_from`, `valid_until`
- `metadata`
- `created_at`, `updated_at`, opcionális `archived_at`

Készíts megfelelő indexeket.

## 6.2 Nagyon fontos működési szabály

Az ismert frekvencia ne jelentsen vak kizárást.

A rendszer továbbra is:

- tárolja a mérést;
- lefuttatja az észlelést;
- összehasonlítja a jel várható tulajdonságaival;
- csak a riasztást nyomja el, ha valóban megfelel az ismert jel profiljának.

Ha a teljesítmény, sávszélesség, moduláció, időbeli viselkedés, helyszín vagy forrás lényegesen eltér, új anomália keletkezzen.

Ne csak a center frekvencia alapján egyeztess. Használj toleranciát és az elérhető további jellemzőket.

## 6.3 Detection kapcsolatok

Új migrációval egészítsd ki az RF detection rekordokat legalább:

- opcionális `known_signal_id`
- `disposition`: new/known/changed/false_positive/reviewed
- opcionális review adatok
- `suppression_reason`
- `reviewed_at`, `reviewed_by`

## 6.4 UI

A spektrum jobb kattintásos menüjében legyen:

- `Marker mentése`
- `Ismert jelként megjelölés`
- `Riasztás elnyomása ennél a jelprofilnál`
- `Korábbi észlelések`
- `Hangolás és demoduláció`

Legyen külön, szűrhető ismertjel-lista a Spektrum nézeten belül, nem új felső fülként.

---

# 7. Fázis F – Referenciakezelés produkciós szinten

A referencia ne csak egy névtelen görbe legyen. Legyen verziózott és visszakövethető.

A referencia metadata legalább:

- reference ID és verzió;
- helyszín;
- eszköz és forrástípus;
- antenna;
- downconverter profil;
- start/stop/step;
- RBW/VBW;
- mérési idő;
- operátor;
- megjegyzés;
- checksum;
- aktív/inaktív állapot;
- érvényességi idő;
- létrehozás forrása: live/import/replay/converted;
- eredeti fájlnév és importformátum.

Készíts:

- referencia listázást;
- részletes nézetet;
- aktiválást/deaktiválást;
- verziózást;
- exportot JSON és CSV formátumba;
- importot dokumentált JSON és CSV formátumból;
- validációt és peak-preserving resamplinget;
- audit eseményeket.

## 7.1 `.peak` fájl

A felhasználó később OSCOR/egyéb `.peak` fájlt szeretne referenciának használni.

Készíts importer registry/interfész réteget, például:

```text
ReferenceImporter
  can_handle(filename, mime, header)
  inspect(...)
  import_points(...)
```

Legyen külön `oscor_peak` adapterhely, de:

- dokumentált formátum vagy valódi, engedélyezett mintafájl nélkül ne írj ál-parser-t;
- ne kezeld a fájlt egyszerű CSV-ként csak a kiterjesztés alapján;
- az upload endpoint biztonságosan felismerheti a `.peak` kiterjesztést;
- ismeretlen/proprietary tartalomra adjon egyértelmű `unsupported_peak_format` választ;
- a UI mondja el, hogy OSCOR Data Viewerből CSV-export használható;
- a CSV-export legyen azonnal importálható;
- a dokumentáció írja le, milyen mintafájl vagy hivatalos formátumleírás szükséges a közvetlen parser elkészítéséhez.

Ha a repositoryban később valódi `.peak` fixture jelenik meg, csak akkor implementálj parser-t, ha a struktúra bizonyítható, dokumentált és tesztekkel validálható.

---

# 8. Fázis G – Felvételek: spectrum, IQ és audio elkülönítése

A jelenlegi spectrum recording maradjon visszafelé kompatibilis. Tedd egyértelművé, hogy a spektrum-power frame nem alkalmas utólagos demodulációra.

Alakíts ki három recording típust:

1. `spectrum`
2. `iq`
3. `audio`

## 8.1 Spectrum recording

- A meglévő tömörített, checksummal lezárt formátum maradjon támogatott.
- Legyen atomikus lezárás: ideiglenes fájl → fsync/flush → checksum → metadata → rename.
- Sérült vagy félbehagyott recording legyen felismerhető.
- Legyen frame count, időtartam, frekvenciatartomány, forrás és méret.

## 8.2 IQ recording

Hardver nélkül is készíts teljes adatmodellt, writer/reader interfészt és mock fixture tesztet.

Elsődlegesen használj nyílt, dokumentált formátumot, például SigMF-kompatibilis párt:

- `.sigmf-meta`
- `.sigmf-data`

Metadata legalább:

- datatype, például `cf32_le` vagy `ci16_le`;
- sample rate;
- center frequency;
- timestamp;
- source/device;
- session/recording ID;
- antenna/downconverter;
- checksum;
- capture szegmensek;
- packet loss/overflow counter.

Ne állítsd, hogy a valódi hardver IQ-t ír, amíg nincs adatforrás. Mock IQ generatorral igazold a writer/reader és checksum működését.

## 8.3 Audio recording

- Dokumentált WAV output és metadata.
- Forrása később SDRangel vagy más demodulátor lehet.
- Hardver/SDRangel nélkül mock audio fixture használható, de a státusz legyen egyértelmű.

## 8.4 Tárhelyvédelem

Legyen:

- szabadhely-ellenőrzés;
- konfigurálható maximális recording méret és időtartam;
- low-disk riasztás;
- retention policy dry-run móddal;
- közvetlen törlés helyett archiválás/karantén vagy külön megerősített művelet;
- checksum ellenőrzés replay előtt.

## 8.5 Felvételek UI

Mutassa:

- recording típus;
- státusz;
- forrás;
- center/span/sample rate/RBW;
- kezdés és időtartam;
- méret;
- checksum állapot;
- replay lehetőség;
- metadata részletek;
- hardverfüggetlen, érthető hibaállapotok.

---

# 9. Fázis H – SDRangel teljes hardverfüggetlen előkészítése

A meglévő SDRangel REST control-plane maradjon meg és legyen moduláris, validált, jól tesztelt.

## 9.1 Control plane

A frontend Spektrum nézetében legyen demodulációs panel és jobb kattintásos művelet:

- kiválasztott frekvencia;
- AM/NFM/WFM/USB/LSB;
- bandwidth;
- squelch;
- opcionális audio sample rate;
- start/stop;
- aktuális SDRangel státusz;
- device set és channel index;
- ténylegesen elfogadott beállítások.

A vezérlők csak akkor legyenek aktívak, ha:

- RF source rendelkezésre áll;
- SDRangel control plane `ready`;
- a kiválasztott adatút konfigurált;
- a source capability támogatja a szükséges IQ-t.

A letiltott gomb mellett jelenjen meg az ok.

## 9.2 Data plane absztrakció

Hozz létre tiszta, verziózott interfészt:

```text
IqSource -> bounded queue -> IqPublisher -> SDRangel-compatible sink
```

Legyenek legalább ezek a státuszok:

- `disabled`
- `not_configured`
- `configured_not_tested`
- `connecting`
- `ready`
- `degraded`
- `failed`

A protokollnak kezelnie kell:

- sample format;
- sample rate;
- center frequency;
- timestamp;
- sequence;
- packet loss;
- overflow;
- bounded queue és drop policy;
- reconnect;
- protocol version.

Készíts mock IQ source és mock sink integrációs tesztet. Valódi SDRangel hálózati sample-source vagy plugin csak hivatalosan ellenőrzött, konkrét verzióhoz tartozó API alapján implementálható. Plugin- és verziófüggő settings kulcsot ne hardcodeolj általános igazságként.

A rendszerállapotban külön jelenjen meg:

- control plane;
- IQ data plane;
- audio output;
- hardware source.

---

# 10. Fázis I – Valós anomáliadetektálási pipeline hardver nélkül

Az ML jelentése `Machine Learning`, de a rendszer ne függjön kizárólag betanított modelltől. Hardver és címkézett adathalmaz nélkül is legyen működő, őszinte szabály- és statisztikai baseline.

## 10.1 Online pipeline

Készíts bounded queue-val működő háttérfolyamatot:

```text
SpectrumFrame
  -> validáció
  -> natív ablakok/jellemzők
  -> referencia-összevetés
  -> szabályalapú detektor
  -> statisztikai detektor
  -> opcionális klasszikus ML/CNN
  -> known-signal matching
  -> rf_detection
  -> alert policy
```

A pipeline ne blokkolja a spektrum megjelenítését. Legyen backpressure/drop metrika.

## 10.2 Hardver nélkül működő spektrumszabályok

Legalább:

- referencia feletti új csúcs;
- újonnan elfoglalt frekvenciatartomány;
- tartós keskenysávú jel;
- rövid burst;
- váratlan sávszélesség-változás;
- ismert jel teljesítmény- vagy sávszélesség-eltérése;
- frekvenciavándorlás;
- occupancy változás;
- zajpadló jelentős eltolódása;
- sequence gap vagy forrásminőségi hiba külön technikai eseményként.

Használj robusztus statisztikát, például median/MAD megközelítést. A küszöbök konfigurálhatók legyenek helyszín és sáv szerint.

## 10.3 Klasszikus ML és CNN

- A modell csak akkor legyen `ready`, ha tényleges modellartifact és kompatibilis feature/schema verzió létezik.
- `not_trained` ne változzon automatikusan `ready` állapotra.
- A model registry tárolja: modellnév, verzió, feature schema, tréningidő, dataset manifest checksum, metrikák és artifact checksum.
- A split recording-szinten történjen, ne frame-szinten, hogy ne legyen adatszivárgás.
- A kiértékelés tartalmazzon confusion matrixot és osztályonkénti precision/recall/F1-et.
- Alacsony confidence esetén legyen `unknown`, ne erőltetett osztály.

## 10.4 Human-in-the-loop

A felhasználó tudja:

- elfogadni vagy elutasítani a detektálást;
- címkézni;
- ismert jelhez kapcsolni;
- false positive-ként jelölni;
- megjegyzést írni;
- a döntést auditálni;
- későbbi tréningdatasetbe bevonni vagy kizárni.

## 10.5 Wi-Fi anomáliák

Passzív adatok alapján, konfigurálható szabályokkal:

- új BSSID egy helyszínen;
- korábban ismert SSID titkosítási tulajdonságának változása;
- rejtett SSID megjelenése;
- azonos BSSID több, szokatlan SSID-vel;
- ismétlődő eszköz több helyszínen;
- szokatlan csatorna vagy RSSI-változás;
- vendor/adattulajdonság eltérés csak jelzésként, nem bizonyosságként.

## 10.6 Bluetooth/BLE anomáliák

- új eszköz egy helyszínen;
- új manufacturer data vagy service UUID;
- ismert eszköz tulajdonságváltozása;
- szokatlanul tartós jelenlét;
- több helyszínen ismétlődés;
- RSSI-viselkedés változása.

A randomizált MAC-címeket kezeld óvatosan; ne állíts biztos azonosságot gyenge fingerprint alapján.

## 10.7 Frontend

A Spektrum, Wi-Fi és Bluetooth füleken belül legyen anomália-panel és review művelet. Ne hozz létre kötelezően új felső fület.

Minden detektálásnál jelenjen meg:

- idő;
- helyszín/session;
- típus;
- frekvencia vagy eszköz;
- súlyosság;
- confidence, ha van;
- szabály/modell neve és verziója;
- rövid, determinisztikus indoklás;
- evidence rekordazonosítók;
- ismertjel-egyezés;
- review állapot.

---

# 11. Fázis J – Alert workflow és audit

A meglévő `system_alerts` és `audit_events` réteget fejezd be.

Legyen:

- alert listázás és szűrés;
- open/acknowledged/resolved életciklus;
- severity;
- assignee vagy operator mező opcionálisan;
- acknowledgement és resolution note;
- deduplikációs kulcs;
- ismétlődő esemény számláló;
- suppression expiry;
- minden állapotváltozás auditálása;
- UI a Rendszerállapot és releváns domainnézetek alatt.

A technikai rendszerhiba és az RF-biztonsági anomália legyen megkülönböztethető.

---

# 12. Fázis K – Produkciós megfigyelhetőség és hibatűrés

## 12.1 Health endpointok

Minden szolgáltatásnál külön:

- liveness;
- readiness;
- részletes status.

A readiness tényleges függőségeket ellenőrizzen, de opcionális komponens hiánya ne tegye automatikusan használhatatlanná a teljes core rendszert.

## 12.2 Strukturált naplózás

- JSON log opció;
- timestamp, level, service, request ID, session ID, recording ID, source ID;
- titkok és teljes nyers érzékeny payload ne kerüljön logba;
- logrotáció;
- egységes exception logging.

## 12.3 Metrikák

Adj Prometheus-kompatibilis metrikákat legalább:

- SpectrumFrame FPS;
- frame size;
- sequence gaps;
- invalid frames;
- queue depth;
- dropped frames;
- WS clients;
- source latency;
- DB query/error;
- recording bytes/frame count;
- disk free;
- ML inference latency/queue/drop;
- alerts by severity;
- SDRangel reconnect/packet loss;
- collector status.

## 12.4 Hibainjektálási tesztek

Teszteld:

- RF Agent leáll;
- DB átmenetileg nem elérhető;
- SDRangel nincs telepítve;
- Ollama ki van kapcsolva;
- lassú WebSocket kliens;
- invalid frame;
- sequence gap;
- kevés tárhely;
- sérült recording;
- ismeretlen `.peak` fájl;
- üres RAG index;
- modell nincs betanítva.

A rendszer ne omoljon össze, és a státusz legyen őszinte.

---

# 13. Fázis L – Biztonságos produkciós profil

A demo mód maradjon egyszerűen indítható, de a production profil ne maradjon védelem nélkül.

## 13.1 Konfiguráció

Legyen explicit:

- `APP_MODE=demo|production`
- biztonságos alapértékek production módban;
- startup config validáció;
- tiltott vagy hiányzó kritikus konfigurációnál érthető hiba;
- `.env.example` frissítés;
- titok nélküli `config/production-hardware.env` sablon.

## 13.2 Hálózat és proxy

- csak a reverse proxy legyen alapértelmezetten publikált;
- backend/DB/MQTT ne legyen szükségtelenül host portra kitéve;
- WebSocket proxy timeoutok és bufferelés helyesen legyen beállítva;
- biztonsági headerek;
- request body/upload limitek;
- MIME és fájlszignatúra validáció;
- path traversal elleni védelem;
- TLS termináció dokumentáció belső CA vagy külső proxy esetére.

## 13.3 Opcionális autentikáció

Készíts jól elkülönített autentikációs módot:

- demo módban konfigurálhatóan kikapcsolható;
- production módban ne legyen névtelen írási művelet;
- legalább viewer/operator/admin szerepkör;
- jelszó csak erős hash formában;
- nincs hardcoded admin jelszó;
- bootstrap admin dokumentált CLI vagy egyszer használható setup folyamat;
- az összes írási művelet auditált;
- a meglévő olvasási API-k kompatibilitása dokumentált legyen.

Ezt külön, kis lépésben implementáld, és ne törje el a demo/acceptance környezetet.

## 13.4 Konténerek

- image tagek legyenek verzióra rögzítve, ne ellenőrizetlen `latest`;
- Python dependencyk legyenek reprodukálhatóan pinelve;
- non-root futás, ahol lehetséges;
- read-only filesystem és tmpfs, ahol biztonságosan alkalmazható;
- capabilityk minimalizálása;
- healthcheck, restart policy, grace period és log limit;
- build cache és runtime image szétválasztása, ahol indokolt;
- generált cache/binary ne kerüljön a forráscsomagba.

---

# 14. Fázis M – Adatbázis és teljesítmény

- Legyen valódi migrációfuttató, amely meglévő adatbázison is biztonságosan alkalmazza az új migrációkat.
- Migráció legyen tranzakciós, idempotenciát vagy alkalmazott verziót kezelő.
- Adatbázis backup nélkül destruktív migráció ne induljon.
- Ellenőrizd az indexeket a fő listázási és időalapú lekérdezésekhez.
- Timescale hypertable/compression/retention csak ott legyen, ahol ténylegesen indokolt és dokumentált.
- Nagy lista endpointokhoz cursor vagy stabil pagination.
- SQL lekérdezések legyenek paraméterezettek.
- Nagy nyers frame-eket ne tárolj indokolatlanul soronként PostgreSQL-ben, ha a recording fájlrendszer a megfelelő réteg.
- Metadata és file index legyen konzisztens; orphan file és orphan DB rekord auditálható legyen.

Készíts terhelési fixture-t mock/replay alapon:

- nagy SpectrumFrame;
- több WS kliens;
- hosszabb recording;
- ML pipeline bekapcsolva és kikapcsolva;
- CPU/memória/latencia mérés.

Ne adj kitalált teljesítményszámot; a mérési környezetet és eredményeket rögzítsd.

---

# 15. Fázis N – Erősebb célgépre történő migráció előkészítése

A projekt másik gépre költözése ne igényeljen forrásmódosítást.

Bővítsd a preflight/migration scripteket, hogy ellenőrizzék:

- OS és kernel;
- CPU architektúra és AVX/AVX2;
- RAM;
- szabad tárhely és filesystem;
- Docker és Compose verzió;
- portütközés;
- NVIDIA GPU/driver/container runtime, ha AI profil használja;
- UHD telepítés és verzió;
- Aaronia SDK helye és dinamikus könyvtárak;
- SDRangel elérhetőség és verzió;
- hálózati interfészek és 10GbE alapadatok;
- időszinkron/NTP/PTP állapot;
- szükséges host könyvtárak és jogosultságok;
- backup checksum;
- adatbázis restore ellenőrzés.

A Compose profilok legyenek tiszták:

- core;
- demo/mock;
- RF/hardware;
- AI/GPU;
- development.

A hardverközeli RF Agent futhasson natívan systemd alatt, miközben a core marad Dockerben. Dokumentáld a hálózati és jogosultsági határt.

---

# 16. Fázis O – Kötelező automata teszt- és acceptance csomag

Készíts vagy frissíts egyetlen fő acceptance belépési pontot, amely hardver nélkül legalább ezeket ellenőrzi:

1. konfiguráció és Compose parse;
2. migrációk;
3. backend liveness/readiness;
4. spectrum-ingest health;
5. RF Agent mock source;
6. SpectrumFrame JSON schema;
7. frontend SpectrumFrame adapter;
8. részleges tartomány helyes kirajzolási adatmodellje;
9. overview accumulator;
10. WebSocket reconnect és stale állapot;
11. slow-client drop policy;
12. recording start/stop/checksum/replay;
13. mock IQ SigMF writer/reader;
14. marker CRUD;
15. known-signal matching és alert suppression;
16. reference JSON/CSV import/export;
17. `.peak` unsupported kontrollált válasz;
18. SDRangel disabled/not-configured/mock data-plane állapot;
19. rule-based/statistical anomaly detection;
20. ML not-trained állapot;
21. Wi-Fi/BLE passzív anomáliaszabályok fixture-rel;
22. RAG disabled/empty/ready állapotok;
23. backup dry-run;
24. restore dry-run;
25. migration preflight;
26. orphan audit;
27. nincs szükségtelen publikus DB/backend port;
28. frontend alap UI smoke teszt;
29. felső fő fülsor változatlanul jelen van;
30. produkciós konfiguráció hibás kritikus beállításnál fail-fast.

A frontendhez használj automatizált DOM vagy Playwright smoke tesztet, ha a környezetben ésszerűen bevezethető. Legalább teszteld a fő füleket, a spektrum frame adaptert, a modalokat és a context menüt.

A tesztek fixture alapúak legyenek, ne függjenek külső internettől vagy valódi hardvertől.

---

# 17. Kötelező dokumentáció és állapotjelölések

Frissítsd az érintett dokumentációkat, és hozz létre:

- `PRODUCTION_READINESS_REPORT.md`
- `KNOWN_SIGNALS.md`
- `REFERENCE_IMPORT.md`
- `RECORDING_FORMATS.md`
- `SPECTRUM_DATA_FLOW.md`
- `ANOMALY_PIPELINE.md`
- `SECURITY_PRODUCTION.md`

Minden komponenshez használd az alábbi vagy ezekkel egyenértékű, egyértelmű állapotokat:

- `implemented_tested`
- `implemented_mock_tested`
- `configured_not_tested`
- `hardware_not_tested`
- `not_configured`
- `not_trained`
- `unsupported`
- `disabled`
- `degraded`
- `failed`

Ne használj általános `ready` státuszt olyan komponensre, amelynek valamely kötelező adatútja hiányzik.

---

# 18. Munkasorrend és megállási szabály

Ebben a sorrendben dolgozz:

1. baseline audit és tesztek;
2. SpectrumFrame kontraktushiba;
3. natív frame + overview adatszerkezet;
4. frontend spektrum UX és modalok;
5. marker CRUD + ismert jel adatmodell;
6. referencia verziózás/import/export;
7. recording típusok és mock IQ;
8. SDRangel control UI + data-plane interfész/mock;
9. szabály- és statisztikai anomáliapipeline;
10. Wi-Fi/BLE anomáliaszabályok;
11. alert/review/audit workflow;
12. backend fokozatos modularizálás befejezése;
13. observability és security production profil;
14. adatbázis/performance hardening;
15. migráció/preflight;
16. teljes acceptance;
17. dokumentáció és végső audit.

Egy fázis csak akkor minősül késznek, ha:

- a kód elkészült;
- a migráció elkészült, ha kell;
- a tesztek elkészültek;
- a releváns tesztek lefutottak;
- a dokumentáció frissült;
- nincs hamis hardver-ready állítás;
- a korábbi funkciók regresszió nélkül működnek.

Ha egy fázisban valódi hardver vagy proprietary dokumentáció hiánya miatt nem lehet továbbmenni, ne állj le az egész projekttel. Fejezd be az interfészt, mockot, teszteket, státuszkezelést és dokumentációt, majd jelöld pontosan a hardveres folytatási pontot.

---

# 19. Minden fázis végén kötelező jelentés

Minden fázis után írd le:

1. módosított fájlok;
2. új fájlok;
3. új/megmaradt API-k;
4. migrációk;
5. konfigurációs változók;
6. tesztparancsok és tényleges eredmények;
7. mi működik valóban;
8. mi mock-only;
9. mi hardverfüggő;
10. ismert kockázatok;
11. következő fázis.

A végén frissítsd:

- `PHASE_PROGRESS.md`
- `FINAL_AUDIT.md`

A végső jelentésben külön táblázatban szerepeljen:

- core platform;
- spectrum adatút;
- overview/detail megjelenítés;
- reference;
- recording spectrum/IQ/audio;
- marker/known signals;
- anomaly pipeline;
- Wi-Fi/BLE;
- ML;
- RAG;
- SDRangel control;
- SDRangel IQ data plane;
- Aaronia;
- USRP;
- backup/restore;
- migration;
- security;
- observability.

## Végső elvárt eredmény

A rendszer hardver nélkül is legyen teljesen demonstrálható mock és replay forrásokkal, de a UI mindenhol világosan különböztesse meg a demóadatot a valós adatoktól. A későbbi erős gépen és valódi hardverrel a forrásadapterek és natív driverek bekötése legyen a fő nyitott feladat, ne az alaparchitektúra, adatmodell, UI, recording, ML-pipeline, audit, biztonság vagy üzemeltetés újratervezése.

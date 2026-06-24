A Wi-Fi és Bluetooth session- és referenciafelület jelenlegi működését
egyszerűsíteni kell. A korábbi prompt referencia-set architektúráját tartsd
meg, de az alábbi szabályok felülírják a korábbi UI-státuszokra vonatkozó
részeket.

ALAPELV

A „jelenlegi mérési session adatai” és a „betöltött referencia adatai” két
teljesen külön fogalom.

Egy eszköz csak akkor kapjon referenciajelölést, ha a felhasználó explicit
módon kiválasztott egy adatbázisban tárolt reference_set rekordot, vagy
importált egy referenciafájlt.

A helyszínnév önmagában soha ne aktiváljon automatikus baseline-összehasonlítást.

SESSION NÉZET

1. Új measurement session indításakor:
   - ürítsd ki a frontend Wi-Fi és Bluetooth listáit;
   - nullázd az aktuális session számlálóit;
   - ürítsd ki a sessionhöz tartozó security/anomaly panelek frontend state-jét;
   - ezután kizárólag az új measurement_session_id értékhez tartozó adatok
     jelenjenek meg.

2. Ne törölj adatbázisrekordokat. A sessionek elkülönítése kizárólag
   measurement_session_id alapú lekérdezéssel történjen.

3. Aktív session nélkül a frontend ne kérje le és ne jelenítse meg
   automatikusan a globális vagy legutóbbi Wi-Fi/Bluetooth adatokat.

4. Aktív vagy explicit módon kiválasztott session nélkül jelenjen meg:

   „Nincs aktív vagy kiválasztott mérési session.”

   Gombok:
   - Új session indítása
   - Korábbi session megnyitása

5. Session leállításakor a lezárt session eredményei maradhatnak láthatók
   read-only állapotban. Új session indításakor ezeket töröld a frontend
   nézetből.

6. A Wi-Fi és Bluetooth eszközendpointokat a frontend mindig explicit
   measurement_session_id paraméterrel hívja session nézetben.

7. A backend ne essen vissza automatikusan globális eszközlistára, ha a
   frontend session nézetet kér, de nincs session ID.

8. A Wi-Fi security eseményeket, Wi-Fi anomáliákat és Bluetooth anomáliákat
   szintén measurement_session_id szerint kell szűrni.

9. Ha a system_alerts táblában nincs measurement_session_id, készíts
   forward-only migrációt:

   ALTER TABLE system_alerts
     ADD COLUMN IF NOT EXISTS measurement_session_id UUID
       REFERENCES measurement_sessions(id) ON DELETE SET NULL;

   Adj hozzá megfelelő indexet, és az új alert létrehozásakor töltsd ki a
   session ID-t.

REFERENCIA AKTIVÁLÁS

1. Szüntesd meg azt a működést, hogy location_name jelenléte automatikusan
   baseline_status_lookup hívást eredményez.

2. A referencia-összehasonlítás kizárólag akkor történjen, ha a request
   explicit reference_set_id értéket tartalmaz.

3. Betöltött referencia nélkül:
   - baseline_status vagy reference_status értéke legyen not_compared;
   - a frontend a Ref oszlopban „—” karaktert mutasson;
   - ne jelenjen meg ismert, új, átmenő vagy hiányzó státusz.

4. A kiválasztott reference_set_id legyen közös frontend state:
   selectedReferenceSetId.

5. Ugyanezt a selectedReferenceSetId értéket használja:
   - Spectrum;
   - Wi-Fi;
   - Bluetooth.

6. A referencia tabváltáskor ne változzon meg és ne válasszon ki automatikusan
   másik referenciát.

REFERENCIAÁLLAPOTOK

A fő Wi-Fi/Bluetooth táblában csak ezek legyenek:

- not_compared:
  karakter: —
  jelentés: nincs referencia betöltve

- in_reference:
  karakter: ✓
  jelentés: az eszköz szerepelt a betöltött referenciában

- new:
  karakter: ＋
  jelentés: az eszköz nem szerepelt a betöltött referenciában

Ne használj a fő táblában:
- transient / átmenő;
- stale / régi;
- known / ismert szöveges badge-et;
- missing / hiányzó sort az aktuális eszközlistában.

A jelenlegi baseline.py logikából távolítsd el azt a besorolást, hogy:

observation_count <= 1 -> transient

Minden aktuális sessionben észlelt eszköz, amelyre nincs biztos referencia-
egyezés, azonnal new státuszt kapjon, függetlenül az observation_count értékétől.

Az observation_count maradjon meg részletes technikai mezőként.

MEGVÁLTOZOTT ESZKÖZ

Ha az identity szerepel a referenciában, de valamely lényeges mező eltér:

- reference_status továbbra is in_reference;
- adj vissza has_differences: true értéket;
- adj vissza differences tömböt;
- a frontend mutasson „✓ ⚠” jelölést.

Wi-Fi különbségek legalább:
- SSID;
- encryption;
- device_type;
- channel;
- frequency;
- vendor.

Bluetooth különbségek legalább:
- device_name;
- vendor;
- address_type;
- bluetooth_type;
- company_id;
- service UUID fingerprint;
- manufacturer data hash.

JELENLÉTI ÁLLAPOT

1. A current_presence_state mezőt a backendben kompatibilitási okból
   megtarthatod.

2. A frontend Wi-Fi és Bluetooth táblájából távolítsd el az „Állapot”
   oszlopot.

3. Ne jeleníts meg „aktív” vagy „régi” szöveget.

4. Az utolsó észlelés oszlop mutassa:
   - pontos idő;
   - relatív idő;
   például: „09:51:25 · 43s”.

5. A session során legalább egyszer észlelt eszköz maradjon a session
   listájában akkor is, ha 60 másodpercnél régebben jelentkezett.

HIÁNYZÓ REFERENCIAESZKÖZÖK

Azok a referenciaeszközök, amelyek nem jelentek meg az aktuális sessionben,
ne kerüljenek az aktuális Wi-Fi/Bluetooth eszköztáblába.

A felső összesítő mutassa:

- Referenciában és aktuálisan is látható
- Új eszköz
- Referenciában szerepelt, de most nem észlelt

A „most nem észlelt” számláló legyen kattintható, és külön drawerben/modalban
mutassa az érintett referenciaeszközöket.

FRONTEND REFERENCIASÁV

Készíts közös referenciasávot:

REFERENCIA: [nincs betöltve / név / verzió / dátum]
Spectrum [✓/—] | Wi-Fi [✓/—] | Bluetooth [✓/—]
[Betöltés] [Eltávolítás] [Részletek]

A referenciasáv legyen ugyanaz minden fő fülön.

WI-FI TÁBLÁZAT

Javasolt oszlopok:

- Ref
- Utolsó észlelés
- BSSID / MAC
- AP/kliens típus
- SSID / kapcsolódó AP
- Vendor
- Csatorna / frekvencia
- RSSI
- Titkosítás
- Kockázat

BLUETOOTH TÁBLÁZAT

Javasolt oszlopok:

- Ref
- Utolsó észlelés
- MAC
- Eszköznév
- Vendor
- Address type
- Bluetooth type
- RSSI
- Service / profile
- Kockázat

RÉSZLETES ÖSSZEHASONLÍTÁS

A Ref karakter vagy a sor legyen kattintható.

Kattintáskor jobb oldali drawer mutassa két oszlopban:

Referenciaérték | Aktuális érték

A válasz tartalmazza:
- reference_values;
- current_values;
- differences;
- match_method;
- match_confidence;
- observation_count;
- first_seen_in_session;
- last_seen_in_session.

BLUETOOTH IDENTITY

Bluetooth/BLE egyezésnél ne csak MAC-címet használj.

Használható:
- stable_identity;
- public/static MAC;
- company ID;
- manufacturer_data_hash;
- service_uuid_fingerprint;
- device_name;
- vendor;
- address_type.

Random/private MAC esetén csak megfelelő confidence mellett jelöld
in_reference állapotúnak.

Ha nincs biztos egyezés, legyen new, és a részletekben jelenjen meg:
„Nem találtunk megfelelően biztos referencia-egyezést.”

BACKWARD COMPATIBILITY

- A régi baseline_status és current_presence_state mezők maradhatnak az API-ban.
- A frontend ne használja a transient és stale státuszokat.
- A meglévő endpointokat ne töröld.
- A régi baseline funkciókat ne törd el.
- Az új reference_set_id alapú összehasonlítás legyen az elsődleges.
- Régi kliens explicit legacy módban továbbra is használhassa a régi endpointot.

TESZTEK

Adj teszteket:

1. Új session indításakor a frontend listák üresek.
2. Új session nem mutat korábbi sessionből származó eszközt.
3. Session nélkül nem történik globális fallback.
4. Reference_set_id nélkül minden eszköz not_compared.
5. Helyszínnév önmagában nem indít összehasonlítást.
6. Referencia betöltése után:
   - szereplő eszköz -> in_reference;
   - nem szereplő eszköz -> new.
7. Egyetlen észlelés esetén is new legyen, ne transient.
8. current_presence_state stale érték ne jelenjen meg „régi” szövegként.
9. Lezárt session adatai read-only láthatók.
10. Új session indításakor a lezárt session frontend state-je törlődik.
11. Wi-Fi security események és anomáliák session szerint szűrődnek.
12. A kiválasztott reference_set_id megmarad Spectrum/Wi-Fi/Bluetooth
    tabváltáskor.
13. A hiányzó referenciaeszközök külön listában jelennek meg, nem az aktuális
    eszköztáblában.

A végén írd le:
- mely fájlokat módosítottad;
- hogyan változott a session-szűrés;
- hogyan változott a referencia kiválasztása;
- milyen teszteket futtattál;
- hogyan indítható újra csak a szükséges konténer.

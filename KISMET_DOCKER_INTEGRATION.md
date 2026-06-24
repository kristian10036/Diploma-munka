# Kismet Bluetooth RSSI konténeres integráció

Ez a projektverzió tartalmaz egy opcionális `kismet` Docker service-t, amely a módosított Kismet forrást építi be. A módosított Kismet Bluetooth/BLE eszközöknél a `bluetooth.device.rssi_last` mezőt is publikálja a WebUI/REST irányba.

## Indítás

`.env` fájlban ajánlott értékek:

```env
KISMET_INTEGRATION_ENABLED=true
KISMET_API_URL=http://host.docker.internal:2501
KISMET_HTTPD_USERNAME=kismet
KISMET_HTTPD_PASSWORD=change_me_kismet
KISMET_DEVICES_ENDPOINT=/devices/views/all/devices.json
KISMET_SOURCE=hci0
KISMET_SOURCE_NAME=bluetooth0
```

Indítás RF profillal:

```bash
docker compose --profile rf up --build
```

Csak a Kismet konténer:

```bash
docker compose --profile rf up --build kismet
```

A Kismet WebUI host network miatt itt lesz elérhető:

```text
http://localhost:2501
```

## Backend API-k

Kismet státusz:

```text
GET /api/kismet/status
```

Élő Kismet eszközök megtekintése:

```text
GET /api/kismet/devices?limit=100
```

Élő Kismet eszközök importálása a saját adatbázisba:

```text
POST /api/import/kismet/live
```

Form mezők:

```text
measurement_session_id: opcionális
location_name: opcionális, aktív session kereséshez
source_name: alapértelmezés kismet_live_api
allow_without_session: true/false
```

## Fontos konténeres korlát

Bluetooth/HCI capture Dockerben csak akkor lesz reális, ha a konténer látja a host HCI interfészt. Emiatt a service `network_mode: host` és `privileged: true` módban fut. Ez fejlesztői/labor környezetben oké, éles környezetben ezt szigorítani kell dedikált USB Bluetooth adapterrel és célzott jogosultságokkal.

## Bettercap kiegészítő konténer (BLE vendor enrichment)

A Bettercap saját, külön Docker service-ben fut (`compose.bettercap.yaml`,
`bettercap` service, `bettercap` profil mögött), ugyanúgy ahogy a Kismet is
külön konténerben fut. A Kismet marad az elsődleges Wi-Fi- és Bluetooth-
adatforrás; a Bettercap kizárólag BLE eszközfelderítésre és a Kismet által
látott eszközök vendor/manufacturer/service-UUID adatainak kiegészítésére
szolgál. Nincs benne aktív/támadó modul (nincs spoofing, deauth, MITM, packet
injection) – csak `api.rest` és `ble.recon` fut.

Indítás:

```bash
docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  -f compose.bettercap.yaml \
  --profile bettercap \
  up -d --build
```

Bettercap nélkül (profil nélküli indításnál) a rendszer változatlanul működik.

A valódi BLE/HCI hardver eléréséhez a `bettercap` service is `network_mode: host`
módban fut (ugyanaz a megkötés, mint a Kismetnél), ezért a backend a Bettercap
API-t `BETTERCAP_API_URL=http://host.docker.internal:8081` címen éri el (nem a
docker-hálózati `bettercap` névvel – host hálózati módban a konténernek nincs
saját docker DNS-neve). A REST API-t csak `NET_ADMIN`/`NET_RAW` capability védi
(nem `privileged: true`), és HTTP Basic Auth mögött van (`BETTERCAP_USERNAME`/
`BETTERCAP_PASSWORD`, alapból `user`/`pass`, a Bettercap saját defaultjai).

A Kismet és Bettercap lehetőleg külön Bluetooth adaptert használjon
(`KISMET_BLUETOOTH_INTERFACE`, alapból `hci0`; `BETTERCAP_BLE_INTERFACE`,
alapból `hci1`). Azonos adapter esetén a backend induláskor jól látható
figyelmeztetést logol és az `/api/bettercap/status` válaszban
`adapter_conflict_warning` mezőt ad vissza – ez nem állítja le a Kismetet.

A Kismet és Bettercap adatait a backend a `bluetooth_devices`/`bluetooth_observations`
táblákban egységes sorrá vonja össze (egy fizikai eszköz egy sor); a frontend nem
jeleníti meg, melyik collector látta. A vendor-feloldás rangsor-alapú
(`bluetooth_company_id` > `bettercap` > `kismet` > `oui` > `unknown`): egy
alacsonyabb rangú forrás ismételt pollingja sosem írja felül egy már megállapított
magasabb rangú vendoradatot. Bettercap teljes hiánya vagy leállása nem okoz
hibát a Kismet Bluetooth ágon, sem a backend, sem a frontend oldalán (a
`/api/bettercap/status` HTTP 200-at ad vissza `unreachable` állapottal, nem 500-at).

## Vendor-feloldási prioritás (Bluetooth/BLE)

1. BLE Manufacturer Specific Data Company Identifier (`bluetooth_company_id`,
   `vendor_resolution_method=bluetooth_company_id`, `vendor_confidence=high`);
2. Bettercap explicit manufacturer/vendor mező (`vendor_resolution_method=bettercap`);
3. Kismet manufacturer mező (`vendor_resolution_method=kismet`);
4. publikus/stabil MAC OUI;
5. `unknown`.

Random/private BLE cím (address type `random`/`private`/`resolvable`) esetén a
vendor-feloldás `vendor_confidence=low`-ra korlátozódik, és a gyártó **nem**
kerül megállapításra kizárólag a MAC első három bájtja alapján.

## Stabil identitás és confidence

- Wi-Fi AP/kliens: normalizált BSSID/MAC; `identity_confidence` `medium`, ha a
  cím locally administered (randomizált), egyébként `high`/`medium`.
- Bluetooth publikus/stabil cím: a MAC maga (`identity_confidence=high`).
- Bluetooth random/private cím: óvatos fingerprint
  (`blefp:<sha256>` a hirdetett név, company ID, rendezett service UUID-k,
  manufacturer data hash, address type és bluetooth type alapján),
  `identity_confidence` `low` erős fingerprint-jellemzők esetén, különben
  `unknown`. Két eszköz soha nem kerül összevonásra kizárólag azonos név vagy
  vendor alapján.

## Current-state vs history és deduplikáció

A `wifi_devices`/`bluetooth_devices` táblák az aktuális eszközállapotot tartják
(egy sor eszközönként, UPSERT). A `wifi_observations`/`bluetooth_observations`
táblák a ritkított mérési történetet tartják: új history sor csak akkor
keletkezik, ha az RSSI legalább `KISMET_HISTORY_RSSI_DELTA_DB` dB-lel változott,
az eszközállapot/SSID/csatorna/titkosítás/vendor/device type megváltozott, vagy
eltelt `KISMET_HISTORY_HEARTBEAT_SECONDS` másodperc az előző mintától. Ugyanaz a
Kismet device snapshot ismételt importja (process restart vagy manuális
"Kismet live import" után is) nem hoz létre új current-state sort, és nem
duplikálja a változatlan history sorokat.

## Wi-Fi management frame-ek és támadásgyanú

A backend a Kismet alert/eventbus API-ját (`GET /api/kismet/alerts`,
`POST /api/import/kismet/alerts`) integrálja a `system_alerts` táblába
(`domain=wifi_security`), és ezt a `GET /api/wifi/security-events` endpoint adja
vissza a frontend "Wi-Fi security események" táblázatának. A háttérfolyamat
(`collect_kismet_alerts_in_background`) `KISMET_POLL_INTERVAL_SECONDS`
időközönként automatikusan lekéri és importálja az új Kismet alerteket; a
Kismet kiesése csak ezt a folyamatot érinti, a device import és a többi backend
funkció tovább működik.

Minden Kismet-eredetű alert mezőt (frame type, reason code, forrás/cél MAC,
súlyosság, confidence) változatlanul, generikusan veszünk át — nincs hardkódolt,
feltételezett Kismet alert-osztálynév. Ha a forrás/cél MAC nem állapítható meg
megbízhatóan, az érték `null`, és a `confidence` `low`.

Emellett a backend néhány biztonsági eseményt **önállóan**, a már importált
Wi-Fi eszközállapot-változásokból derít (mert ezekre nincs általános, minden
Kismet-verzióban garantált natív alert):

- `new_open_ap` – korábban sosem látott BSSID, titkosítás nélkül. Locally
  administered (randomizált) BSSID esetén `confidence=low`, mert ez gyakran
  telefon hotspot/Wi-Fi Direct vagy randomizált kliens MAC, nem fix rogue AP
  (élő teszt során ez igazolódott: egy forgalmas helyszínen az új "nyílt AP"
  észlelések többsége ebbe a kategóriába esett).
- `ap_security_changed` – ismert BSSID titkosítása megváltozott.
- `bssid_fingerprint_changed` – ismert BSSID más SSID-vel jelent meg (Evil
  Twin/AP-impersonation gyanú).

**Korlát:** a Kismet eszköz-polling REST végpontja (`KISMET_DEVICE_FIELDS`) nem
ad vissza általános, eszközönkénti beacon/probe/auth/assoc darabszámot; ezért az
eszközönkénti management frame summary (`wifi_devices.management_frame_counts`,
`GET /api/wifi/devices` → `management_frame_summary`) kizárólag a tényleges
Kismet alert/eventbus eseményekből számolt, felismert frame type-okból épül fel
(`beacon`, `probe_request`, `probe_response`, `authentication`,
`association_request`, `association_response`, `reassociation`,
`disassociation`, `deauthentication`, `action`). Nem felismert frame/alert
típusnál nincs számlálás (nincs kitalált mező). Normál (nem támadás alatti)
környezetben ez a számláló jellemzően üres, mert a beacon/probe forgalmat
Kismet nem alert-ként jelenti.

A frontend felirata szándékosan "Feltételezett keretküldő", nem "Támadó", mert
a forrás MAC spoofolható.

## Wi-Fi/Bluetooth helyiség-referencia (baseline)

A meglévő mérési session/location rendszert használja, de **különálló**
adatmodell a `device_baselines` táblában (a spektrum reference rendszer
változatlan marad). Endpointok (Wi-Fi és Bluetooth közös, `protocol`
paraméterrel megkülönböztetve):

```text
POST /api/device-baseline/save        {protocol, location_name, measurement_session_id?, notes?}
GET  /api/device-baseline/compare?protocol=wifi&location_name=...&measurement_session_id=...
POST /api/device-baseline/deactivate  {protocol, location_name}
```

A mentés a megadott helyszínen (és opcionálisan session-ön) aktuálisan látott
Wi-Fi/Bluetooth eszközöket menti el új, verziószámmal jelölt, location-scoped
referenciaként, és a korábbi aktív verziót deaktiválja (nem törli). A
`GET /api/wifi/devices` és `GET /api/bluetooth/devices` `location_name`
paraméterrel hívva a `baseline_status` mezőt is feltölti.

Összehasonlítási állapotok:

- `known` – a baseline szerinti eszköz változatlanul jelen van;
- `changed` – ismert stabil identitás, de SSID/titkosítás (Wi-Fi) vagy vendor
  (Bluetooth) megváltozott;
- `new` – nincs egyező baseline-bejegyzés;
- `missing` – baseline-bejegyzés nem látható, **csak** a türelmi idő
  (`WIFI_BASELINE_MISSING_GRACE_SECONDS`, alapból 180s;
  `BLUETOOTH_BASELINE_MISSING_GRACE_SECONDS`, alapból 300s) letelte után — a
  csatornahopping és a BLE advertising-intervallum ne okozzon hamis hiányzást;
- `transient` – nem egyező eszköz, amelyet a session során csak egyszer
  észleltünk (jellemzően randomizált MAC-es, átmenő eszköz);
- `uncertain_match` – nem egyező stabil identitás, de a vendor (és Bluetooth
  esetén az alacsony/ismeretlen identity confidence) arra utal, hogy ugyanaz a
  fizikai eszköz randomizált címmel térhetett vissza; ez sosem von össze két
  eszközt automatikusan, csak jelzi a bizonytalan egyezést;
- `ignored` – a baseline-bejegyzés `expected_state=ignored`, ezért hiányzás
  esetén sem kerül `missing`-ként jelzésre.

A frontend Wi-Fi és Bluetooth fülén "Helyiség referencia mentése",
"Referencia összehasonlítás" és "Referencia deaktiválása" gomb érhető el; az
új/megváltozott sorok bal oldali színes jelölést kapnak, a sötét/zöld
alapstílus változatlan marad.

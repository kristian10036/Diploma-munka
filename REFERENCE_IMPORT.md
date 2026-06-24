# Referenciaimport és verziózás

## Támogatott formátumok

A verziózott referencia API két közvetlen formátumot támogat:

- CSV: vessző, pontosvessző vagy tabulátor elválasztással;
- JSON: metadata és frekvencia/jelszint pontokkal.

A minimális adatok:

```csv
frequency_hz,power_dbm
100000000,-84.2
100012500,-82.7
```

A frekvenciák pozitívak, szigorúan növekvők; a teljesítményértékek véges számok.
Egy import legfeljebb 64 MiB és 65 536 megtartott pont lehet. Nagyobb adatsornál
peak-preserving resampling történik, amely a lokális maximumokat nem egyszerű
átlagolással tünteti el.

## Verziózás

Az azonos `reference_key` új importja új verziót kap. Aktiváláskor ugyanazon kulcs
korábbi aktív verziói inaktívvá válnak. A fájl SHA-256 checksumja, az eredeti
fájlnév, mérési idő, antenna, downconverter, RBW/VBW, operátor, érvényesség és
megjegyzés tárolható. A meglévő migrációk nem íródnak át; az adatmodell forward
migrációval bővül.

Fő API-k:

- `POST /api/references/inspect`
- `POST /api/references/import`
- `GET /api/references`
- `GET /api/references/{id}`
- `POST /api/references/{id}/activate`
- `POST /api/references/{id}/deactivate`
- `GET /api/references/{id}/export?format=json|csv`

## `.peak`

A `.peak` gyártói formátumhoz nincs dokumentált parser a projektben. A rendszer
szándékosan `unsupported_peak_format` választ ad, nem próbálja CSV-ként vagy
kitalált bináris struktúraként értelmezni. Jelenlegi biztonságos folyamat:

```text
OSCOR .peak → gyártói Data Viewer → CSV export → referenciaimport
```

Közvetlen `.peak` támogatás csak hivatalos formátumleírás vagy jogszerűen
ellenőrizhető minták alapján, külön importer pluginnal kerülhet be.

## Állapot

- CSV/JSON importer: `implemented_tested`
- verziózás/aktiválás/export: `implemented_tested` kódszinten, élő DB acceptance szükséges
- `.peak`: `unsupported`
- valós OSCOR exportok széles körű validálása: `hardware_not_tested`

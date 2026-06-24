# Ismert jelek és marker workflow

## Marker

A marker frekvenciát, opcionális teljesítményt, helyszínt, sessiont, recordingot,
címkét, megjegyzést, kategóriát, színt és metadata objektumot tárol. A törlési
művelet archiválás (`archived_at`), nem fizikai törlés. Minden create/update/
archive művelet audit eseményt ír.

API: `GET/POST /api/markers`, `GET/PATCH/DELETE /api/markers/{id}`.

## Ismert jel profil

Az ismert jel nem frekvencia-alapú vak kivétel. A matching ellenőrzi a
frekvenciatoleranciát és minden megadott várható tulajdonságot: sávszélesség,
teljesítménytartomány, moduláció, protokoll, forrástípus és helyszín. Hiányzó
kötelező mérési tulajdonság eltérésnek számít.

Riasztás csak akkor nyomható el, ha a profil aktív, `suppress_alerts=true`, és
az összes megadott tulajdonság megfelel. A mérés és detection ettől még
megmarad. Eltérő teljesítmény, sávszélesség, moduláció, protokoll, helyszín vagy
forrás `changed` anomália alapja lehet.

API:

- `GET/POST /api/known-signals`
- `GET/PATCH/DELETE /api/known-signals/{id}`
- `POST /api/known-signals/match`

A `DELETE` itt is archiválás. Az adatmodell és a `rf_detections` review mezői a
`011_known_signals.sql` forward migrationben vannak.

## Állapot

- adatmodell/API/matching/unit és élő contract: `implemented_tested`;
- UI marker és ismertjel lista/context műveletek: `implemented_tested`;
- valódi hardveres jelprofil-validáció: `hardware_not_tested`;
- mock eredmény mindenhol mockként marad jelölve.

# Online anomáliadetektálási pipeline

## Adatút

```text
SpectrumFrame → bounded queue → rolling median/MAD baseline → detections
             ↘ drop counter                         ↘ known-signal matching
                                                      ↘ alert + audit
```

A spektrum broadcastot az elemzés nem blokkolhatja. A queue mérete korlátozott;
túlterheléskor frame drop történik, amely státuszban és Prometheus-metrikában
látható. A rendszer nem állítja, hogy betanított AI működik, amikor csak a
statisztikai baseline aktív.

## Hardver nélkül működő detektorok

- sequence gap;
- új csúcs a rolling median/MAD baseline felett;
- zajpadlóeltolódás;
- occupancy-változás;
- tartós keskenysávú jel;
- sávszélesség-változás;
- frekvenciadrift;
- rövid burst.

A detektor minden eseményhez típust, súlyosságot, confidence értéket,
magyarázatot és bizonyíték-metadata objektumot ad.

## Ismert jelek

A riasztás nem pusztán a frekvencia miatt némul el. Az egyezés frekvencia-
toleranciát, sávszélességet, teljesítményt, forrást, érvényességet és opcionális
moduláció/protokoll profilt is vizsgál. A mérés és a detection ettől még megmarad;
csak a megfelelő profilhoz illeszkedő riasztás nyomható el.

## Wi‑Fi és BLE

Passzív szabályok figyelik többek között az új BSSID-t/eszközt, titkosítás-
változást, rejtett SSID-t, szokatlan csatornát, service UUID-t, manufacturer
adatot, RSSI-változást és több helyszínen történő megjelenést. A randomizált BLE
MAC-cím önmagában nem bizonyít stabil eszközazonosságot.

## Human-in-the-loop

A detection review állapotai: `known`, `changed`, `false_positive`, `reviewed`.
Menthető operátor, megjegyzés, ismertjel-kapcsolat és a későbbi tanításba történő
bevonhatóság. Az alert életciklusa: `open → acknowledged → resolved`; minden
állapotváltozás auditált.

## ML

A klasszikus nearest-centroid és kis CNN kódja/model registry-je rendelkezésre
áll, de valós, recording-szinten szeparált és címkézett RF-adat nélkül
`not_trained`. A szabályalapú/statisztikai detektor nem kerül AI-ként félrecímkézésre.

## Állapot

- statisztikai pipeline és fixture tesztek: `implemented_tested`
- Wi‑Fi/BLE szabályok: `implemented_tested`
- DB persistence/alert workflow: `implemented_tested` kódszinten, élő DB acceptance szükséges
- klasszikus ML/CNN valós modell: `not_trained`
- hardveres teljesítménymérés: `hardware_not_tested`

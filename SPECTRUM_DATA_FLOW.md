# Spectrum adatfolyam

## Kontraktus

Az RF Agent `SpectrumFrame v1` objektumot ad a `/ws/spectrum` végponton. A
`spectrum-ingest` validálja, méretkorlátos latest-frame fan-outtal továbbítja,
a frontend pedig a `spectrum-frame-adapter.js` rétegen keresztül fogadja.

A frontend belső frekvenciaegysége Hz. A v1 frame mellett kompatibilis marad a
régi `[{x,y}]`, `[{freq,dbm}]` és számtömb payload. Hiányzó tartomány `NaN`, nem
zajpadló vagy `-105 dBm` mérés.

## Detail és overview

- Az aktuális natív frame saját `frequenciesHz` és `powersDbm` tömbje megmarad.
- A detail görbe pixelszintű min/max envelope-ot használ; a peak és marker a
  natív pontokon számolódik.
- A waterfall az aktuális center/span natív frame-jéből készül.
- A teljes tartományú overview külön accumulator. Bucketenként értéket,
  validity állapotot és utolsó frissítési időt tárol; a nem mért tartomány üres,
  a régi tartomány stale.

## Viewport/ROI v1

```text
POST /source/viewport
POST /api/rf-agent/source/viewport
```

Kötelező request mezők: `request_id`, `mode` (`fixed` vagy `sweep`),
`center_frequency_hz`, `span_hz`, `maximum_points`. Opcionális igényként
küldhető `desired_rbw_hz`. A válasz `accepted`, `constrained` vagy strukturált
elutasítás, és tartalmazza a tényleges start/stop/step/pontszám értékeket.

A mock source végrehajtása `implemented_mock_tested`. Replay és a jelenlegi
hardveradapterek capability alapján kontrolláltan elutasítják. Aaronia/USRP
hardveres viewport végrehajtás `hardware_not_tested`; a mock válaszban ezért
`hardware_execution=false`.

## Nagy frame továbbítás

A kompatibilis JSON WebSocket működik, méret- és pontszámkorláttal. Bináris
protokoll nincs kész; dokumentálatlan wire formátum nem került bevezetésre.

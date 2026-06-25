# RF ML classifier

## Megvalósított

- kizárólag valid `SpectrumFrame v1` bemenet;
- normalizált spektrogram/feature pipeline;
- recording/session szerinti determinisztikus split;
- szabályalapú baseline;
- klasszikus baseline tréner;
- kis CPU CNN prototípus;
- accuracy, precision, recall, macro-F1, per-class F1 és confusion matrix;
- modellregistry státusz és REST API.

## Jelenlegi őszinte állapot

A szabályalapú baseline használható. A klasszikus és CNN modell valós,
megbízhatóan címkézett, recording-szinten szeparált RF adatok nélkül
`not_trained`. Kismet RSSI soha nem használható CNN spektrogramként.

## Konfiguráció

- `ML_ENABLED` (default `true`): ha `false`, a runtime nem tölt be semmilyen
  modellt; `/api/ml/status` és `/api/ml/classify` egyértelmű `disabled`
  állapotot/503-at ad, nem esik vissza csendben a szabályalapú baseline-ra.
- `ML_MODEL_TYPE` (`rule` | `classical` | `cnn` | `onnx`, default `rule`):
  csak a `rule` ág tölt be valós, futtatható modellt. A `classical`/`cnn` ág
  `not_trained`, az `onnx` ág `model_not_found` állapotot ad, mivel ezekhez
  nincs a csomagban betanított modell vagy futtató loader; hibás értéknél a
  runtime figyelmeztetést logol és `rule`-ra esik vissza.

API:

```text
GET  /api/ml/status
GET  /api/ml/models
POST /api/ml/classify
```

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

API:

```text
GET  /api/ml/status
GET  /api/ml/models
POST /api/ml/classify
```

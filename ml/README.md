# RF ML pipeline

Az ML bemenet kizárólag valid `SpectrumFrame v1` sorozat vagy IQ-ból előállított
spektrogram lehet. Kismet Wi-Fi/Bluetooth RSSI nem spektrogram; csak időszinkron
kontextushoz és weak labelhez használható.

Adatkönyvtárak:

```text
ml/data/raw/        változatlan recordingok és IQ
ml/data/processed/  reprodukálható előfeldolgozott spektrogramok
ml/data/labels/     címkék és provenance
ml/data/splits/     recording/session szintű split manifestek
```

A közös implementáció a `python-processor/app/ml` csomagban található. A split
recording ID, ennek hiányában session ID szerint történik; frame-szintű random
split tilos. A core backend csak a kis CPU-s szabályalapú baseline-t tölti be.
PyTorch kizárólag külön training környezetben szükséges a `build_small_cnn`
modellhez; a háló kimenete logits, nincs explicit Softmax a tréningmodellben.

Recording címkézés JSONL formátuma:

```json
{"recording_path":"/recordings/uuid","label":"unknown","label_quality":"controlled_simulation","provenance":"scenario-id and generator version"}
```

A `label_quality` értéke `ground_truth`, `controlled_simulation` vagy `weak_label`.
A builder a weak labelt alapértelmezetten elutasítja, ellenőrzi a recording SHA-256
checksumát, majd atomikusan `.npz` spektrogramablakokat ír. Példa:

```bash
python ml/build_dataset.py ml/data/labels/recordings.jsonl ml/data/processed ml/data/labels/windows.jsonl
python ml/split_manifest.py ml/data/labels/windows.jsonl ml/data/splits/v1.json
python ml/train_classical.py ml/data/labels/windows.jsonl ml/data/splits/v1.json ml/models/classical-v1
python ml/train_cnn.py ml/data/labels/windows.jsonl ml/data/splits/v1.json ml/models/cnn-v1
```

A zstd recordingok feldolgozásához a `zstd` CLI szükséges. A CNN tréning külön
környezetében a `ml/requirements-training.txt` telepítendő. Mindkét tréner
elutasítja a weak labelt; a kimenet tartalmazza a teljes metrikakészletet, az
inferencia-latencyt és a modellméretet.

Első osztálylista: `wifi_2_4g`, `wifi_5g`, `bluetooth`, `zigbee`,
`narrowband_unknown`, `wideband_unknown`, `noise`, `unknown`. A baseline a
`zigbee` osztályt visszatartja, mert spektrum-alakból önmagában nem áll
rendelkezésre elég protokollbizonyíték.

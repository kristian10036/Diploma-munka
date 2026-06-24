# RF agent

A `rf-agent` C++17 szolgáltatás a hardverfüggetlen RF source API és a
`SpectrumFrame v1` előállítója.

## Megvalósított

- mock és replay source;
- központi producer/latest-frame elosztás;
- zstd NDJSON recording, atomikus publikálás és SHA-256;
- REST: health/status/capabilities/source/replay/recording;
- WebSocket: spectrum és status;
- izolált Aaronia és USRP probe runner;
- SDRangel REST control client;
- strukturált disabled/unavailable/ready állapotok.
- verziózott viewport/ROI szerződés: mock source tesztelt, replay és hardver
  capability alapján kontrolláltan elutasított.

## Build

```bash
sudo apt install -y build-essential cmake ninja-build libboost-dev \
  libssl-dev libzstd-dev nlohmann-json3-dev

cmake -S rf-agent -B rf-agent/build-native -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DENABLE_AARONIA=ON \
  -DENABLE_USRP=OFF
cmake --build rf-agent/build-native --parallel "$(nproc)"
ctest --test-dir rf-agent/build-native --output-on-failure
```

USRP helper fordítása UHD-val:

```bash
cmake -S rf-agent -B rf-agent/build-usrp -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DENABLE_AARONIA=ON \
  -DENABLE_USRP=ON
cmake --build rf-agent/build-usrp --parallel "$(nproc)"
```

Az `ENABLE_USRP=ON` jelenleg az `usrp-probe` helper elkészítését jelenti, nem
folyamatos IQ data plane-t.

## Natív futtatás

```bash
RF_AGENT_BIND_ADDRESS=0.0.0.0 \
RF_AGENT_PORT=8765 \
RF_SOURCE_MODE=mock \
RF_RECORDINGS_ROOT="$PWD/recordings" \
ENABLE_AARONIA=true \
ENABLE_USRP=false \
SDRANGEL_ENABLED=false \
./rf-agent/build-native/rf-agent
```

## Hardver-státusz értelmezése

- Aaronia `sdk_ready`: SDK betölthető, **nem** bizonyítja a teljes adatút működését.
- Aaronia `library_sigill`: CPU utasításkészlet inkompatibilitás; a fő agent nem omlik össze.
- USRP `device_found`: UHD lát eszközt; a worker adatút továbbra is `not_implemented`.
- SDRangel `control_plane=ready`: REST elérhető.
- SDRangel `data_plane=configured_not_tested`: csak konfiguráció létezik, valós IQ továbbítás nincs igazolva.

Viewport API: `POST /source/viewport`. A mock végrehajtás nem bizonyítja az
Aaronia vagy USRP tuning működését; ezek továbbra is `hardware_not_tested`.

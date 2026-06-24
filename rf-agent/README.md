# C++ RF Agent

A `rf-agent` a hardverfüggetlen RF source lifecycle, a közös `SpectrumFrame v1`,
a replay/recording és a hardverközeli integrációs pontok gazdája.

## Megvalósított

- `MockRfSource` és `ReplayRfSource`;
- egyetlen központi producer és latest-frame fan-out;
- WebSocket-klienstől független recording;
- streaming zstd NDJSON, SHA-256 és atomikus publikálás;
- timestamp-alapú replay, pause/resume/seek/loop/sebesség;
- REST és `/ws/spectrum`, `/ws/status`;
- izolált Aaronia és USRP probe runner;
- SDRangel REST control client;
- közös FFT pipeline és unit tesztek.

## Nem kész hardveres adatút

- Aaronia SPECTRAN V6 packet/IQ worker;
- folyamatos UHD RX worker;
- SDRangel IQ data plane.

Ezek státuszban is külön `not_implemented`, `not_configured` vagy
`configured_not_tested` értéket adnak. A probe siker csak SDK/device discovery,
nem teljes adatút.

## Natív build

```bash
sudo apt install -y build-essential cmake ninja-build libboost-dev \
  libssl-dev libzstd-dev nlohmann-json3-dev

cmake -S . -B build-native -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DENABLE_AARONIA=ON \
  -DENABLE_USRP=OFF
cmake --build build-native --parallel "$(nproc)"
ctest --test-dir build-native --output-on-failure
```

UHD helperrel:

```bash
cmake -S . -B build-native-uhd -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DENABLE_AARONIA=ON \
  -DENABLE_USRP=ON
cmake --build build-native-uhd --parallel "$(nproc)"
```

## Fő endpointok

```text
GET  /health
GET  /status
GET  /capabilities
GET  /sources
POST /sources/select
POST /source/start
POST /source/stop
POST /source/configure
GET  /recordings
GET  /recordings/{id}
GET  /recordings/status
POST /recordings/start
POST /recordings/stop
POST /replay/start|pause|resume|seek|stop
GET/POST /aaronia/probe
GET      /aaronia/status
GET/POST /usrp/status|probe
GET      /sdrangel/status
POST     /sdrangel/tune
POST     /sdrangel/demod/start
POST     /sdrangel/demod/stop
WS       /ws/spectrum
WS       /ws/status
```

A részletes indítás a gyökér `RUNNING.md` fájlban található.

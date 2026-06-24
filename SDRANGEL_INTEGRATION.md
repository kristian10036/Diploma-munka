# SDRangel integráció

## Control plane

A C++ RF Agent opcionális REST klienst tartalmaz:

```text
GET  /sdrangel/status
GET  /sdrangel/devicesets
GET  /sdrangel/devices
POST /sdrangel/tune
POST /sdrangel/demod/start
POST /sdrangel/demod/stop
```

Konfiguráció:

```env
SDRANGEL_ENABLED=true
SDRANGEL_API_URL=http://host.docker.internal:8091/sdrangel
SDRANGEL_TIMEOUT_SECONDS=5
SDRANGEL_DEVICE_SET_INDEX=0
SDRANGEL_DEVICE_SETTINGS_KEY=
```

A device settings kulcs plugin- és verziófüggő. Üres
`SDRANGEL_DEVICE_SETTINGS_KEY` esetén a kliens a futó DeviceSet settings
válaszából validáltan választja ki az egyetlen `*Settings` objektumot.
Támogatott vezérlőnevek: `AM`, `NFM`, `WFM`, `USB`, `LSB`.

Hostoldali indítás:

```bash
flatpak run --command=sdrangelsrv org.sdrangel.SDRangel
curl -i http://127.0.0.1:8091/sdrangel
```

Alkalmazásoldali végpontok: `/api/integrations/sdrangel/status`,
`GET/POST /api/integrations/sdrangel/devicesets`,
`/api/integrations/sdrangel/devices`, `/api/rf-agent/sdrangel/tune`,
`/api/rf-agent/sdrangel/demod/start` és `/api/rf-agent/sdrangel/demod/stop`.
A kliens timeoutot, egy korlátozott retryt, JSON-validálást és az utolsó sikeres
kapcsolódás időpontját kezeli. Az SDRangel hiánya nem állítja le az rf-agentet.
Az élő control plane SDRangelSrv 7.23.1 verzióval hostról és konténerből
tesztelt. DeviceSet létrehozás, TestSource kiválasztás, 145,5 MHz tuning, NFM
csatorna létrehozás és `running` állapot is alkalmazás-API-n át ellenőrzött.
Az NFM `rfBandwidth`, `squelch` és `inputFrequencyOffset` mezők a 7.23.1
válaszából visszaolvasva igazoltak.

## IQ data-plane absztrakció

Az SDRangel REST API nem IQ-adatcsatorna. A projekt ezért külön, verziózott IQ
packet szerződést és bounded pipeline-t tartalmaz:

- explicit `cf32_le` vagy `ci16_le` formátum;
- center frequency és sample rate metadata;
- sequence és timestamp;
- bounded queue és drop-oldest szabály;
- packet-loss, queue, drop és reconnect számlálók;
- mock source/sink roundtrip teszt;
- kontrollált `not_configured`, `configured_not_tested`, `ready_mock` és
  hibaállapotok.

Konfiguráció:

```env
SDRANGEL_DATA_PLANE_MODE=not_configured
SDRANGEL_DATA_PLANE_ENDPOINT=
SDRANGEL_IQ_SAMPLE_FORMAT=cf32_le
SDRANGEL_IQ_SAMPLE_RATE_HZ=0
```

A mock data plane `implemented_mock_tested`; a tényleges SDRangel network
sample-source vagy saját input plugin nincs kiválasztva, ezért a valós adatút
`not_configured`/`hardware_not_tested`.

## UI gating

A Spektrum nézet demodulációs panelje akkor enged indítást, ha:

1. a control plane elérhető;
2. legalább egy SDRangel Rx DeviceSet létezik.

A panel külön DeviceSetet hozhat létre explicit forrástípussal. Nem irányítja
automatikusan az Aaronia SpectrumFrame adatot SDRangelen át. A bandwidth és
squelch az igazolt NFM 7.23.1 profilnál aktív. A spectrum `powers_dbm` adatból
nem készíthető utólag hang; a demoduláció az SDRangel saját Rx DeviceSetjén fut.

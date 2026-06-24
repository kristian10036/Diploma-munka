# USRP / UHD integráció

## Megvalósított skeleton

- runtime engedélyezés: `ENABLE_USRP`;
- izolált `usrp-probe` runner és REST státusz;
- opcionális UHD-alapú `usrp-probe` build;
- modellfüggetlen UHD device discovery;
- device args továbbítása;
- strukturált `device_found`, `no_devices`, `uhd_error`, timeout és helper-hiány státusz.

## Nem implementált

- folyamatos UHD RX worker;
- IQ frame IPC;
- FFT bekötés;
- overflow/late packet kezelés;
- több USRP idő/PPS/GPSDO szinkron;
- sweep scheduler;
- valós hardveres acceptance.

## Natív ellenőrzés

```bash
uhd_config_info --version
uhd_find_devices
uhd_usrp_probe
/usr/local/bin/usrp-probe
curl -s -X POST http://127.0.0.1:8765/usrp/probe | jq
```

A `No UHD Devices Found` hardver nélkül normális. A `device_found` csak discovery,
nem jelenti a data plane elkészültét.

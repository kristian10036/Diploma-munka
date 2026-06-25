# Aaronia SPECTRAN V6 integráció

## Jelenlegi állapot

- RTSA Suite/SDK útvonal-felderítés: **implemented**.
- `aaronia-probe` izolált subprocess: **implemented and tested**.
- `SIGILL`, `SIGSEGV`, timeout és hibás JSON kezelése: **tested**.
- Valós SPECTRAN V6 SDK init és eszközfelderítés: **tested on this host**.
- Valós SPECTRAN V6 SpectrumFrame worker: **implemented and hardware-tested**.
- Folyamatos spektrummérés: **tested through rf-agent, spectrum-ingest and frontend WebSocket**.
- IQ-mérés: **not implemented by this SpectrumFrame worker**.

AVX2 nélküli gépen a probe `incompatible_cpu`, váratlan `SIGILL` esetén
`illegal_instruction` állapotot ad. Ez host-kompatibilitási korlát, nem
telepítési vagy Compose-hiba.
Az agent a probe-folyamat izolációja miatt tovább működik.

## Ellenőrzés

```bash
curl -s -X POST http://127.0.0.1:8765/aaronia/probe | jq
curl -s http://127.0.0.1:8765/aaronia/status | jq
```

Compose-ban a hoston már telepített PRO könyvtár és a hozzá tartozó `lib`
könyvtár read-only bind mount. A használt útvonal:

```env
AARONIA_RTSA_LIBRARY_PATH=/opt/aaronia-rtsa-suite/Aaronia-RTSA-Suite-PRO/libAaroniaRTSAAPI.so
```

Az SDK firmware-feltöltés közben újraenumerálja az USB eszközt, ezért egyetlen
`/dev/bus/usb/BBB/DDD` node nem tartós. Az rf-agent a host USB buszt bind
mountként és csak a 189-es USB character-device cgroup szabállyal kapja meg;
nem fut privileged módban. A `72-aaronia.rules` a `2f72:0060` eszköznek 0666
jogosultságot ad.

Fontos állapotok: `library_not_found`, `dependency_missing`,
`incompatible_architecture`, `incompatible_cpu`, `illegal_instruction`,
`initialization_failed`, `device_not_connected`, `degraded`, `running`.

## Folyamatos adatút

Az izolált `aaronia-worker` a dokumentált `spectranv6/sweepsa` SDK-forrást
használja. A worker NDJSON IPC-n adja át a SpectrumFrame adatot az rf-agentnek;
az agent központi latest-frame buffere megakadályozza, hogy lassú kliensek
blokkolják a hardvert. Worker-hiba után 5–30 másodperces korlátozott exponential
backoff indul. Az rf-agent processzenként egyedi session ID-t használ, ezért
újraindításkor nem keveredik két sequence-tartomány.

Az ellenőrzött hardveres útvonal:

```text
SPECTRAN V6 -> aaronia-worker -> rf-agent /ws/spectrum
            -> spectrum-ingest -> frontend (WEB/Nginx, közvetlenül)

rf-agent /ws/spectrum -> backend (párhuzamos analitikai fogyasztó: DB, ML,
                          riasztások - nem a frontend útjának közbenső állomása)
```

A pontos felelősségi határt és a teljes ábrát lásd: `ARCHITECTURE.md`
("Áttekintő diagram", "RF adatút", "Felelősségi határok") és
`SPECTRUM_DATA_FLOW.md`.

A tesztelt beállítás 2400–2500 MHz, 100 kHz RBW, legfeljebb 16384 pont és
10 FPS. A tényleges frame 2000 pontot tartalmazott. Az SDK `dropped` és
`inaccurate` flagjei változtatás nélkül megmaradnak; az ingest külön méri a
sequence gapet és a lassú kliens queue-dropot.

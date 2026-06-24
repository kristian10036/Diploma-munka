# A rendszer indítása

Ez a fájl a Debian szerverhez készült. A parancsokat a projekt gyökerében futtasd:

```bash
cd ~/Diploma_munka5_kismet_integrated
```

## 1. Első beállítás

```bash
cp .env.example .env
nano .env
```

Legalább ezeket változtasd meg:

```env
POSTGRES_PASSWORD=egy_hosszu_eros_jelszo
KISMET_HTTPD_PASSWORD=egy_masik_eros_jelszo
```

A Compose-fájlokat mindig explicit add meg; kizárólag a karbantartott `compose*.yaml` rétegeket használd.

Konfiguráció ellenőrzése:

```bash
docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  config --quiet
```

## 2. Ajánlott HP-demó indítás

A régi HP-n mock/replay RF-forrással, Kismettel, de AI nélkül:

```bash
set -a
source config/hp-demo.env
source .env
set +a

docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  up -d --build
```

Elérési címek:

```text
Webalkalmazás:  http://SZERVER_IP:8080
Kismet UI:      http://SZERVER_IP:2501  # csak a host-network RF/Kismet profilban
```

Az RF Agent alapból csak a belső Compose-hálózaton érhető el. Közvetlen host
portot csak diagnosztikai/dev override-ban vagy natív systemd futtatásnál nyiss.

Állapot:

```bash
docker compose -f compose.yaml -f compose.rf.yaml ps -a
curl -s http://127.0.0.1:8080/api/health | jq
docker compose -f compose.yaml -f compose.rf.yaml exec rf-agent curl -fsS http://127.0.0.1:8765/status | jq
```

Naplók:

```bash
docker compose -f compose.yaml -f compose.rf.yaml logs -f --tail=150
```

## 3. Csak a core rendszer

RF Agent, Kismet és Ollama nélkül:

```bash
docker compose -f compose.yaml up -d --build
```

A backend ilyenkor működik, az RF-integráció státusza viszont `unreachable` vagy `disabled` lehet. A Prometheus helyben, internet nélkül fut; Grafana nincs a rendszerben.

Leállítás:

```bash
docker compose -f compose.yaml down
```

## 4. Teljes rendszer Ollamával

```bash
docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  up -d --build
```

A `.env` fájlban állíts be válaszadó modellt:

```env
AI_ENABLED=true
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=300
RAG_ENABLED=true
RAG_EMBEDDING_PROVIDER=ollama
RAG_EMBEDDING_MODEL=bge-m3
```

Modellek letöltése:

```bash
bash scripts/ollama-setup.sh
```

Embeddingmodell-váltás után a dokumentumokat újra kell indexelni.

Teljes stack leállítása:

```bash
docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  down
```

**Ne használd a `-v` kapcsolót**, mert az volume-okat és így adatokat törölhet.

## 5. Módosított fájlok újrabuildelése

```bash
docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  up -d --build
```

Teljes cache nélküli build csak indokolt esetben:

```bash
docker compose \
  -f compose.yaml \
  -f compose.rf.yaml \
  -f compose.ai.yaml \
  build --no-cache
```

## 6. Natív RF Agent

A hardverközeli végleges megoldásnál az RF Agent natívan fusson. Függőségek Debian 13-on:

```bash
sudo apt update
sudo apt install -y \
  build-essential cmake ninja-build pkg-config \
  libboost-dev libssl-dev libzstd-dev nlohmann-json3-dev
```

Alap build mock/replay és Aaronia probe támogatással:

```bash
cd ~/Diploma_munka5_kismet_integrated/rf-agent
cmake -S . -B build-native -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DENABLE_AARONIA=ON \
  -DENABLE_USRP=OFF
cmake --build build-native --parallel "$(nproc)"
ctest --test-dir build-native --output-on-failure
```

UHD-val fordított USRP probe az újabb gépen:

```bash
cmake -S . -B build-native-uhd -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=ON \
  -DENABLE_AARONIA=ON \
  -DENABLE_USRP=ON
cmake --build build-native-uhd --parallel "$(nproc)"
ctest --test-dir build-native-uhd --output-on-failure
```

Telepítés:

```bash
sudo install -m 0755 build-native/rf-agent /usr/local/bin/rf-agent
sudo install -m 0755 build-native/aaronia-probe /usr/local/bin/aaronia-probe
```

UHD build esetén:

```bash
sudo install -m 0755 build-native-uhd/usrp-probe /usr/local/bin/usrp-probe
```

Systemd példa: `deploy/systemd/README.md`.

### Natív agent + Docker core

Ne fusson egyszerre a Dockeres és a natív RF Agent ugyanazon a `8765` porton.

A `.env` fájlba:

```env
RF_AGENT_URL=http://host.docker.internal:8765
RF_AGENT_WS_URL=ws://host.docker.internal:8765/ws/spectrum
```

Indítsd a natív agentet, majd a core stacket:

```bash
sudo systemctl start diploma-rf-agent
docker compose -f compose.yaml up -d --build
```

Kismet külön indítható a Dockeres rf-agent elindítása nélkül:

```bash
docker compose -f compose.yaml -f compose.rf.yaml up -d kismet
```

## 7. Aaronia, USRP és SDRangel ellenőrzés

```bash
curl -s -X POST http://127.0.0.1:8765/aaronia/probe | jq
curl -s -X POST http://127.0.0.1:8765/usrp/probe | jq
curl -s http://127.0.0.1:8765/sdrangel/status | jq
```

AVX2 hiányakor az Aaronia probe `incompatible_cpu`, váratlan SIGILL esetén
`illegal_instruction` állapotot ad. A valódi SPECTRAN V6 teszt külön,
csatlakoztatott hardvert igényel.

Az SDRangel REST control plane implementált. A bounded IQ data-plane interfész és mock source/sink tesztelt, de a tényleges SDRangel input/plugin addig `not_configured`, amíg nincs kiválasztva és valós eszközzel ellenőrizve.

## 8. Acceptance, audit és mentés

```bash
bash scripts/acceptance-test.sh --offline
PYTHONPATH=python-processor python scripts/mock-load-fixture.py --output /tmp/dm-load-report.json
bash scripts/acceptance-test.sh       # futó Docker stack mellett
bash scripts/docker-audit.sh
bash scripts/docker-cleanup.sh
bash scripts/backup.sh
```

A cleanup és backup alapból dry-run. Tényleges végrehajtás:

```bash
bash scripts/docker-cleanup.sh --apply
bash scripts/backup.sh --apply
```

Restore először dry-run módban:

```bash
bash scripts/restore.sh /backup/konyvtar
```

Tényleges restore csak üres célra:

```bash
bash scripts/restore.sh /backup/konyvtar --apply
```

Meglévő adatok felülírása csak tudatosan:

```bash
bash scripts/restore.sh /backup/konyvtar --apply --force
```

## 9. Gyors hibakeresés

```bash
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml ps -a
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml logs --tail=200
curl -i http://127.0.0.1:8080/api/health
docker compose -f compose.yaml -f compose.rf.yaml exec rf-agent curl -i http://127.0.0.1:8765/status
ss -lntp | grep -E ':(8080|8765|2501|8091)\b'
```

Adatvesztést okozó parancsokat ne használj:

```text
docker compose down -v
docker system prune -a --volumes
```


## 10. Offline monitoring

A Prometheus csak a belső Docker-hálózaton fut, nincs `remote_write` és nincs
Grafana. A saját Rendszerállapot fül a backend `/api/monitoring/*` API-ján
keresztül jeleníti meg az aktuális és történeti adatokat. Részletek:
`MONITORING.md`.

## 11. Aktuális Compose indítások és health ellenőrzés

Fejlesztés (a dev fájl csak override):

```bash
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml -f compose.dev.yaml up -d --build
```

Demo/production jellegű futás bind mount és reload nélkül:

```bash
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml up -d --build
```

A `migrate` a `diploma-backend:local` image-et használja, healthy adatbázisra
vár, checksumot ellenőriz és siker után `Exited (0)`. Az Ollama image
`ollama/ollama:latest`; frissítése nem törli a `ollama-data` volume-ot.

```bash
bash scripts/ollama-setup.sh
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml exec ollama ollama list
curl -s http://127.0.0.1:8080/api/health/status | jq
curl -s http://127.0.0.1:8080/api/assistant/status | jq
curl -s http://127.0.0.1:8080/api/rag/status | jq
```

## 12. Valós Aaronia és SDRangel futás

Az Aaronia valós spektrumforrás alapbeállítása:

```env
RF_SOURCE_MODE=aaronia
SPECTRUM_SOURCE_MODE=spectrum_ingest
FFT_MAX_FPS=10
AARONIA_MAX_FPS=10
```

Ellenőrzés:

```bash
curl -s http://127.0.0.1:8080/api/spectrum/source/status | jq
curl -s http://127.0.0.1:8080/api/integrations/sdrangel/status | jq
```

Az SDRangel külön hostfolyamat:

```bash
flatpak run --no-documents-portal --command=sdrangelsrv org.sdrangel.SDRangel
```

A frontend SDRangel panelje explicit DeviceSet létrehozást, tuningot és
AM/NFM/WFM/USB/LSB csatornavezérlést ad. Az NFM bandwidth/squelch profil
SDRangelSrv 7.23.1-en tesztelt. Az Aaronia spektrumút és az SDRangel demoduláció
két külön adatút; egyik sem kerül automatikusan a másikba.

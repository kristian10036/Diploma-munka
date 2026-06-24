# Migráció a demonstrációs gépről az erősebb célgépre

A költözés forráskód-módosítás nélkül, konfigurációval és ellenőrzött backuppal
történjen. A core alkalmazás Dockerben maradhat; a hardverközeli RF Agent
ajánlottan natív systemd szolgáltatásként fusson.

## 1. Forrásgép lezárása

```bash
bash scripts/pre-migration-check.sh
bash scripts/acceptance-test.sh --offline
bash scripts/backup.sh --apply
```

Ellenőrizd a backup könyvtár `SHA256SUMS` fájlját, a PostgreSQL dumpot és a
recording-katalógust. A projektet, a backupot és az előre lehúzott Docker
image-eket együtt másold át.

## 2. Célgép előkészítése

```bash
sudo mkdir -p /srv/diploma/{postgres,kismet,uploads,exports,backups,prometheus}
sudo mkdir -p /srv/diploma/recordings/{spectrum,iq,audio,.quarantine}
sudo mkdir -p /srv/diploma/ml/{models,data}
sudo chown -R 10003:10003 /srv/diploma/recordings /srv/diploma/uploads /srv/diploma/exports
```

Telepítendő:

- Docker Engine és Compose plugin;
- natív RF Agent buildfüggőségei;
- Aaronia SDK és dinamikus könyvtárai, ha használva lesz;
- UHD, ha USRP lesz;
- opcionálisan `sdrangelsrv`;
- GPU driver és NVIDIA Container Toolkit csak AI/GPU profilhoz.

Másold a `.env.example` fájlt `.env` néven, állíts be erős titkokat, és generáld
a tokenhasheket:

```bash
python python-processor/scripts/hash_api_token.py 'hosszu-egyszeri-operator-token'
```

Production minimum:

```env
APP_MODE=production
AUTH_MODE=api_token
AUTH_ANONYMOUS_READ=true
AUTH_OPERATOR_TOKEN_SHA256=<sha256>
POSTGRES_PASSWORD=<eros-egyedi-jelszo>
```

## 3. Profilok

- core: `compose.yaml`
- RF/Kismet: `compose.rf.yaml`
- opcionális AI: `compose.ai.yaml`
- fejlesztési kiegészítés: `compose.dev.yaml`
- hardver nélküli profil: `config/hp-demo.env`
- célgépes sablon: `config/production-hardware.env`

Konfigurációellenőrzés:

```bash
docker compose -f compose.yaml -f compose.rf.yaml -f compose.ai.yaml config --quiet
```

## 4. Restore és indítás

1. Töltsd be az offline image-csomagot, ha nincs internet.
2. Indítsd a PostgreSQL-t és a migrációs szolgáltatást.
3. Restore először dry-run módban:

```bash
bash scripts/restore.sh /backup/konyvtar
bash scripts/restore.sh /backup/konyvtar --apply
```

4. Indítsd a core stacket.
5. Futtasd a post-migration és online acceptance ellenőrzést.
6. Csak ezután aktiváld külön az Aaronia, USRP és SDRangel komponenseket.

Meglévő céladat felülírásához a `--force` tudatosan szükséges; előtte új backup
kötelező.

## 5. Natív RF Agent határ

A Dockeres és natív RF Agent ne fusson egyszerre ugyanazon a porton. A natív
szolgáltatás mintája:

- `deploy/systemd/dm-rf-agent.service`
- `deploy/systemd/rf-agent.env.example`

A backend a host agentet belső, tűzfallal korlátozott címen érje el. A 8765-ös
portot ne tedd ki nem megbízható hálózatra.

## 6. Hardveres ellenőrzési sorrend

```text
Aaronia probe → USRP probe → SDRangel control → IQ data-plane teszt →
SpectrumFrame schema/sequence → recording/replay → teljes mérési acceptance
```

A discovery/probe siker nem bizonyítja a folyamatos nagysebességű adatút
működését. A hardveres terhelést és a tényleges frame/RBW értékeket külön kell
mérni és dokumentálni.

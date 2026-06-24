# Biztonságos production profil

## Módok

- `APP_MODE=demo`: az autentikáció konfigurálhatóan kikapcsolható.
- `APP_MODE=production`: a backend fail-fast módon megtagadja az indulást, ha
  nincs `DATABASE_URL`, `AUTH_MODE=api_token`, illetve operátor/admin tokenhash.

Éles módban alapértelmezetten nincs névtelen írás. Az olvasás az
`AUTH_ANONYMOUS_READ` kapcsolóval engedélyezhető vagy tiltható.

## Tokenes szerepkörök

- viewer: olvasás;
- operator: írási műveletek;
- admin: írási műveletek és későbbi admin funkciók alapja.

A nyers token nem kerül konfigurációba. SHA-256 hash készítése:

```bash
python3 python-processor/scripts/hash_api_token.py
```

A kapott hash az `AUTH_OPERATOR_TOKEN_SHA256` vagy
`AUTH_ADMIN_TOKEN_SHA256` változóba kerül. Kérés:

```text
Authorization: Bearer <nyers-hosszú-véletlen-token>
```

A projekt nem tárol hardcoded admin jelszót. Ez tokenes mód; felhasználói
jelszavas login később csak erős, adaptív jelszóhash-sel vezethető be.

## Hálózat

A core `compose.yaml` fájlban csak a reverse proxy publikál host portot.
PostgreSQL, MQTT, backend, spectrum-ingest és Prometheus csak a belső Docker-
hálózaton érhető el. A konténeres RF-agent szintén belső `expose` portot használ;
natív hardveres futtatásnál a systemd minta alapból `127.0.0.1` címre bindol.

Grafana nincs a rendszerben. A Prometheus helyi, offline TSDB és lekérdezőmotor;
`remote_write` nincs konfigurálva.

## Proxy és HTTP

- request-body limit;
- WebSocket bufferelés kikapcsolva;
- hosszú read timeout;
- `nosniff`, frame tiltás, referrer és permissions policy;
- CSP;
- backend request ID;
- API-válaszok `no-store` cache kezelése.

TLS-t a reverse proxy előtt belső CA-val vagy szervezeti TLS terminátorral kell
megoldani. A kulcs és tanúsítvány nem kerülhet a repositoryba.

## Napló és audit

A JSON log tartalmaz timestampet, szintet, szolgáltatást, request/session/
recording/source ID-t. Titokjellegű kulcsok maszkoltak, teljes nyers import vagy
érzékeny payload nem kerül logba. Docker `local` logging driver rotációt használ.
Minden API írási kérés műveleti auditot kap; a domainműveletek saját részletes
audit eseményt is írnak.

## Fájlbiztonság

- a feltöltések korlátozott olvasással (`limit + 1 byte`) kerülnek memóriába, így
  a kliens által megadott `Content-Length` nem kerül vakon elfogadásra;
- a CSV/JSON importok elutasítják az egyértelmű bináris tartalmat;
- a referencia-képek PNG/BMP magic byte alapján azonosítottak, nem kizárólag a
  fájlnév vagy a kliens MIME fejléce alapján;
- fájlnév `Path(...).name` normalizálás;
- recording ID allowlist;
- atomikus staging és rename;
- checksum;
- retention csak dry-run terv, automatikus törlés nincs;
- `.peak` ismeretlen formátum kontrolláltan elutasított.

## Konténer hardening

A nem privilegizált, állapotmentes szolgáltatások read-only root fájlrendszert,
`/tmp` tmpfs-t, `no-new-privileges` beállítást és eldobott Linux capability-ket
kapnak. Az Nginx konténerek csak a saját futási könyvtáraikhoz kapnak tmpfs-t.
A PostgreSQL és a hardveres Kismet profil kivétel, mert a szigorítás ott a
szükséges írást vagy eszközhozzáférést törné.

## Production indítás

A `config/production-hardware.env` titok nélküli sablon. Másolás után a titkokat
külön, nem verziókezelt `.env` fájlban kell megadni. Indítás előtt:

```bash
bash scripts/pre-migration-check.sh
bash scripts/acceptance-test.sh --offline
bash scripts/backup.sh --apply
```

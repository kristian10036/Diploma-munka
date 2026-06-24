# A kiadott ZIP tartalma

Ez a csomag a teljes alkalmazás-forráskódot, konfigurációs mintákat,
adatbázis-migrációkat, teszteket, Docker Compose rétegeket, natív RF Agent
forrást, üzemeltetési scripteket és dokumentációt tartalmazza.

Szándékosan nincs benne:

- valódi `.env` fájl vagy jelszó;
- futásidejű PostgreSQL/Kismet backup;
- korábbi CMake build-könyvtár és bináris;
- Python cache és naplófájl.

Első indításkor:

```bash
cp .env.example .env
nano .env
```

A teljes indítási útmutató: `RUNNING.md`.

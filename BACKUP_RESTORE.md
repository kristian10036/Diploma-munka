# Backup és restore

## Backup

Alapból csak tervet ír ki:

```bash
bash scripts/backup.sh
```

Tényleges mentés:

```bash
bash scripts/backup.sh --apply
```

A mentés tartalma:

- PostgreSQL custom-format dump;
- Compose és migrációs fájlok;
- védett `.env`, ha létezik;
- recordings, uploads, Kismet-adatok;
- ML modellek és dataset metadata;
- projektadatok és exportok;
- manifest és SHA-256 lista.

A backup könyvtár alapértelmezetten `backups/runtime/TIMESTAMP`, felülírható a
`BACKUP_ROOT` változóval.

## Restore

Ellenőrzés és dry-run:

```bash
bash scripts/restore.sh /út/a/backuphoz
```

Tényleges restore üres célra:

```bash
bash scripts/restore.sh /út/a/backuphoz --apply
```

Meglévő adatok felülírása kizárólag explicit módon:

```bash
bash scripts/restore.sh /út/a/backuphoz --apply --force
```

A script először minden checksumot ellenőriz. Volume-ot nem töröl, és `--force`
nélkül nem ír felül nem üres adatbázist vagy célkönyvtárat.

## Visszaállítás utáni ellenőrzés

```bash
bash scripts/post-migration-check.sh
```

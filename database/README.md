# Database

The main database is PostgreSQL with TimescaleDB.

On first container startup, Docker runs `database/init/001_apply_migrations.sql`,
which applies every numbered migration in order.

For later schema changes, add an idempotent numbered SQL file under
`database/migrations/` and wire it from `database/init/` for fresh installs.
The Compose `migrate` service reapplies the idempotent migration set on startup,
so existing named database volumes also receive forward-only schema changes
before the backend starts.

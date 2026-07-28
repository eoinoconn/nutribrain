# NutriBrain

A personal meal, macro, and calorie tracking app combining an MCP server (for natural-language meal logging via Claude) with a React web dashboard (for visualization and structured editing).

- **Backend:** FastAPI + FastMCP server in Python, with Postgres database
- **Frontend:** React + TypeScript dashboard
- **Hosting:** Render (API + static site) + Neon (database) + intervals.icu (energy expenditure)
- **Integrations:** MCP tools for Claude, standard HTTP API for the dashboard

See [docs/spec.md](docs/spec.md) for the full technical specification.

---

## Make targets

A root `Makefile` wraps the common tasks and mirrors the CI pipeline. Run `make`
(or `make help`) to list every target. The most useful ones:

```bash
make install        # Install api/ and web/ dependencies
make check          # Run the full CI gate locally (lint, typecheck, migrations, tests, build)
make lint           # Ruff check + format-check (api) and ESLint (web)
make typecheck      # mypy (api) and tsc (web)
make test           # pytest (api) and vitest (web)
make migrate        # Apply Alembic migrations to head
make migrate-check  # Apply migrations and assert models match (no drift)
```

`make check`, `make migrate`, and `make migrate-check` need a reachable Postgres
(`DATABASE_URL` in `api/.env` or the environment); all other targets run without
a database. The individual commands each target wraps are documented in the
sections below.

---

## Quick start

### Prerequisites

- Python 3.12+ (managed with `uv`)
- Node.js 18+ (with `npm`)
- A Postgres database — a Neon branch (see below) or a local Docker container
- Neon account (free tier) and one `DATABASE_URL` connection string
- Docker (optional, for a local Postgres — matches the CI image)
- intervals.icu credentials (optional for cron)

### Local development

#### API server

```bash
cd api
uv sync --all-groups
cp .env.example .env  # Edit with your DATABASE_URL and APP_TOKEN
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Runs on http://localhost:8000
- `/health` endpoint available without auth
- `/api/*` and `/mcp` require `Authorization: Bearer <APP_TOKEN>` header

#### Web dashboard

```bash
cd web
cp .env.example .env   # set VITE_API_BASE to the running API's origin
npm ci
npm run dev -- --host --port 5173
```

- Runs on http://localhost:5173
- Requires a valid `APP_TOKEN` pasted on first visit
- `VITE_API_BASE` must point at the API's origin (`http://localhost:8000` for
  local dev) — the dashboard and API are served from different origins even
  in development, so requests are never same-origin by default

#### Cron entrypoint (intervals sync)

```bash
cd api
uv sync --all-groups
cp .env.example .env  # Ensure DATABASE_URL, INTERVALS_API_KEY, INTERVALS_ATHLETE_ID
uv run python -m app.intervals.sync
```

Fetches calories-out from intervals.icu for the last N days (default 3). Run this periodically via cron, GitHub Actions, or Render Cron Job.

---

## Token generation

To generate a secure token for `APP_TOKEN`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

~256 bits of entropy. Store in `.env` locally and in Render's environment variables on deployment.

**MCP client setup:** See [docs/mcp-client-setup.md](docs/mcp-client-setup.md)
for full configuration instructions covering Claude Desktop (`mcp-remote`),
Claude web/mobile (custom connector), and token rotation.

**Claude Desktop quick config** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "nutrition": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://nutrition-api.onrender.com/mcp",
        "--header",
        "Authorization: Bearer <token>"
      ]
    }
  }
}
```

---

## Testing

### API

```bash
cd api
uv run pytest                      # All tests
uv run pytest -v                   # Verbose
uv run pytest --cov=app          # Coverage report
```

### Web

```bash
cd web
npm run test                       # Watch mode
npm run test -- --run            # Single run
npm run test -- --coverage       # Coverage report
```

---

## Linting and type-checking

### API

```bash
cd api
uv run ruff check .               # Lint
uv run ruff format .              # Format
uv run mypy app                   # Type-check
```

### Web

```bash
cd web
npx tsc -b                        # Type-check
npm run lint                      # ESLint + Prettier
```

---

## Database

### Neon branch workflow

The shared database lives on Neon (free tier). Rather than run a local Postgres,
give each developer and each environment its own **branch** — they are free,
instant, and copy-on-write from the parent, so every branch starts with the
current schema and data.

1. **Provision once.** Create the Neon project (`nutribrain`) and pin compute to
   **0.25 CU** in the console to keep scale-to-zero cheap. Record two connection
   strings from the dashboard:
   - the **pooled** string (host contains `-pooler`) — use this for the app and
     `DATABASE_URL`; PgBouncer absorbs the connection churn from scale-to-zero;
   - the **direct** string — only for tools that need a non-pooled session.
2. **Branch per environment.** In the Neon console (or `neonctl branches create`),
   create a branch off `main` for each dev/preview environment, e.g.
   `dev-<name>`. Copy that branch's pooled connection string.
3. **Point the app at your branch.** Put the pooled string in `api/.env`:

   ```bash
   DATABASE_URL=postgresql+psycopg://<user>:<pass>@ep-...-pooler.<region>.aws.neon.tech/nutribrain?sslmode=require
   ```

4. **Migrate and verify.** From `api/`, run `uv run alembic upgrade head`, start
   the server, and hit `/health` — it returns `{"status": "ok"}` without touching
   the database, so uptime checks never hold the endpoint awake.
5. **Reset cheaply.** Delete and recreate a branch to get a clean schema; the
   parent is untouched.

**Connection pooling.** The engine ([api/app/db/engine.py](api/app/db/engine.py))
applies the G6 settings from [docs/decisions.md](docs/decisions.md): `pool_pre_ping`
(reconnect transparently after Neon suspends the endpoint), `pool_recycle=300`
(retire connections before Neon does), and `pool_size=2` (single user). There is
no keep-alive ping — cold starts of a few hundred milliseconds are accepted.

### Local Postgres (Docker)

For running tests and migrations locally without a Neon branch, start a throwaway
Postgres matching the CI image:

```bash
docker run -d --name nutribrain-pg \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=nutribrain \
  -p 5432:5432 postgres:16
```

Then point the API at it (in `api/.env` or the shell):

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/nutribrain
```

The pure `psycopg` build needs the system `libpq` library present (see
[docs/decisions.md](docs/decisions.md) — D-001); on Debian/Ubuntu:
`sudo apt install libpq5`. Remove the container with
`docker rm -f nutribrain-pg` when done.

### Migrations

```bash
cd api
uv run alembic upgrade head       # Apply all
uv run alembic downgrade base     # Rollback all
```

### Schema

See [docs/spec.md § 3](docs/spec.md#3-data-model) for the full schema. Tables: `foods`, `meals`, `meal_items`, `templates`, `template_items`, `targets`, `intervals_calories_out`.

---

## Architecture

- **Domain layer** (`app/domain/`): All business logic — mutations, validations, and read-time calculations
- **FastAPI routes** (`app/api/`): HTTP adapters, thin wrappers over domain functions
- **MCP tools** (`app/mcp/`): Adapter for Claude integration, same domain functions
- **Database** (`app/db/`): SQLAlchemy models and session management
- **Cron** (`app/intervals/`): Scheduled sync worker for intervals.icu data

One Postgres database, one source of truth. Both API and MCP entry points call the same domain functions.

See [CLAUDE.md](CLAUDE.md) for agent-specific guidance, [docs/style.md](docs/style.md) for code conventions, and [docs/decisions.md](docs/decisions.md) for specification amendments.

---

## Documentation

- [CLAUDE.md](CLAUDE.md) — Agent guide
- [docs/spec.md](docs/spec.md) — Technical specification
- [docs/backlog.md](docs/backlog.md) — Build backlog with task descriptions
- [docs/style.md](docs/style.md) — Code style guide
- [docs/decisions.md](docs/decisions.md) — Specification amendments and resolutions
- [docs/mcp-client-setup.md](docs/mcp-client-setup.md) — MCP client configuration guide
- [api/CLAUDE.md](api/CLAUDE.md) — API module guide
- [web/CLAUDE.md](web/CLAUDE.md) — Web module guide

---

## License

MIT


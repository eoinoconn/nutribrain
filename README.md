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
- Neon account (free tier) and one `DATABASE_URL` connection string
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
npm ci
npm run dev -- --host --port 5173
```

- Runs on http://localhost:5173
- Requires a valid `APP_TOKEN` pasted on first visit

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

**MCP client setup (Claude Desktop):**

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
- [api/CLAUDE.md](api/CLAUDE.md) — API module guide
- [web/CLAUDE.md](web/CLAUDE.md) — Web module guide

---

## License

MIT


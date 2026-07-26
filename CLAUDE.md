# NutriBrain Agent Guide

## What this is
NutriBrain is a single-user nutrition tracker. One Python service hosts both a FastAPI app and a FastMCP server over a shared domain layer and one Postgres database, while a React dashboard consumes the HTTP API for structured views and edits.

## Quick Commands

### API (`api/`)
- Install deps: `uv sync --all-groups`
- Dev server: `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- Tests: `uv run pytest`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Typecheck: `uv run mypy app`
- Migrate: `uv run alembic upgrade head`
- Cron entrypoint: `uv run python -m app.intervals.sync` (planned entrypoint; module may not exist until intervals sync implementation lands)

### Web (`web/`)
- Install deps: `npm ci`
- Dev server: `npm run dev -- --host --port 5173`
- Tests: `npm run test`
- Lint: `npm run lint`
- Typecheck: `npx tsc -b`
- Build: `npm run build`
- Migrate: not applicable
- Cron entrypoint: not applicable

## Architecture in 5 lines
1. There are two entry points: `/api` and `/mcp`.
2. Both entry points call the same domain functions in `api/app/domain/`.
3. Business rules live only in the domain layer.
4. FastAPI routes and MCP tools are adapters only.
5. One Postgres database is the source of truth.

## Mutation Rules (Do Not Deviate)
These are product rules and must be preserved exactly.

Food edits propagate to past meals.
- Editing `food.calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sat_fat_g`, `sodium_mg` recomputes every past meal_item referencing that food (read-time calculation, no writes needed)
- Editing `food.serving_size` propagates (it's a rate change — `cal/g = calories ÷ serving_size`)
- Editing `food.name` is cosmetic — propagates freely
- Editing `food.serving_unit` is forbidden. The API must reject this; the correct action is to create a new food.

Meal_item edits stay local.
- `meal_item.quantity` — you ate what you ate that day
- `meal_item.food_id` — swap the food, only affects that meal
- For ad-hoc items (`food_id NULL`), editing the stored macros only affects that meal_item

Template edits don't touch past meals.
- Editing a `template_item` affects future applications only
- Past meals logged from a template are already materialized as meal_items; they don't recompute
- Deleting a template is soft; past meal_items are unaffected

## Read-Time Computation Rule
For `meal_items` with `food_id` present, macros are never snapshotted onto the meal item row. They are always computed on read from the current food nutrition values and unit-normalization logic. Do not add write-time snapshots for these rows.

## Deletion Semantics
- Soft delete: `foods`, `templates` (`deleted_at`)
- Hard delete: `meals`, `meal_items`

## What Not To Do
- Do not add new dependencies without PR justification.
- Do not put business logic in FastAPI routes or MCP tools.
- Do not edit merged Alembic migrations.
- Do not log `Authorization` headers or full request bodies.
- Do not introduce multi-user assumptions; there is exactly one user and no `user_id`.

## Canonical References
- Style guide: `docs/style.md`
- Spec: `docs/spec.md`
- Build backlog: `docs/backlog.md`
- Decisions: `docs/decisions.md`

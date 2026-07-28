# NutriBrain — Agent Build Backlog

Derived from `nutrition-tracker-spec.md`. Tasks are dependency-ordered and sized for a single agent to complete in one focused session with a reviewable diff at the end.

**Section references (`§`) point back at the spec, which is canonical.** The seven amendments below were folded into spec v1.1; where this backlog and the spec disagree on anything else, the spec wins.

---

## How to work this backlog

**Working agreement for every task**

- One task = one branch (`t-042-templates-api`) = one PR. Don't bundle.
- Read the referenced spec sections in full before writing code. Don't infer the data model from adjacent tasks.
- Tests ship in the same PR as the code. A task with no test story is not done.
- If the spec is ambiguous, stop and record the question in `docs/decisions.md` with your proposed answer. Don't silently pick.
- Never edit a merged Alembic migration. Add a new one.
- Domain logic goes in `app/domain/`. Route handlers and MCP tools are thin adapters over it — no business rules in either.

**Definition of done (applies to all tasks)**

1. Lint, format, type-check, and tests pass locally and in CI.
2. Public functions have docstrings stating what propagates and what doesn't, where relevant.
3. New env vars are added to `.env.example` and Appendix A of the spec.
4. The PR description lists which spec sections it implements.

---

## Amendments folded into spec v1.1

These were resolved before implementation and are now written into the spec itself,
with a changelog table at its foot. Listed here only so the task references to
`G1`-`G7` resolve.

| # | Change | Affects |
|---|---|---|
| G1 | `deleted_at` added to `foods` and `templates` | T-010, T-011 |
| G2 | Tool count corrected 15 -> 17 | T-051, T-052, T-053 |
| G3 | `last_logged_at` / `logged_count` computed in-query, not stored | T-040 |
| G4 | `quantity_unit` extended to twelve units; `foods.density_g_per_ml` added | T-010, T-020 |
| G5 | `intervals_calories_out.source` added | T-010, T-045, T-061 |
| G6 | Neon pool settings documented; no keep-alive ping | T-013 |
| G7 | FastMCP auth inheritance corrected — **must be verified, not assumed** | T-030 |

G7 is the one to read in full before starting Phase 3. If the assumption in the
original spec had gone unchecked, every MCP write tool would have been exposed
unauthenticated.

---

## Phase 0 — Repository, conventions, and agent instructions

### T-001 · Initialize the monorepo ✅
**Depends:** — **Spec:** §2

- `git init`, `main` as default branch, MIT or unlicensed as preferred.
- Create the directory skeleton exactly as §2 specifies: `api/app/{domain,api,mcp,intervals,db}`, `api/migrations`, `api/tests`, `web/src`, plus root `render.yaml` placeholder and `README.md`.
- `.gitignore` covering `.env`, `__pycache__`, `.venv`, `node_modules`, `dist`, `.ruff_cache`, `.pytest_cache`, `*.db`.
- `.editorconfig`: LF, UTF-8, final newline, 4-space Python / 2-space TS.

**Done when:** a fresh clone shows the full tree with `.gitkeep` placeholders and nothing ignored is tracked.

---

### T-002 · Python toolchain and API scaffold ✅
**Depends:** T-001 **Parallel with:** T-003 **Spec:** §2, stack table

- `api/pyproject.toml` managed by `uv`, Python 3.12+, with runtime deps (fastapi, fastmcp, uvicorn, sqlalchemy, alembic, psycopg, httpx, structlog, pydantic-settings) and dev deps (pytest, pytest-asyncio, ruff, mypy, coverage).
- Ruff configured as both linter and formatter — line length 100, target py312, rule set including `E,F,I,N,UP,B,SIM,RUF`.
- Mypy in strict mode for `app/domain/**`, standard elsewhere. Domain code is the part worth the strictness.
- `app/settings.py` using pydantic-settings to read every var in Appendix A, failing loudly at import on missing required ones.
- A trivial `/health` returning `{"status": "ok"}` so the scaffold is provably runnable.

**Done when:** `uv run uvicorn app.main:app` serves `/health` and `uv run ruff check . && uv run mypy app && uv run pytest` all pass on an empty test suite.

---

### T-003 · Frontend toolchain and web scaffold ✅
**Depends:** T-001 **Parallel with:** T-002 **Spec:** §7

- Vite + React + TypeScript in `web/`, strict `tsconfig` (`strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`).
- Tailwind configured with dark mode via `media` (§7 — system preference, no toggle).
- Deps installed: `@tanstack/react-query`, `react-router-dom`, `recharts`, `react-calendar-heatmap`, `react-day-picker`.
- ESLint (flat config) + Prettier, with `eslint-plugin-jsx-a11y` enabled — §7 sets an accessibility floor, so the linter should enforce part of it.
- Vitest + React Testing Library wired up with one smoke test.

**Done when:** `npm run dev`, `npm run build`, `npm run lint`, and `npm run test` all succeed.

---

### T-004 · Coding style guide ✅
**Depends:** T-002, T-003 **Spec:** §2, §3, §11

Write `docs/style.md`. This is the document agents are pointed at, so it must be prescriptive rather than aspirational.

Cover:

- **Layering.** Domain functions take primitives and typed DTOs, return DTOs, raise domain exceptions, and never import FastAPI, FastMCP, or SQLAlchemy session-management concerns beyond an injected session. Routes and tools translate only.
- **Naming.** `snake_case` Python, `camelCase` TS, `PascalCase` components, verb-first domain functions (`log_meal`, `resolve_food`, `compute_effective_target`).
- **Errors.** One exception hierarchy rooted at `DomainError`, each carrying the Appendix C `error` code. No bare `raise HTTPException` outside the error-handler module.
- **Money-shaped numbers.** All macros are `Decimal` in Python and `number` in TS; never float in domain math, never round before the final serialization step. State the rounding rule once: round for display only, at one decimal for grams and whole numbers for calories.
- **Dates and timezones.** UTC in the DB, IANA name alongside, `local_date` computed at write time. Never `datetime.now()` without a tz. Never derive a local date in the frontend from a UTC timestamp — read `local_date` from the API.
- **Nullability.** `food_id NULL` means ad-hoc; macros on a `meal_item` are populated *if and only if* `food_id IS NULL`. Both the DB constraint and the domain layer enforce this.
- **Tests.** Domain gets unit tests with no DB where possible and a transactional DB fixture where not. Routes get one happy path and one error path each. Frontend gets tests for state logic, not for chart rendering.
- **Commits.** Conventional Commits, imperative mood, one logical change.
- **Comments.** Explain propagation rules and non-obvious business decisions. Don't narrate the code.

**Done when:** `docs/style.md` exists and T-002/T-003 tool configs actually enforce everything mechanically enforceable in it.

---

### T-005 · Author CLAUDE.md ✅
**Depends:** T-004 **Spec:** all

Write a root `CLAUDE.md`, plus focused `api/CLAUDE.md` and `web/CLAUDE.md`. Root file stays under ~200 lines; if it grows past that, push detail into `docs/` and link.

Root `CLAUDE.md` must contain:

- **What this is.** Single-user nutrition tracker; MCP server plus React dashboard over one Python service. One paragraph.
- **Commands.** Exact invocations for install, dev server, test, lint, typecheck, migrate, and the cron entrypoint, for both `api/` and `web/`. Agents should never have to guess a command.
- **Architecture in five lines.** Two entry points (`/api`, `/mcp`), one domain layer, one DB. The rule that both entry points call the same domain functions, stated as a rule.
- **The mutation rules from §3, verbatim and prominent.** Food edits propagate to history. Meal_item edits stay local. Template edits affect future applications only. `serving_unit` is immutable. This is the single most likely thing for an agent to get wrong, so it goes near the top.
- **Read-time computation.** Macros for `food_id`-bearing items are never stored; they're computed on read. An agent that "optimizes" by snapshotting them has broken the product.
- **Deletion semantics.** Soft for foods and templates, hard for meals and meal_items.
- **What not to do.** No new dependencies without justification in the PR. No business logic in routes or MCP tools. No editing merged migrations. No logging the `Authorization` header or full request bodies. No multi-user assumptions — there is exactly one user and no `user_id` anywhere.
- **Pointers.** Links to `docs/style.md`, the spec, and `docs/decisions.md`.

`api/CLAUDE.md`: domain-layer contract, exception hierarchy, session/transaction boundaries, how to add an Alembic migration, how MCP tools are registered.

`web/CLAUDE.md`: TanStack Query key conventions, the optimistic-update-with-rollback pattern, where the token lives and how the fetch interceptor uses it, the accessibility floor from §7.

**Done when:** an agent handed only `CLAUDE.md` can run the test suite, find the mutation rules, and correctly say where a new business rule belongs.

---

### T-006 · CI pipeline ✅
**Depends:** T-002, T-003 **Spec:** §10

- GitHub Actions with two jobs, path-filtered so `web/` changes don't run Python.
- API job: `uv sync`, ruff, mypy, pytest against a Postgres service container.
- Web job: `npm ci`, lint, typecheck, test, build.
- Both required to pass before merge.

**Done when:** a deliberately broken PR fails CI for the expected reason and a clean one goes green.

---

### T-007 · Environment, secrets, and README ✅
**Depends:** T-002, T-003 **Spec:** §10, Appendix A

- `.env.example` with every Appendix A variable, placeholder values, and a one-line comment each.
- Token generation snippet from §9 documented in the README.
- README: what this is, local dev for api/web/cron, links to `CLAUDE.md` and `docs/style.md`.
- `docs/decisions.md` seeded with the G1–G7 resolutions from this backlog.

**Done when:** a new machine can go from clone to running dev servers using only the README.

---

## Phase 1 — Data layer

### T-010 · SQLAlchemy models and enums ✅
**Depends:** T-002 **Spec:** §3, Appendix B

- All seven tables from §3 with exact column names, types, and nullability.
- Native Postgres enums for all five enum columns in Appendix B, with `quantity_unit` widened per G4 to `g, kg, oz, lb, ml, l, fl_oz, tsp, tbsp, cup, piece, serving`. `serving_unit` stays `g, ml, piece`.
- `deleted_at` on `foods` and `templates` per G1; `source` on `intervals_calories_out` per G5; `density_g_per_ml numeric nullable` on `foods` per G4.
- Numeric columns as `Numeric` with explicit precision/scale, mapped to `Decimal`.
- A `CHECK` constraint on `meal_items` and `template_items` enforcing that macro columns are non-null when `food_id IS NULL` and null when it is set. The invariant belongs in the database, not only in the domain layer.
- Relationships with `passive_deletes` set so meal → meal_items cascades hard-delete correctly.

**Done when:** models import cleanly, mypy passes, and the CHECK constraint rejects a mixed-mode row in a test.

---

### T-011 · Alembic setup and initial migration ✅
**Depends:** T-010 **Spec:** §3, §10

- Alembic configured to read `DATABASE_URL` from settings, with `compare_type` and `compare_server_default` on.
- Initial migration creating all tables, enums, and every index from §3: `meals(local_date)`, `meal_items(meal_id)`, `foods(lower(name))`, partial index on `foods(is_favorite) WHERE is_favorite`, `targets(effective_from DESC)`.
- Downgrade path implemented, not stubbed.

**Done when:** `alembic upgrade head` then `downgrade base` runs clean on an empty database, and autogenerate against head produces an empty diff.

---

### T-012 · Test database harness ✅
**Depends:** T-011 **Spec:** §2

- Pytest fixtures: session-scoped migrated database, function-scoped transaction rolled back after each test.
- Factory helpers for foods, meals, meal_items, templates, and targets so test setup stays one line.
- A frozen-clock fixture — timezone and `local_date` logic is heavily time-dependent and must be tested deterministically.

**Done when:** two tests writing conflicting data both pass in any order.

---

### T-013 · Neon provisioning and branch workflow ✅
**Depends:** T-011 **Spec:** §10

- Create the Neon project and record the pooled and direct connection strings.
- Document the per-developer branch workflow from §10 in the README.
- Apply the G6 pooling settings to the engine configuration.

**Done when:** migrations run against a Neon branch and the API serves `/health` pointed at it.

---

## Phase 2 — Domain layer

This phase is the product. Everything after it is adapters.

### T-020 · Unit normalization and read-time macro calculation ✅
**Depends:** T-012 **Spec:** §3 (read-time macro calculation)

- `normalize_to_grams(quantity, unit, food)` handling the full G4 unit set. Mass units use fixed factors; volume units convert to ml, then to grams via `food.density_g_per_ml` (null → 1.0).
- Conversion factors as one frozen domain constant. No magic numbers scattered through call sites.
- `compute_item_macros(meal_item, food)` implementing the factor calculation exactly as §3 specifies.
- Ad-hoc path: read stored values straight off the row.
- `piece` and `serving` are per-food and cannot be converted to or from mass/volume units — attempting it raises rather than guessing.

**Done when:** a table-driven test covers every unit × food-unit combination including the invalid ones, plus a density case asserting that one cup of a food with `density_g_per_ml = 0.78` normalises to ~185 g and the same food with density null normalises to ~237 g.

---

### T-021 · Food resolution rules ✅
**Depends:** T-020 **Spec:** §4 (`log_meal` resolution), §6

Implement the resolution ladder precisely and in order:

1. explicit `food_id` wins;
2. single fuzzy name match wins;
3. multiple matches with exactly one favorite → the favorite;
4. multiple matches, no favorite, exactly one logged in the last 30 days → most recent;
5. otherwise raise `food_ambiguous` with the candidate list from Appendix C;
6. no match and no supplied macros → `food_not_found`.

- Fuzzy matching uses the `lower(name)` index plus trigram similarity; pick a threshold, document it in `docs/decisions.md`, and make it a constant.
- Soft-deleted foods are never candidates.

**Done when:** each rung of the ladder has a dedicated test, including one asserting that two favorites is ambiguous rather than arbitrary.

---

### T-022 · Meal-type inference and date parsing ✅
**Depends:** T-012 **Spec:** §4

- Time-window inference: breakfast 04:00–10:59, lunch 11:00–15:59, dinner 16:00–21:59, snack 22:00–03:59, computed in the meal's local timezone.
- Shared parser for `today` / `yesterday` / ISO dates, resolved against the caller's local timezone.
- Explicit caller values always override inference.

**Done when:** boundary tests at every window edge pass, including a 00:30 snack landing on the correct local date.

---

### T-023 · `log_meal` domain function ✅
**Depends:** T-021, T-022 **Spec:** §4, §5

- Resolves each item, derives `local_date` from `logged_at` + `local_tz`, writes meal and items in one transaction, sets `source` correctly per item.
- Returns the created meal with resolved items, computed totals, and delta versus the effective target.
- Ad-hoc items store macros; food-backed items store none.

**Done when:** a mixed meal (one food-backed, one ad-hoc, one favorite-resolved) round-trips with correct totals.

---

### T-024 · Foods domain operations ✅
**Depends:** T-021 **Spec:** §3 (mutation rules), §4

- `add_food` with fuzzy-duplicate detection raising `food_duplicate` unless `force`.
- `update_food` partial update, rejecting any `serving_unit` change with `serving_unit_immutable`.
- `update_food` returns the count of past meals that will recompute — a query over `meal_items`, not a stored counter.
- `set_favorite_food`, and soft delete.

**Done when:** a test asserts that changing `calories` on a food changes the totals of an already-logged historical meal, and that changing `serving_unit` is rejected.

---

### T-025 · Targets domain ✅
**Depends:** T-012 **Spec:** §3, §4

- `set_target` always inserts a new versioned row, never mutates.
- `get_effective_target(date)` = latest target where `effective_from <= date`, plus `calories_out` for that date when a cache row exists.
- Returns the base and activity components separately so the UI can show the breakdown from §8.
- No cache row falls back to base alone — distinct from a cached zero, which is a real rest day.

**Done when:** tests cover no-target, multiple-targets-same-day, missing cache row, and cached-zero cases.

---

### T-026 · Templates domain ✅
**Depends:** T-023 **Spec:** §6

- `create_template`, `update_template`, soft `delete_template`, `list_templates` returning items in full.
- `log_template` materializes items into meal_items: `food_id` carried through when set, estimate copied when null, `quantity_scale` applied uniformly, `source: template` on every resulting item.
- Editing a template must not touch already-logged meals.

**Done when:** a test logs a template, edits the template, and asserts the historical meal is byte-for-byte unchanged.

---

### T-027 · Day and range aggregation ✅
**Depends:** T-023, T-025 **Spec:** §4

- `get_day(date)`: meals grouped by meal_type, per-meal and day totals, effective target with breakdown, delta.
- `get_range(from, to, granularity)`: per-period totals, effective targets, adherence flags, `day` or `week`.
- Macro computation happens at read time throughout — no snapshotting anywhere.
- Watch the N+1: load meals, items, and referenced foods in bounded queries.

**Done when:** a 90-day range over seeded data returns correct totals in a bounded number of queries, asserted in a test.

---

### T-028 · Deletion and error taxonomy ✅
**Depends:** T-023 **Spec:** §3, Appendix C

- `delete_meal` and `delete_meal_item` as hard deletes returning `{deleted: true}`.
- `DomainError` hierarchy covering every Appendix C code, each carrying `error`, `message`, and optional `candidates`.
- Soft-delete filtering applied consistently in every read path.

**Done when:** every code in Appendix C maps to exactly one exception class, asserted by a test that walks the hierarchy.

---

## Phase 3 — Service composition

### T-030 · Auth, health, and CORS ✅
**Depends:** T-002 **Spec:** §9

- `require_auth` exactly as §9 specifies, using `hmac.compare_digest`.
- `/health` unauthenticated, returning only `{"status": "ok"}` — no DB check by design.
- CORS allowlist driven by an env var holding the static site origin. No wildcards.
- **Resolve G7 here:** verify empirically whether the mounted FastMCP app enforces the FastAPI dependency. If it doesn't, implement auth as ASGI middleware covering both mounts and record the change in `docs/decisions.md`.

**Done when:** a test proves `/api/*` and `/mcp` both reject a missing token, a wrong token, and a malformed header, and that `/health` needs none.

---

### T-031 · Application composition ✅
**Depends:** T-030 **Spec:** §2, §9

- `app/main.py` composing FastAPI and FastMCP in one process with a shared database session lifecycle.
- Startup validates required settings and fails fast.
- Exception handler mapping `DomainError` to the Appendix C envelope with correct status codes.

**Done when:** both mounts serve from one uvicorn process and a domain exception surfaces as the standard JSON error shape.

---

### T-032 · Structured logging ✅
**Depends:** T-031 **Spec:** §11

- structlog: JSON in production, pretty console in dev, level from `LOG_LEVEL`.
- Middleware binding `request_id` to every request; MCP tool calls bind `tool_name`.
- A processor that redacts `Authorization` unconditionally — implement it as a processor, not a convention, so it can't be forgotten.
- Log every mutation with entity id, every sync with days affected and duration, auth failures as counts, any request over 500ms. Don't log successful reads or full bodies.

**Done when:** a test asserts the redaction processor strips a token from a log event containing one.

---

### T-033 · Sentry (optional) ✅
**Depends:** T-031 **Spec:** §11

- Python SDK behind `SENTRY_DSN`, no-op when unset.
- Scrubbing configured so request bodies and auth headers never leave the process.

**Done when:** the app runs identically with the DSN absent.

---

## Phase 4 — HTTP API

Each task: routes, Pydantic request/response schemas, one happy-path and one error-path test. No business logic — call the domain layer.

### T-040 · Foods routes ✅
**Depends:** T-024, T-031 **Spec:** §4, §7
`GET /api/foods?q=` (fuzzy search, returns favorites marker, `last_logged_at`, `logged_count` per G3), `POST /api/foods`, `PATCH /api/foods/{id}` (returns recompute count), `POST /api/foods/{id}/favorite`, `DELETE /api/foods/{id}` (soft).

### T-041 · Meals routes ✅
**Depends:** T-023, T-028 **Spec:** §4, §7
`POST /api/meals`, `DELETE /api/meals/{id}`, `DELETE /api/meal-items/{id}`. Day detail is the primary correction surface, so error messages here are user-facing — make them readable.

### T-042 · Templates routes ✅
**Depends:** T-026 **Spec:** §6, §7
Full CRUD plus `POST /api/templates/{id}/log` accepting `quantity_scale`.

### T-043 · Targets routes ✅
**Depends:** T-025 **Spec:** §4, §7
`GET /api/targets` (versioned history, `effective_from` desc), `POST /api/targets`, `GET /api/targets/effective?date=`.

### T-044 · Day and range read routes ✅
**Depends:** T-027 **Spec:** §4, §7
`GET /api/day/{date}`, `GET /api/range?from=&to=&granularity=`. These back the Today, Day detail, Trends, and Calendar views — shape the payloads so the calendar heatmap needs exactly one call for twelve months.

### T-045 · Sync routes ✅
**Depends:** T-061 **Spec:** §8
`POST /api/sync/intervals`, `GET /api/sync/status` (last sync timestamp, last error), and the manual calories-out override writing `source: manual` per G5.

---

## Phase 5 — MCP surface

### T-050 · FastMCP scaffolding and serializers ✅
**Depends:** T-031 **Spec:** §4

- Tool registration structure under `app/mcp/`, one module per tool group.
- Shared serializers producing the same DTO shapes the HTTP API returns — Claude and the dashboard should never see two versions of "a meal".
- Every tool returns structured, quotable data; errors follow Appendix C.
- All date arguments accept `today` / `yesterday` / ISO via the T-022 parser.

**Done when:** an MCP client lists the full tool surface with usable descriptions and schemas.

---

### T-051 · Write tools ✅
**Depends:** T-050, T-023, T-024, T-026 **Spec:** §4, §5
`log_meal`, `log_template`, `add_food`, `update_food`, `create_template`, `update_template`, `delete_template`, `set_target`, `set_favorite_food`, `delete_meal`, `delete_meal_item`.

`add_food` must encode the `serving_unit` convention from §3 in its description: prefer mass with `serving_size` = the weight of one natural unit, reserve `piece` for foods with no useful weight. Claude creates most foods during label scans, and a `piece`-defined food is a one-way door — the description is the only thing standing between a label reading "12 squares per bar" and an unweighable food.

Tool descriptions must likewise encode the §5 "what Claude should not do" rules — that `update_food` rewrites history and is never the fix for one meal, that templates are user-initiated only, that ambiguity gets escalated rather than guessed. The description is the enforcement mechanism for a model-facing API.

### T-052 · Read tools ✅
**Depends:** T-050, T-027 **Spec:** §4
`get_day`, `get_range`, `find_food`, `list_templates`, `get_target`. `find_food` returns everything the resolution rules in §5 need so Claude can decide without a second round trip.

### T-053 · Sync tool ✅
**Depends:** T-050, T-061 **Spec:** §4, §8
`sync_intervals(from?, to?)`, defaulting to the last 7 days, returning days synced and a failure list.

### T-054 · MCP client configuration docs ✅
**Depends:** T-051, T-052, T-053 **Spec:** §9
Document the `mcp-remote` config from §9 and the Claude web/mobile custom connector setup, including token rotation steps.

---

## Phase 6 — intervals.icu integration

### T-060 · intervals API client ✅
**Depends:** T-002 **Spec:** §8

- httpx client hitting the wellness endpoint with HTTP Basic (`API_KEY` as username).
- Extracts `sportInfo.Calories` per day.
- Timeouts and bounded retries; raises `intervals_unavailable` on failure.
- Tests use recorded fixtures, never the live API.

### T-061 · Sync worker ✅
**Depends:** T-060, T-012 **Spec:** §8

- One shared sync function behind all three triggers.
- Missing-data rules exactly as §8 states: `null` writes no row; `0` writes a genuine zero. Getting this backwards silently corrupts every target.
- Partial failures write per day and log the rest without aborting.
- Writes `source: sync`, overwriting manual overrides by design.

**Done when:** tests cover null, zero, partial failure, and a manual override being replaced by a later sync.

### T-062 · Cron entrypoint ✅
**Depends:** T-061 **Spec:** §8, §10
`python -m app.intervals.sync_recent` reading `INTERVALS_SYNC_DAYS` (default 3), logging days affected and duration, exiting non-zero on total failure so Render surfaces it.

---

## Phase 7 — Web dashboard

### T-070 · App shell, routing, and token gate
**Depends:** T-003, T-040 **Spec:** §7, §9

- Router covering all eight routes from §7.
- Token paste landing screen; `localStorage` under `nutrition:token`; fetch interceptor attaching the bearer header.
- 401 clears the token and returns to the paste screen with an invalid-token message.
- TanStack Query provider with sensible defaults and a documented query-key convention.

### T-071 · Typed API client
**Depends:** T-070 **Spec:** §7
One module wrapping every endpoint with shared types. Consider generating types from the OpenAPI schema — if generated, wire it into CI so drift fails the build.

### T-072 · Design foundations
**Depends:** T-003 **Spec:** §7
Tailwind tokens, the adherence colour scale (green in target, yellow near, red outside, grey no log) checked for contrast, focus-ring styles, toast and skeleton primitives, empty-state component.

### T-073 · Meal editor component
**Depends:** T-071 **Spec:** §7
Item repeater with food search (★ favorites), quantity and unit, ad-hoc toggle exposing macro fields, meal-type dropdown defaulting by time window, time picker defaulting to now. Reused by Today, Day detail, and Templates — build it standalone with its own tests before wiring it in.

### T-074 · Today view
**Depends:** T-073, T-044 **Spec:** §7
Header with the target breakdown, calorie ring, three prominent macro bars, muted micro row, meals grouped by type and expandable, log button, sync button.

### T-075 · Day detail
**Depends:** T-074 **Spec:** §7, §8
Same layout for any date, fully editable, plus the manual calories-out override input.

### T-076 · Trends
**Depends:** T-071, T-044 **Spec:** §7
7/30/90 selector, calorie line chart with target `ReferenceLine`, stacked macro bars, stat tiles for average adherence, longest streak, worst miss. Text summary beneath each chart per the accessibility floor.

### T-077 · Calendar heatmap
**Depends:** T-071, T-044 **Spec:** §7
Twelve-month heatmap, hover tooltip with totals, click through to `/day/:date`.

### T-078 · Foods manager
**Depends:** T-071, T-040 **Spec:** §7
Searchable sortable table, favorite star toggle, edit modal showing "this will recompute N past meals" before commit, add form, serving-unit field disabled after creation.

### T-079 · Templates manager
**Depends:** T-073, T-042 **Spec:** §6, §7
List with item counts, edit form with item repeater, ad-hoc items with inline macros, "log now" button.

### T-080 · Targets and settings
**Depends:** T-071, T-043, T-045 **Spec:** §7, §9
Targets: versioned list descending, create form, past targets read-only. Settings: masked token with test-connection, timezone override defaulting to browser, sync status with manual trigger, diagnostic panel.

### T-081 · Cross-cutting behaviour
**Depends:** T-074…T-080 **Spec:** §7
Optimistic mutations with rollback on every write, success and failure toasts, first-paint skeletons, empty states, error boundary, and a keyboard-navigation pass over every form.

---

## Phase 8 — Deploy and operations

### T-090 · render.yaml
**Depends:** T-031, T-003 **Spec:** §10
All three services as specified, migrations in the API build command, health check path, cron at 03:00 UTC, env var wiring including `fromService` references for the cron.

### T-091 · First deploy
**Depends:** T-090, T-013 **Spec:** §10
Deploy all three services, set every env var in Render's UI, generate `APP_TOKEN`, confirm the static site reaches the API and CORS is correct with a real origin.

### T-092 · Weekly backup job
**Depends:** T-091 **Spec:** §11
Second cron: `pg_dump | gzip` to Cloudflare R2, retaining the last 8 dumps and pruning older. Failures must log loudly — a silent backup job is worse than none.

### T-093 · Restore drill
**Depends:** T-092 **Spec:** §11
Run the four-step drill from §11 — pull the latest dump, restore into a Neon branch, verify reads, delete the branch — and write up the result in `docs/runbook.md`. Do this in the first week, not later.

### T-094 · Uptime monitoring (optional)
**Depends:** T-091 **Spec:** §11
UptimeRobot or Better Stack hitting `/health` every five minutes.

---

## Phase 9 — Verification

### T-100 · Mutation-rule regression suite
**Depends:** Phase 2–4 **Spec:** §3
A dedicated test module that exists solely to defend the propagation rules. Food edit changes history; meal_item edit doesn't; template edit doesn't; serving_unit change is rejected; soft-deleted foods stay resolvable from historical meals but unfindable in search. This suite is the guardrail against a future agent "optimizing" read-time computation into snapshots.

### T-101 · End-to-end acceptance
**Depends:** Phase 5, Phase 7 **Spec:** Appendix D, §5
Walk the Appendix D sequence against a deployed environment via MCP: label scan → `find_food` miss → `add_food` → `log_meal` → confirmation with correct day totals. Then the §5 flows: typical meal log, template resolution, backfill of yesterday's lunch, and a correction via `update_food` reporting the propagation count.

### T-102 · Seed data script
**Depends:** T-012 **Spec:** —
A script generating ~90 days of plausible meals, foods, templates, targets, and calories-out rows. Needed to develop Trends and Calendar against anything meaningful, and to make the T-027 query-count assertion honest.

---

## Known issues

Bugs found in already-merged tasks, discovered incidentally while working on
later tasks. Not blocking the tasks above; fix opportunistically or pick up
as a dedicated task.

### KI-001 — `POST /api/meals` 500s on a naive `logged_at` instead of a 4xx

**Found:** manually exercising the Today view (T-074) against a live API
during phase-7, 2026-07-27.

**Repro:** `POST /api/meals` with `logged_at` missing a UTC offset (e.g.
`"2026-07-27T08:30:00"` instead of `"2026-07-27T08:30:00+01:00"`) raises a
bare `ValueError("logged_at must be timezone-aware")` in
`api/app/domain/meal_logging.py:70`. It isn't a `DomainError` subclass, so
nothing maps it to an Appendix C error code — it surfaces as an unhandled
500 rather than a 4xx validation error.

**Where:** `api/app/api/meals.py` (`CreateMealRequest.logged_at: datetime` —
Pydantic doesn't enforce tz-awareness on plain `datetime` fields) and
`api/app/domain/meal_logging.py:70` (T-023, already merged before phase-7).

**Suggested fix:** either a Pydantic validator on `CreateMealRequest` that
rejects naive datetimes with a proper 422, or a `DomainError` subclass
(`invalid_timestamp` or similar) raised instead of the bare `ValueError`,
caught by the existing exception-handler mapping from T-031.

---

## Parallelization map

| Wave | Tasks | Notes |
|---|---|---|
| 1 | T-001 | Blocks everything |
| 2 | T-002, T-003 | Two agents |
| 3 | T-004 → T-005 → T-006, T-007 | Style guide before CLAUDE.md; both before CI is meaningful |
| 4 | T-010 → T-011 → T-012, T-013 | Sequential; schema is the shared contract |
| 5 | T-020 → T-021, T-022 | T-021 and T-022 parallel after T-020 |
| 6 | T-023 → T-024, T-025, T-026 | Three agents after `log_meal` lands |
| 7 | T-027, T-028, T-030, T-060 | Four agents |
| 8 | T-031 → T-032, T-033, T-061 → T-062 | |
| 9 | T-040…T-045, T-050 | Six API agents in parallel once T-031 is in |
| 10 | T-051, T-052, T-053, T-070, T-071, T-072 | MCP and frontend foundations in parallel |
| 11 | T-073 → T-074…T-080 | Meal editor first; then most views are independent |
| 12 | T-081, T-090…T-094, T-100…T-102 | |

The critical path runs T-001 → T-002 → T-010 → T-011 → T-012 → T-020 → T-023 → T-031 → T-044 → T-070 → T-073 → T-074. Everything else can be scheduled around it.
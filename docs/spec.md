# NutriBrain — Technical Specification

*v1.1 — incorporates amendments G1–G7. See the changelog at the foot of this document.*

**Purpose:** Personal meal, macro, and calorie tracking app powering fitness goals for a single user. Combines an MCP server (for natural-language meal logging via Claude) with a React web dashboard (for visualization and structured editing).

**Audience for this document:** engineering agents implementing the system. Decisions are made where they matter; ambiguity is called out explicitly.

---

## Stack summary

| Concern | Choice |
|---|---|
| Backend runtime | Python 3.12+, managed with `uv` |
| Backend framework | FastAPI + FastMCP mounted in a single process |
| Frontend | React (TypeScript) + Vite |
| Charts / calendar | Recharts, react-calendar-heatmap, react-day-picker |
| Data fetching | TanStack Query |
| Styling | Tailwind |
| Database | Neon (free tier), Postgres |
| ORM / migrations | SQLAlchemy + Alembic |
| Hosting | Render — Starter web service (~$7/mo) + free static site + cron |
| Auth | Bearer token via shared `APP_TOKEN` env var |
| External integration | intervals.icu (read-only) |
| Error tracking (optional) | Sentry free tier |

**Total run cost:** ~$7/month.

---

## 1. Goals & non-goals

### Goals
- Log meals via natural language conversation with Claude (MCP tools)
- Log and edit meals via a dashboard form when Claude isn't the fastest path
- See today's macros vs. targets at a glance
- Browse historical days (calendar navigation, day detail views)
- Trend visualization over 7 / 30 / 90 day windows
- Dynamic daily targets: base target + calories-out from intervals.icu
- Frequent-food templates ("my usual overnight oats")
- Favorite-food resolution to disambiguate common items

### Non-goals
- Multi-user support
- Weight or body-composition tracking (belongs in intervals.icu)
- Recipe or grocery management
- Native mobile app
- Public food database or barcode-first data entry
- Coaching / prescriptive suggestions

---

## 2. Architecture overview

### Services

- **`nutrition-api`** — Python service on Render. Hosts FastAPI (`/api/*`) and FastMCP (`/mcp`) in one process, sharing a domain layer. Owns all reads and writes.
- **`nutrition-web`** — React static site on Render. Calls `/api/*` only. Never talks to `/mcp`.
- **`nutrition-cron`** — Render cron job. Runs the intervals sync nightly.
- **Neon Postgres** — shared database, single `DATABASE_URL`.
- **intervals.icu** — external, read-only. Fetched via API by the sync path only.

### Write paths

```
Claude client ──► /mcp ──► domain layer ──► DB
Dashboard     ──► /api ──► domain layer ──► DB
Cron          ────► intervals sync ────► domain layer ──► DB (cache)
```

Both entry points call the same domain functions. There is one meaning of "log a meal" in the codebase.

### Repository layout

Monorepo:

```
nutribrain/
├── api/                 # Python service
│   ├── app/
│   │   ├── domain/      # pure business logic (log_meal, get_day, set_target)
│   │   ├── api/         # FastAPI routes
│   │   ├── mcp/         # FastMCP tools
│   │   ├── intervals/   # sync worker
│   │   ├── db/          # SQLAlchemy models, session, migrations helper
│   │   └── main.py      # composes FastAPI + FastMCP
│   ├── migrations/      # Alembic
│   ├── tests/
│   └── pyproject.toml   # uv
├── web/                 # React app
│   ├── src/
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
├── render.yaml          # infrastructure as code
└── README.md
```

---

## 3. Data model

### Conventions
- All primary keys `bigserial`
- All timestamps `TIMESTAMPTZ`, stored in UTC
- `local_date` derived at write time from meal's local clock. Timezone (IANA name) stored with each meal so training-camp trips log correctly.
- "Day" = local calendar date. A 00:30 snack belongs to the calendar date it happens on locally.

### Tables

#### `foods`
Reusable items — either from label scans or manual entry.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| name | text | |
| serving_size | numeric | |
| serving_unit | enum(`g`,`ml`,`piece`) | Cannot be changed after creation (see mutation rules) |
| calories | numeric | per serving |
| protein_g | numeric | per serving |
| carbs_g | numeric | per serving |
| fat_g | numeric | per serving |
| fiber_g | numeric nullable | per serving |
| sat_fat_g | numeric nullable | per serving |
| sodium_mg | numeric nullable | per serving |
| density_g_per_ml | numeric nullable | Null is treated as 1.0. Enables volume-to-mass conversion per food (uncooked rice ≈ 0.78, oil ≈ 0.92) |
| is_favorite | boolean default false | |
| created_at | timestamptz | |
| deleted_at | timestamptz nullable | Soft delete. Every read path filters `deleted_at IS NULL`; historical `meal_items` still resolve their food |

#### `meals`
An eating event.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| logged_at | timestamptz | UTC |
| local_tz | text | IANA name (e.g. `Europe/Dublin`) |
| local_date | date | derived from `logged_at` and `local_tz` at write time |
| meal_type | enum(`breakfast`,`lunch`,`dinner`,`snack`) | |
| notes | text nullable | |
| created_at | timestamptz | |

#### `meal_items`
Line items in a meal.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| meal_id | bigint FK meals | |
| food_id | bigint FK foods **nullable** | null = ad-hoc estimate |
| name | text | Copied from food.name, or free text if ad-hoc |
| quantity | numeric | |
| quantity_unit | enum(`g`,`kg`,`oz`,`lb`,`ml`,`l`,`fl_oz`,`tsp`,`tbsp`,`cup`,`piece`,`serving`) | |
| calories | numeric nullable | **Only populated when `food_id` is null** (ad-hoc estimate) |
| protein_g | numeric nullable | ditto |
| carbs_g | numeric nullable | ditto |
| fat_g | numeric nullable | ditto |
| fiber_g | numeric nullable | ditto |
| sat_fat_g | numeric nullable | ditto |
| sodium_mg | numeric nullable | ditto |
| source | enum(`label`,`template`,`estimate`,`manual`) | provenance |
| created_at | timestamptz | |

#### `templates`
Named presets.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| name | text | |
| created_at | timestamptz | |
| deleted_at | timestamptz nullable | Soft delete. Past applications are already materialized into `meal_items` and are unaffected |

#### `template_items`
References, not snapshots.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| template_id | bigint FK templates | |
| food_id | bigint FK foods **nullable** | null = ad-hoc estimate baked into the template |
| name | text | |
| quantity | numeric | |
| quantity_unit | enum(`g`,`kg`,`oz`,`lb`,`ml`,`l`,`fl_oz`,`tsp`,`tbsp`,`cup`,`piece`,`serving`) | |
| calories through sodium_mg | numeric nullable | **Only populated when `food_id` is null** |

#### `targets`
Daily base targets, versioned by effective date.

| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| effective_from | date | |
| base_calories | integer | |
| protein_g | integer | |
| carbs_g | integer | |
| fat_g | integer | |
| created_at | timestamptz | |

Effective target for a given day = most recent target where `effective_from <= day`, plus `intervals_calories_out.calories_out` for that day if present.

#### `intervals_calories_out`
Cache of intervals.icu daily calories expended.

| Column | Type | Notes |
|---|---|---|
| date | date PK | |
| calories_out | integer | |
| fetched_at | timestamptz | |
| source | enum(`sync`,`manual`) default `sync` | Distinguishes a synced value from a dashboard override, so the UI can show which days were hand-set |

### Indices
- `meals(local_date)` — the load-bearing index for day/week views
- `meal_items(meal_id)`
- `foods(lower(name))` — fuzzy resolution
- `foods(is_favorite) where is_favorite = true` — cheap favorite lookup
- `targets(effective_from desc)`

### Mutation rules — critical

These rules define what edits propagate to historical data and what stays local. Agents must not deviate.

**Food edits propagate to past meals.**
- Editing `food.calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `sat_fat_g`, `sodium_mg` recomputes every past meal_item referencing that food (read-time calculation, no writes needed)
- Editing `food.serving_size` propagates (it's a rate change — `cal/g = calories ÷ serving_size`)
- Editing `food.name` is cosmetic — propagates freely
- Editing `food.serving_unit` is **forbidden**. The API must reject this; the correct action is to create a new food.

**Choosing `serving_unit` — convention, not a constraint.**

Because `serving_unit` is immutable, it fixes the dimension a food can ever be
logged in. Mass and volume interoperate via `density_g_per_ml`; `piece` bridges
to neither, so a `piece`-defined food can never be logged by weight and vice
versa.

Therefore: **if a food has a natural countable unit *and* a meaningful weight,
define it by mass with `serving_size` set to the weight of one unit, and log
counts as `serving`.** A chocolate square becomes `serving_size 8, serving_unit
g`, so `20 g` and `3 serving` both resolve and reconcile with each other.

Reserve `piece` for foods with no useful weight in practice — an egg, a banana,
a rice cake. Getting this wrong is a one-way door: the fix is a new food and a
manual re-point of past meal_items.

**Meal_item edits stay local.**
- `meal_item.quantity` — you ate what you ate that day
- `meal_item.food_id` — swap the food, only affects that meal
- For ad-hoc items (`food_id NULL`), editing the stored macros only affects that meal_item

**Template edits don't touch past meals.**
- Editing a `template_item` affects future applications only
- Past meals logged from a template are already materialized as meal_items; they don't recompute
- Deleting a template is soft; past meal_items are unaffected

### Read-time macro calculation

For meal_items with `food_id` set:

```
grams = normalize_to_grams(meal_item.quantity, meal_item.quantity_unit, food)
factor = grams / normalize_to_grams(food.serving_size, food.serving_unit, food)
item_calories = food.calories * factor
item_protein_g = food.protein_g * factor
# ... etc for every macro
```

For meal_items with `food_id` NULL: read the macro values directly from the meal_item row.

Unit normalization is handled by the domain layer, driven by one frozen conversion constant.

- **Mass units** (`g`, `kg`, `oz`, `lb`) convert by fixed factor.
- **Volume units** (`ml`, `l`, `fl_oz`, `tsp`, `tbsp`, `cup`) convert to millilitres by fixed factor, then to grams via `food.density_g_per_ml`. A null density means 1.0, which reproduces the naive `g` ≡ `ml` behaviour.
- **`piece` and `serving`** are defined per food and cannot be converted to or from mass/volume units. Attempting it raises rather than guessing.

Density matters because volume-to-mass is a property of the food, not of the unit: a cup of uncooked rice is roughly 185 g while a cup of water is 237 g. Leaving density null is fine for foods logged by weight, which is most of them.

### Deletion semantics
- Foods: soft delete (`deleted_at`), never actually removed — past meals still reference them
- Templates: soft delete, same reason
- Meals & meal_items: hard delete. Undo is "log it again."

---

## 4. MCP tool surface

**Design principles**
- Every tool returns structured data Claude can quote back for confirmation
- Read tools are cheap and idempotent
- Ambiguity is escalated to the user, not guessed
- All date inputs accept `today`, `yesterday`, or ISO `YYYY-MM-DD`
- All time inputs default to now if omitted

### Write tools

**`log_meal(items, meal_type?, at?, notes?)`**
- `items`: list of `{name, quantity, unit, food_id?, macros?}`
- Resolution per item:
  1. If `food_id` given → use it directly
  2. Else fuzzy match on `name`:
     - Exactly one match → use it
     - Multiple matches with one favorite → use the favorite
     - Multiple matches, no favorite, one logged in last 30 days → use most recent
     - Multiple matches otherwise → return disambiguation error listing candidates
     - No match → require `macros` in the item, log as ad-hoc estimate
- `at` defaults to now; `meal_type` inferred from local time if omitted (see meal-type inference below)
- Returns: the created meal with resolved items, totals, and delta vs. today's effective target

**`log_template(template_name_or_id, at?, quantity_scale?, notes?)`**
- Materializes the template into a meal via the resolution rules above
- `quantity_scale`: optional multiplier applied to every item (0.5 = half portion)
- Returns: the created meal

**`add_food(name, serving_size, serving_unit, calories, protein_g, carbs_g, fat_g, fiber_g?, sat_fat_g?, sodium_mg?)`**
- Errors on fuzzy-duplicate name unless `force: true`
- Returns: the created food

**`update_food(food_id, ...fields)`**
- Partial update
- Rejects `serving_unit` changes with a clear error message
- Returns: the updated food plus a count of past meals affected ("47 meals will recompute")

**`create_template(name, items)`** / **`update_template(id, ...)`** / **`delete_template(id)`**
- `items` shape matches `log_meal`
- Delete is soft

**`set_target(base_calories, protein_g, carbs_g, fat_g, effective_from?)`**
- `effective_from` defaults to today
- Creates a new versioned target row (never mutates existing)
- Returns: the new target, plus a note if it overlaps or replaces an earlier same-day target

**`set_favorite_food(food_id, is_favorite)`**
- Toggle for disambiguation resolution
- Returns: the updated food

**`delete_meal(meal_id)`** / **`delete_meal_item(item_id)`**
- Hard delete
- Returns: `{deleted: true}`

### Read tools

**`get_day(date?)`**
- Default: today
- Returns: meals grouped by meal_type, totals, effective target (base + calories_out), calories_out for context, delta vs. target
- The primary tool for "how am I doing today"

**`get_range(from, to, granularity?)`**
- `granularity`: `day` (default) or `week`
- Returns per-period totals + effective targets + adherence flags

**`find_food(query, limit?)`**
- Fuzzy search over `foods.name`
- Returns matches with per-serving macros, `is_favorite`, `last_logged_at`, `logged_count` — enough for Claude's resolution rules
- `last_logged_at` and `logged_count` are **computed in-query** by joining `meal_items` to `meals`. They are deliberately not columns on `foods`: stored counters would need maintaining on every meal insert and delete, and a drifted counter silently corrupts the resolution rules above

**`list_templates()`**
- Returns all templates with their items (small enough to always return in full)

**`get_target(date?)`**
- Returns: effective target for the specified day with base + calories_out breakdown

### Sync tool

**`sync_intervals(from?, to?)`**
- Pulls calories-out from intervals.icu into the cache
- Defaults: last 7 days
- Returns: count of days synced, list of failures if any

### Meal-type inference

Local time windows (Ireland tz):
- `breakfast`: 04:00 – 10:59
- `lunch`: 11:00 – 15:59
- `dinner`: 16:00 – 21:59
- `snack`: 22:00 – 03:59 or explicitly requested

If the log time falls outside a natural window (e.g. mid-afternoon), default to `snack`. Always overridable by the caller.

### Deliberately absent
- No `get_food(id)` — `find_food` covers it
- No bulk import
- No `update_meal_item` — delete + relog is fine at v1 scale
- No template categories, tags, or search facets

**Total surface: 17 tools.**

---

## 5. AI logging flow

### Typical meal log

1. User: "Log my breakfast — two eggs, toast with butter, and a coffee"
2. Claude parses into candidate items
3. Claude calls `find_food` on each unfamiliar name
4. For matches: reuses `food_id`. For non-matches: estimates macros inline and marks the item as `source: estimate`
5. Claude calls `log_meal` with the fully-resolved item list
6. Tool returns the created meal + totals + delta vs. today's effective target
7. Claude confirms in chat: "Logged breakfast — 520 cal, 28g protein. You're at 620/2500 for the day."

### Nutrition label flow

1. User uploads a label photo in chat
2. Claude reads the label directly (in-context, no OCR call)
3. Claude calls `add_food` with the extracted per-serving values
4. Claude usually loops immediately into `log_meal` for the amount just eaten

### Frequent food resolution

- "My usual overnight oats" → Claude calls `list_templates`, fuzzy-matches against template names locally, then calls `log_template`
- Ambiguous or missing → Claude asks the user rather than guessing

### Estimation policy

- Estimates aren't auto-promoted to foods. They stay on the meal_item as ad-hoc rows.
- Claude surfaces uncertainty in chat: "roughly 450 cal, ±80" so the user knows when to correct. Not a schema field; chat behavior only.
- If the user later scans a label for the same item, Claude explicitly calls `add_food` to create a proper foods row.

### Commit model

The tool commits immediately; Claude describes what it did in the reply. No two-phase propose/commit. Corrections are handled via `delete_meal_item` + `log_meal`.

### Correction & backfill

- "I forgot lunch yesterday" → `log_meal` with `at: yesterday 13:00`
- "That granola was 60g not 40g" → `delete_meal_item` + `log_meal` (or `update_meal_item` if added later)
- "That granola has 380 cal per serving not 400" → `update_food`; tool returns propagation count so Claude can report "updated — that recomputed 23 past meals"

### Target / calories-out flow

- Nightly cron runs `sync_intervals` for yesterday + 2 buffer days
- Mid-day queries call `sync_intervals(today, today)` before answering "how am I doing"
- Effective target computed automatically in `get_day` / `get_target`

### What Claude should not do

- **Never** call `update_food` to fix a single meal's numbers — that propagates to history. Use meal_item delete+relog instead.
- **Never** create a template unprompted from a repeated pattern. User-initiated only.
- **Never** guess between multiple matching foods when the resolution rules are ambiguous. Ask.
- **Never** attempt to change `food.serving_unit` — the API rejects it. Create a new food.

---

## 6. Frequent foods / templates

### Resolution flow

Claude's flow when the user references a template by name:
1. Call `list_templates`
2. Fuzzy match locally against template names
3. Single confident match → `log_template`
4. Ambiguous or missing → ask the user

### Materialization rules

When `log_template` runs, each `template_item` becomes a `meal_item`:

- **`food_id` set** → meal_item gets the same `food_id`; macros compute live from the current food per section 3
- **`food_id` NULL** → the template_item's estimate copies into the new meal_item as an ad-hoc entry
- `quantity` from the template_item, optionally multiplied by `quantity_scale`
- `source: template` on every resulting meal_item

### Editing semantics

- Editing a `template_item` (quantity, food swap, estimate adjustment) → affects future applications only
- Past meals are already materialized; nothing recomputes
- Deleting a template → soft delete; past meal_items untouched

### Interaction with favorites

Templates lock to specific `food_id`s at creation time. Changing your favorite brand of bagel does not retroactively change what's inside your "morning bagel" template.

To get dynamic favorite-based resolution, log ad-hoc ("bagel with cream cheese") and let `find_food`'s resolution rules pick. Favorites and templates compose but don't override each other.

### Quantity scaling

- `log_template(name, quantity_scale: 0.5)` for a half portion
- Applies to every item uniformly
- For finer control, log the components ad-hoc
- Not a template edit; per-application multiplier

### Out of scope
- Template categories, tags, search facets
- Auto-suggestion of new templates from repeated patterns
- Nested templates (template referencing template)
- Template versioning

---

## 7. Web dashboard

### Stack
- Vite + React + TypeScript
- Recharts, react-calendar-heatmap, react-day-picker
- TanStack Query
- Tailwind
- Deployed as Render static site

### Routes

| Route | Purpose |
|---|---|
| `/` | Today view (landing) |
| `/day/:date` | Day detail (fully editable) |
| `/trends` | Trend view |
| `/calendar` | Adherence heatmap |
| `/foods` | Foods manager |
| `/templates` | Templates manager |
| `/targets` | Target history |
| `/settings` | Token, timezone, sync status |

### Today view (`/`)
- Header: date, effective target with base + calories_out breakdown
- Calories: ring or large bar with progress
- Big-three macros (protein, carbs, fat): three prominent secondary bars
- Micro row: fiber, sat fat, sodium — smaller, muted
- Meal list grouped by meal_type, each expandable to items
- "Log a meal" button → inline meal editor
- "Sync intervals now" button

### Day detail (`/day/:date`)
- Same layout as Today for any date
- Fully editable — primary correction surface

### Trend view (`/trends`)
- Range selector: 7 / 30 / 90 days
- Line chart: calories per day with target overlay (Recharts `ReferenceLine`)
- Stacked bar: protein/carbs/fat per day
- Small stat tiles: average adherence %, longest in-target streak, worst-miss day

### Calendar view (`/calendar`)
- 12-month react-calendar-heatmap
- Color: green in target, yellow near, red outside, grey no log
- Hover → totals tooltip
- Click → `/day/:date`

### Foods manager (`/foods`)
- Searchable, sortable table
- Star icon toggles `is_favorite`
- Row click → edit modal
- Edit modal shows "this will recompute N past meals" before commit
- "Add food" opens a manual form
- Serving-unit field is disabled after creation

### Templates manager (`/templates`)
- List with item counts
- Edit form: template name + repeater of items
- Ad-hoc items (no food) allowed with inline macro fields
- "Log now" button applies the template as today's meal

### Meal editor component
Used in Today, Day detail, and template management:
- Item repeater: food search + quantity + unit
- Food search calls `GET /api/foods?q=...`, shows ★ marker for favorites
- Ad-hoc toggle exposes macro fields
- Meal-type dropdown (defaults per time window)
- Time picker (defaults to now)

### Targets (`/targets`)
- List of versioned targets, `effective_from` desc
- Create new: form with base calories + macros + `effective_from`
- Read-only view of past targets; new edits create a new version

### Settings (`/settings`)
- Bearer token: paste field, "test connection" button, `localStorage` storage
- Timezone override (defaults to browser)
- Intervals sync status: last sync timestamp + "sync now" button
- Diagnostic panel: DB connection, last error

### Cross-cutting behavior
- All mutations optimistic via TanStack Query with rollback on error
- Toasts for success / failure
- Loading skeletons on first paint
- Empty states with a nudge ("no meals logged today — tell Claude, or use the button")

### Accessibility floor
- Full keyboard navigation on forms
- Charts have text summaries beneath them (Recharts alone isn't screen-reader-friendly)
- Focus rings preserved
- Sufficient color contrast on adherence heatmap

### Out of scope for v1
- PWA / installable app (responsive layout only)
- Dark mode toggle (respects system preference via Tailwind)
- CSV export
- User accounts / password reset (token paste only)

---

## 8. intervals.icu integration

### Purpose
- Pull daily calories-out into the local cache
- Feed dynamic target: `effective_target = base_target + calories_out(date)`
- Read-only; no writes back to intervals

### Data flow

```
intervals.icu API ──► sync worker ──► intervals_calories_out cache ──► domain layer ──► /api & /mcp
```

The cache is the source of truth for reads. Only the sync worker writes it.

### intervals API details

- Endpoint: `GET https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest=YYYY-MM-DD&newest=YYYY-MM-DD`
- Auth: HTTP Basic; username `API_KEY`, password `<INTERVALS_API_KEY>`
- Field of interest: `sportInfo.Calories` per day (total daily calories expended)

### Sync triggers

Three triggers, one shared sync function:

1. **Nightly cron** — 03:00 UTC, syncs last 3 days (yesterday + 2 buffer days for late intervals corrections)
2. **On-demand MCP tool** — `sync_intervals(from?, to?)`, default last 7 days
3. **Dashboard button** — `POST /api/sync/intervals` with today's date

### Missing-data rules

- `null` from intervals → don't insert a row; day treated as "no data"
- `0` from intervals → insert as 0; day treated as a genuine rest day
- Effective target with no cache row → falls back to `base_target` alone
- Dashboard distinguishes: "target 2500 (2000 base + 500 out)" vs "target 2000 (no activity data)"

### Failure modes

- intervals API down → sync fails; last known values stay in cache; dashboard shows "last sync N hours ago"
- Auth failure → sync fails loudly; dashboard shows banner; MCP tool returns error
- Partial success in a range → per-day writes; log failures; don't block the rest

### Config
- `INTERVALS_API_KEY` env var
- `INTERVALS_ATHLETE_ID` env var
- `INTERVALS_SYNC_DAYS` env var (default 3 for cron)

### Manual override

Dashboard's day detail view includes a manual "set calories out" input for the rare case when intervals is down or Garmin didn't sync. Writes directly to the cache with `fetched_at: now()` and `source: manual`. The next real sync overwrites it and resets `source` to `sync` — desired behaviour. The `source` column exists so the dashboard can mark which days are hand-set rather than measured.

### Out of scope
- Pulling calories-in from intervals
- Pulling workouts, HR, TSS
- Reconciliation UI when intervals corrections change targets historically (recomputation is automatic)

---

## 9. Auth

### Model
- Single shared secret in `APP_TOKEN` env var
- Sent as `Authorization: Bearer <token>` on every request
- Same check protects `/api/*` and `/mcp` — one dependency, one env var

### Implementation

```python
# app/auth.py
import os
import hmac
from fastapi import Header, HTTPException

APP_TOKEN = os.environ["APP_TOKEN"]

def require_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization[7:]
    if not hmac.compare_digest(token, APP_TOKEN):
        raise HTTPException(401, "invalid token")
```

- `hmac.compare_digest` for constant-time comparison
- Applied via `dependencies=[Depends(require_auth)]` per router
- **The FastMCP sub-app does not automatically inherit this dependency, and this must be verified before any other work proceeds.** FastAPI's `dependencies=[...]` only runs for routes FastAPI itself owns; mounting an ASGI sub-application hands the request off before the dependency machinery executes. If `/mcp` does not reject an unauthenticated request, every write tool is exposed on the public internet, and it fails silently because your own client sends the header regardless.
- Required test: a request to `/mcp` with **no** `Authorization` header must be rejected. If it is not, move auth into ASGI middleware wrapping both mounts.

### Token generation

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

~256 bits of entropy. Store in Render's env var UI.

### MCP client config

Claude Desktop:
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

For Claude web / mobile: custom connector with the same header.

### Dashboard UX
- First visit → landing screen: "Paste your API token"
- Token stored in `localStorage` under `nutribrain:token`
- Fetch interceptor attaches token to every call
- 401 response → clear token, redirect to paste screen with "token invalid" message
- Settings shows masked token (`sk...abc123`) with copy and rotate helpers

### Health endpoint
- `GET /health` — unauthenticated, returns `{"status": "ok"}` only
- No version info, no DB check (both would need auth to be safe)

### CORS
- Explicit allowlist of the Render static site's origin
- No wildcards

### Logging discipline
- Never log the `Authorization` header value (structlog processor redacts)
- Log 401s as counts, not with token attempts

### Forward-compatibility
- The `require_auth` dependency is the seam for future Google OAuth
- Function name and imports stable; body swaps to session-cookie or JWT validation
- Zero route code touched during upgrade

### Out of scope for v1
- User tables, sessions, refresh tokens
- Token scopes (read-only vs write)
- Rate limiting (add reactively if needed via `slowapi`)
- 2FA

---

## 10. Hosting & deployment

### Services on Render

| Service | Type | Tier | Purpose |
|---|---|---|---|
| `nutrition-api` | Web (Python) | Starter ~$7/mo | FastAPI + FastMCP |
| `nutrition-web` | Static site | Free | React dashboard |
| `nutrition-cron` | Cron job | Included | Nightly intervals sync |

### External
- Neon (free tier) — Postgres
- intervals.icu — data source
- Sentry (optional, free tier) — error tracking

### render.yaml

```yaml
services:
  - type: web
    name: nutrition-api
    runtime: python
    rootDir: api
    plan: starter
    buildCommand: uv sync && uv run alembic upgrade head
    startCommand: uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: DATABASE_URL          # from Neon
      - key: APP_TOKEN             # generated once
      - key: CORS_ORIGIN
        value: https://nutrition-web.onrender.com
      - key: INTERVALS_API_KEY
      - key: INTERVALS_ATHLETE_ID
      - key: TZ
        value: Europe/Dublin

  - type: static
    name: nutrition-web
    rootDir: web
    buildCommand: npm ci && npm run build
    staticPublishPath: ./dist
    envVars:
      - key: VITE_API_BASE
        value: https://nutrition-api.onrender.com

  - type: cron
    name: nutrition-cron
    runtime: python
    rootDir: api
    schedule: "0 3 * * *"          # 03:00 UTC
    buildCommand: uv sync
    startCommand: uv run python -m app.intervals.sync_recent
    envVars:
      - fromService: { type: web, name: nutrition-api, envVarKey: DATABASE_URL }
      - fromService: { type: web, name: nutrition-api, envVarKey: INTERVALS_API_KEY }
      - fromService: { type: web, name: nutrition-api, envVarKey: INTERVALS_ATHLETE_ID }
```

### Deploy flow
- `git push origin main` → Render auto-builds any service whose `rootDir` changed
- API build runs Alembic migrations before startup
- Static site deploys are near-instant
- If a migration fails, the deploy fails and the previous version keeps serving

### Local development

```bash
# API
cd api
uv sync
uv run uvicorn app.main:app --reload

# Web
cd web
npm install
VITE_API_BASE=http://localhost:8000 npm run dev

# Cron (on demand)
cd api
uv run python -m app.intervals.sync_recent
```

Neon branches are free and instant — create one per dev environment rather than a local Postgres.

### Database connections

Neon's free tier scales compute to zero after ~5 minutes idle, closing every open connection. SQLAlchemy's pool does not find out, and will hand out a dead connection on the next request. Configure the engine accordingly:

- Use Neon's **pooled** (`-pooler`) connection string
- `pool_pre_ping=True` — validates before checkout, turning a suspended endpoint into a transparent reconnect instead of a 500
- `pool_recycle=300` — retire connections before Neon does
- `pool_size=2` — single user; there is nothing to pool for
- Pin compute to 0.25 CU in the Neon console

No keep-alive ping. Holding the endpoint awake around the clock costs roughly 182 CU-hours against a 100 CU-hour monthly allowance, which suspends the project mid-month. Cold starts of a few hundred milliseconds are accepted, and the dashboard's loading skeletons already absorb them. Note also that `/health` deliberately does not touch the database, so uptime monitoring cannot accidentally hold compute awake.

### Migrations
- Alembic, autogenerated then hand-reviewed
- Never edit past migrations; only add new ones
- Migration runs in the API build step

### Secrets
- Render env vars (encrypted, not in git)
- `.env.example` committed with placeholders; `.env` gitignored
- Rotating `APP_TOKEN`: generate new, update Render, re-paste in dashboard, update MCP config

### Custom domain
- Not required — `.onrender.com` URLs work fine
- Optional later: `nutrition-api.<domain>` and `nutrition.<domain>`, TLS handled by Render

### Cost check
- Render Starter: $7/mo
- Everything else: $0
- **Total: $7/mo**

---

## 11. Observability & backup

### Logging

Structured logs via `structlog` → stdout → Render's log pipeline.

Config:
- JSON output in production, pretty console in dev
- Every request bound to a `request_id`; MCP tool calls carry `tool_name`
- Default level `INFO`; `DEBUG` behind an env flag
- Domain-layer functions log at mutation boundaries, not inside loops

Log:
- Every mutation (meal logged, food edited, target changed) with entity id
- Every intervals sync with days affected + duration
- Every auth failure (as a count trigger)
- Any request over 500ms

Don't log:
- The `Authorization` header value
- Full request bodies
- Successful reads

Retention: Render keeps ~7 days on Starter. If longer needed, ship to Axiom or Better Stack free tier.

### Error tracking

Sentry free tier (5k errors/month):
- Python SDK in API — unhandled exceptions with request context
- Browser SDK in React — render errors, unhandled promise rejections
- One account, two projects
- Alert on new issue types

### Metrics

Skip. One user, no traffic to graph. Add targeted structlog timing entries if a specific query starts to bite.

### Health checks
- `GET /health` unauthenticated, returns `{"status": "ok"}`
- Render pings this, restarts on failure
- Deliberately doesn't check DB

### Uptime monitoring

Optional: UptimeRobot or Better Stack free tier hits `/health` every 5 minutes.

### Backup strategy

**Primary: Neon PITR**
- Free tier includes ~24 hours point-in-time recovery
- Covers "I fat-fingered an update an hour ago"

**Belt-and-braces: weekly `pg_dump` to R2**
- Cron job runs weekly
- `pg_dump | gzip | upload to Cloudflare R2`
- Retention: last 8 dumps, prune older
- R2 free tier: 10 GB, 1M ops/month — not a limiting factor

Why both: Neon PITR is one platform, one account. A hosed account or a mass-delete outside the PITR window means zero recovery without independent dumps.

### Restore drill (do once, in first week)
1. Grab latest R2 dump
2. Restore into a Neon dev branch
3. Point local API at it, confirm data reads correctly
4. Delete the branch

Establishes backups actually work.

### Out of scope
- Distributed tracing
- Log aggregation platform
- Custom dashboards / Grafana
- Multi-region redundancy

---

## 12. Open questions / v2

### Nice-to-haves

- **Weekly summary.** Sunday-evening review: average calories, macro adherence, standout days. Cron generates it into a Google Doc, email, or scheduled Claude prompt.
- **Hydration.** Separate simple counter, not a food. `hydration_entries` table, one MCP tool, Today widget.
- **Supplements.** Similar shape to hydration — timing more than macros. Possibly just tags on meals.
- **Meal photos.** Attach photo to a meal for later reference. R2 storage, URL on meal row. No macro extraction from photo — Claude reads in-context when needed.
- **Barcode lookup.** Open Food Facts as a fallback. Adds `barcode` column to `foods` and a lookup MCP tool.
- **`foods.grams_per_piece`.** A nullable column bridging count to mass, mirroring what `density_g_per_ml` does for volume. Deferred from v1: the convention above covers the common case, and the residual gap is narrow — a food whose serving is several pieces, logged as a different count. Add the column and one branch in `normalize_to_grams` if that case shows up in practice.

### Behavior questions to revisit after a month of use

- **Estimate promotion.** Do repeated ad-hoc estimates warrant prompting to promote to a food?
- **Template auto-detection.** If the same three items are logged together six mornings running, offer to save?
- **Meal-type inference edge cases.** Time-window rules misfire on shift days or long rides.

### Auth upgrade path
- Google OAuth via Authlib when token-pasting gets old
- Section 9's `require_auth` seam absorbs it

### Integrations to consider

- Garmin Connect food logging — probably skip, intervals covers energy expenditure
- Apple Health / Health Connect — read-only pull; nice on paper, brittle in practice
- MyFitnessPal — no public API
- Cronometer export — one-shot migration path if seeding history

### Multi-user
- Requires `users` table, `user_id` FK on every mutable row, real auth, per-user intervals credentials
- Meaningful rewrite; only worth it if building for someone specific

### Explicit non-goals (recorded to prevent drift)
- Not a food database. Foods are yours, curated by you.
- Not a coach. Shows numbers; doesn't prescribe.
- Not social. No sharing, leaderboards, comparisons.
- Not general-purpose. Nutrition only.

---

## Appendix A — Environment variables

| Var | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | api, cron | Neon connection string |
| `APP_TOKEN` | api | Bearer token for auth |
| `CORS_ORIGIN` | api | Static dashboard site origin, allowlisted for CORS |
| `INTERVALS_API_KEY` | api, cron | intervals.icu HTTP Basic password |
| `INTERVALS_ATHLETE_ID` | api, cron | intervals.icu athlete id |
| `INTERVALS_SYNC_DAYS` | cron | Days of history to sync nightly (default 3) |
| `TZ` | api, cron, mcp | `Europe/Dublin`. Also the MCP server's default effective local timezone when a tool call omits `local_tz` |
| `LOG_LEVEL` | api | `INFO` default, `DEBUG` for deep dives |
| `SENTRY_DSN` | api, web | Optional |
| `VITE_API_BASE` | web build | API base URL |
| `GOOGLE_OAUTH_CLIENT_ID` | api | Google OAuth client ID for `/mcp` (optional; see `docs/features/mcp_oauth.md`) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | api | Google OAuth client secret for `/mcp` (optional) |
| `MCP_ALLOWED_EMAIL` | api | Sole Google account allowed to authenticate to `/mcp` (optional) |
| `MCP_PUBLIC_BASE_URL` | api | Public base URL for constructing the `/mcp` OAuth redirect (optional) |

## Appendix B — Enums

- `foods.serving_unit`: `g`, `ml`, `piece` — the immutable reference unit. Deliberately narrow; `add_food` normalises a label serving such as "1 cup" into `ml` on the way in
- `meals.meal_type`: `breakfast`, `lunch`, `dinner`, `snack`
- `meal_items.quantity_unit`: `g`, `kg`, `oz`, `lb`, `ml`, `l`, `fl_oz`, `tsp`, `tbsp`, `cup`, `piece`, `serving`
- `meal_items.source`: `label`, `template`, `estimate`, `manual`
- `template_items.quantity_unit`: same as `meal_items`
- `intervals_calories_out.source`: `sync`, `manual`

Postgres enum values are cheap to add and painful to remove, so the unit list above is deliberately complete at the outset.

## Appendix C — Standard error responses

All API and MCP tool errors follow:

```json
{
  "error": "food_ambiguous",
  "message": "Multiple foods match 'bagel'. Specify one.",
  "candidates": [
    {"id": 12, "name": "Brennans Bagel", "calories": 260},
    {"id": 13, "name": "M&S Sourdough Bagel", "calories": 240}
  ]
}
```

Error codes agents should handle:
- `unauthorized` — 401
- `food_not_found` — no fuzzy match for a name
- `food_ambiguous` — multiple matches, no resolution rule fires
- `food_duplicate` — `add_food` name collision without `force: true`
- `serving_unit_immutable` — `update_food` attempt to change serving unit
- `food_merge_same_food` — `merge_food` called with `from_id` equal to `into_id`
- `template_not_found`
- `intervals_unavailable` — sync failed
- `meal_not_found`
- `meal_item_not_found`
- `meal_item_food_linked` — `update_meal_item` attempt to edit macros while `food_id` is set
- `meal_item_macros_required` — `update_meal_item` cleared `food_id` without supplying the now-required macros
- `invalid_timezone` — an explicit or effective-default `local_tz` is not a valid IANA timezone name

## Appendix D — Sequence: label scan → log

```
User uploads label + "I had one serving"
    │
    ▼
Claude reads label in-context
    │
    ▼
find_food(name)  ──► no match
    │
    ▼
add_food(name, serving_size, serving_unit, macros...)
    │              returns food_id
    ▼
log_meal(items=[{food_id, quantity: serving_size, unit: serving_unit}])
    │              returns meal + totals + delta
    ▼
Claude reports: "Logged. You're at X/Y for the day."
```


---

## Changelog

### v1.1 — amendments G1–G7

Resolved before implementation began. These override anything earlier in the
document that contradicts them.

| # | Change |
|---|---|
| G1 | Added `deleted_at` to `foods` and `templates`. The soft-delete rule in §3 previously referenced a column that did not exist. |
| G2 | Corrected the tool count in §4 from 15 to 17. The original figure counted bullet headings, grouping the three template mutations and the two delete tools as single entries. |
| G3 | Documented that `find_food`'s `last_logged_at` and `logged_count` are computed in-query rather than stored. |
| G4 | Extended `quantity_unit` to twelve units and added `foods.density_g_per_ml`. Volume-to-mass is food-specific, so a fixed `g` ≡ `ml` rule could not support logging by cup. One nullable column replaces the `food_units` side table considered earlier. |
| G5 | Added `intervals_calories_out.source` so a manual override is distinguishable from a synced value. |
| G6 | Documented Neon connection-pool settings in §10. Scale-to-zero closes connections that SQLAlchemy will otherwise reuse. No keep-alive ping. |
| G7 | Corrected the claim in §9 that the FastMCP sub-app inherits the FastAPI auth dependency. It does not necessarily, and the consequence of the assumption being wrong is an unauthenticated write surface. |
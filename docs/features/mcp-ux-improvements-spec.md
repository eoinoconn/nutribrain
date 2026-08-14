# MCP Tool UX Improvements — Spec & Task List

Source: a Claude Desktop review of nine dogfooding sessions against the live
NutriBrain MCP server (`api/app/mcp/`). This document restates that review as
verified findings and dependency-ordered tasks. Where the review's claim was
checked against the current code (`git rev-parse HEAD` at time of writing, branch
`today-ui-redesign`) and found accurate, wrong, or already fixed, that's called
out explicitly — some of the original claims came from session summaries, not
raw transcripts, and didn't hold up.

Tools referenced live in `api/app/mcp/tools_read.py` and `tools_write.py`.
Domain logic lives in `api/app/domain/`, per `api/CLAUDE.md`.

---

## Verification notes (read before starting any task)

- **`update_meal` / `update_meal_item` do not exist.** Confirmed — `tools_write.py`
  only exposes `delete_meal` and `delete_meal_item`. This is the real gap.
- **`log_meal`'s response already includes per-item `id`.** Confirmed —
  `MealItemModel.id` in `serializers.py:53-60`. The review asked for this as
  part of the fix; it's already there. Only the update tools are missing.
- **`copy_meal` / `find_meal` do not exist.** Confirmed.
- **`local_tz` is required on exactly six tools**: `log_meal`, `log_template`,
  `get_day`, `get_range`, `set_target`, `get_target`. Confirmed by direct count.
- **`find_food` already does fuzzy matching.** Not confirmed as broken —
  `search_foods` (`app/domain/foods.py:197`) already uses `pg_trgm` similarity
  (threshold `FOOD_NAME_SIMILARITY_THRESHOLD = 0.35`, `app/domain/constants.py:25`)
  with a substring-contains fallback, case-folded via `lower()`. The GetPRO miss
  needs root-causing against this existing logic, not a rewrite — see MCP-06.
- **`add_food`'s `force` flag and duplicate detection exist and are wired
  correctly** (`app/domain/foods.py:76-82`, raises `FoodDuplicateError` unless
  `force=True`). The GetPRO duplicate happened because `find_food` didn't
  surface the existing row as a candidate in the first place, not because
  `force` malfunctioned.
- **`delete_food` already exists in the domain layer and the REST API**
  (`app/domain/foods.py:177-194`, wired in `app/api/foods.py`) but has **no MCP
  tool**. This is a wiring task, not new domain logic.
- **`merge_food` does not exist anywhere** (domain or transport). Needs new
  domain logic.
- **Numeric fields really do cost ~60-70 tokens each in schema.** Confirmed —
  Pydantic v2's default JSON Schema for `Decimal` is
  `anyOf: [{type: number}, {type: string, pattern: ...}]`. Verified by
  generating the schema directly. ~40+ fields across `log_meal`, `add_food`,
  `update_food`, `create_template`, `update_template` carry this.
- **`items[].name` is required even when `food_id` is set.** Confirmed —
  `MealItemInput.name` and `TemplateItemInput.name` are both
  `Field(min_length=1)` with no default, in `tools_write.py:52-77`.
- **`get_target` is redundant with `get_day`.** Confirmed — `DayResponse`
  already carries `effective_target` (`app/domain/dto.py:186`), same shape
  `get_target` returns.
- **`meal_type` is an unconstrained `str | None` in both `log_meal` and
  `log_template`.** Confirmed, `tools_write.py:102`, `:135`.
- **Naive `logged_at` does error today**, at least in `log_template`:
  `app/domain/templates.py:147-148` raises `ValueError("logged_at must be
  timezone-aware")` on a naive datetime. `log_meal`'s equivalent path should be
  checked for the same behavior (MCP-04/05) but the "sometimes errors, sometimes
  doesn't" claim likely reflects inconsistent *description* text, not
  inconsistent *validation*.
- **`create_template` does NOT actually require macros on `food_id`-linked
  items — this review claim is false, no fix needed.** `_spec_to_template_item`
  (`app/domain/templates.py:290-314`) already drops macro fields entirely when
  `food_id` is set, regardless of what the caller sent. The CHECK constraint
  (`adhoc_macros` on both `meal_items` and `template_items`,
  `app/db/models.py:156-165`, `:209-218`) is already satisfied correctly by
  current code. Do not queue a fix; if a future session reproduces this,
  capture the exact tool call first.
- **`list_templates` does return full items every call, with no summary
  mode.** Confirmed, `tools_read.py:100-105`.
- **No `idempotency_key` parameter exists anywhere.** Confirmed.

---

## Priority tiers

### P0 — highest leverage, do first

#### MCP-01 · `update_meal` and `update_meal_item`
**Problem:** every correction today is `delete_meal` + full `log_meal`
re-emission. This is the single largest source of both token waste and data
corruption (ghost meals from a forgotten or racing delete).

**Scope:**
- New domain function `update_meal(session, *, meal_id, meal_type=None,
  logged_at=None, notes=None)` — mutate the `Meal` row in place, no item
  changes. Follows the same partial-update sentinel pattern as `update_food`
  for fields that need "explicitly clear" vs. "leave alone" (`notes` likely
  needs the `_SENTINEL` treatment; `meal_type`/`logged_at` don't since they're
  simple non-nullable value swaps).
- New domain function `update_meal_item(session, *, item_id, quantity=None,
  quantity_unit=None, calories=None, protein_g=None, carbs_g=None, fat_g=None,
  fiber_g=None, sat_fat_g=None, sodium_mg=None)`.
  - Must preserve the `adhoc_macros` CHECK invariant: if the item's `food_id`
    is set, reject any macro-field edit (`food_id`-linked items compute macros
    live and must stay NULL in storage) — raise a domain error, don't silently
    drop the value the way `create_template` does for creation. This is an
    edit path; silent drops would look like data loss to the caller.
  - `food_id` itself is swappable per the existing mutation rule
    ("meal_item.food_id — swap the food, only affects that meal") — decide
    whether this lands in MCP-01 or a follow-up; if included, swapping
    `food_id` from set→NULL or NULL→set changes which fields are legal to
    edit in the same call, so validate the combination explicitly.
- MCP tool registrations in `tools_write.py` mirroring the `update_food` tool
  shape (partial update, same domain-error-to-`ToolErrorResponse` mapping via
  `capture_domain_error`).
- Tool descriptions should state plainly that this is the correction path —
  mirroring the existing `log_meal` description's "do not use update_food to
  fix a single meal" pattern, e.g. "Use this instead of delete_meal + log_meal
  to correct one field."
- Tests: partial update semantics, CHECK-constraint rejection for
  `food_id`-linked macro edits, meal totals/`delta_vs_target` recompute
  correctly on read after a `quantity` change.

**Out of scope:** adding/removing items from a meal — that's still
`delete_meal_item` + a fresh `log_meal` item, or covered by MCP-02's
`copy_meal` for the common "same meal, different day" case.

#### MCP-02 · `copy_meal`
**Problem:** "same as yesterday" costs a `get_day` (whole day) → parse → full
re-emission of every item.

**What this saves, precisely:** a source `meal_id` is still needed, so in the
cold-start case (nothing looked up yet this conversation) call count doesn't
drop — it's `lookup + copy_meal` vs. today's `get_day + log_meal`, same
number of round-trips. What shrinks is the *payload*: `copy_meal`'s request
is just `meal_id` plus a few optional fields, versus `log_meal` having to
retransmit every item's name/quantity/unit/macros, which is both the token
cost and the main source of ghost-meal duplication (a botched re-emission
diverging from the delete). Call count only drops to one when the `meal_id`
is already known from earlier in the same conversation (e.g. "log the same
for lunch too" right after logging breakfast) — or, once MCP-03 (`find_meal`)
exists, the lookup itself becomes a small targeted call instead of
`get_day`'s whole-day payload, so "same as yesterday" becomes
`find_meal → copy_meal`: still two calls, but both small.

**Scope:**
- Domain function `copy_meal(session, *, meal_id, local_tz, to_day=None,
  at=None, quantity_scale=None, notes=None)` that reads the source meal's
  items and re-materializes them as a new meal, same shape as
  `log_template`'s materialization logic (`app/domain/templates.py:128-`) —
  `food_id`-linked items carry the food_id forward (macros stay live-computed);
  ad-hoc items copy their stored macro snapshot; `quantity_scale` multiplies
  quantity on every item, matching `log_template`'s existing parameter.
- `to_day` defaults to today (date token or ISO date, via the existing
  `resolve_date_arg` helper in `app/mcp/date_args.py`); `at` sets time-of-day
  within that resolved day.
- MCP tool in `tools_write.py`, response shape matches `log_meal`'s
  `MealModel` (including item ids, so a copy immediately followed by a
  one-field correction can go straight to MCP-01 without a lookup).

#### MCP-03 · `find_meal`
**Problem:** "when did I last have X" means walking `get_day` one day at a
time.

**Scope:**
- Domain function `find_meal(session, *, query, since=None, limit=None)` —
  search meal items by name (and joined food name where `food_id` is set),
  most-recent-first, optionally bounded by `since`. Reuse the fuzzy-match
  approach from `search_foods` (trigram + substring fallback) for consistency
  rather than inventing a second matching strategy.
- Return enough per-result context (`meal_id`, `item_id`, `logged_at`,
  `local_date`, `name`, `quantity`) that the result can feed directly into
  `copy_meal` or `update_meal_item` without another round-trip.
- MCP tool in `tools_read.py`.

### P1 — high friction, moderate effort

#### MCP-04 / MCP-05 · Effective timezone resolution + `logged_at` handling
**These two do not sequence independently — they share one piece of state
(the "effective local timezone" for a call) and must be built as a single
unit with one resolver, or two PRs will each invent their own fallback and
diverge.** Originally scoped as separate P1 tasks; merged here after review.

**Problem (MCP-04 half):** single-user app, but `local_tz` is a required
string on six tools, and at least two sessions burned a call just to
establish it.

**Problem (MCP-05 half):** confusion across sessions about `logged_at`
formats; one path (`log_template`) is known to reject naive datetimes today.
Resolving *that* naive datetime requires knowing the effective timezone —
the same value MCP-04 is introducing a fallback for. Doing them separately
risks two different fallback implementations and two different precedence
orders landing in different PRs.

**Scope:**
- Add a server-side default timezone config (env var, e.g. `DEFAULT_LOCAL_TZ`,
  following the existing `.env.example` / Appendix A convention referenced in
  `docs/backlog.md`'s definition of done).
- Introduce **one shared helper**, e.g. `resolve_effective_local_tz(explicit:
  str | None) -> str` in `app/mcp/date_args.py` (alongside the existing
  `resolve_date_arg`), used by every tool and by the `logged_at` handling
  below. Precedence: explicit `local_tz` argument > config default. No second
  copy of this fallback anywhere else.
- Make `local_tz` optional on all six tools that require it today: `log_meal`,
  `log_template`, `get_day`, `get_range`, `set_target`, `get_target` — each
  calls the shared helper before calling `resolve_date_arg`.
- Make `day` (on `get_day`, and `from_date`/`to_date` on `get_range`) default
  to "today" resolved via the same helper, rather than a required argument.
- Confirm `log_meal`'s domain function has the same naive-datetime check as
  `log_template` (`app/domain/templates.py:147-148`) — if missing or
  inconsistent, align them first; divergent behavior between the two entry
  points is its own bug independent of the review.
- **Decision: option (a).** Accept naive `logged_at` and interpret it via
  `resolve_effective_local_tz` — an aware `logged_at` (carries an offset or
  `Z`) is used as-is with no interpretation; a naive `logged_at` is localized
  using the same explicit-`local_tz`-then-config-default precedence as
  everything else in this task. This replaces the current
  `raise ValueError("logged_at must be timezone-aware")` in
  `app/domain/templates.py:147-148` (and the equivalent path in `log_meal`,
  once confirmed) with localization instead of rejection.
  - Both domain functions take `local_tz` already (`log_meal`, `log_template`)
    — no new parameter needed, just change what happens when `logged_at` is
    naive: `datetime.combine`/`.replace(tzinfo=ZoneInfo(local_tz))` (mind DST
    fold/gap edge cases — Python's `zoneinfo` needs `fold` handled explicitly
    for the ambiguous-hour case, or accept the default `fold=0` behavior and
    don't over-engineer it for a single-user app).
  - This is a genuine behavior change, not just a schema tweak — test both
    the previously-passing aware-datetime path (unchanged) and the
    newly-accepted naive path, including one case that crosses a DST
    transition if this timezone observes DST.
- Natural-language forms ("yesterday 20:00") are a bigger lift — scope
  separately if wanted; not required for the core fix.
- Update all six tool descriptions plus `log_meal`/`log_template`'s
  `logged_at` description to state plainly: naive datetimes are interpreted
  in the effective local timezone (explicit `local_tz` or the server
  default); datetimes with an explicit offset are used as given.

#### MCP-06 · Root-cause the `find_food` miss, then close the gap it left
**Problem:** `find_food("get pro yogurt")` and `find_food("getpro yogurt")`
both missed an existing "GetPRO" food, leading to a duplicate `add_food`.

**Existing GH issues this task overlaps/closes:**
[#72](https://github.com/eoinoconn/nutribrain/issues/72) (add `delete_food`
MCP tool) and
[#73](https://github.com/eoinoconn/nutribrain/issues/73) (improve food
search relevance/matching) predate this doc and cover the `delete_food`
wiring and `find_food` root-cause work below — implementing this task should
close both rather than duplicate them.
[#76](https://github.com/eoinoconn/nutribrain/issues/76) tracks the
deferred "refuse `delete_food` on logged history" follow-up (see below).

**Scope:**
- First, reproduce against current code: run `search_foods` with both query
  strings against a food named "GetPRO" (or similar) and confirm whether
  trigram similarity actually falls below `0.35`, or whether the real bug is
  elsewhere (e.g. query stripping, an index/extension not installed in the
  session's environment, `to_regproc("similarity")` returning NULL so it fell
  back to plain substring match). Don't change matching logic before this is
  understood — see verification notes above.
- Only if the trigram fallback is the cause: consider normalizing both sides
  (strip whitespace/punctuation before comparing) as a pre-filter alongside
  the existing similarity check, per the review's suggestion.
- Add `merge_food(session, *, from_id, into_id)` domain function: reassign all
  `meal_items.food_id` from `from_id` to `into_id`, then soft-delete `from_id`
  (reuse `delete_food`'s soft-delete). This matters more than delete alone —
  duplicates get logged against before anyone notices, so a bare
  `delete_food` isn't enough by itself.
- Wire up `delete_food` as an MCP tool (domain function already exists,
  `app/domain/foods.py:177-194` — this part is pure adapter work). Its tool
  description should explicitly point at `merge_food` for the duplicate case
  — e.g. "Soft-delete a food with no logged history. If this food has been
  logged against, use merge_food instead so past meal_items are reassigned
  rather than left pointing at a deleted food." Without that pointer, an
  agent that reaches for `delete_food` to clean up a duplicate (the exact
  GetPRO scenario) has no way to discover `merge_food` exists unless it
  happens to read the full tool list first.
- Wire up `merge_food` as an MCP tool.
- Out of scope for now: making `delete_food` refuse (domain-level error) when
  the food has logged history, forcing `merge_food` for that case instead of
  relying on the tool description. Tracked as a follow-up —
  see GH issue link below.

### P2 — cheap wins, schema and response shape

#### MCP-07 · `find_foods` — batch food search
**Problem:** one session fired nine consecutive `find_food` calls before
logging, because there was no way to resolve several item names in one
round-trip.

**Rejected alternative:** the original review also floated having `log_meal`
resolve food names server-side (accept `name`-only items, auto-attach
`food_id` on a confident match, return a disambiguation error only when
ambiguous). Decided against — `food_id` linkage drives read-time macro
recomputation and historical propagation (`CLAUDE.md`'s mutation rules), so a
*confident-but-wrong* auto-match — exactly what happened with GetPRO — would
silently bind a meal to the wrong food with no checkpoint for the agent to
catch it. A disambiguation error only fires on genuine ambiguity, not on a
wrong-but-confident match. Batch search preserves an agent-visible check
before that binding happens, at no cost to `log_meal`'s existing contract or
the ad-hoc-item invariant.

**Scope:**
- Pure batched read tool: `find_foods(session, *, queries: list[str], limit:
  int = 20) -> list[FindFoodsResult]`, where each result carries the
  originating query alongside its candidates —
  `{"query": "bagel", "candidates": [...]}` — so results stay attributable
  per input item rather than a flattened, ambiguous list. Implementation is a
  loop over the existing `search_foods` per query within one session/
  transaction; no new matching logic.
- MCP tool in `tools_read.py`, response model mirrors `find_food`'s
  `FoodSearchResponse` items, just nested under each query.
- Update `find_food`'s (singular) description to mention `find_foods` for the
  multi-item case, so the agent doesn't default to N sequential singular
  calls out of habit.
- No `docs/decisions.md` entry needed — this doesn't change any mutation
  semantics.

#### MCP-08 · Replace `Decimal` unions with plain `number` in tool schemas
**Problem:** ~40+ fields across `log_meal`, `add_food`, `update_food`,
`create_template`, `update_template` carry Pydantic's default
`anyOf: [number, string]` schema for `Decimal`, at ~60-70 tokens each versus
~10 for a plain `number`, on every single request.

**Scope:**
- Coerce numeric strings to `Decimal` server-side (a `field_validator` or a
  shared `Annotated[Decimal, ...]` type with `json_schema_extra` overriding
  the emitted schema to `{"type": "number"}`) rather than accepting the union.
- Apply the same annotation/validator across `MealItemInput`,
  `TemplateItemInput`, and the numeric parameters of `add_food_tool`,
  `update_food_tool`, `set_target_tool`.
- Verify the resulting JSON schema is exactly `{"type": "number", ...}` per
  field (mirror the check done for verification: dump
  `model_json_schema()` and confirm no `anyOf`).
- Confirm existing tests that pass numeric values as JSON strings (if any)
  still pass, or update them — this is a behavior narrowing, not just a
  schema cosmetic change, if any caller relies on string-typed numeric input.

#### MCP-09 · Make `items[].name` optional when `food_id` is set
**Problem:** `name` is required on every meal/template item even when
`food_id` already identifies the food, which is redundant on every
referenced item.

**Scope:**
- `MealItemInput.name` and `TemplateItemInput.name` (`tools_write.py:52-77`)
  become `str | None = None`.
- Domain layer (`MealItemSpec`/`TemplateItemSpec` construction and the
  `_spec_to_food_id_item`-equivalent paths) must supply a fallback — almost
  certainly the food's current `name` looked up server-side — when `name` is
  omitted and `food_id` is set. Ad-hoc items (`food_id` NULL) still require
  `name`.
- Validate the "food_id set + name omitted" vs. "food_id NULL + name
  required" combination explicitly at the domain layer so the error is clear
  rather than falling through to the CHECK constraint or a null-name row.

#### MCP-11 · Constrain `meal_type` to an enum, document time-based inference, echo it back
**Problem:** `meal_type` is `str | None` on both `log_meal` and
`log_template`; inconsistent acceptance across sessions ("Dinner" reportedly
rejected elsewhere, but "dinner"/"snack"/"pre-workout" all logged fine
somewhere).

**Verified:** `MealType` (`app/db/models.py:56-60`) has exactly four members —
`breakfast`, `lunch`, `dinner`, `snack`. There is no `pre-workout` member, and
`log_template`'s domain code does `MealType(meal_type) if meal_type else None`
(`app/domain/templates.py:157-158`), which raises a `ValueError` — not a clean
domain error — for anything outside those four, case-sensitive (Python's
`StrEnum(...)` constructor is exact-match, so `"Dinner"` fails and `"dinner"`
succeeds, matching the review's report exactly). If `"pre-workout"` really
was logged successfully in some session, it almost certainly went into
`notes`, not `meal_type` — worth confirming against that session's transcript
if available, but don't assume the domain silently accepts arbitrary strings.
- Since the raw `ValueError` on bad input is likely uncaught and surfaces as
  an unhelpful 500-equivalent MCP error today, moving the tool parameter to
  `MealType | None` (below) also fixes error quality, not just documentation.
- Change `log_meal_tool`/`log_template_tool`'s `meal_type` parameter from
  `str | None` to `MealType | None` so FastMCP emits a proper enum schema and
  Pydantic rejects invalid casing/values with a clear error instead of
  whatever `resolve_meal_type` currently does with an unconstrained string.
- Confirm `resolve_meal_type` (`app/domain/meal_timing.py`) already documents
  time-based inference when `meal_type` is omitted; if not, add that to its
  docstring.
- Response (`MealModel.meal_type`) already round-trips the resolved value
  (`serializers.py:68`, type `MealType`) — confirm this is populated with the
  *inferred* value when the caller omitted `meal_type`, not just echoed
  input. If it already is, no change needed there; if not, that's the actual
  gap to fix (the "echo it back" part of this task, distinct from the enum
  typing part).

#### MCP-13 · `list_templates` summary mode
**Problem:** always returns full items; expensive when the caller just needs
id + name to pick one.

**Scope:**
- Add `include_items: bool = False` to `list_templates_tool`.
- Default response: id + name only (new lightweight serializer, or reuse
  `TemplateModel` with `items` omitted/empty depending on how the response
  model is structured — check whether `items` is required on `TemplateModel`
  today and adjust if so).
- `include_items=True` preserves current full-item behavior.

---

## What's already working — don't touch

- Mutation-rule prose baked into tool descriptions (e.g. `update_food`'s "never
  use this to fix one meal entry") — the review confirmed these are
  respected consistently. Preserve this pattern; new tools added above
  (`update_meal`, `update_meal_item`, `copy_meal`, `merge_food`) should follow
  the same convention of stating the boundary rule directly in the tool
  description, not just in this doc.
- `food_id` reuse and read-time macro computation are correct and should not
  be touched by any task above — MCP-01 in particular must preserve the
  CHECK-constraint invariant rather than work around it.

## Suggested sequencing

MCP-01 → MCP-02 → MCP-03 cover the review's "biggest problem" and "second"
items and should land first, each as its own branch/PR per the backlog's
one-task-one-PR convention (`docs/backlog.md`). MCP-04/05 (now one combined
task — effective timezone resolution + `logged_at` handling — see above) is
small and unlocks easier manual testing of everything after it, so pull it
forward if convenient even though it's P1; land it as a single PR, not split
across two. MCP-06 touches the food-resolution/duplicate-handling gap and
overlaps existing GH issues #72/#73, so land it with those in mind — no
`docs/decisions.md` entry needed since the resolved plan (root-cause +
`merge_food`, no `log_meal` contract change) doesn't touch a mutation
invariant. MCP-07 is now a standalone P2 batched-read tool with no
dependencies. MCP-08 through MCP-13 are independent and can be done in any
order, in parallel with the above.

# Live Energy chart — tech spec

**Status:** proposed, not yet built. **Depends on:** current `docs/spec.md` §3, §4, §7, §8 (data model, targets, web dashboard, intervals.icu integration). Read those before starting any task below.

## 1. What we're building and why

A chart on the Today view showing **running net energy balance across the day** — cumulative calories consumed minus cumulative calories expended, plotted against time-of-day — so the user can see at a glance whether they're well-fueled ahead of a scheduled workout. Inspired by Hexis's "Live Energy" chart (`Minute-By-Minute Fuelling Insights`): a solid line from midnight to now, a dashed forecast line from now to end of day, markers at meals and workouts, and an end-of-day predicted-vs-target comparison.

This is a **v1 approximation of Energy Availability (EA)**, not literal EA. True EA (Loucks & Thuma 2003) is `(intake − exercise expenditure) / kg fat-free mass/day`, and is the basis for the IOC's RED-S (Relative Energy Deficiency in Sport) framework. We don't track fat-free mass, so the chart shows raw net kcal balance, not kcal/kg FFM. This is a deliberate, disclosed simplification (see §7 below) — it signals *directional* fueling status, not a clinical EA score.

It's also a proxy for glycogen/carbohydrate status, not a direct measure of it (ACSM/ISSN pre-exercise fueling guidance is carbohydrate-specific, ~1–4 g/kg carb in the 1–4h pre-exercise window). A person can show positive net kcal while being carb-depleted. The chart is a useful first-pass signal, not a substitute for macro-aware planning — this doc doesn't try to fix that; it's noted as a known limitation.

## 2. What already exists vs. what's new

Confirmed by reading the current codebase (not assumed):

| Need | Status |
|---|---|
| Meal timestamp (time-of-day, not just date) | **Exists.** `Meal.logged_at: DateTime(timezone=True)` (`api/app/db/models.py`), populated at log time. |
| Logging a meal for a future time today | **Already works, no new plumbing.** `log_meal()` (`api/app/domain/meal_logging.py`) takes a caller-supplied `logged_at` and only checks tz-awareness — no past/future check anywhere in domain, API schema (`CreateMealRequest`), MCP tool, or the web `MealEditor` form. A meal logged for 18:00 while it's 14:00 now already persists and shows up in `get_day`. |
| Daily kcal target | **Exists**, flat versioned target (`Target.base_calories` + `IntervalsCaloriesOut.calories_out`), no BMR/TDEE field — see `api/app/domain/targets.py`. |
| Per-workout time/duration/calories for **completed** activities | **Missing.** `fetch_activity_calories_by_day` (`api/app/intervals/client.py`) sums same-day activity calories into one number and discards start time, duration, per-activity detail. |
| **Scheduled/future** workouts | **Missing entirely.** Nothing in the codebase fetches or stores planned/upcoming training. |
| Charting library | **Available, unused.** `recharts` is already a `web/package.json` dependency; no chart component exists yet in `web/src`. |

So the two real gaps are: (a) per-activity detail for completed workouts, and (b) a source of scheduled/future workouts. Both come from the same fix: stop summing intervals.icu activities into a daily total, and start fetching and storing individual events/activities with time, duration, and calories — including intervals.icu's **planned events** (their calendar/events endpoint), not just completed activities.

## 3. Data model changes

### New table: `planned_workouts`

Replaces the "sum calories per day" model with per-workout rows carrying enough detail to place a marker on a time axis and distribute its expenditure over its duration.

```
planned_workouts
  id                  serial primary key
  external_id         text            -- intervals.icu event/activity id, unique per source
  source              enum('intervals_planned', 'intervals_completed', 'manual')
  local_date          date not null   -- for cheap day-grouping, same convention as meals.local_date
  start_at            timestamptz not null   -- null start times are not usable for this feature; reject/skip
  duration_minutes    int not null
  sport_type          text            -- intervals.icu `type` (Ride/Run/Swim/...); nullable for manual rows
  icu_joules            int           -- intervals.icu's own computed work estimate; requires
                                       -- structured targets + configured zones, often absent
                                       -- on unstructured placeholder events
  estimated_calories  int             -- planned rows only; see "Workout calorie estimation" below
  actual_calories     int             -- completed rows: the same device-reported calories field
                                       -- `_extract_activity_calories` already reads today, just kept
                                       -- per-activity instead of summed. Not a new sourcing mechanism.
  status              enum('planned', 'completed')
  fetched_at          timestamptz not null
```

- Unique constraint on `(source, external_id)` so re-syncing upserts rather than duplicates.
- Index on `local_date`.
- A `manual` source row lets a user hand-enter "I'm training at 6pm for ~45min, ~400kcal" when there's no intervals.icu event (this is the fallback path — see §6 open question on scope).
- This table is **additive** relative to `intervals_calories_out`'s cache-row *shape*, but see "Reconciling calories-out" below — `intervals_calories_out.calories_out` becomes *derived from* this table rather than independently synced, to remove a source of disagreement between the target panel and the energy chart.

### Workout calorie estimation

This only applies to **planned** rows — `actual_calories` on a **completed** row is sourced exactly as it is today: the existing `_extract_activity_calories` (`api/app/intervals/client.py:143-146`) already reads a device-reported `calories`/`Calories`/`kcal` field off completed activities, which is how `calories_out` gets populated in production right now. `fetch_activities_detailed` (§4) doesn't change that sourcing — it just keeps per-activity duration/load/timestamp alongside the same calories field instead of discarding them into a same-day sum.

A **planned** event, having no device upload yet (nothing has happened), never carries a calories value — confirmed against intervals.icu's documented API schema. But intervals.icu itself *does* compute a server-side work estimate for a planned event when it has real structure: `icu_joules`, computed from the event's structured power/pace/HR targets, is stored on the calendar event object and retrievable from `/api/v1/athlete/{id}/events` — **but only when the event has target structure (power/pace + duration) and the athlete's zones are configured**, confirmed via intervals.icu staff forum posts. A vague "Run — 45 min" placeholder with no structure gets no `icu_joules`.

**Simplified v1 approach (no personal-ratio calibration, no MET tables):**

- **`icu_joules` present → flat conversion.** `estimated_calories = round(icu_joules / 1000 * KCAL_PER_KILOJOULE)`, where `KCAL_PER_KILOJOULE = 1.1` is one frozen domain constant in `api/app/domain/energy_balance.py`, not scattered magic numbers. This value was checked against three of this athlete's own completed rides (pulled live via the intervals.icu MCP during spec review) by computing `calories ÷ (avg_power_w × moving_time_s / 1000)` for each: 1.17, 0.96, and 1.23 kcal/kJ (outdoor rides with elevation gain ran higher, an indoor trainer session closest to the textbook ~1.0 gross-efficiency figure). `1.1` splits that observed range and the literature's ~1.0–1.05 convention (Strava/Garmin/TrainingPeaks all treat kcal≈kJ as a first-order approximation) without over-fitting to three data points. No per-athlete calibration, no historical-data dependency, no minimum-sample-size logic — one constant, revisit only if real usage shows it's off.
- **`icu_joules` absent → the workout isn't placed on the chart at all.** No step, no marker, `estimated_calories` stays null. An unstructured placeholder event ("Run — 45 min" with no target) isn't a fueling-relevant plan — there's nothing to be fueled *for* yet, so it's simply excluded rather than guessed at via training-load ratios or MET tables. The row still syncs and is still stored (so it can later flip to `completed` with real device calories once the workout happens), it just contributes nothing to `compute_energy_timeline` while `status='planned'` and `icu_joules` is null.

This replaces the earlier three-tier personal-ratio design entirely — no `training_load`, `intensity`, or `avg_watts` columns are needed, and `estimate_workout_calories` is now a single arithmetic function with no session/historical-data argument.

Recalibrate the personal ratios at read time (a query, not a stored coefficient) so they drift naturally as fitness/efficiency changes over a training block — consistent with this codebase's read-time-computation philosophy elsewhere (no snapshotting). Do not build a generic power-based `kcal ≈ kJ` formula as the primary method; only reach for it inside tier 1 when a personal power/calorie ratio is unavailable, and even then, prefer the load-based personal ratio (tier 2) over an unscaled textbook conversion.

### Alembic migration
One new migration adding `planned_workouts` and its enums. Follow the existing convention in `api/migrations` (native Postgres enums, explicit down-migration). Do not touch `intervals_calories_out` or any merged migration.

## 4. intervals.icu client changes

`api/app/intervals/client.py` currently has one function, `fetch_activity_calories_by_day`, hitting `/api/v1/athlete/{id}/activities` (completed only) and collapsing to a daily sum. Add, don't replace:

- `fetch_activities_detailed(oldest, newest) -> list[ActivityDetail]` — same endpoint, but keep `start_date_local`, `moving_time`/`elapsed_time` (duration), `type` (sport), and `calories` per activity instead of summing them away. Feeds `planned_workouts` rows with `status='completed'`.
- `fetch_planned_events(oldest, newest) -> list[PlannedEventDetail]` — intervals.icu's **events** endpoint (`/api/v1/athlete/{id}/events`), which returns calendar entries including future planned workouts, each with a start time, an estimated moving time, sport type, and — only when the event has structured power/pace/HR targets and the athlete's zones are configured — `icu_joules`. Commonly absent on an unstructured placeholder event; the client passes it through as null rather than requiring it. Feeds `planned_workouts` rows with `status='planned'`.
- Same retry/timeout/error-handling shape as the existing function (bounded retries, `IntervalsUnavailableError` on failure, recorded-fixture tests, never live API in tests) — don't invent a new failure pattern.
- `fetch_activity_calories_by_day` stays as-is for now (untouched by EC-01 through EC-07) — it's retired in EC-08 once `get_effective_target` is repointed at `planned_workouts` (see "Reconciling calories-out" below). Don't remove it before then.

## 5. Domain layer

New module `api/app/domain/energy_balance.py`. Domain function, no FastAPI/FastMCP/SQLAlchemy-session-management imports beyond the injected session (per `api/CLAUDE.md`):

```
compute_energy_timeline(session, *, day: date, now: datetime) -> EnergyTimeline
```

Returns a DTO (add to `api/app/domain/dto.py`) shaped roughly as:

```
EnergyTimeline:
  points: list[EnergyPoint]       # solid line, local_date's midnight -> now
  forecast_points: list[EnergyPoint]  # dashed line, now -> local end of day
  events: list[EnergyEvent]       # markers: each meal (logged_at, delta_kcal, "meal"), each planned_workout (start_at, delta_kcal, "workout", status)
  current_balance: int            # net kcal balance right now
  predicted_end_of_day: int
  end_of_day_target: int          # from get_effective_target — reuse existing function, don't recompute
  fueling_flags: list[FuelingFlag]  # see §6
```

**Algorithm (step function, per product decision — see §8 open questions resolved):**

1. Basal drain: `base_calories` from the effective target, divided by 1440, applied as a constant per-minute rate from local midnight onward. (No diurnal curve, no TEF modeling in v1 — the research brief flags these as low-value refinements not worth v1 complexity.)
2. At each `meal.logged_at`, step the cumulative line up by that meal's total kcal (sum of its `meal_item`s' read-time-computed macros — reuse `get_day`'s existing item-macro computation, don't recompute macros in a second place).
3. At each `planned_workouts` row's `start_at`, step the cumulative line down by `actual_calories` (if `status='completed'`) or `estimated_calories` (if `status='planned'` **and** `estimated_calories` is not null), as an instant step at `start_at` — **not** distributed over `duration_minutes`. (Literal step function, matching Hexis's reference visual — product decision, see §8.)
   - **No `icu_joules` → no step at all.** A `planned` row with `estimated_calories` still null (its source event had no structured targets, so intervals.icu never computed `icu_joules`) is skipped entirely — no line step, no chart marker, no fueling flag. It isn't a fueling-relevant plan yet.
   - **Grace period for skipped workouts:** a `planned` row (never confirmed completed by sync) only counts toward the line for **4 hours past its `start_at`**. Once `now > start_at + 4h` and the row is still `status='planned'`, drop its step from both the solid line (if `start_at` has already passed) and the "so far" total — treat it as skipped rather than silently keeping a phantom deficit from a workout that likely didn't happen. If the next sync later confirms it completed, the row flips to `status='completed'` with `actual_calories`, and starts counting again as an ordinary past step. This only matters for `start_at` values in the past; a future `planned` row on the dashed line is unaffected until its own `start_at + 4h` arrives.
4. Solid line = steps 1–3 evaluated from local midnight up to `now`.
5. Dashed line = steps 1–3 continued from `now` to local end-of-day, where:
   - basal drain keeps accruing at the same constant rate,
   - any **already-logged future meal** (a meal with `logged_at > now` on this `local_date` — confirmed possible today, §2) is included as a known step, not assumed away,
   - any **planned** `planned_workouts` row with `start_at > now` is included as a known step,
   - **no other future intake is assumed** — the forecast's default is "if you eat nothing else beyond what you've already logged," per the research brief's recommendation to favor the conservative/safety framing over a historical-average guess. Do not build a rolling-average predictor in v1.
6. `predicted_end_of_day` = the final value of the dashed line at local 23:59.
7. `end_of_day_target` = `get_effective_target(session, day=day).effective_calories`, reusing the existing function — do not recompute target logic here.

### Fueling indicator

For each `planned_workouts` row with `status='planned'` and `start_at` in the future, evaluate the cumulative balance **at `start_at`** (i.e., a point already on the dashed line) and classify:

- `well_fueled`: balance at that point **> 0**
- `under_fueled`: balance at that point **≤ 0**

(Starting deliberately with a strict `> 0` cutoff and no positive buffer for v1 — sports-nutrition guidance would likely want some margin before a hard session, but that's a tuning question best answered once real usage data exists, not guessed upfront.)

No finer-grained thresholds in v1 (e.g. no "moderately under-fueled" tier) — two states, categorical, matching the research brief's steer away from a raw-deficit display. Surface this as `fueling_flags: [{workout_id, at: start_at, status: 'well_fueled' | 'under_fueled'}]` so the frontend can render a badge on the workout marker, not a numeric deficit callout.

**Framing constraint (carries through to frontend, §7):** never render this as a bare negative number described as an achievement or a streak. Categorical language only (`"Fueled"` / `"Consider eating before this session"`), consistent with RED-S-aware design guidance — this app has exactly one user and no clinical oversight, so it must not read as a diagnostic score.

## 6. Sync changes

Extend `api/app/domain/intervals_sync.py`'s `sync_intervals` (or add a sibling function called from the same triggers — cron, manual "sync now" button, MCP `sync_intervals` tool) to also call `fetch_activities_detailed` and `fetch_planned_events`, upserting into `planned_workouts` keyed on `(source, external_id)`, capturing `sport_type` and `icu_joules` alongside the existing fields, and setting `estimated_calories = round(icu_joules / 1000 * 1.1)` on any `planned` row where `icu_joules` is present (left null otherwise).

This adds exactly one additional upstream call per sync run (`/events`, for planned items) — `fetch_activities_detailed` reuses the same `/activities` call the existing sync already makes, it just stops discarding per-activity fields into a sum. Not an N+1 against intervals.icu; sync goes from one call to two per run, not one-per-activity.

Manual fallback: a lightweight "plan a workout" input (start time + estimated kcal, `source='manual'`) for days without an intervals.icu event, so the fueling indicator isn't hard-blocked on intervals.icu having the session scheduled. Small form, not a full workout editor.

### Reconciling calories-out (single source of truth)

Today, `IntervalsCaloriesOut.calories_out` is populated by a separate sync path (`fetch_activity_calories_by_day`, a same-day sum) and can also be set by a manual override. Once `planned_workouts` exists, having two independently-synced calorie-out numbers feeding two different UI surfaces (the target-panel breakdown vs. this chart) is a real inconsistency risk. Resolve it as a single source of truth rather than reconciling two pipelines after the fact:

- `get_effective_target` (`api/app/domain/targets.py`) computes `calories_out` for a day as `sum(planned_workouts.actual_calories where status='completed' and local_date=day)` at read time, **unless** a manual override row exists for that day in `intervals_calories_out` (`source='manual'`), which still wins — preserves the existing "manual override always beats sync" behavior, just changes what it's overriding.
- `fetch_activity_calories_by_day` and the old daily-sum sync path are retired once `fetch_activities_detailed` covers the same completed-activity data with more detail — this doesn't add API calls (see above), it removes the redundant client-side summing path.
- This means the target panel's "calories out" and the energy chart's workout total are now, by construction, the same number for any given day. No separate reconciliation logic needed anywhere else.

## 6a. Account-level timezone setting

`SettingsPage.tsx:210-211` already has a timezone-override UI, but it's explicitly localStorage-only today — the component's own comment notes "no backend field exists yet to persist a timezone override," and there is no settings/account table in the schema at all (`api/app/db/models.py` has none). The energy chart needs a durable "whose midnight is this" answer for days with no meals logged yet (a day with only a target set has no `Meal.local_tz` to borrow from), so this becomes a real dependency, not a nice-to-have:

- New singleton table `app_settings` (single-user app, no `user_id`, so this is a one-row table — id fixed at 1 or enforced via a check constraint): `local_timezone: text not null default 'UTC'`.
- `GET /api/settings` / `PATCH /api/settings` routes, thin adapters over a small `app/domain/settings.py`.
- `SettingsPage.tsx` repointed to read/write this instead of `localStorage`; keep the browser-timezone default for the initial value shown before the user has set anything.
- `compute_energy_timeline` reads this for its local-midnight/end-of-day bounds on any day lacking a logged meal to infer tz from.

## 7. HTTP API

New route: `GET /api/day/{date}/energy` (or fold into the existing `GET /api/day/{date}` payload as an `energy` key — prefer folding it in, since the Today view already fetches `get_day` once per date and a second round trip just for this chart adds a waterfall for no reason). Calls `compute_energy_timeline`. No business logic in the route — translate DTO to JSON only, per `api/CLAUDE.md`.

## 8. Frontend

New component `web/src/components/EnergyChart.tsx`, built on `recharts` (already a dependency — this is the first chart built with it in this app, so keep the recharts usage conventional: a `LineChart` with two `Line`s sharing an x-axis, one solid (`strokeDasharray` unset) for the "so far" segment and one dashed (`strokeDasharray="4 4"`) for the forecast segment, a `ReferenceLine` at `x = now` labeled "Live Energy: {current_balance}", scatter markers (recharts `Scatter` or custom dot renderer) for meal/workout events, and a `ReferenceLine` or annotation for the fueling badge at any future planned-workout marker.

Slots into `DayView.tsx` as its own `<section>` between `SummaryRow` and the action buttons (per the codebase exploration — that's the natural gap; it also reads sensibly directly under the existing calorie-ring/macro summary). Gate it behind `isToday` initially — a "live" chart makes less sense on a past/future date route (`/day/:date`); revisit once the design is validated.

Must follow existing conventions: TanStack Query (`queryKeys.day(localDate)` already covers this if energy is folded into `get_day`'s payload — no new query key needed), skeleton while loading, empty state if no target is set for the day (mirrors existing `SummaryRow` handling), and the accessibility floor from `web/CLAUDE.md` — the chart needs a text-equivalent summary beneath it (current balance, predicted EOD vs target, fueling status in words), consistent with the accessibility floor already applied to Trends (`docs/spec.md` §7).

## 9. Explicitly out of scope for v1

- True EA (kcal/kg fat-free mass) — no body-composition tracking exists or is being added for this feature.
- Macro-aware (carbohydrate-specific) fueling status — net kcal only.
- Diurnal BMR curve or thermic-effect-of-food modeling — flat basal rate.
- Smoothing meal/workout steps over a digestion/duration window — literal step function, per product decision.
- Historical-average intake forecasting — zero-further-intake assumption only.
- Non-intervals.icu workout sources (Garmin, manual free-text) beyond the small manual planned-workout fallback form in §6.
- A configurable fueling-threshold buffer (e.g. requiring +100 kcal margin, not just >0) — start at a strict `>0` cutoff (§5) and revisit once real usage data exists.
- Personal per-athlete kJ→kcal calibration or MET-table fallback for planned workouts — v1 uses one flat `KCAL_PER_KILOJOULE` constant and skips the chart entirely for unstructured events (see "Workout calorie estimation" above). Revisit only if the flat constant proves visibly wrong in practice.
- **Making `KCAL_PER_KILOJOULE` user-configurable.** `1.1` is a single-sample-athlete estimate (three of your own rides) sitting inside a literature range of ~1.0–1.05 for a *generic* athlete, so it's a reasonable default but not something to treat as fixed forever — different athletes' real gross efficiency varies, and this app has exactly one user who could just measure their own drift over time. File a GitHub issue tracking a future settings field (`app_settings.kcal_per_kilojoule`, alongside the timezone field from §6a) rather than building it now — v1 ships with the hardcoded constant; see EC-11 below.

---

# Task list

Follow the existing backlog conventions in `docs/backlog.md`: one task = one branch = one PR, tests ship with the code, domain logic only in `app/domain/`, never edit a merged migration.

## EC-01 · `planned_workouts` table and migration
**Depends:** — **Spec:** §3 above
Add the SQLAlchemy model (enums for `source`, `status`), the unique constraint on `(source, external_id)`, the `local_date` index, and a new Alembic migration with a working downgrade. No domain logic yet.
**Done when:** `alembic upgrade head` / `downgrade -1` both run clean and a duplicate `(source, external_id)` upsert test passes against the constraint.

## EC-02 · intervals.icu client: per-activity detail + planned events
**Depends:** EC-01 **Spec:** §4 above
Add `fetch_activities_detailed` and `fetch_planned_events` to `api/app/intervals/client.py`, same retry/timeout/error shape as the existing function, tests against recorded fixtures (never the live API). Do not modify `fetch_activity_calories_by_day`.
**Done when:** both functions have fixture-backed tests covering a normal payload, an empty payload, and an upstream failure.

## EC-03 · Sync: populate `planned_workouts`, estimate calories
**Depends:** EC-02 **Spec:** §6, "Workout calorie estimation" above
Extend the sync path to upsert `planned_workouts` rows from both new client functions, keyed on `(source, external_id)`, capturing `sport_type` and `icu_joules`. For any `planned` row where `icu_joules` is present, set `estimated_calories = round(icu_joules / 1000 * 1.1)` (the flat `KCAL_PER_KILOJOULE` constant — a one-line function, no historical-data lookup); leave it null otherwise. Wire into the same triggers (cron, manual sync route, MCP `sync_intervals` tool). Do **not** yet touch `intervals_calories_out` or retire the old sync path — that's EC-07.
**Done when:** a test proves a re-sync upserts rather than duplicates, that a previously-`planned` row flips to `status='completed'` with `actual_calories` set once intervals.icu reports it as done, and that a planned event with no `icu_joules` gets a null `estimated_calories` rather than a guessed one.

## EC-04 · Manual planned-workout fallback
**Depends:** EC-01 **Spec:** §6 above
Small domain function + API route + minimal web form to hand-enter a `source='manual'` planned workout (start time, estimated kcal) for a day. Parallel with EC-02/EC-03.
**Done when:** a manually-entered row shows up in the same read path as a synced one.

## EC-05 · `compute_energy_timeline` domain function
**Depends:** EC-01, EC-03 **Spec:** §5 above
Implement the step-function algorithm exactly as specified: basal drain from effective target, meal steps from `get_day`'s existing macro computation (don't recompute macros in a second place), workout steps from `planned_workouts` (`actual_calories` for completed, `estimated_calories` for planned), **excluding any `planned` row where `estimated_calories` is null** (no `icu_joules` → no step, no marker — not fueling-relevant), the 4-hour grace period dropping a still-`planned` row's step once `now > start_at + 4h`, solid/dashed split at `now`, future-logged-meals and future-planned-workouts included in the forecast, zero-further-intake otherwise, fueling flag at `>0` (well-fueled) vs `≤0` (under-fueled). Add the `EnergyTimeline`/`EnergyPoint`/`EnergyEvent`/`FuelingFlag` DTOs to `api/app/domain/dto.py`.
**Done when:** tests cover: a day with no meals/workouts (flat basal line), a day with a past meal and a past workout (correct solid-line steps), a day with a future-logged meal and a future-planned workout (correct dashed-line steps, not assumed-zero), a `planned` row past its 4-hour grace window with no completion (dropped from the total), a `planned` row with null `estimated_calories` (excluded entirely, no marker), and the fueling-flag classification at a future workout's `start_at` for a `>0` and a `≤0` balance case.

## EC-06 · Account-level timezone setting
**Depends:** — **Spec:** §6a above
New `app_settings` singleton table + migration, `app/domain/settings.py`, `GET/PATCH /api/settings` routes, `SettingsPage.tsx` repointed from `localStorage` to these routes (keep browser-timezone as the shown default before anything is set). Independent of the rest of this feature — can run in parallel with everything else.
**Done when:** setting the timezone via the API persists across a page reload and a second browser/session sees the same value.

## EC-07 · Reconcile `intervals_calories_out` onto `planned_workouts` (single source of truth)
**Depends:** EC-03 **Spec:** "Reconciling calories-out" above
Change `get_effective_target` to compute `calories_out` as `sum(planned_workouts.actual_calories where status='completed' and local_date=day)`, falling back to an existing manual-override row in `intervals_calories_out` exactly as today when one exists. Retire `fetch_activity_calories_by_day` and its sync call once this is live.
**Done when:** the existing targets test suite is updated to source its fixtures from `planned_workouts` instead of `intervals_calories_out` sync rows, a manual override still wins, and `fetch_activity_calories_by_day` has no remaining callers.

## EC-08 · Fold `energy` into `get_day` (or new route)
**Depends:** EC-05 **Spec:** §7 above
Wire `compute_energy_timeline` into the `GET /api/day/{date}` response (preferred) or a new `GET /api/day/{date}/energy` route if folding proves awkward — route/schema only, no logic.
**Done when:** the existing day-route test suite gains one happy-path assertion for the new payload shape and one error-path (no target set) assertion.

## EC-09 · `EnergyChart` component
**Depends:** EC-08 **Spec:** §8 above
Build the recharts-based chart: solid + dashed `Line`s, `now` `ReferenceLine`, event markers, fueling badge, text-equivalent summary beneath for accessibility. Standalone component with its own tests (state/data-shape logic per `docs/style.md`'s "frontend gets tests for state logic, not chart rendering" rule) before wiring into `DayView.tsx`.
**Done when:** component tests cover the loading/empty/populated states and the fueling-badge rendering for both flag values.

## EC-10 · Wire into `DayView`
**Depends:** EC-09, EC-06 **Spec:** §8 above
Slot `EnergyChart` between `SummaryRow` and the action buttons, gated on `isToday`. Manually exercise it in a running dev server against real logged data before calling this done (per the "test the golden path in a browser" rule) — screenshot-check it looks like the Hexis reference at a coarse level (solid-to-dashed transition, markers, badge).
**Done when:** manually verified in-browser on today's date with at least one past meal, one past workout, and one future-planned workout present.

## EC-11 · File a GitHub issue: configurable `KCAL_PER_KILOJOULE`
**Depends:** EC-03 **Spec:** out-of-scope list above
Not a code task — no branch/PR. Once EC-03 lands the hardcoded `1.1` constant, open a GitHub issue documenting: the constant's current value and where it lives (`api/app/domain/energy_balance.py`), how it was derived (three of this athlete's own completed rides, checked against the literature's ~1.0–1.05 range), and the proposed future shape (a `kcal_per_kilojoule` field on the `app_settings` table from EC-06, editable from `SettingsPage.tsx` alongside the timezone override). Link it from this spec doc once filed.
**Done when:** the issue exists and is linked here.

---

## Parallelization map

| Wave | Tasks |
|---|---|
| 1 | EC-01, EC-06 |
| 2 | EC-02, EC-04 |
| 3 | EC-03 |
| 4 | EC-05, EC-07, EC-11 |
| 5 | EC-08 |
| 6 | EC-09 |
| 7 | EC-10 |

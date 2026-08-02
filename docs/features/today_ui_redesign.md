# Nutrition Tracker — Day View UI Redesign Spec

**Scope:** This spec covers the **Day view** (currently split across `TodayPage.tsx` and `DayPage.tsx`) only. Other pages — Trends, Calendar, Foods, Templates, Targets, Settings — are not covered here, with the exception of the sidebar and color scheme, which are app-wide and affect every page.

Reference mockup: `nutrition-ui-redesign.html`

**Current implementation (for grounding):**
- `web/src/pages/TodayPage.tsx` — today only, no date navigation, no edit/delete.
- `web/src/pages/DayPage.tsx` — `/day/:date`, supports edit/delete on meals/items and a manual calories-out override, but has no prev/next date navigation.
- Both duplicate the same JSX; the shared presentational pieces (`CalorieProgress` ring, `MacroBars`, `MicroRow`, `DayHeader`) live in `web/src/components/DaySummary.tsx`.
- Both fetch a single payload via `getDay(date)` → `GET /api/day/{date}`. Meal items already include per-item macros (`MealItem.macros: ItemMacros`) — no new endpoint fields are needed for this redesign.
- `web/src/App.tsx` has a flat top-level `<nav>`; no sidebar component exists yet.
- No CSS-variable theme file exists; styling is ad hoc Tailwind slate/sky classes, plus a separate WCAG-verified `adherence` color token set in `tailwind.config.ts` (in-target/near/outside/no-log) used elsewhere in the app.

## 0. Page Consolidation (foundational — do first)

**Change:** Merge `TodayPage.tsx` and `DayPage.tsx` into a single component that renders any date with full parity. This is required by §3 (date picker) and resolves the "read-only vs. editable" open question below: **all dates are fully editable, same as today.**

- New/renamed component (e.g. `DayView.tsx`) handles both the `/` route (redirects to or renders today's `local_date`) and `/day/:date`.
- All actions available on today's data must be available on any date: log a meal, log macros (§4), edit/delete meal items, manual calories-out override.
- Delete the now-duplicate `TodayPage.tsx`/`DayPage.tsx` JSX once merged; reuse `DaySummary.tsx` pieces and `MealEditor/` as-is.

**Tasks**
- [ ] Create merged day-view component/route handling both `/` and `/day/:date`
- [ ] Port manual calories-out override (currently `DayPage`-only) so it works for every date
- [ ] Port meal/meal-item edit and delete (currently `DayPage`-only) so it works for every date
- [ ] Remove duplicated JSX between the old `TodayPage` and `DayPage`
- [ ] Update routing/links app-wide that pointed at the old separate pages

## 1. Navigation (app-wide)

**Change:** Move primary nav from a top bar (`App.tsx`'s flat `<nav>`) to a collapsible left sidebar. This is a net-new component — no sidebar exists today.

- Sidebar is fixed-width, full height, sits left of all page content.
- Items: Today, Trends, Calendar, Foods, Templates, Targets, Settings.
- Active page is visually distinguished (highlighted background + accent-colored left border).
- **Collapsible:** a toggle control collapses the sidebar to a narrow icon-only rail, giving the day view more horizontal space. Expanding restores labels.
- Collapsed/expanded state persists across page loads and navigation (localStorage).
- **Mobile breakpoint:** below Tailwind's `md` (768px), collapse to a horizontal scrollable bar (top) rather than a permanent sidebar — reuses the project's existing breakpoint convention rather than introducing a new one.

**Tasks**
- [ ] Build new `Sidebar.tsx`, replacing the `<nav>` in `App.tsx`
- [ ] Add active-route highlighting (based on current router path)
- [ ] Add collapse/expand toggle control
- [ ] Add icon-only collapsed state (icons for each nav item, labels hidden)
- [ ] Persist collapsed/expanded state in localStorage across sessions
- [ ] Ensure main content area reflows to fill space when sidebar collapses
- [ ] Add `md:` responsive variant that collapses sidebar to horizontal bar below 768px

## 2. Summary Row — Ring + Macros (day view)

**Change:** Reposition the calorie ring and macro bars into a single horizontal row instead of stacked full-width sections. This is a layout-only change — `CalorieProgress`, `MacroBars`, and `MicroRow` already exist in `DaySummary.tsx` and already receive the data they need; no data-fetching changes required here.

- Calorie ring sits on the left.
- Protein / Carbs / Fat bars stack vertically to the right of the ring, each full-width within that column.
- Fiber / Sat fat / Sodium micro-stats (`MicroRow`) remain below the macro bars.
- Row wraps to stacked layout on narrow screens (`md:` breakpoint, consistent with §1).

**Tasks**
- [ ] Rebuild summary section in `DaySummary.tsx` as a flex row: ring (fixed width) + macro column (flexible width)
- [ ] Ensure macro bars scale to fill available width in their column
- [ ] Add wrap/stack behavior below `md`

## 3. Date Picker (day view)

**Change:** Add date navigation so the day view can show, and fully edit, any date. Depends on §0 (page consolidation).

- Prev/next arrow buttons step one day at a time (based on `local_date`, matching the timezone semantics already used by `Meal.local_date`).
- Native date input allows jumping directly to any date.
- Page header (title, target line, ring, macros, meal list) all re-render for the selected date, sourced from `getDay(date)`.
- Selected date is reflected in the URL (`/day/:date`) so it's bookmarkable/shareable and browser back/forward works.
- No restriction on how far back or forward the date can go (matches "editable same as today" decision — there is no read-only mode to gate against).

**Tasks**
- [ ] Add date picker component to page header (prev arrow, date input, next arrow)
- [ ] Wire arrows to increment/decrement selected date and push a new `/day/:date` route
- [ ] Wire date input `onChange` to update the route/selected date
- [ ] Fetch/render day summary + meal list keyed off the route's date param
- [ ] Update page title ("Today — YYYY-MM-DD" when date is today, otherwise weekday name + date, e.g. "Wednesday — 2026-07-29") to reflect selected date

## 4. Actions Row (day view)

**Change:** Add a second action button, "Log macros," for quick macro-only entry.

- Buttons: **Log a meal** (primary, opens existing `MealEditor`), **Log macros** (secondary, new), **Sync intervals now** (secondary, existing).
- **"Log macros" behavior (resolved):** opens a lightweight form that creates a single ad-hoc `meal_item` (`food_id` NULL) with directly-entered macros — calories, protein_g, carbs_g, fat_g, and optionally fiber_g/sat_fat_g/sodium_mg. No food search/lookup. This is the same "ad-hoc item" case already defined in the project's mutation rules (editing its macros later only affects that one meal_item, per CLAUDE.md).
- The quick-entry form needs a `meal_type` and `logged_at`: default `meal_type` to `snack` and `logged_at` to now, both editable inline before saving, consistent with how `MealEditor` handles timing today.
- Available on any date via §0, not just today.

**Tasks**
- [ ] Build a new lightweight "Log macros" form component (separate from `MealEditor`, no food search)
- [ ] Fields: calories, protein_g, carbs_g, fat_g (required); fiber_g, sat_fat_g, sodium_mg (optional)
- [ ] Default `meal_type=snack`, `logged_at=now`, both editable before save
- [ ] Wire submit to create a meal with a single ad-hoc `meal_item` (`food_id` NULL)
- [ ] Add "Log macros" button between "Log a meal" and "Sync intervals now"

## 5. Meal List — Ordering & Content (day view)

**Change:** List logged meals in chronological order (by `logged_at`), not grouped under meal-type section headers. Multiple entries of the same meal type (e.g. two snacks) are already supported by the data model (no uniqueness constraint on `(local_date, meal_type)`) and are already fetched as separate `DayMealGroup`s — this is a **display-only** change: remove the `MEAL_TYPE_ORDER` grouping/headers and render one flat list sorted by `loggedAt` ascending.

- Each meal row shows: logged time, meal name/type, total calories, and the three macro totals (P/C/F) for that meal.

**Tasks**
- [ ] Replace meal-type-grouped rendering with a flat list sorted by `loggedAt` ascending
- [ ] Remove now-unused `MEAL_TYPE_ORDER` section-header rendering (keep `MEAL_TYPE_LABELS` for the per-row type label)
- [ ] Add logged time to each meal row's display
- [ ] Compute and display per-meal macro totals (P/C/F) alongside calories (sum of item macros already present in the payload)

## 6. Meal List — Expandable Detail (day view)

**Change:** Clicking a meal row expands it to show the individual foods logged within that meal. Per-item macros (`MealItem.macros`) are already included in the `getDay` payload — **no new fetch is needed**, this is purely a render-state change.

- Each food line shows: food name, quantity/unit, per-food macros (P/C/F), and per-food calories.
- Expand/collapse is per-row (multiple rows can be open at once, independent local state).
- Chevron indicator rotates/changes state to reflect open/closed.
- Row is keyboard-operable (see Accessibility below).

**Tasks**
- [ ] Add per-row expanded/collapsed local state (e.g. `Set<mealId>` of open rows)
- [ ] Render expanded food list under the meal row when open, using already-fetched `item.macros`
- [ ] Add chevron/indicator with open/closed visual state
- [ ] Ensure the row toggle is reachable via keyboard (Enter/Space), not just `onClick`

## 7. Color Scheme (app-wide)

**Change:** Replace the current ad hoc slate/sky Tailwind classes with an orange-on-grey token set.

- Background: dark neutral grey (not navy-tinted).
- Accent color (progress ring, bars, active nav state, primary button, highlights): orange.
- Text: off-white primary, grey secondary/tertiary tones.
- The existing `adherence` token set (`in-target`/`near`/`outside`/`no-log` in `tailwind.config.ts`) is a **separate semantic system** used elsewhere (e.g. Calendar heatmap) and must be preserved — do not let the new orange accent collide with or overload its meaning. Check whether orange is already used by `adherence` for any state; if so, resolve the conflict explicitly (e.g. pick a different accent, or confirm the two systems are never visible side-by-side).

**Tasks**
- [ ] Add new color tokens (background, panel, border, text tiers, accent) to `tailwind.config.ts`
- [ ] Verify contrast/accessibility of new orange accent against grey backgrounds (same WCAG bar used for the existing `adherence` tokens)
- [ ] Check the new tokens don't collide semantically with existing `adherence` tokens; resolve if they do
- [ ] Replace ad hoc slate/sky Tailwind classes in `DaySummary.tsx`, the merged day-view page, and `MealEditor/` with the new tokens
- [ ] Sweep other pages using the same shared components (nav, buttons) to confirm they pick up new tokens rather than hardcoded old colors

## 8. Empty, Loading, and Error States (day view)

Not covered by the mockup; needed for a real implementation.

- **Empty day:** no meals logged for the selected date — show a distinct empty state under "Logged today, in order" (e.g. "Nothing logged for this day yet") rather than an empty list with just the section label.
- **Loading:** date navigation (prev/next/date-input) triggers a new fetch — define a loading state for the summary row + meal list while `getDay(date)` is in flight (e.g. skeleton or dimmed previous content), so navigating dates doesn't flash a blank page.
- **Error:** `getDay(date)` failure (network/5xx) needs a visible error state with a retry action, not a silent blank page.

**Tasks**
- [ ] Add empty-state UI for a day with zero meals
- [ ] Add loading state for summary + meal list during date-change fetches
- [ ] Add error state with retry for failed `getDay` fetches

## 9. Accessibility

- Sidebar collapse toggle and nav items must be reachable and operable via keyboard, with visible focus states.
- Meal row expand/collapse (§6) must be keyboard-operable and expose expanded/collapsed state to assistive tech (e.g. `aria-expanded` on the row, not just a rotated chevron).
- Date input and prev/next buttons need accessible labels (`aria-label="Previous day"` / `"Next day"`).
- New orange accent must meet WCAG contrast against the new grey backgrounds for both text and non-text UI (ring, bars) — folded into the §7 contrast check.

**Tasks**
- [ ] Add `aria-expanded`/`aria-controls` to meal row toggles
- [ ] Add `aria-label`s to date-picker prev/next buttons
- [ ] Verify sidebar and meal-list keyboard navigation and focus visibility

---

## Resolved decisions

- **"Log macros" behavior:** quick macro-only entry, creates an ad-hoc `meal_item` (`food_id` NULL). See §4.
- **Past/future date editability:** fully editable, identical to today. See §0.
- **Mobile sidebar breakpoint:** Tailwind's default `md` (768px), no custom value. See §1.

## Out of scope
- Trends, Calendar, Foods, Templates, Targets, Settings page redesigns (future work).
- Changing the `MealType` enum (still breakfast/lunch/dinner/snack; no new "other"/custom type).
- Any change to how macros are computed (read-time computation rule is unaffected by this redesign).

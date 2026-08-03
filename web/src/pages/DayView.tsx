/**
 * Merged day view (§0-1 of docs/features/today_ui_redesign.md): renders any
 * date with full parity, replacing the former split between `TodayPage.tsx`
 * (today only, read/log only) and `DayPage.tsx` (`/day/:date`, full
 * edit/delete/override). Handles both routes:
 *   - `/`         — no route param; resolves to today's `local_date`.
 *   - `/day/:date` — route param drives the fetched/displayed date.
 *
 * Same layout for every date — reuses the shared header/calorie-ring/
 * macro-bars/micro-row pieces from `../components/DaySummary` and the
 * `MealEditor` (T-073) for logging new meals — plus every logged item is
 * editable and deletable, whole meals are deletable, and there is a manual
 * "set calories out" override input (§8) for days Intervals/Garmin never
 * synced.
 *
 * This component only reads and displays already-computed backend output
 * and issues the existing typed endpoints; it does not compute macro
 * totals, propagation, or target logic itself (CLAUDE.md).
 *
 * NOTE: this intentionally duplicates logic that used to live in
 * `TodayPage.tsx`/`DayPage.tsx`. Deleting those now-superseded files and
 * repointing other app-wide links is a separate follow-up task.
 */

import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMeal,
  createPlannedWorkout,
  deleteMeal,
  deleteMealItem,
  getDay,
  setManualCaloriesOut,
  syncIntervals
} from "../lib/api/client";
import { queryKeys } from "../lib/queryClient";
import { useToast } from "../design/useToast";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import type { DayMealGroup, DayResponse, MealItemRequest, MealType } from "../lib/api/types";
import { MealEditor, MealItemRow, type MealEditorItem, type MealEditorValue } from "../components/MealEditor";
import { QuickMacroEntry, type QuickMacroValue } from "../components/QuickMacroEntry";
import { PlannedWorkoutForm, type PlannedWorkoutValue } from "../components/PlannedWorkoutForm";
import EnergyChart from "../components/EnergyChart";
import { DayHeader, MEAL_TYPE_LABELS, SummaryRow, formatCalories, formatGrams } from "../components/DaySummary";
import {
  buildCreateMealRequest,
  buildCreatePlannedWorkoutRequest,
  buildQuickMacroRequest,
  mealEditorItemToRequest,
  mealItemToEditorItem
} from "../lib/mealForms";
import { addDays, dayTitleLabel } from "../lib/dateNav";

/** Best-effort key only; the header's displayed date always comes from the
 * API response's `date` field (docs/style.md), never this. */
function todayLocalDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** `YYYY-MM-DD`, matching the `/day/:date` route param shape. */
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

interface EditItemVars {
  itemId: number;
  mealType: MealType;
  loggedAt: string;
  request: MealItemRequest;
}

export default function DayView(): JSX.Element {
  const { date: routeDate } = useParams<{ date: string }>();
  // `/` has no `:date` param at all; `/day/:date` supplies one. Either way we
  // resolve to a concrete YYYY-MM-DD before querying.
  const localDate = routeDate ?? todayLocalDate();
  const isValidDate = DATE_PATTERN.test(localDate);

  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const navigate = useNavigate();

  // Arrows/date-input never mutate `localDate` in place — they push a new
  // `/day/:date` route (spec §3: bookmarkable, back/forward works). The
  // route param then drives the query above on the next render.
  function handleStepDay(deltaDays: number): void {
    void navigate(`/day/${addDays(localDate, deltaDays)}`);
  }

  function handleDateChange(nextDate: string): void {
    void navigate(`/day/${nextDate}`);
  }

  const dayQuery = useQuery({
    queryKey: queryKeys.day(localDate),
    queryFn: () => getDay(localDate),
    enabled: isValidDate,
    // §8: date-picker navigation (prev/next/date-input) fetches a new
    // `['day', date]` key on every step. Without this, each step would drop
    // back into `isLoading` (no cached data for the new key yet) and swap
    // the whole page for the generic first-paint skeleton below — losing
    // the date-picker controls themselves mid-navigation and causing a
    // layout jump. Keeping the previous date's data on screen (dimmed, via
    // `isRefetching` below) while the new fetch is in flight avoids both.
    placeholderData: keepPreviousData
  });

  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorValue, setEditorValue] = useState<MealEditorValue | null>(null);
  // Independent of `isEditorOpen`/`editorValue` (the `MealEditor` panel's
  // state) — "Log macros" is a separate lightweight panel that can be open
  // on its own, per §4 of docs/features/today_ui_redesign.md.
  const [isQuickMacroOpen, setIsQuickMacroOpen] = useState(false);
  const [quickMacroValue, setQuickMacroValue] = useState<QuickMacroValue | null>(null);
  // Independent of the meal-entry panels — "plan a workout" (EC-04, §6) is a
  // manual fallback for days without an intervals.icu event, unrelated to
  // logging food, so opening it doesn't close (and isn't closed by) either.
  const [isPlannedWorkoutOpen, setIsPlannedWorkoutOpen] = useState(false);
  const [plannedWorkoutValue, setPlannedWorkoutValue] = useState<PlannedWorkoutValue | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editingItemValue, setEditingItemValue] = useState<MealEditorItem | null>(null);
  const [manualCaloriesOut, setManualCaloriesOutInput] = useState<string>("");
  // Independent of the editor/quick-macro panels above — it's a distinct
  // kind of action (an occasional override, not another meal-entry path),
  // so opening it doesn't close, and isn't closed by, either of those.
  const [isCaloriesOutOpen, setIsCaloriesOutOpen] = useState(false);

  // Prefill the override input with whatever calories-out already applies to
  // this day so re-opening the page shows the current value, not a blank
  // box. Only resyncs when the date or the fetched value itself changes, so
  // it never clobbers the operator mid-edit.
  useEffect(() => {
    setManualCaloriesOutInput(
      dayQuery.data?.effectiveTarget?.caloriesOut != null ? String(dayQuery.data.effectiveTarget.caloriesOut) : ""
    );
  }, [dayQuery.data?.date, dayQuery.data?.effectiveTarget?.caloriesOut]);

  const logMealMutation = useMutation({
    mutationFn: (payload: ReturnType<typeof buildCreateMealRequest>) =>
      createMeal(payload as NonNullable<ReturnType<typeof buildCreateMealRequest>>),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.day(localDate) });
      const previous = queryClient.getQueryData<DayResponse>(queryKeys.day(localDate));
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.day(localDate), context.previous);
      }
      showToast("Could not log meal.", "error");
    },
    onSuccess: () => {
      showToast("Meal logged.", "success");
      setIsEditorOpen(false);
      setEditorValue(null);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  const logMacrosMutation = useMutation({
    mutationFn: (payload: NonNullable<ReturnType<typeof buildQuickMacroRequest>>) => createMeal(payload),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.day(localDate) });
      const previous = queryClient.getQueryData<DayResponse>(queryKeys.day(localDate));
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.day(localDate), context.previous);
      }
      showToast("Could not log macros.", "error");
    },
    onSuccess: () => {
      showToast("Macros logged.", "success");
      setIsQuickMacroOpen(false);
      setQuickMacroValue(null);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  const createPlannedWorkoutMutation = useMutation({
    mutationFn: (payload: NonNullable<ReturnType<typeof buildCreatePlannedWorkoutRequest>>) =>
      createPlannedWorkout(payload),
    onError: () => {
      showToast("Could not save planned workout.", "error");
    },
    onSuccess: () => {
      showToast("Workout planned.", "success");
      setIsPlannedWorkoutOpen(false);
      setPlannedWorkoutValue(null);
    }
    // No `onSettled` invalidation: no read path in this app queries
    // `planned_workouts` yet (EC-05, not built) — nothing on this page
    // displays the new row today, so there's nothing to refetch.
  });

  const syncMutation = useMutation({
    mutationFn: () => syncIntervals(),
    onError: () => {
      showToast("Sync failed.", "error");
    },
    onSuccess: () => {
      showToast("Synced with Intervals.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  const deleteMealMutation = useMutation({
    mutationFn: (mealId: number) => deleteMeal(mealId),
    onMutate: async (mealId: number) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.day(localDate) });
      const previous = queryClient.getQueryData<DayResponse>(queryKeys.day(localDate));
      if (previous) {
        const nextMeals: DayResponse["meals"] = {};
        for (const [mealType, groups] of Object.entries(previous.meals)) {
          nextMeals[mealType] = groups.filter((group) => group.id !== mealId);
        }
        queryClient.setQueryData(queryKeys.day(localDate), { ...previous, meals: nextMeals });
      }
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.day(localDate), context.previous);
      }
      showToast("Could not delete meal.", "error");
    },
    onSuccess: () => {
      showToast("Meal deleted.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  const deleteMealItemMutation = useMutation({
    mutationFn: (itemId: number) => deleteMealItem(itemId),
    onMutate: async (itemId: number) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.day(localDate) });
      const previous = queryClient.getQueryData<DayResponse>(queryKeys.day(localDate));
      if (previous) {
        const nextMeals: DayResponse["meals"] = {};
        for (const [mealType, groups] of Object.entries(previous.meals)) {
          nextMeals[mealType] = groups
            .map((group) => ({ ...group, items: group.items.filter((item) => item.id !== itemId) }))
            .filter((group) => group.items.length > 0);
        }
        queryClient.setQueryData(queryKeys.day(localDate), { ...previous, meals: nextMeals });
      }
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.day(localDate), context.previous);
      }
      showToast("Could not delete item.", "error");
    },
    onSuccess: () => {
      showToast("Item deleted.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  // No `update_meal_item` exists (docs/spec.md: "delete + relog is fine at
  // v1 scale"), so an edit is delete-old-item + create-a-new-single-item
  // meal carrying the original meal's type/time. That new item lands as its
  // own meal group rather than merging back into the old one — an accepted
  // v1 limitation, not a bug. We don't attempt an optimistic patch of the
  // edited values (computing resulting macros/grouping client-side would be
  // domain logic); we cancel in-flight fetches and roll back the snapshot
  // on failure, then let the settle-time invalidation fetch the true state.
  const editMealItemMutation = useMutation({
    mutationFn: async (vars: EditItemVars) => {
      await deleteMealItem(vars.itemId);
      return createMeal({
        items: [vars.request],
        loggedAt: vars.loggedAt,
        localTz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        mealType: vars.mealType
      });
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.day(localDate) });
      const previous = queryClient.getQueryData<DayResponse>(queryKeys.day(localDate));
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.day(localDate), context.previous);
      }
      showToast("Could not update item.", "error");
    },
    onSuccess: () => {
      showToast("Item updated.", "success");
      setEditingItemId(null);
      setEditingItemValue(null);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  const manualOverrideMutation = useMutation({
    mutationFn: (caloriesOut: number) => setManualCaloriesOut({ date: localDate, caloriesOut }),
    onError: () => {
      showToast("Could not save calories-out override.", "error");
    },
    onSuccess: () => {
      showToast("Calories-out override saved.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(localDate) });
    }
  });

  function handleToggleEditor(): void {
    setIsEditorOpen((open) => {
      const next = !open;
      if (next) {
        setIsQuickMacroOpen(false);
      }
      return next;
    });
  }

  function handleSubmitMeal(): void {
    if (!editorValue) {
      return;
    }
    const request = buildCreateMealRequest(editorValue, dayQuery.data?.date ?? localDate);
    if (!request) {
      showToast("Add at least one item before saving.", "error");
      return;
    }
    logMealMutation.mutate(request);
  }

  function handleToggleCaloriesOut(): void {
    setIsCaloriesOutOpen((open) => !open);
  }

  function handleToggleQuickMacro(): void {
    setIsQuickMacroOpen((open) => {
      const next = !open;
      if (next) {
        setIsEditorOpen(false);
      }
      return next;
    });
  }

  function handleSubmitQuickMacro(): void {
    // `quickMacroValue` is null until the form's `onChange` first fires
    // (mirrors `MealEditor`'s `onChange`-reports-up pattern) — treat an
    // untouched form the same as one missing required fields.
    const request = quickMacroValue ? buildQuickMacroRequest(quickMacroValue, dayQuery.data?.date ?? localDate) : null;
    if (!request) {
      showToast("Enter calories, protein, carbs, and fat before saving.", "error");
      return;
    }
    logMacrosMutation.mutate(request);
  }

  function handleTogglePlannedWorkout(): void {
    setIsPlannedWorkoutOpen((open) => !open);
  }

  function handleSubmitPlannedWorkout(): void {
    const request = plannedWorkoutValue
      ? buildCreatePlannedWorkoutRequest(plannedWorkoutValue, dayQuery.data?.date ?? localDate)
      : null;
    if (!request) {
      showToast("Enter estimated calories before saving.", "error");
      return;
    }
    createPlannedWorkoutMutation.mutate(request);
  }

  // The row toggle below is a native `<button>`, so Enter/Space already
  // activate it via the browser's default keyboard handling — no extra
  // `onKeyDown` wiring needed (same pattern as the editor/quick-macro
  // toggle buttons above).
  function toggleGroup(mealId: number): void {
    setExpanded((current) => ({ ...current, [mealId]: !current[mealId] }));
  }

  function handleStartEditItem(itemId: number, current: MealEditorItem): void {
    setEditingItemId(itemId);
    setEditingItemValue(current);
  }

  function handleCancelEditItem(): void {
    setEditingItemId(null);
    setEditingItemValue(null);
  }

  function handleSaveEditItem(mealType: MealType, loggedAt: string): void {
    if (editingItemId === null || !editingItemValue) {
      return;
    }
    const request = mealEditorItemToRequest(editingItemValue);
    if (!request) {
      showToast("Enter a quantity greater than zero.", "error");
      return;
    }
    editMealItemMutation.mutate({ itemId: editingItemId, mealType, loggedAt, request });
  }

  function handleSubmitOverride(event: FormEvent): void {
    event.preventDefault();
    const trimmed = manualCaloriesOut.trim();
    const parsed = Number(trimmed);
    if (trimmed === "" || Number.isNaN(parsed) || parsed < 0) {
      showToast("Enter a non-negative number of calories.", "error");
      return;
    }
    manualOverrideMutation.mutate(Math.round(parsed));
  }

  if (!isValidDate) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Day detail</h1>
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          &quot;{localDate}&quot; isn&apos;t a valid date (expected YYYY-MM-DD).
        </p>
      </section>
    );
  }

  if (dayQuery.isLoading) {
    return (
      <section className="space-y-6">
        <Skeleton className="h-8 w-64" label="Loading day summary" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
      </section>
    );
  }

  if (dayQuery.isError || !dayQuery.data) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Day detail &mdash; {localDate}</h1>
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load this day&apos;s data.
        </p>
        <button
          type="button"
          onClick={() => void dayQuery.refetch()}
          className="focus-ring rounded-md border border-line px-3 py-2 text-sm font-medium hover:bg-canvas dark:border-line-dark dark:hover:bg-panel-dark"
        >
          Retry
        </button>
      </section>
    );
  }

  const day = dayQuery.data;
  // §5: one flat, chronological list of meal *instances* (each
  // `DayMealGroup`), not grouped under meal-type section headers. Multiple
  // entries of the same meal type (e.g. two snacks) each get their own row.
  const flatMealGroups = (Object.entries(day.meals) as [MealType, DayMealGroup[]][])
    .flatMap(([mealType, groups]) => (groups ?? []).map((group) => ({ mealType, group })))
    .sort((a, b) => new Date(a.group.loggedAt).getTime() - new Date(b.group.loggedAt).getTime());
  const hasMeals = flatMealGroups.length > 0;
  const isToday = day.date === todayLocalDate();
  const title = dayTitleLabel(day.date, todayLocalDate());
  // True only for a background refetch of an *already-displayed* date (e.g.
  // stepping to a new date via the picker, which keeps rendering the
  // previous date's data per `placeholderData: keepPreviousData` above) —
  // not the first-paint case, which is handled by the `isLoading` branch
  // above and never reaches here. Dim the body rather than swap it out so
  // the date-picker/header stay stable and interactive during navigation.
  const isRefetching = dayQuery.isFetching && !dayQuery.isLoading;

  return (
    <section className="space-y-8">
      <DayHeader
        day={day}
        title={title}
        onPrevDay={() => handleStepDay(-1)}
        onNextDay={() => handleStepDay(1)}
        onDateChange={handleDateChange}
        caloriesOutToggle={
          <button
            type="button"
            onClick={handleToggleCaloriesOut}
            aria-expanded={isCaloriesOutOpen}
            aria-controls="calories-out-panel"
            className="focus-ring shrink-0 rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-canvas dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
          >
            {isCaloriesOutOpen ? "Close" : "Calories out"}
          </button>
        }
        caloriesOutPanel={
          isCaloriesOutOpen ? (
            <div id="calories-out-panel">
              <ManualCaloriesOutForm
                value={manualCaloriesOut}
                onChange={setManualCaloriesOutInput}
                onSubmit={handleSubmitOverride}
                isPending={manualOverrideMutation.isPending}
                currentCaloriesOut={day.effectiveTarget?.caloriesOut ?? null}
              />
            </div>
          ) : null
        }
      />

      {isRefetching ? (
        <p className="flex items-center gap-2 text-xs text-ink-tertiary dark:text-ink-secondary-dark">
          <Skeleton className="h-2 w-2 rounded-full" label="Updating for selected date" />
          <span aria-hidden="true">Updating&hellip;</span>
        </p>
      ) : null}

      <div aria-busy={isRefetching} className={`space-y-8 transition-opacity ${isRefetching ? "opacity-50" : "opacity-100"}`}>
        <SummaryRow totals={day.dayTotals} target={day.effectiveTarget} />

        <section aria-labelledby="live-energy-heading" className="space-y-3">
          <h2 id="live-energy-heading" className="text-lg font-semibold">
            {isToday ? "Live Energy" : "Energy Balance"}
          </h2>
          <EnergyChart energy={day.energy} isLoading={dayQuery.isLoading} isToday={isToday} />
        </section>

        <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleToggleEditor}
          aria-expanded={isEditorOpen}
          className="focus-ring rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent dark:bg-accent-dark dark:text-ink-primary dark:hover:bg-accent-dark"
        >
          {isEditorOpen ? "Cancel" : "Log a meal"}
        </button>
        <button
          type="button"
          onClick={handleToggleQuickMacro}
          aria-expanded={isQuickMacroOpen}
          className="focus-ring rounded-md border border-line px-4 py-2 text-sm font-medium hover:bg-canvas dark:border-line-dark dark:hover:bg-panel-dark"
        >
          {isQuickMacroOpen ? "Cancel" : "Log macros"}
        </button>
        <button
          type="button"
          onClick={handleTogglePlannedWorkout}
          aria-expanded={isPlannedWorkoutOpen}
          className="focus-ring rounded-md border border-line px-4 py-2 text-sm font-medium hover:bg-canvas dark:border-line-dark dark:hover:bg-panel-dark"
        >
          {isPlannedWorkoutOpen ? "Cancel" : "Plan a workout"}
        </button>
        {isToday ? (
          <button
            type="button"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="focus-ring rounded-md border border-line px-4 py-2 text-sm font-medium hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:hover:bg-panel-dark"
          >
            {syncMutation.isPending ? "Syncing..." : "Sync intervals now"}
          </button>
        ) : null}
      </div>

      {isEditorOpen ? (
        <div className="space-y-4 rounded-lg border border-line p-4 dark:border-line-dark">
          <MealEditor onChange={setEditorValue} />
          <button
            type="button"
            onClick={handleSubmitMeal}
            disabled={logMealMutation.isPending}
            className="focus-ring rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent dark:bg-accent-dark dark:text-ink-primary dark:hover:bg-accent-dark disabled:opacity-50"
          >
            {logMealMutation.isPending ? "Saving..." : "Save meal"}
          </button>
        </div>
      ) : null}

      {isQuickMacroOpen ? (
        <div className="space-y-4 rounded-lg border border-line p-4 dark:border-line-dark">
          <QuickMacroEntry onChange={setQuickMacroValue} />
          <button
            type="button"
            onClick={handleSubmitQuickMacro}
            disabled={logMacrosMutation.isPending}
            className="focus-ring rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent dark:bg-accent-dark dark:text-ink-primary dark:hover:bg-accent-dark disabled:opacity-50"
          >
            {logMacrosMutation.isPending ? "Saving..." : "Save macros"}
          </button>
        </div>
      ) : null}

      {isPlannedWorkoutOpen ? (
        <div className="space-y-4 rounded-lg border border-line p-4 dark:border-line-dark">
          <PlannedWorkoutForm onChange={setPlannedWorkoutValue} />
          <button
            type="button"
            onClick={handleSubmitPlannedWorkout}
            disabled={createPlannedWorkoutMutation.isPending}
            className="focus-ring rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent dark:bg-accent-dark dark:text-ink-primary dark:hover:bg-accent-dark disabled:opacity-50"
          >
            {createPlannedWorkoutMutation.isPending ? "Saving..." : "Save planned workout"}
          </button>
        </div>
      ) : null}

      {hasMeals ? (
        <div className="space-y-3">
          {flatMealGroups.map(({ mealType, group }) => {
            const isOpen = expanded[group.id] ?? false;
            const panelId = `meal-items-panel-${group.id}`;
            return (
              <div key={group.id} className="rounded-lg border border-line dark:border-line-dark">
                <div className="flex items-center gap-2 px-4 py-3">
                  <button
                    type="button"
                    onClick={() => toggleGroup(group.id)}
                    aria-expanded={isOpen}
                    aria-controls={panelId}
                    className="focus-ring flex flex-1 flex-wrap items-center justify-between gap-x-4 gap-y-1 text-left"
                  >
                    <span className="flex items-center gap-3">
                      <span className="text-xs font-medium uppercase tracking-wide text-ink-tertiary dark:text-ink-tertiary-dark">
                        {new Date(group.loggedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="font-medium">{MEAL_TYPE_LABELS[mealType] ?? mealType}</span>
                    </span>
                    <span className="flex items-center gap-4 text-sm text-ink-tertiary dark:text-ink-secondary-dark">
                      <span className="font-medium text-accent dark:text-accent-dark">
                        {formatCalories(group.totals.calories)} cal
                      </span>
                      <span>P {formatGrams(group.totals.proteinG)}g</span>
                      <span>C {formatGrams(group.totals.carbsG)}g</span>
                      <span>F {formatGrams(group.totals.fatG)}g</span>
                      <span
                        aria-hidden="true"
                        className={`inline-block transition-transform ${isOpen ? "rotate-90 text-accent" : "text-ink-secondary-dark"}`}
                      >
                        &#8250;
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMealMutation.mutate(group.id)}
                    disabled={deleteMealMutation.isPending}
                    className="focus-ring shrink-0 rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
                  >
                    Delete meal
                  </button>
                </div>
                {isOpen ? (
                  <div id={panelId} className="space-y-2 border-t border-line px-4 py-3 dark:border-line-dark">
                    <ul className="space-y-2 text-sm">
                      {group.items.map((item) => (
                        <li key={item.id} className="space-y-2">
                          {editingItemId === item.id && editingItemValue ? (
                            <div className="space-y-2 rounded-md border border-accent-dark p-3 dark:border-accent">
                              <MealItemRow
                                item={editingItemValue}
                                index={0}
                                canRemove={false}
                                onChange={setEditingItemValue}
                                onRemove={() => undefined}
                              />
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  onClick={() => handleSaveEditItem(mealType, group.loggedAt)}
                                  disabled={editMealItemMutation.isPending}
                                  className="focus-ring rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent dark:bg-accent-dark dark:text-ink-primary dark:hover:bg-accent-dark disabled:opacity-50"
                                >
                                  {editMealItemMutation.isPending ? "Saving..." : "Save item"}
                                </button>
                                <button
                                  type="button"
                                  onClick={handleCancelEditItem}
                                  className="focus-ring rounded-md border border-line px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-canvas dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                              <span className="flex items-baseline gap-2">
                                <span>{item.name}</span>
                                <span className="text-xs text-ink-tertiary dark:text-ink-secondary-dark">
                                  {formatGrams(item.quantity)} {item.quantityUnit}
                                </span>
                              </span>
                              <div className="flex items-center gap-3">
                                <span className="text-xs text-ink-tertiary dark:text-ink-secondary-dark">
                                  P {formatGrams(item.macros.proteinG)}g
                                </span>
                                <span className="text-xs text-ink-tertiary dark:text-ink-secondary-dark">
                                  C {formatGrams(item.macros.carbsG)}g
                                </span>
                                <span className="text-xs text-ink-tertiary dark:text-ink-secondary-dark">
                                  F {formatGrams(item.macros.fatG)}g
                                </span>
                                <span className="text-ink-tertiary dark:text-ink-secondary-dark">
                                  {formatCalories(item.macros.calories)} cal
                                </span>
                                <button
                                  type="button"
                                  onClick={() => handleStartEditItem(item.id, mealItemToEditorItem(item))}
                                  className="focus-ring rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-canvas dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
                                >
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  onClick={() => deleteMealItemMutation.mutate(item.id)}
                                  disabled={deleteMealItemMutation.isPending}
                                  className="focus-ring rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
                                >
                                  Delete
                                </button>
                              </div>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState
          message={isToday ? "no meals logged today" : "no meals logged this day"}
          nudge="tell Claude, or use the button"
          action={{ label: "Log a meal", onClick: handleToggleEditor }}
        />
      )}
      </div>
    </section>
  );
}

function ManualCaloriesOutForm({
  value,
  onChange,
  onSubmit,
  isPending,
  currentCaloriesOut
}: {
  value: string;
  onChange: (next: string) => void;
  onSubmit: (event: FormEvent) => void;
  isPending: boolean;
  currentCaloriesOut: number | null;
}): JSX.Element {
  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label="Manual calories-out override"
      className="space-y-2 rounded-lg border border-line p-4 dark:border-line-dark"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="manual-calories-out" className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
            Calories out (manual)
          </label>
          <input
            id="manual-calories-out"
            type="number"
            inputMode="numeric"
            min={0}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="focus-ring w-32 rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
        </div>
        <button
          type="submit"
          disabled={isPending}
          className="focus-ring rounded-md border border-line px-4 py-2 text-sm font-medium hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:hover:bg-panel-dark"
        >
          {isPending ? "Saving..." : "Set"}
        </button>
      </div>
      <p className="text-xs text-ink-tertiary dark:text-ink-secondary-dark">
        {currentCaloriesOut !== null
          ? `Current: ${formatCalories(currentCaloriesOut)} cal. Use this only when Intervals/Garmin didn't sync for this day — the next real sync overwrites it.`
          : "Use this only when Intervals/Garmin didn't sync for this day — the next real sync overwrites it."}
      </p>
    </form>
  );
}

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
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMeal,
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
import type { DayResponse, MealItemRequest, MealType } from "../lib/api/types";
import { MealEditor, MealItemRow, type MealEditorItem, type MealEditorValue } from "../components/MealEditor";
import {
  CalorieProgress,
  DayHeader,
  MEAL_TYPE_LABELS,
  MEAL_TYPE_ORDER,
  MacroBars,
  MicroRow,
  formatCalories
} from "../components/DaySummary";
import { buildCreateMealRequest, mealEditorItemToRequest, mealItemToEditorItem } from "../lib/mealForms";

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

  const dayQuery = useQuery({
    queryKey: queryKeys.day(localDate),
    queryFn: () => getDay(localDate),
    enabled: isValidDate
  });

  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorValue, setEditorValue] = useState<MealEditorValue | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [editingItemId, setEditingItemId] = useState<number | null>(null);
  const [editingItemValue, setEditingItemValue] = useState<MealEditorItem | null>(null);
  const [manualCaloriesOut, setManualCaloriesOutInput] = useState<string>("");

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
    setIsEditorOpen((open) => !open);
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

  function toggleGroup(key: string): void {
    setExpanded((current) => ({ ...current, [key]: !current[key] }));
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
          className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Retry
        </button>
      </section>
    );
  }

  const day = dayQuery.data;
  const mealTypeKeys = Object.keys(day.meals) as MealType[];
  const orderedMealTypes = [
    ...MEAL_TYPE_ORDER.filter((type) => mealTypeKeys.includes(type)),
    ...mealTypeKeys.filter((type) => !MEAL_TYPE_ORDER.includes(type))
  ];
  const hasMeals = orderedMealTypes.some((type) => (day.meals[type]?.length ?? 0) > 0);
  const isToday = day.date === todayLocalDate();

  return (
    <section className="space-y-8">
      <DayHeader day={day} title={isToday ? "Today" : "Day detail"} />

      <CalorieProgress totals={day.dayTotals} target={day.effectiveTarget} />

      <MacroBars totals={day.dayTotals} target={day.effectiveTarget} />

      <MicroRow totals={day.dayTotals} />

      <ManualCaloriesOutForm
        value={manualCaloriesOut}
        onChange={setManualCaloriesOutInput}
        onSubmit={handleSubmitOverride}
        isPending={manualOverrideMutation.isPending}
        currentCaloriesOut={day.effectiveTarget?.caloriesOut ?? null}
      />

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleToggleEditor}
          aria-expanded={isEditorOpen}
          className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700"
        >
          {isEditorOpen ? "Cancel" : "Log a meal"}
        </button>
        {isToday ? (
          <button
            type="button"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="focus-ring rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            {syncMutation.isPending ? "Syncing..." : "Sync intervals now"}
          </button>
        ) : null}
      </div>

      {isEditorOpen ? (
        <div className="space-y-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <MealEditor onChange={setEditorValue} />
          <button
            type="button"
            onClick={handleSubmitMeal}
            disabled={logMealMutation.isPending}
            className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {logMealMutation.isPending ? "Saving..." : "Save meal"}
          </button>
        </div>
      ) : null}

      {hasMeals ? (
        <div className="space-y-3">
          {orderedMealTypes.map((mealType) => {
            const groups = day.meals[mealType] ?? [];
            if (groups.length === 0) {
              return null;
            }
            const isOpen = expanded[mealType] ?? false;
            return (
              <div key={mealType} className="rounded-lg border border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => toggleGroup(mealType)}
                  aria-expanded={isOpen}
                  className="focus-ring flex w-full items-center justify-between px-4 py-3 text-left font-medium"
                >
                  <span>{MEAL_TYPE_LABELS[mealType] ?? mealType}</span>
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    {formatCalories(groups.reduce((sum, g) => sum + g.totals.calories, 0))} cal
                  </span>
                </button>
                {isOpen ? (
                  <div className="space-y-4 border-t border-slate-200 px-4 py-3 dark:border-slate-800">
                    {groups.map((group) => (
                      <div key={group.id} className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-500">
                            {new Date(group.loggedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </span>
                          <button
                            type="button"
                            onClick={() => deleteMealMutation.mutate(group.id)}
                            disabled={deleteMealMutation.isPending}
                            className="focus-ring rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                          >
                            Delete meal
                          </button>
                        </div>
                        <ul className="space-y-2 text-sm">
                          {group.items.map((item) => (
                            <li key={item.id} className="space-y-2">
                              {editingItemId === item.id && editingItemValue ? (
                                <div className="space-y-2 rounded-md border border-sky-300 p-3 dark:border-sky-700">
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
                                      className="focus-ring rounded-md bg-sky-600 px-3 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
                                    >
                                      {editMealItemMutation.isPending ? "Saving..." : "Save item"}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={handleCancelEditItem}
                                      className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <div className="flex items-center justify-between gap-4">
                                  <span>{item.name}</span>
                                  <div className="flex items-center gap-3">
                                    <span className="text-slate-500 dark:text-slate-400">
                                      {formatCalories(item.macros.calories)} cal
                                    </span>
                                    <button
                                      type="button"
                                      onClick={() => handleStartEditItem(item.id, mealItemToEditorItem(item))}
                                      className="focus-ring rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                                    >
                                      Edit
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => deleteMealItemMutation.mutate(item.id)}
                                      disabled={deleteMealItemMutation.isPending}
                                      className="focus-ring rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
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
                    ))}
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
      className="space-y-2 rounded-lg border border-slate-200 p-4 dark:border-slate-800"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="manual-calories-out" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Calories out (manual)
          </label>
          <input
            id="manual-calories-out"
            type="number"
            inputMode="numeric"
            min={0}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="focus-ring w-32 rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <button
          type="submit"
          disabled={isPending}
          className="focus-ring rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {isPending ? "Saving..." : "Set"}
        </button>
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        {currentCaloriesOut !== null
          ? `Current: ${formatCalories(currentCaloriesOut)} cal. Use this only when Intervals/Garmin didn't sync for this day — the next real sync overwrites it.`
          : "Use this only when Intervals/Garmin didn't sync for this day — the next real sync overwrites it."}
      </p>
    </form>
  );
}

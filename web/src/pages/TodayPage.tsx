/**
 * Today view (T-074, spec §7): the dashboard's home route.
 *
 * Fetches `GET /api/day/{date}` for today's local date and renders:
 * header (date + effective target breakdown), a calorie progress
 * visualization with a text summary, three prominent macro bars
 * (protein/carbs/fat), a muted micro row (fiber/sat fat/sodium), a meal
 * list grouped by `meal_type` (expandable), a "Log a meal" button that
 * opens the standalone `MealEditor` (T-073) inline, and a "Sync intervals
 * now" button.
 *
 * This component only reads and displays already-computed backend output
 * (CLAUDE.md: no business logic in UI components) — it does not compute
 * macro totals, propagation, or target logic itself.
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createMeal, getDay, syncIntervals } from "../lib/api/client";
import { queryKeys } from "../lib/queryClient";
import { useToast } from "../design/useToast";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import type { CreateMealRequest, DayResponse, ItemMacros, MealItemRequest, MealType } from "../lib/api/types";
import { MealEditor, type MealEditorValue } from "../components/MealEditor";

function todayLocalDate(): string {
  // Best-effort initial fetch key only; the header's displayed date always
  // comes from the API response's `date` field (docs/style.md), never this.
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatGrams(value: number): string {
  return value.toFixed(1);
}

const MEAL_TYPE_ORDER: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

const MEAL_TYPE_LABELS: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack"
};

function mealEditorItemToRequest(item: MealEditorValue["items"][number]): MealItemRequest | null {
  if (item.quantity === null || item.quantity <= 0) {
    return null;
  }
  return {
    name: item.name,
    quantity: item.quantity,
    quantityUnit: item.quantityUnit,
    foodId: item.isAdHoc ? null : item.foodId,
    calories: item.isAdHoc ? item.calories : null,
    proteinG: item.isAdHoc ? item.proteinG : null,
    carbsG: item.isAdHoc ? item.carbsG : null,
    fatG: item.isAdHoc ? item.fatG : null,
    fiberG: item.isAdHoc ? item.fiberG : null,
    satFatG: item.isAdHoc ? item.satFatG : null,
    sodiumMg: item.isAdHoc ? item.sodiumMg : null
  };
}

/**
 * Builds a timezone-aware ISO datetime from a `MealEditorValue.time`
 * (`HH:mm`) and the current day. `POST /api/meals` rejects a naive
 * datetime (backend domain layer requires tz-awareness) — constructing a
 * `Date` from local components and reading back `toISOString()` gives a
 * `Z`-suffixed UTC instant that correctly accounts for the browser's
 * offset (and DST) for that date, rather than string-concatenating an
 * offset-less timestamp.
 */
function buildLoggedAt(localDate: string, time: string): string {
  const [year = 0, month = 1, day = 1] = localDate.split("-").map(Number);
  const [hours = 0, minutes = 0] = time.split(":").map(Number);
  return new Date(year, month - 1, day, hours, minutes, 0).toISOString();
}

export default function TodayPage(): JSX.Element {
  const localDate = useMemo(() => todayLocalDate(), []);
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const dayQuery = useQuery({
    queryKey: queryKeys.day(localDate),
    queryFn: () => getDay(localDate)
  });

  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorValue, setEditorValue] = useState<MealEditorValue | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const logMealMutation = useMutation({
    mutationFn: (payload: CreateMealRequest) => createMeal(payload),
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

  function handleToggleEditor(): void {
    setIsEditorOpen((open) => !open);
  }

  function handleSubmitMeal(): void {
    if (!editorValue) {
      return;
    }
    const items = editorValue.items
      .map(mealEditorItemToRequest)
      .filter((item): item is MealItemRequest => item !== null);
    if (items.length === 0) {
      showToast("Add at least one item before saving.", "error");
      return;
    }
    const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    logMealMutation.mutate({
      items,
      loggedAt: buildLoggedAt(dayQuery.data?.date ?? localDate, editorValue.time),
      localTz,
      mealType: editorValue.mealType
    });
  }

  function toggleGroup(key: string): void {
    setExpanded((current) => ({ ...current, [key]: !current[key] }));
  }

  if (dayQuery.isLoading) {
    return (
      <section className="space-y-6">
        <Skeleton className="h-8 w-64" label="Loading today's summary" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
      </section>
    );
  }

  if (dayQuery.isError || !dayQuery.data) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Today</h1>
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load today&apos;s data.
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

  return (
    <section className="space-y-8">
      <Header day={day} />

      <CalorieProgress totals={day.dayTotals} target={day.effectiveTarget} />

      <MacroBars totals={day.dayTotals} target={day.effectiveTarget} />

      <MicroRow totals={day.dayTotals} />

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleToggleEditor}
          aria-expanded={isEditorOpen}
          className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700"
        >
          {isEditorOpen ? "Cancel" : "Log a meal"}
        </button>
        <button
          type="button"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="focus-ring rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {syncMutation.isPending ? "Syncing..." : "Sync intervals now"}
        </button>
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
                  <div className="space-y-3 border-t border-slate-200 px-4 py-3 dark:border-slate-800">
                    {groups.map((group) => (
                      <ul key={group.id} className="space-y-1 text-sm">
                        {group.items.map((item) => (
                          <li key={item.id} className="flex justify-between gap-4">
                            <span>{item.name}</span>
                            <span className="text-slate-500 dark:text-slate-400">
                              {formatCalories(item.macros.calories)} cal
                            </span>
                          </li>
                        ))}
                      </ul>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyState
          message="no meals logged today"
          nudge="tell Claude, or use the button"
          action={{ label: "Log a meal", onClick: handleToggleEditor }}
        />
      )}
    </section>
  );
}

function Header({ day }: { day: DayResponse }): JSX.Element {
  const target = day.effectiveTarget;
  return (
    <header className="space-y-1">
      <h1 className="text-3xl font-bold tracking-tight">Today &mdash; {day.date}</h1>
      {target ? (
        target.caloriesOut !== null ? (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            target {formatCalories(target.effectiveCalories)} ({formatCalories(target.baseCalories)} base +{" "}
            {formatCalories(target.caloriesOut)} out)
          </p>
        ) : (
          <p className="text-sm text-slate-600 dark:text-slate-400">
            target {formatCalories(target.effectiveCalories)} (no activity data)
          </p>
        )
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-400">No target set.</p>
      )}
    </header>
  );
}

function CalorieProgress({
  totals,
  target
}: {
  totals: ItemMacros;
  target: DayResponse["effectiveTarget"];
}): JSX.Element {
  const targetCalories = target?.effectiveCalories ?? null;
  const fraction = targetCalories ? Math.min(totals.calories / targetCalories, 1) : 0;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - fraction);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="140" height="140" viewBox="0 0 140 140" role="img" aria-hidden="true">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="currentColor" strokeWidth="12" className="text-slate-200 dark:text-slate-800" />
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="12"
          strokeLinecap="round"
          className="text-sky-600 transition-[stroke-dashoffset]"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          transform="rotate(-90 70 70)"
        />
      </svg>
      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
        {targetCalories !== null
          ? `${formatCalories(totals.calories)} / ${formatCalories(targetCalories)} calories`
          : `${formatCalories(totals.calories)} calories (no target set)`}
      </p>
    </div>
  );
}

function MacroBar({
  label,
  grams,
  targetGrams
}: {
  label: string;
  grams: number;
  targetGrams: number | null;
}): JSX.Element {
  const fraction = targetGrams ? Math.min(grams / targetGrams, 1) : 0;
  const summary =
    targetGrams !== null
      ? `${formatGrams(grams)} / ${formatGrams(targetGrams)} g ${label.toLowerCase()}`
      : `${formatGrams(grams)} g ${label.toLowerCase()} (no target set)`;

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium text-slate-700 dark:text-slate-300">{label}</span>
        <span className="text-slate-600 dark:text-slate-400">
          {targetGrams !== null ? `${formatGrams(grams)} / ${formatGrams(targetGrams)} g` : `${formatGrams(grams)} g`}
        </span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div
          className="h-full rounded-full bg-sky-600"
          style={{ width: targetGrams !== null ? `${fraction * 100}%` : "100%" }}
        />
      </div>
      <p className="sr-only">{summary}</p>
    </div>
  );
}

function MacroBars({
  totals,
  target
}: {
  totals: ItemMacros;
  target: DayResponse["effectiveTarget"];
}): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <MacroBar label="Protein" grams={totals.proteinG} targetGrams={target?.proteinG ?? null} />
      <MacroBar label="Carbs" grams={totals.carbsG} targetGrams={target?.carbsG ?? null} />
      <MacroBar label="Fat" grams={totals.fatG} targetGrams={target?.fatG ?? null} />
    </div>
  );
}

function MicroRow({ totals }: { totals: ItemMacros }): JSX.Element {
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500 dark:text-slate-500">
      <div className="flex gap-1">
        <dt>Fiber</dt>
        <dd>{totals.fiberG !== null ? `${formatGrams(totals.fiberG)} g` : "—"}</dd>
      </div>
      <div className="flex gap-1">
        <dt>Sat fat</dt>
        <dd>{totals.satFatG !== null ? `${formatGrams(totals.satFatG)} g` : "—"}</dd>
      </div>
      <div className="flex gap-1">
        <dt>Sodium</dt>
        <dd>{totals.sodiumMg !== null ? `${formatCalories(totals.sodiumMg)} mg` : "—"}</dd>
      </div>
    </dl>
  );
}

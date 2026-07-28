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
import type { CreateMealRequest, DayResponse, MealType } from "../lib/api/types";
import { MealEditor, type MealEditorValue } from "../components/MealEditor";
import {
  CalorieProgress,
  DayHeader,
  MEAL_TYPE_LABELS,
  MEAL_TYPE_ORDER,
  MacroBars,
  MicroRow,
  formatCalories
} from "../components/DaySummary";
import { buildCreateMealRequest } from "../lib/mealForms";

function todayLocalDate(): string {
  // Best-effort initial fetch key only; the header's displayed date always
  // comes from the API response's `date` field (docs/style.md), never this.
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
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
      <DayHeader day={day} title="Today" />

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

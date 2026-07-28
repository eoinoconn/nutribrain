/**
 * Presentational pieces shared by the Today view (T-074) and Day detail
 * (T-075): header with the target breakdown, the calorie progress ring, the
 * big-three macro bars, and the muted micro row. Extracted so Day detail
 * reuses the exact same layout rather than duplicating it (both pages read
 * an already-computed `DayResponse` — no macro totals, propagation, or
 * target math happens here, per CLAUDE.md).
 */

import type { DayResponse, ItemMacros, MealType } from "../lib/api/types";

export function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

export function formatGrams(value: number): string {
  return value.toFixed(1);
}

export function DayHeader({ day, title }: { day: DayResponse; title: string }): JSX.Element {
  const target = day.effectiveTarget;
  return (
    <header className="space-y-1">
      <h1 className="text-3xl font-bold tracking-tight">
        {title} &mdash; {day.date}
      </h1>
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

export function CalorieProgress({
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

export function MacroBars({
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

export function MicroRow({ totals }: { totals: ItemMacros }): JSX.Element {
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

export const MEAL_TYPE_ORDER: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

export const MEAL_TYPE_LABELS: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack"
};

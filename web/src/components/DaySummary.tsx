/**
 * Presentational pieces shared by the Today view (T-074) and Day detail
 * (T-075): header with the target breakdown, the calorie progress ring, the
 * big-three macro bars, and the muted micro row. Extracted so Day detail
 * reuses the exact same layout rather than duplicating it (both pages read
 * an already-computed `DayResponse` — no macro totals, propagation, or
 * target math happens here, per CLAUDE.md).
 */

import type { ReactNode } from "react";
import type { DayResponse, ItemMacros, MealType } from "../lib/api/types";

export function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

export function formatGrams(value: number): string {
  return value.toFixed(1);
}

/**
 * Prev arrow / native date input / next arrow, styled per the app's
 * existing slate/sky Tailwind tokens (only the *structure* — arrows either
 * side of a native `<input type="date">` — is borrowed from
 * `nutrition-ui-redesign.html`'s `.date-picker`; its colors are a separate,
 * later task per §7). All calendar-day arithmetic and the date-string
 * source of truth live in the caller (`DayView.tsx` + `../lib/dateNav`) —
 * this component only renders controls and reports raw intent upward.
 */
export function DatePicker({
  date,
  onPrevDay,
  onNextDay,
  onDateChange
}: {
  date: string;
  onPrevDay: () => void;
  onNextDay: () => void;
  onDateChange: (nextDate: string) => void;
}): JSX.Element {
  return (
    <div className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700">
      <button
        type="button"
        aria-label="Previous day"
        onClick={onPrevDay}
        className="focus-ring rounded-md px-2 py-1 text-lg leading-none text-slate-600 hover:bg-slate-100 hover:text-sky-600 dark:text-slate-400 dark:hover:bg-slate-800"
      >
        <span aria-hidden="true">&#8249;</span>
      </button>
      <input
        type="date"
        aria-label="Select date"
        value={date}
        onChange={(event) => {
          if (event.target.value) {
            onDateChange(event.target.value);
          }
        }}
        className="focus-ring rounded-md border-0 bg-transparent px-1 py-1 text-sm font-medium text-slate-700 dark:text-slate-300"
      />
      <button
        type="button"
        aria-label="Next day"
        onClick={onNextDay}
        className="focus-ring rounded-md px-2 py-1 text-lg leading-none text-slate-600 hover:bg-slate-100 hover:text-sky-600 dark:text-slate-400 dark:hover:bg-slate-800"
      >
        <span aria-hidden="true">&#8250;</span>
      </button>
    </div>
  );
}

export function DayHeader({
  day,
  title,
  onPrevDay,
  onNextDay,
  onDateChange,
  caloriesOutToggle,
  caloriesOutPanel
}: {
  day: DayResponse;
  title: string;
  onPrevDay: () => void;
  onNextDay: () => void;
  onDateChange: (nextDate: string) => void;
  /** Compact toggle button rendered directly to the left of `DatePicker` in
   * the header row (docs/features/today_ui_redesign.md backlog: the manual
   * calories-out override moved out of the page body into the header). Owned
   * and composed by the caller (`DayView.tsx`) — this component stays
   * presentational and only positions it. */
  caloriesOutToggle?: ReactNode;
  /** The collapsible override form itself, rendered as a full-width block
   * below the header row when open — same "toggle row, panel underneath"
   * shape as the other panels in `DayView.tsx`. */
  caloriesOutPanel?: ReactNode;
}): JSX.Element {
  const target = day.effectiveTarget;
  return (
    <header className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
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
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {caloriesOutToggle}
          <DatePicker date={day.date} onPrevDay={onPrevDay} onNextDay={onNextDay} onDateChange={onDateChange} />
        </div>
      </div>
      {caloriesOutPanel}
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
    <div className="grid grid-cols-1 gap-4">
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

/**
 * Composes the calorie ring, macro bars, and micro-stats into the summary
 * layout used by Day detail/Today (§2 of docs/features/today_ui_redesign.md):
 * ring on the left, macro bars + micro row stacked in a column to its right,
 * wrapping to a stacked layout below the `md` breakpoint. Pure layout — the
 * three pieces it composes already receive and render the data.
 */
export function SummaryRow({
  totals,
  target
}: {
  totals: ItemMacros;
  target: DayResponse["effectiveTarget"];
}): JSX.Element {
  return (
    <div className="flex flex-col items-center gap-6 md:flex-row md:items-center md:gap-10">
      <div className="shrink-0">
        <CalorieProgress totals={totals} target={target} />
      </div>
      <div className="w-full min-w-0 flex-1 space-y-4">
        <MacroBars totals={totals} target={target} />
        <MicroRow totals={totals} />
      </div>
    </div>
  );
}

export const MEAL_TYPE_LABELS: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack"
};

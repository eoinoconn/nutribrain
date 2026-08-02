import { useId, useState } from "react";
import { formatTimeInputValue } from "../MealEditor/mealTiming";
import { createBlankPlannedWorkoutValue, type PlannedWorkoutValue } from "./types";

export interface PlannedWorkoutFormProps {
  /**
   * Called on every change to the assembled form state. Mirrors
   * `QuickMacroEntry`'s pattern: this component owns its own state
   * internally but always reports the latest value up so a parent (Day
   * view) can hold it, validate it, and submit it via `createPlannedWorkout`
   * — this component never calls the endpoint itself.
   */
  onChange?: (value: PlannedWorkoutValue) => void;
  /** Injectable "now" for deterministic defaulting in tests; defaults to `new Date()`. */
  now?: Date;
}

function numericFieldValue(value: number | null): string {
  return value === null ? "" : String(value);
}

function parseNumericInput(raw: string): number | null {
  if (raw.trim() === "") {
    return null;
  }
  const parsed = Number(raw);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * Small "Plan a workout" fallback form (EC-04, §6): start time + estimated
 * kcal for a day without an intervals.icu event, so a future fueling
 * indicator (EC-05) isn't hard-blocked on intervals.icu having the session
 * scheduled. Deliberately not a full workout editor — no sport type,
 * structured targets, or intervals.icu linkage.
 */
export default function PlannedWorkoutForm({ onChange, now }: PlannedWorkoutFormProps): JSX.Element {
  const referenceNow = now ?? new Date();
  const [value, setValue] = useState<PlannedWorkoutValue>(
    createBlankPlannedWorkoutValue(formatTimeInputValue(referenceNow))
  );

  const timeId = useId();
  const estimatedCaloriesId = useId();
  const durationId = useId();

  const update = (patch: Partial<PlannedWorkoutValue>): void => {
    const next = { ...value, ...patch };
    setValue(next);
    onChange?.(next);
  };

  return (
    <form className="space-y-4" aria-label="Plan a workout">
      <div className="flex flex-wrap gap-4">
        <div>
          <label htmlFor={timeId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
            Start time
          </label>
          <input
            id={timeId}
            type="time"
            value={value.time}
            onChange={(event) => update({ time: event.target.value })}
            className="focus-ring rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
        </div>
        <div>
          <label
            htmlFor={estimatedCaloriesId}
            className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark"
          >
            Estimated calories
          </label>
          <input
            id={estimatedCaloriesId}
            type="number"
            inputMode="decimal"
            min={0}
            value={numericFieldValue(value.estimatedCalories)}
            onChange={(event) => update({ estimatedCalories: parseNumericInput(event.target.value) })}
            className="focus-ring w-32 rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
        </div>
        <div>
          <label
            htmlFor={durationId}
            className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark"
          >
            Duration (min, optional)
          </label>
          <input
            id={durationId}
            type="number"
            inputMode="numeric"
            min={1}
            value={numericFieldValue(value.durationMinutes)}
            onChange={(event) => update({ durationMinutes: parseNumericInput(event.target.value) })}
            placeholder="60"
            className="focus-ring w-32 rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
        </div>
      </div>
    </form>
  );
}

import { useId, useState } from "react";
import type { MealType } from "../../lib/api/types";
import { formatTimeInputValue } from "../MealEditor/mealTiming";
import { MEAL_TYPES } from "../MealEditor/types";
import { createBlankQuickMacroValue, type QuickMacroValue } from "./types";

export interface QuickMacroEntryProps {
  /**
   * Called on every change to the assembled form state. This component owns
   * its own state internally (mirroring `MealEditor`'s pattern) but always
   * reports the latest value up so a parent (Day view) can hold it, validate
   * it, and submit it via `createMeal` — this component never calls the
   * meal-creation endpoint itself.
   */
  onChange?: (value: QuickMacroValue) => void;
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
 * Lightweight "Log macros" quick-entry form (§4 of
 * docs/features/today_ui_redesign.md): a single ad-hoc macro entry with no
 * food search, defaulted to `meal_type=snack` and `logged_at=now`, both
 * editable before saving. Deliberately separate from `MealEditor` — there is
 * no item repeater and no food/quantity concept, just the raw macro totals
 * the user typed.
 */
export default function QuickMacroEntry({ onChange, now }: QuickMacroEntryProps): JSX.Element {
  const referenceNow = now ?? new Date();
  const [value, setValue] = useState<QuickMacroValue>(
    createBlankQuickMacroValue("snack", formatTimeInputValue(referenceNow))
  );

  const nameId = useId();
  const mealTypeId = useId();
  const timeId = useId();
  const caloriesId = useId();
  const proteinId = useId();
  const carbsId = useId();
  const fatId = useId();
  const fiberId = useId();
  const satFatId = useId();
  const sodiumId = useId();

  const update = (patch: Partial<QuickMacroValue>): void => {
    const next = { ...value, ...patch };
    setValue(next);
    onChange?.(next);
  };

  return (
    <form className="space-y-4" aria-label="Log macros">
      <div className="flex flex-wrap gap-4">
        <div>
          <label htmlFor={mealTypeId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Meal type
          </label>
          <select
            id={mealTypeId}
            value={value.mealType}
            onChange={(event) => update({ mealType: event.target.value as MealType })}
            className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {MEAL_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor={timeId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Time
          </label>
          <input
            id={timeId}
            type="time"
            value={value.time}
            onChange={(event) => update({ time: event.target.value })}
            className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>

        <div className="flex-1">
          <label htmlFor={nameId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Name (optional)
          </label>
          <input
            id={nameId}
            type="text"
            value={value.name}
            onChange={(event) => update({ name: event.target.value })}
            placeholder="Quick entry"
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label htmlFor={caloriesId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Calories
          </label>
          <input
            id={caloriesId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.calories)}
            onChange={(event) => update({ calories: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={proteinId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Protein (g)
          </label>
          <input
            id={proteinId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.proteinG)}
            onChange={(event) => update({ proteinG: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={carbsId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Carbs (g)
          </label>
          <input
            id={carbsId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.carbsG)}
            onChange={(event) => update({ carbsG: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={fatId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Fat (g)
          </label>
          <input
            id={fatId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.fatG)}
            onChange={(event) => update({ fatG: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={fiberId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Fiber (g)
          </label>
          <input
            id={fiberId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.fiberG)}
            onChange={(event) => update({ fiberG: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={satFatId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Sat. fat (g)
          </label>
          <input
            id={satFatId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.satFatG)}
            onChange={(event) => update({ satFatG: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={sodiumId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Sodium (mg)
          </label>
          <input
            id={sodiumId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(value.sodiumMg)}
            onChange={(event) => update({ sodiumMg: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
      </div>
    </form>
  );
}

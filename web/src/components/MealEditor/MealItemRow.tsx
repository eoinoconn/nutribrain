import { useId } from "react";
import type { FoodSearchResult } from "../../lib/api/types";
import FoodSearchField from "./FoodSearchField";
import { QUANTITY_UNITS, type MealEditorItem } from "./types";

interface MealItemRowProps {
  item: MealEditorItem;
  index: number;
  onChange: (next: MealEditorItem) => void;
  onRemove: () => void;
  /** Disables the remove button when this is the only remaining row. */
  canRemove: boolean;
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

/** One row of the meal item repeater: food-search-or-ad-hoc, quantity, unit. */
export default function MealItemRow({ item, index, onChange, onRemove, canRemove }: MealItemRowProps): JSX.Element {
  const adHocToggleId = useId();
  const quantityId = useId();
  const unitId = useId();
  const nameId = useId();
  const caloriesId = useId();
  const proteinId = useId();
  const carbsId = useId();
  const fatId = useId();
  const fiberId = useId();
  const satFatId = useId();
  const sodiumId = useId();

  const handleFoodPick = (food: FoodSearchResult): void => {
    onChange({ ...item, foodId: food.id, name: food.name });
  };

  const handleToggleAdHoc = (): void => {
    if (item.isAdHoc) {
      // Switching back to food-search mode: clear ad-hoc-only fields.
      onChange({
        ...item,
        isAdHoc: false,
        calories: null,
        proteinG: null,
        carbsG: null,
        fatG: null,
        fiberG: null,
        satFatG: null,
        sodiumMg: null
      });
    } else {
      // Switching to ad-hoc: clear the picked food.
      onChange({ ...item, isAdHoc: true, foodId: null, name: "" });
    }
  };

  return (
    <fieldset className="rounded-lg border border-slate-300 p-4 dark:border-slate-700">
      <legend className="px-1 text-sm font-semibold text-slate-700 dark:text-slate-300">Item {index + 1}</legend>

      <div className="flex flex-wrap items-end gap-3">
        {item.isAdHoc ? (
          <div className="flex-1">
            <label htmlFor={nameId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Name (item {index + 1})
            </label>
            <input
              id={nameId}
              type="text"
              value={item.name}
              onChange={(event) => onChange({ ...item, name: event.target.value })}
              placeholder="e.g. Homemade soup"
              className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
        ) : (
          <FoodSearchField itemIndex={index} selectedName={item.name} onPick={handleFoodPick} />
        )}

        <div className="w-28">
          <label htmlFor={quantityId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Quantity
          </label>
          <input
            id={quantityId}
            type="number"
            inputMode="decimal"
            value={numericFieldValue(item.quantity)}
            onChange={(event) => onChange({ ...item, quantity: parseNumericInput(event.target.value) })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>

        <div className="w-32">
          <label htmlFor={unitId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Unit
          </label>
          <select
            id={unitId}
            value={item.quantityUnit}
            onChange={(event) => onChange({ ...item, quantityUnit: event.target.value as MealEditorItem["quantityUnit"] })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {QUANTITY_UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 pb-2">
          <input
            id={adHocToggleId}
            type="checkbox"
            checked={item.isAdHoc}
            onChange={handleToggleAdHoc}
            className="focus-ring h-4 w-4"
          />
          <label htmlFor={adHocToggleId} className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Ad-hoc (enter macros manually)
          </label>
        </div>

        <button
          type="button"
          onClick={onRemove}
          disabled={!canRemove}
          className="focus-ring ml-auto rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Remove item {index + 1}
        </button>
      </div>

      {item.isAdHoc ? (
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label htmlFor={caloriesId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Calories
            </label>
            <input
              id={caloriesId}
              type="number"
              inputMode="decimal"
              value={numericFieldValue(item.calories)}
              onChange={(event) => onChange({ ...item, calories: parseNumericInput(event.target.value) })}
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
              value={numericFieldValue(item.proteinG)}
              onChange={(event) => onChange({ ...item, proteinG: parseNumericInput(event.target.value) })}
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
              value={numericFieldValue(item.carbsG)}
              onChange={(event) => onChange({ ...item, carbsG: parseNumericInput(event.target.value) })}
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
              value={numericFieldValue(item.fatG)}
              onChange={(event) => onChange({ ...item, fatG: parseNumericInput(event.target.value) })}
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
              value={numericFieldValue(item.fiberG)}
              onChange={(event) => onChange({ ...item, fiberG: parseNumericInput(event.target.value) })}
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
              value={numericFieldValue(item.satFatG)}
              onChange={(event) => onChange({ ...item, satFatG: parseNumericInput(event.target.value) })}
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
              value={numericFieldValue(item.sodiumMg)}
              onChange={(event) => onChange({ ...item, sodiumMg: parseNumericInput(event.target.value) })}
              className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </div>
        </div>
      ) : null}
    </fieldset>
  );
}

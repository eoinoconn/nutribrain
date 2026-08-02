import { useId, useState } from "react";
import type { MealType } from "../../lib/api/types";
import { inferMealTypeFromLocalTime, formatTimeInputValue } from "./mealTiming";
import MealItemRow from "./MealItemRow";
import { MEAL_TYPES, createBlankItem, type MealEditorItem, type MealEditorValue } from "./types";

export interface MealEditorProps {
  /**
   * Called on every change to the assembled form state (items, meal type,
   * time). Controlled-ish: this component owns its own state internally
   * (item list, meal type, time) for simplicity, but always reports the
   * latest value up so a parent (T-074 Today, T-075 Day detail, T-079
   * Templates) can hold it, validate it, and submit it via the typed API
   * client (`createMeal`, `logTemplate`, etc.) — this component never
   * calls a meal-creation endpoint itself.
   */
  onChange?: (value: MealEditorValue) => void;
  /** Optional initial values, e.g. when re-opening a draft. Defaults: one blank item, time-inferred meal type, current time. */
  initialItems?: MealEditorItem[];
  initialMealType?: MealType;
  initialTime?: string;
  /** Injectable "now" for deterministic defaulting in tests; defaults to `new Date()`. */
  now?: Date;
}

function buildValue(items: MealEditorItem[], mealType: MealType, time: string): MealEditorValue {
  return { items, mealType, time };
}

/**
 * Standalone, reusable meal editor: an item repeater (food search or ad-hoc
 * macro entry per item), a meal-type dropdown defaulted from the current
 * local time window, and a time picker defaulted to now. Collects and
 * validates form input only — actual meal creation, food ambiguity
 * resolution, and macro computation are backend domain-layer concerns
 * (CLAUDE.md).
 */
export default function MealEditor({
  onChange,
  initialItems,
  initialMealType,
  initialTime,
  now
}: MealEditorProps): JSX.Element {
  const referenceNow = now ?? new Date();
  const [items, setItems] = useState<MealEditorItem[]>(initialItems ?? [createBlankItem()]);
  const [mealType, setMealType] = useState<MealType>(initialMealType ?? inferMealTypeFromLocalTime(referenceNow));
  const [time, setTime] = useState<string>(initialTime ?? formatTimeInputValue(referenceNow));

  const mealTypeId = useId();
  const timeId = useId();

  const emit = (nextItems: MealEditorItem[], nextMealType: MealType, nextTime: string): void => {
    onChange?.(buildValue(nextItems, nextMealType, nextTime));
  };

  const handleItemChange = (index: number, next: MealEditorItem): void => {
    const nextItems = items.map((item, itemIndex) => (itemIndex === index ? next : item));
    setItems(nextItems);
    emit(nextItems, mealType, time);
  };

  const handleAddItem = (): void => {
    const nextItems = [...items, createBlankItem()];
    setItems(nextItems);
    emit(nextItems, mealType, time);
  };

  const handleRemoveItem = (index: number): void => {
    if (items.length <= 1) {
      return;
    }
    const nextItems = items.filter((_, itemIndex) => itemIndex !== index);
    setItems(nextItems);
    emit(nextItems, mealType, time);
  };

  const handleMealTypeChange = (nextMealType: MealType): void => {
    setMealType(nextMealType);
    emit(items, nextMealType, time);
  };

  const handleTimeChange = (nextTime: string): void => {
    setTime(nextTime);
    emit(items, mealType, nextTime);
  };

  return (
    <form className="space-y-4" aria-label="Meal editor">
      <div className="flex flex-wrap gap-4">
        <div>
          <label htmlFor={mealTypeId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
            Meal type
          </label>
          <select
            id={mealTypeId}
            value={mealType}
            onChange={(event) => handleMealTypeChange(event.target.value as MealType)}
            className="focus-ring rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          >
            {MEAL_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor={timeId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
            Time
          </label>
          <input
            id={timeId}
            type="time"
            value={time}
            onChange={(event) => handleTimeChange(event.target.value)}
            className="focus-ring rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
        </div>
      </div>

      <div className="space-y-3">
        {items.map((item, index) => (
          <MealItemRow
            key={item.key}
            item={item}
            index={index}
            canRemove={items.length > 1}
            onChange={(next) => handleItemChange(index, next)}
            onRemove={() => handleRemoveItem(index)}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={handleAddItem}
        className="focus-ring rounded-md border border-line px-3 py-2 text-sm font-medium text-ink-secondary hover:bg-canvas dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
      >
        Add item
      </button>
    </form>
  );
}

import type { MealType, QuantityUnit } from "../../lib/api/types";

/**
 * One row in the item repeater. This is UI-local editing state, not the
 * wire shape (`MealItemRequest`) — callers (T-074 Today, T-075 Day detail,
 * T-079 Templates) convert `MealEditorItem[]` to whatever request shape
 * their submission endpoint needs (e.g. `POST /api/meals`'s
 * `MealItemRequest`, or a template item request).
 *
 * `isAdHoc: true` means the user is manually entering a name + macros
 * instead of picking a food via search; `foodId` is always `null` in that
 * case. `isAdHoc: false` means `foodId` (once picked) identifies the food,
 * and `name` mirrors the picked food's name for display only.
 */
export interface MealEditorItem {
  /** Stable client-side key for React list rendering / removal; not sent to the backend. */
  key: string;
  isAdHoc: boolean;
  foodId: number | null;
  name: string;
  quantity: number | null;
  quantityUnit: QuantityUnit;
  calories: number | null;
  proteinG: number | null;
  carbsG: number | null;
  fatG: number | null;
  fiberG: number | null;
  satFatG: number | null;
  sodiumMg: number | null;
}

/** The assembled, submittable form state exposed to parent components. */
export interface MealEditorValue {
  items: MealEditorItem[];
  mealType: MealType;
  /** `HH:mm` local time-of-day, as produced by `<input type="time">`. */
  time: string;
}

export const QUANTITY_UNITS: QuantityUnit[] = [
  "g",
  "kg",
  "oz",
  "lb",
  "ml",
  "l",
  "fl_oz",
  "tsp",
  "tbsp",
  "cup",
  "piece",
  "serving"
];

export const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

let nextKey = 0;

/** Generates a stable-enough client-side key for a new item repeater row. */
export function createItemKey(): string {
  nextKey += 1;
  return `item-${nextKey}-${Date.now()}`;
}

export function createBlankItem(): MealEditorItem {
  return {
    key: createItemKey(),
    isAdHoc: false,
    foodId: null,
    name: "",
    quantity: null,
    quantityUnit: "g",
    calories: null,
    proteinG: null,
    carbsG: null,
    fatG: null,
    fiberG: null,
    satFatG: null,
    sodiumMg: null
  };
}

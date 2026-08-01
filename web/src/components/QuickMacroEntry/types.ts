import type { MealType } from "../../lib/api/types";

/**
 * UI-local state for the "Log macros" quick-entry form (§4 of
 * docs/features/today_ui_redesign.md): a lightweight alternative to
 * `MealEditor` for logging a single ad-hoc (`food_id` NULL) meal_item by
 * typing macro totals directly, with no food search. Mirrors
 * `MealEditorItem`'s ad-hoc fields but flattened (no item repeater, no
 * quantity/unit picker) since there's exactly one item and no food/quantity
 * concept here.
 */
export interface QuickMacroValue {
  /** Optional label for the entry; blank falls back to "Quick entry" at submit time. */
  name: string;
  mealType: MealType;
  /** `HH:mm` local time-of-day, as produced by `<input type="time">`. */
  time: string;
  calories: number | null;
  proteinG: number | null;
  carbsG: number | null;
  fatG: number | null;
  fiberG: number | null;
  satFatG: number | null;
  sodiumMg: number | null;
}

export function createBlankQuickMacroValue(mealType: MealType, time: string): QuickMacroValue {
  return {
    name: "",
    mealType,
    time,
    calories: null,
    proteinG: null,
    carbsG: null,
    fatG: null,
    fiberG: null,
    satFatG: null,
    sodiumMg: null
  };
}

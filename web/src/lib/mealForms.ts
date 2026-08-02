/**
 * Shared helpers for converting `MealEditor` UI state (T-073) into the
 * `POST /api/meals` wire request shape. Used by both the Today view
 * (T-074) and Day detail (T-075) so the conversion logic lives in one
 * place rather than being copy-pasted per page.
 */

import { createItemKey, type MealEditorItem } from "../components/MealEditor/types";
import type { MealEditorValue } from "../components/MealEditor";
import type { PlannedWorkoutValue } from "../components/PlannedWorkoutForm/types";
import type { QuickMacroValue } from "../components/QuickMacroEntry/types";
import type { CreateMealRequest, CreatePlannedWorkoutRequest, MealItem, MealItemRequest, MealType } from "./api/types";

export function mealEditorItemToRequest(item: MealEditorValue["items"][number]): MealItemRequest | null {
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
 * (`HH:mm`) and a local calendar day (`YYYY-MM-DD`). `POST /api/meals`
 * rejects a naive datetime (backend domain layer requires tz-awareness).
 * Constructing a `Date` from local components and reading back
 * `toISOString()` gives a `Z`-suffixed UTC instant that correctly accounts
 * for the browser's offset (and DST) for that date, rather than
 * string-concatenating an offset-less timestamp.
 */
export function buildLoggedAt(localDate: string, time: string): string {
  const [year = 0, month = 1, day = 1] = localDate.split("-").map(Number);
  const [hours = 0, minutes = 0] = time.split(":").map(Number);
  return new Date(year, month - 1, day, hours, minutes, 0).toISOString();
}

/** Assembles the full `POST /api/meals` request from editor state for a given local date. */
export function buildCreateMealRequest(
  editorValue: MealEditorValue,
  localDate: string
): CreateMealRequest | null {
  const items = editorValue.items
    .map(mealEditorItemToRequest)
    .filter((item): item is MealItemRequest => item !== null);
  if (items.length === 0) {
    return null;
  }
  const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return {
    items,
    loggedAt: buildLoggedAt(localDate, editorValue.time),
    localTz,
    mealType: editorValue.mealType
  };
}

/**
 * Assembles the `POST /api/meals` request for the "Log macros" quick-entry
 * form (§4 of docs/features/today_ui_redesign.md): a single ad-hoc
 * (`food_id` NULL) meal_item carrying directly-entered macro totals, no food
 * search. Calories/protein/carbs/fat are required (returns `null`, mirroring
 * `buildCreateMealRequest`'s "nothing to submit" signal, if any is missing);
 * fiber/sat-fat/sodium stay optional. There's no food/quantity concept here
 * since the user is typing raw totals, so this follows the same fixed
 * convention as `MealItemRow`'s ad-hoc default (`quantity: 1`,
 * `quantityUnit: "serving"`), with `name` defaulting to "Quick entry" when
 * left blank.
 */
export function buildQuickMacroRequest(value: QuickMacroValue, localDate: string): CreateMealRequest | null {
  if (value.calories === null || value.proteinG === null || value.carbsG === null || value.fatG === null) {
    return null;
  }
  const item: MealItemRequest = {
    name: value.name.trim() === "" ? "Quick entry" : value.name.trim(),
    quantity: 1,
    quantityUnit: "serving",
    foodId: null,
    calories: value.calories,
    proteinG: value.proteinG,
    carbsG: value.carbsG,
    fatG: value.fatG,
    fiberG: value.fiberG,
    satFatG: value.satFatG,
    sodiumMg: value.sodiumMg
  };
  const localTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return {
    items: [item],
    loggedAt: buildLoggedAt(localDate, value.time),
    localTz,
    mealType: value.mealType
  };
}

/**
 * Assembles the `POST /api/planned-workouts` request from `PlannedWorkoutForm`
 * state (EC-04, §6) for a given local date. Returns `null` (mirroring
 * `buildCreateMealRequest`'s "nothing to submit" signal) if estimated
 * calories haven't been entered yet — the only required field per the spec's
 * "start time + estimated kcal" minimal form. `durationMinutes` is only sent
 * when the user filled it in; omitted, the backend applies its own default.
 */
export function buildCreatePlannedWorkoutRequest(
  value: PlannedWorkoutValue,
  localDate: string
): CreatePlannedWorkoutRequest | null {
  if (value.estimatedCalories === null) {
    return null;
  }
  return {
    startAt: buildLoggedAt(localDate, value.time),
    estimatedCalories: value.estimatedCalories,
    durationMinutes: value.durationMinutes
  };
}

/** `HH:mm` (input[type=time]) extracted from an ISO datetime, in the browser's local time. */
export function timeFromIso(iso: string): string {
  const parsed = new Date(iso);
  const hours = String(parsed.getHours()).padStart(2, "0");
  const minutes = String(parsed.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

/**
 * Converts an already-logged `MealItem` (wire shape, from `GET /api/day`)
 * into `MealEditorItem` UI state so an existing item can be prefilled into
 * a `MealItemRow` for editing (T-075, Day detail's "primary correction
 * surface"). There is deliberately no `update_meal_item` domain function
 * (docs/spec.md: "delete + relog is fine at v1 scale") — editing a logged
 * item is implemented as `deleteMealItem` followed by `createMeal` with a
 * single item, so this is only ever used to seed that replacement item's
 * form state, never sent back to the API as-is.
 */
export function mealItemToEditorItem(item: MealItem): MealEditorItem {
  const isAdHoc = item.foodId === null;
  return {
    key: createItemKey(),
    isAdHoc,
    foodId: item.foodId,
    name: item.name,
    quantity: item.quantity,
    quantityUnit: item.quantityUnit,
    calories: isAdHoc ? item.macros.calories : null,
    proteinG: isAdHoc ? item.macros.proteinG : null,
    carbsG: isAdHoc ? item.macros.carbsG : null,
    fatG: isAdHoc ? item.macros.fatG : null,
    fiberG: isAdHoc ? item.macros.fiberG : null,
    satFatG: isAdHoc ? item.macros.satFatG : null,
    sodiumMg: isAdHoc ? item.macros.sodiumMg : null
  };
}

export type { MealType };

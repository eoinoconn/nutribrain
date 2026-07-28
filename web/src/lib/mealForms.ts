/**
 * Shared helpers for converting `MealEditor` UI state (T-073) into the
 * `POST /api/meals` wire request shape. Used by both the Today view
 * (T-074) and Day detail (T-075) so the conversion logic lives in one
 * place rather than being copy-pasted per page.
 */

import { createItemKey, type MealEditorItem } from "../components/MealEditor/types";
import type { MealEditorValue } from "../components/MealEditor";
import type { CreateMealRequest, MealItem, MealItemRequest, MealType } from "./api/types";

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

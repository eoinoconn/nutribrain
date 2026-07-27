import type { MealType } from "../../lib/api/types";

/**
 * Mirrors `infer_meal_type` in `api/app/domain/meal_timing.py` exactly, so the
 * dropdown's *initial* default agrees with what the backend would infer for
 * the same local time. The backend remains the source of truth: it
 * independently infers `meal_type` if the caller doesn't override it, and
 * this is only a UX convenience for pre-selecting the dropdown.
 *
 * Windows (local time):
 * - breakfast: 04:00-10:59
 * - lunch: 11:00-15:59
 * - dinner: 16:00-21:59
 * - snack: 22:00-03:59 (and any non-matching edge)
 */
export function inferMealTypeFromLocalTime(date: Date): MealType {
  const hour = date.getHours();

  if (hour >= 4 && hour <= 10) {
    return "breakfast";
  }
  if (hour >= 11 && hour <= 15) {
    return "lunch";
  }
  if (hour >= 16 && hour <= 21) {
    return "dinner";
  }
  return "snack";
}

/** Formats a Date as the `HH:mm` value expected by `<input type="time">`. */
export function formatTimeInputValue(date: Date): string {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

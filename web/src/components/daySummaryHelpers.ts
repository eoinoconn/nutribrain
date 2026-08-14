import type { MealType } from "../lib/api/types";

export function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

export function formatGrams(value: number): string {
  return value.toFixed(1);
}

export const MEAL_TYPE_LABELS: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack"
};

/**
 * Shared helpers for converting between `MealEditorItem` UI state (reused
 * from the meal editor's item repeater, T-073) and the templates wire
 * shapes (`CreateTemplateRequest`/`UpdateTemplateRequest`/`Template`,
 * T-071) for the Templates manager (T-079).
 *
 * `TemplateItemRequest` and `MealItemRequest` (`lib/api/types.ts`) are
 * field-for-field identical, so outbound conversion reuses
 * `mealEditorItemToRequest` from `lib/mealForms.ts` rather than duplicating
 * it. The read shape differs, though: a `TemplateItem`'s macro fields are
 * flat (`item.calories`), not nested under `item.macros` the way a
 * materialized `MealItem`'s are (macros are computed at read time for
 * food-linked meal items, per CLAUDE.md — templates have no such
 * computation, so their ad-hoc macro fields are stored directly on the
 * item). Inbound conversion therefore needs its own function rather than
 * reusing `mealItemToEditorItem`.
 */

import { createItemKey, type MealEditorItem } from "../components/MealEditor/types";
import { mealEditorItemToRequest } from "./mealForms";
import type { CreateTemplateRequest, Template, TemplateItem, TemplateItemRequest, UpdateTemplateRequest } from "./api/types";

export function templateItemToEditorItem(item: TemplateItem): MealEditorItem {
  const isAdHoc = item.foodId === null;
  return {
    key: createItemKey(),
    isAdHoc,
    foodId: item.foodId,
    name: item.name,
    quantity: item.quantity,
    quantityUnit: item.quantityUnit,
    calories: isAdHoc ? item.calories : null,
    proteinG: isAdHoc ? item.proteinG : null,
    carbsG: isAdHoc ? item.carbsG : null,
    fatG: isAdHoc ? item.fatG : null,
    fiberG: isAdHoc ? item.fiberG : null,
    satFatG: isAdHoc ? item.satFatG : null,
    sodiumMg: isAdHoc ? item.sodiumMg : null
  };
}

/** Drops rows with no valid quantity, same rule `mealEditorItemToRequest` applies for meals. */
export function buildTemplateItemRequests(items: MealEditorItem[]): TemplateItemRequest[] {
  return items.map(mealEditorItemToRequest).filter((item): item is TemplateItemRequest => item !== null);
}

/** `null` return means "add a name and at least one item" — caller shows a validation message. */
export function buildCreateTemplateRequest(name: string, items: MealEditorItem[]): CreateTemplateRequest | null {
  const trimmedName = name.trim();
  const itemRequests = buildTemplateItemRequests(items);
  if (!trimmedName || itemRequests.length === 0) {
    return null;
  }
  return { name: trimmedName, items: itemRequests };
}

export function buildUpdateTemplateRequest(name: string, items: MealEditorItem[]): UpdateTemplateRequest | null {
  const trimmedName = name.trim();
  const itemRequests = buildTemplateItemRequests(items);
  if (!trimmedName || itemRequests.length === 0) {
    return null;
  }
  return { name: trimmedName, items: itemRequests };
}

/** Short "3 items: Chicken, Rice, Broccoli" style summary for the templates list. */
export function summarizeTemplateItems(template: Template): string {
  const count = template.items.length;
  const label = `${count} item${count === 1 ? "" : "s"}`;
  if (count === 0) {
    return label;
  }
  const names = template.items.slice(0, 3).map((item) => item.name || "(unnamed)");
  const suffix = count > names.length ? ", …" : "";
  return `${label}: ${names.join(", ")}${suffix}`;
}

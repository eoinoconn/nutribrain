/**
 * Shared request/response types for every `/api` endpoint (T-071).
 *
 * These mirror the FastAPI Pydantic schemas under `api/app/api/*.py` field
 * for field. Money/macro-shaped numbers are `Decimal` in Python but `number`
 * here per docs/style.md. Dates that represent a local calendar day are
 * plain ISO `YYYY-MM-DD` strings (`string`), never client-parsed — per
 * docs/style.md the frontend must use API-provided local date fields as-is.
 */

// --- Enums (api/app/db/models.py) ------------------------------------------

export type ServingUnit = "g" | "ml" | "piece";

export type MealType = "breakfast" | "lunch" | "dinner" | "snack";

export type QuantityUnit =
  | "g"
  | "kg"
  | "oz"
  | "lb"
  | "ml"
  | "l"
  | "fl_oz"
  | "tsp"
  | "tbsp"
  | "cup"
  | "piece"
  | "serving";

export type MealItemSource = "label" | "template" | "estimate" | "manual";

// --- Shared shapes ----------------------------------------------------------

export interface ItemMacros {
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  fiberG: number | null;
  satFatG: number | null;
  sodiumMg: number | null;
}

export interface MealItem {
  id: number;
  foodId: number | null;
  name: string;
  quantity: number;
  quantityUnit: QuantityUnit;
  source: MealItemSource;
  macros: ItemMacros;
}

export interface EffectiveTarget {
  effectiveFrom: string;
  baseCalories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  caloriesOut: number | null;
  effectiveCalories: number;
}

// --- Foods (api/app/api/foods.py) ------------------------------------------

export interface Food {
  id: number;
  name: string;
  servingSize: number;
  servingUnit: ServingUnit;
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  fiberG: number | null;
  satFatG: number | null;
  sodiumMg: number | null;
  densityGPerMl: number | null;
  isFavorite: boolean;
  createdAt: string;
}

export interface FoodSearchResult extends Food {
  lastLoggedAt: string | null;
  loggedCount: number;
}

export interface CreateFoodRequest {
  name: string;
  servingSize: number;
  servingUnit: ServingUnit;
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  fiberG?: number | null;
  satFatG?: number | null;
  sodiumMg?: number | null;
  densityGPerMl?: number | null;
  force?: boolean;
}

/**
 * Partial update. `servingUnit` is deliberately omitted: editing
 * `food.serving_unit` is forbidden by product rules (CLAUDE.md) and the
 * backend `UpdateFoodRequest` schema does accept the field, but this client
 * never sends it — create a new food instead.
 */
export interface UpdateFoodRequest {
  name?: string | null;
  servingSize?: number | null;
  calories?: number | null;
  proteinG?: number | null;
  carbsG?: number | null;
  fatG?: number | null;
  fiberG?: number | null;
  satFatG?: number | null;
  sodiumMg?: number | null;
  densityGPerMl?: number | null;
}

export interface UpdateFoodResponse {
  food: Food;
  recomputeCount: number;
}

export interface FavoriteFoodRequest {
  isFavorite: boolean;
}

export interface DeleteFoodResponse {
  deleted: boolean;
}

export interface ListFoodsParams {
  q?: string;
}

// --- Meals (api/app/api/meals.py) ------------------------------------------

export interface MealItemRequest {
  name: string;
  quantity: number;
  quantityUnit: QuantityUnit;
  foodId?: number | null;
  calories?: number | null;
  proteinG?: number | null;
  carbsG?: number | null;
  fatG?: number | null;
  fiberG?: number | null;
  satFatG?: number | null;
  sodiumMg?: number | null;
}

export interface CreateMealRequest {
  items: MealItemRequest[];
  loggedAt: string;
  localTz: string;
  mealType?: string | null;
  notes?: string | null;
}

export interface CreateMealResponse {
  id: number;
  loggedAt: string;
  localTz: string;
  localDate: string;
  mealType: MealType;
  notes: string | null;
  items: MealItem[];
  totals: ItemMacros;
  deltaVsTarget: ItemMacros | null;
}

export interface DeleteResponse {
  deleted: boolean;
}

// --- Day / range (api/app/api/day.py) --------------------------------------

export interface DayMealGroup {
  id: number;
  loggedAt: string;
  mealType: MealType;
  notes: string | null;
  items: MealItem[];
  totals: ItemMacros;
}

export interface DayResponse {
  date: string;
  meals: Record<string, DayMealGroup[]>;
  dayTotals: ItemMacros;
  effectiveTarget: EffectiveTarget | null;
  deltaVsTarget: ItemMacros | null;
}

export interface PeriodTotals {
  periodStart: string;
  periodEnd: string;
  totals: ItemMacros;
  effectiveTarget: EffectiveTarget | null;
  adherence: boolean | null;
}

export type RangeGranularity = "day" | "week";

export interface RangeParams {
  from: string;
  to: string;
  granularity?: RangeGranularity;
}

export interface RangeResponse {
  fromDate: string;
  toDate: string;
  granularity: string;
  periods: PeriodTotals[];
}

// --- Targets (api/app/api/targets.py) --------------------------------------

export interface Target {
  id: number;
  effectiveFrom: string;
  baseCalories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  createdAt: string;
}

export interface CreateTargetRequest {
  effectiveFrom: string;
  baseCalories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
}

export interface CreateTargetResponse {
  id: number;
  effectiveFrom: string;
  baseCalories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  sameDayOverlap: boolean;
}

// --- Templates (api/app/api/templates.py) ----------------------------------

export interface TemplateItemRequest {
  name: string;
  quantity: number;
  quantityUnit: QuantityUnit;
  foodId?: number | null;
  calories?: number | null;
  proteinG?: number | null;
  carbsG?: number | null;
  fatG?: number | null;
  fiberG?: number | null;
  satFatG?: number | null;
  sodiumMg?: number | null;
}

export interface TemplateItem {
  id: number;
  foodId: number | null;
  name: string;
  quantity: number;
  quantityUnit: QuantityUnit;
  calories: number | null;
  proteinG: number | null;
  carbsG: number | null;
  fatG: number | null;
  fiberG: number | null;
  satFatG: number | null;
  sodiumMg: number | null;
}

export interface Template {
  id: number;
  name: string;
  createdAt: string;
  deletedAt: string | null;
  items: TemplateItem[];
}

export interface CreateTemplateRequest {
  name: string;
  items: TemplateItemRequest[];
}

export interface UpdateTemplateRequest {
  name?: string | null;
  items?: TemplateItemRequest[] | null;
}

export interface LogTemplateRequest {
  loggedAt: string;
  localTz: string;
  mealType?: string | null;
  quantityScale?: number;
  notes?: string | null;
}

/** Response shape of `POST /api/templates/{id}/log` (a materialized meal). */
export interface TemplateLogResponse {
  id: number;
  loggedAt: string;
  localTz: string;
  localDate: string;
  mealType: MealType;
  notes: string | null;
  items: MealItem[];
  totals: ItemMacros;
  deltaVsTarget: ItemMacros | null;
}

export interface DeleteTemplateResponse {
  deleted: boolean;
}

export interface ListTemplatesParams {
  q?: string;
}

// --- Sync (api/app/api/sync.py) --------------------------------------------

export interface SyncIntervalsResponse {
  fromDate: string;
  toDate: string;
  daysSynced: number;
  failures: Record<string, unknown>[];
}

export interface SyncStatusResponse {
  lastSyncedAt: string | null;
  lastError: string | null;
}

export interface SetManualCaloriesOutRequest {
  date: string;
  caloriesOut: number;
}

export interface ManualCaloriesOutResponse {
  date: string;
  caloriesOut: number;
  fetchedAt: string;
}

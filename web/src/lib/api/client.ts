/**
 * Typed client for the NutriBrain `/api` backend (T-071).
 *
 * One function per backend endpoint. This module is pure request/response
 * plumbing over `apiFetch`/`apiFetchJson` (T-070, `../apiClient`) — no
 * business rules live here (see CLAUDE.md: business logic belongs only in
 * the backend domain layer). It reuses the existing transport for
 * auth-header attachment and 401 handling rather than duplicating it.
 *
 * Field names are hand-converted between this module's camelCase types
 * (`./types`) and the backend's snake_case JSON via `./transform`, since the
 * FastAPI routes were read directly from `api/app/api/*.py` rather than
 * generated from the OpenAPI schema (see the module-level decision note in
 * `./index.ts`).
 */

import { apiFetchJson } from "../apiClient";
import { keysToCamel, keysToSnake } from "./transform";
import type {
  AppSettings,
  CreateFoodRequest,
  CreateMealRequest,
  CreateMealResponse,
  CreatePlannedWorkoutRequest,
  CreateTargetRequest,
  CreateTargetResponse,
  CreateTemplateRequest,
  DayResponse,
  DeleteFoodResponse,
  DeleteResponse,
  DeleteTemplateResponse,
  EffectiveTarget,
  Food,
  FoodSearchResult,
  ListFoodsParams,
  ListTemplatesParams,
  LogTemplateRequest,
  ManualCaloriesOutResponse,
  PlannedWorkoutResponse,
  RangeParams,
  RangeResponse,
  SetManualCaloriesOutRequest,
  SyncIntervalsResponse,
  SyncStatusResponse,
  Target,
  Template,
  TemplateLogResponse,
  UpdateFoodRequest,
  UpdateFoodResponse,
  UpdateSettingsRequest,
  UpdateTemplateRequest
} from "./types";

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

async function getJson<T>(path: string): Promise<T> {
  const raw = await apiFetchJson<unknown>(path);
  return keysToCamel<T>(raw);
}

async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const raw = await apiFetchJson<unknown>(path, {
    method,
    body: body !== undefined ? JSON.stringify(keysToSnake(body)) : undefined
  });
  return keysToCamel<T>(raw);
}

// --- Foods (api/app/api/foods.py) ------------------------------------------

export function listFoods(params: ListFoodsParams = {}): Promise<FoodSearchResult[]> {
  return getJson<FoodSearchResult[]>(`/api/foods${buildQuery({ q: params.q })}`);
}

export function createFood(payload: CreateFoodRequest): Promise<Food> {
  return sendJson<Food>("/api/foods", "POST", payload);
}

export function updateFood(foodId: number, payload: UpdateFoodRequest): Promise<UpdateFoodResponse> {
  return sendJson<UpdateFoodResponse>(`/api/foods/${foodId}`, "PATCH", payload);
}

export function setFavoriteFood(foodId: number, isFavorite: boolean): Promise<Food> {
  return sendJson<Food>(`/api/foods/${foodId}/favorite`, "POST", { isFavorite });
}

export function deleteFood(foodId: number): Promise<DeleteFoodResponse> {
  return sendJson<DeleteFoodResponse>(`/api/foods/${foodId}`, "DELETE");
}

// --- Meals (api/app/api/meals.py) ------------------------------------------

export function createMeal(payload: CreateMealRequest): Promise<CreateMealResponse> {
  return sendJson<CreateMealResponse>("/api/meals", "POST", payload);
}

export function deleteMeal(mealId: number): Promise<DeleteResponse> {
  return sendJson<DeleteResponse>(`/api/meals/${mealId}`, "DELETE");
}

export function deleteMealItem(itemId: number): Promise<DeleteResponse> {
  return sendJson<DeleteResponse>(`/api/meal-items/${itemId}`, "DELETE");
}

// --- Day / range (api/app/api/day.py) --------------------------------------

export function getDay(date: string): Promise<DayResponse> {
  return getJson<DayResponse>(`/api/day/${date}`);
}

export function getRange(params: RangeParams): Promise<RangeResponse> {
  const query = buildQuery({
    from: params.from,
    to: params.to,
    granularity: params.granularity
  });
  return getJson<RangeResponse>(`/api/range${query}`);
}

// --- Planned workouts (api/app/api/planned_workouts.py) --------------------

export function createPlannedWorkout(
  payload: CreatePlannedWorkoutRequest
): Promise<PlannedWorkoutResponse> {
  return sendJson<PlannedWorkoutResponse>("/api/planned-workouts", "POST", payload);
}

// --- Targets (api/app/api/targets.py) --------------------------------------

export function listTargets(): Promise<Target[]> {
  return getJson<Target[]>("/api/targets");
}

export function createTarget(payload: CreateTargetRequest): Promise<CreateTargetResponse> {
  return sendJson<CreateTargetResponse>("/api/targets", "POST", payload);
}

export function getEffectiveTarget(date: string): Promise<EffectiveTarget | null> {
  return getJson<EffectiveTarget | null>(`/api/targets/effective${buildQuery({ date })}`);
}

// --- Templates (api/app/api/templates.py) ----------------------------------

export function listTemplates(params: ListTemplatesParams = {}): Promise<Template[]> {
  return getJson<Template[]>(`/api/templates${buildQuery({ q: params.q })}`);
}

export function createTemplate(payload: CreateTemplateRequest): Promise<Template> {
  return sendJson<Template>("/api/templates", "POST", payload);
}

export function updateTemplate(
  templateId: number,
  payload: UpdateTemplateRequest
): Promise<Template> {
  return sendJson<Template>(`/api/templates/${templateId}`, "PATCH", payload);
}

export function deleteTemplate(templateId: number): Promise<DeleteTemplateResponse> {
  return sendJson<DeleteTemplateResponse>(`/api/templates/${templateId}`, "DELETE");
}

export function logTemplate(
  templateId: number,
  payload: LogTemplateRequest
): Promise<TemplateLogResponse> {
  return sendJson<TemplateLogResponse>(`/api/templates/${templateId}/log`, "POST", payload);
}

// --- Sync (api/app/api/sync.py) --------------------------------------------

export function syncIntervals(): Promise<SyncIntervalsResponse> {
  return sendJson<SyncIntervalsResponse>("/api/sync/intervals", "POST");
}

export function getSyncStatus(): Promise<SyncStatusResponse> {
  return getJson<SyncStatusResponse>("/api/sync/status");
}

export function setManualCaloriesOut(
  payload: SetManualCaloriesOutRequest
): Promise<ManualCaloriesOutResponse> {
  return sendJson<ManualCaloriesOutResponse>("/api/sync/intervals/manual", "PUT", payload);
}

// --- Settings (api/app/api/settings.py) -------------------------------------

export function getSettings(): Promise<AppSettings> {
  return getJson<AppSettings>("/api/settings");
}

export function updateSettings(payload: UpdateSettingsRequest): Promise<AppSettings> {
  return sendJson<AppSettings>("/api/settings", "PATCH", payload);
}

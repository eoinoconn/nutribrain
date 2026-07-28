/**
 * Foods manager (T-078, spec §7): `/foods`.
 *
 * A searchable/sortable table over `GET /api/foods?q=`, a star toggle for
 * `is_favorite` (optimistic, matching the established rollback pattern from
 * T-074/T-075), a row-click edit modal, and a separate "Add food" form.
 *
 * Mutation-rule notes this component has to respect (CLAUDE.md / spec §3):
 * - `serving_unit` is immutable after creation. The backend rejects changing
 *   it (`serving_unit_immutable`), but per the task this UI also disables
 *   the field itself once a food has an id, rather than relying solely on
 *   the 422.
 * - Editing nutrition fields recomputes every past meal referencing this
 *   food at read time — no write-time snapshot exists to preview from.
 *
 * "Recompute count before commit" gap: `update_food`'s only count
 * (`recomputeCount`, exact distinct-meals-affected) is returned by the
 * PATCH response itself — there is no dry-run endpoint (confirmed by
 * reading `api/app/api/foods.py` / `api/app/domain/foods.py`). So this
 * modal shows a best-effort *preview* using `loggedCount` (item-level usage
 * count, already available from the list load) before commit, and then
 * shows the authoritative distinct-meal `recomputeCount` in the success
 * toast once the PATCH actually returns. See the task report for why a
 * literal "N past meals" figure can't be shown before commit without a
 * backend change (out of scope here).
 */

import { useId, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFood, listFoods, setFavoriteFood, updateFood } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import { queryKeys } from "../lib/queryClient";
import { useToast } from "../design/useToast";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import Modal from "../design/Modal";
import type { CreateFoodRequest, FoodSearchResult, ServingUnit, UpdateFoodRequest } from "../lib/api/types";

const SERVING_UNITS: ServingUnit[] = ["g", "ml", "piece"];

type SortColumn = "name" | "calories" | "proteinG" | "carbsG" | "fatG" | "isFavorite";
type SortDirection = "asc" | "desc";

interface DomainErrorBody {
  error?: string;
  message?: string;
  candidates?: Array<{ id: number; name: string; calories: number }>;
}

function domainErrorBody(error: unknown): DomainErrorBody | null {
  if (error instanceof ApiError && error.body && typeof error.body === "object") {
    return error.body;
  }
  return null;
}

function formatNumber(value: number | null): string {
  return value === null ? "—" : String(value);
}

interface FoodFormValues {
  name: string;
  servingSize: string;
  servingUnit: ServingUnit;
  calories: string;
  proteinG: string;
  carbsG: string;
  fatG: string;
  fiberG: string;
  satFatG: string;
  sodiumMg: string;
}

function blankFormValues(): FoodFormValues {
  return {
    name: "",
    servingSize: "",
    servingUnit: "g",
    calories: "",
    proteinG: "",
    carbsG: "",
    fatG: "",
    fiberG: "",
    satFatG: "",
    sodiumMg: ""
  };
}

function formValuesFromFood(food: FoodSearchResult): FoodFormValues {
  return {
    name: food.name,
    servingSize: String(food.servingSize),
    servingUnit: food.servingUnit,
    calories: String(food.calories),
    proteinG: String(food.proteinG),
    carbsG: String(food.carbsG),
    fatG: String(food.fatG),
    fiberG: food.fiberG === null ? "" : String(food.fiberG),
    satFatG: food.satFatG === null ? "" : String(food.satFatG),
    sodiumMg: food.sodiumMg === null ? "" : String(food.sodiumMg)
  };
}

/** `null` return means "required field missing/invalid" — caller shows a validation message. */
function parseRequiredNumber(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isNaN(parsed) ? null : parsed;
}

function parseOptionalNumber(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isNaN(parsed) ? null : parsed;
}

export default function FoodsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [query, setQuery] = useState("");
  const filters = useMemo(() => ({ q: query || undefined }), [query]);

  const [sortColumn, setSortColumn] = useState<SortColumn>("name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [addValues, setAddValues] = useState<FoodFormValues>(blankFormValues());
  const [addError, setAddError] = useState<string | null>(null);
  const [duplicateCandidates, setDuplicateCandidates] = useState<DomainErrorBody["candidates"]>(undefined);

  const [editingFood, setEditingFood] = useState<FoodSearchResult | null>(null);
  const [editValues, setEditValues] = useState<FoodFormValues | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const foodsQuery = useQuery({
    queryKey: queryKeys.foods(filters),
    queryFn: () => listFoods({ q: query || undefined })
  });

  const sortedFoods = useMemo(() => {
    const data = foodsQuery.data ?? [];
    const factor = sortDirection === "asc" ? 1 : -1;
    return [...data].sort((left, right) => {
      const leftValue = left[sortColumn];
      const rightValue = right[sortColumn];
      if (typeof leftValue === "string" && typeof rightValue === "string") {
        return factor * leftValue.localeCompare(rightValue);
      }
      const leftNum = typeof leftValue === "number" ? leftValue : Number(leftValue);
      const rightNum = typeof rightValue === "number" ? rightValue : Number(rightValue);
      return factor * (leftNum - rightNum);
    });
  }, [foodsQuery.data, sortColumn, sortDirection]);

  function handleSort(column: SortColumn): void {
    if (column === sortColumn) {
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
  }

  const favoriteMutation = useMutation({
    mutationFn: ({ foodId, isFavorite }: { foodId: number; isFavorite: boolean }) =>
      setFavoriteFood(foodId, isFavorite),
    onMutate: async ({ foodId, isFavorite }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.foods(filters) });
      const previous = queryClient.getQueryData<FoodSearchResult[]>(queryKeys.foods(filters));
      if (previous) {
        queryClient.setQueryData(
          queryKeys.foods(filters),
          previous.map((food) => (food.id === foodId ? { ...food, isFavorite } : food))
        );
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.foods(filters), context.previous);
      }
      showToast("Could not update favorite.", "error");
    },
    onSuccess: (_data, vars) => {
      showToast(vars.isFavorite ? "Added to favorites." : "Removed from favorites.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.foods(filters) });
    }
  });

  const addFoodMutation = useMutation({
    mutationFn: (payload: CreateFoodRequest) => createFood(payload),
    onSuccess: () => {
      showToast("Food added.", "success");
      setIsAddOpen(false);
      setAddValues(blankFormValues());
      setAddError(null);
      setDuplicateCandidates(undefined);
    },
    onError: (error) => {
      const body = domainErrorBody(error);
      if (body?.error === "food_duplicate") {
        setAddError(body.message ?? "A similar food already exists.");
        setDuplicateCandidates(body.candidates);
        return;
      }
      setAddError(body?.message ?? "Could not add food.");
      showToast("Could not add food.", "error");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.foods(filters) });
    }
  });

  const updateFoodMutation = useMutation({
    mutationFn: ({ foodId, payload }: { foodId: number; payload: UpdateFoodRequest }) => updateFood(foodId, payload),
    onSuccess: (result) => {
      showToast(
        result.recomputeCount > 0
          ? `Food updated — ${result.recomputeCount} past meal${result.recomputeCount === 1 ? "" : "s"} recomputed.`
          : "Food updated.",
        "success"
      );
      setEditingFood(null);
      setEditValues(null);
      setEditError(null);
    },
    onError: (error) => {
      const body = domainErrorBody(error);
      setEditError(body?.message ?? "Could not update food.");
      showToast("Could not update food.", "error");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.foods(filters) });
    }
  });

  function handleOpenEdit(food: FoodSearchResult): void {
    setEditingFood(food);
    setEditValues(formValuesFromFood(food));
    setEditError(null);
  }

  function handleCloseEdit(): void {
    setEditingFood(null);
    setEditValues(null);
    setEditError(null);
  }

  function handleSubmitEdit(event: FormEvent): void {
    event.preventDefault();
    if (!editingFood || !editValues) {
      return;
    }

    const name = editValues.name.trim();
    if (!name) {
      setEditError("Name is required.");
      return;
    }
    const servingSize = parseRequiredNumber(editValues.servingSize);
    const calories = parseRequiredNumber(editValues.calories);
    const proteinG = parseRequiredNumber(editValues.proteinG);
    const carbsG = parseRequiredNumber(editValues.carbsG);
    const fatG = parseRequiredNumber(editValues.fatG);
    if (servingSize === null || calories === null || proteinG === null || carbsG === null || fatG === null) {
      setEditError("Serving size, calories, protein, carbs, and fat must be numbers.");
      return;
    }

    // Only send fields that actually changed — a true partial update, and
    // it keeps `serving_unit` (never editable here) out of the payload
    // entirely rather than relying only on the type omitting it.
    const payload: UpdateFoodRequest = {};
    if (name !== editingFood.name) payload.name = name;
    if (servingSize !== editingFood.servingSize) payload.servingSize = servingSize;
    if (calories !== editingFood.calories) payload.calories = calories;
    if (proteinG !== editingFood.proteinG) payload.proteinG = proteinG;
    if (carbsG !== editingFood.carbsG) payload.carbsG = carbsG;
    if (fatG !== editingFood.fatG) payload.fatG = fatG;
    const fiberG = parseOptionalNumber(editValues.fiberG);
    if (fiberG !== editingFood.fiberG) payload.fiberG = fiberG;
    const satFatG = parseOptionalNumber(editValues.satFatG);
    if (satFatG !== editingFood.satFatG) payload.satFatG = satFatG;
    const sodiumMg = parseOptionalNumber(editValues.sodiumMg);
    if (sodiumMg !== editingFood.sodiumMg) payload.sodiumMg = sodiumMg;

    if (Object.keys(payload).length === 0) {
      handleCloseEdit();
      return;
    }

    updateFoodMutation.mutate({ foodId: editingFood.id, payload });
  }

  function handleOpenAdd(): void {
    setAddValues(blankFormValues());
    setAddError(null);
    setDuplicateCandidates(undefined);
    setIsAddOpen(true);
  }

  function handleCloseAdd(): void {
    setIsAddOpen(false);
    setAddError(null);
    setDuplicateCandidates(undefined);
  }

  function buildCreatePayload(force: boolean): CreateFoodRequest | null {
    const name = addValues.name.trim();
    const servingSize = parseRequiredNumber(addValues.servingSize);
    const calories = parseRequiredNumber(addValues.calories);
    const proteinG = parseRequiredNumber(addValues.proteinG);
    const carbsG = parseRequiredNumber(addValues.carbsG);
    const fatG = parseRequiredNumber(addValues.fatG);
    if (!name || servingSize === null || calories === null || proteinG === null || carbsG === null || fatG === null) {
      return null;
    }
    return {
      name,
      servingSize,
      servingUnit: addValues.servingUnit,
      calories,
      proteinG,
      carbsG,
      fatG,
      fiberG: parseOptionalNumber(addValues.fiberG),
      satFatG: parseOptionalNumber(addValues.satFatG),
      sodiumMg: parseOptionalNumber(addValues.sodiumMg),
      force
    };
  }

  function handleSubmitAdd(event: FormEvent): void {
    event.preventDefault();
    const payload = buildCreatePayload(false);
    if (!payload) {
      setAddError("Name, serving size, calories, protein, carbs, and fat are required.");
      return;
    }
    setAddError(null);
    setDuplicateCandidates(undefined);
    addFoodMutation.mutate(payload);
  }

  function handleForceAdd(): void {
    const payload = buildCreatePayload(true);
    if (!payload) {
      return;
    }
    addFoodMutation.mutate(payload);
  }

  if (foodsQuery.isLoading) {
    return (
      <section className="space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Foods</h1>
        <Skeleton className="h-10 w-full max-w-sm" label="Loading foods" />
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (foodsQuery.isError) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Foods</h1>
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load foods.
        </p>
        <button
          type="button"
          onClick={() => void foodsQuery.refetch()}
          className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Retry
        </button>
      </section>
    );
  }

  const foods = foodsQuery.data ?? [];

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-bold tracking-tight">Foods</h1>
        <button
          type="button"
          onClick={handleOpenAdd}
          className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700"
        >
          Add food
        </button>
      </div>

      <div>
        <label htmlFor="foods-search" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
          Search foods
        </label>
        <input
          id="foods-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. chicken"
          className="focus-ring w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
      </div>

      {foods.length === 0 ? (
        <EmptyState
          message="no foods yet"
          nudge="tell Claude, or add one"
          action={{ label: "Add food", onClick: handleOpenAdd }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:text-slate-400">
              <tr>
                <SortableHeader label="Favorite" column="isFavorite" active={sortColumn} direction={sortDirection} onSort={handleSort} />
                <SortableHeader label="Name" column="name" active={sortColumn} direction={sortDirection} onSort={handleSort} />
                <SortableHeader label="Calories" column="calories" active={sortColumn} direction={sortDirection} onSort={handleSort} />
                <SortableHeader label="Protein (g)" column="proteinG" active={sortColumn} direction={sortDirection} onSort={handleSort} />
                <SortableHeader label="Carbs (g)" column="carbsG" active={sortColumn} direction={sortDirection} onSort={handleSort} />
                <SortableHeader label="Fat (g)" column="fatG" active={sortColumn} direction={sortDirection} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {sortedFoods.map((food) => (
                <tr key={food.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800/60">
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => favoriteMutation.mutate({ foodId: food.id, isFavorite: !food.isFavorite })}
                      disabled={favoriteMutation.isPending}
                      aria-pressed={food.isFavorite}
                      aria-label={food.isFavorite ? `Remove ${food.name} from favorites` : `Add ${food.name} to favorites`}
                      className="focus-ring rounded-md px-2 py-1 text-lg text-amber-500 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800"
                    >
                      {food.isFavorite ? "★" : "☆"}
                    </button>
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => handleOpenEdit(food)}
                      className="focus-ring rounded-md text-left font-medium text-sky-700 hover:underline dark:text-sky-400"
                    >
                      {food.name}
                    </button>
                  </td>
                  <td className="px-3 py-2">{formatNumber(food.calories)}</td>
                  <td className="px-3 py-2">{formatNumber(food.proteinG)}</td>
                  <td className="px-3 py-2">{formatNumber(food.carbsG)}</td>
                  <td className="px-3 py-2">{formatNumber(food.fatG)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingFood && editValues ? (
        <EditFoodModal
          food={editingFood}
          values={editValues}
          onChange={setEditValues}
          onClose={handleCloseEdit}
          onSubmit={handleSubmitEdit}
          error={editError}
          isPending={updateFoodMutation.isPending}
        />
      ) : null}

      {isAddOpen ? (
        <AddFoodModal
          values={addValues}
          onChange={setAddValues}
          onClose={handleCloseAdd}
          onSubmit={handleSubmitAdd}
          onForceAdd={handleForceAdd}
          error={addError}
          duplicateCandidates={duplicateCandidates}
          isPending={addFoodMutation.isPending}
        />
      ) : null}
    </section>
  );
}

function SortableHeader({
  label,
  column,
  active,
  direction,
  onSort
}: {
  label: string;
  column: SortColumn;
  active: SortColumn;
  direction: SortDirection;
  onSort: (column: SortColumn) => void;
}): JSX.Element {
  const isActive = active === column;
  return (
    <th scope="col" aria-sort={isActive ? (direction === "asc" ? "ascending" : "descending") : "none"} className="px-3 py-2">
      <button
        type="button"
        onClick={() => onSort(column)}
        className="focus-ring flex items-center gap-1 font-semibold uppercase tracking-wide"
      >
        {label}
        {isActive ? <span aria-hidden="true">{direction === "asc" ? "↑" : "↓"}</span> : null}
      </button>
    </th>
  );
}

interface NutritionFieldsProps {
  values: FoodFormValues;
  onChange: (next: FoodFormValues) => void;
  servingUnitDisabled: boolean;
  idPrefix: string;
}

function NutritionFields({ values, onChange, servingUnitDisabled, idPrefix }: NutritionFieldsProps): JSX.Element {
  return (
    <>
      <div>
        <label htmlFor={`${idPrefix}-name`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
          Name
        </label>
        <input
          id={`${idPrefix}-name`}
          type="text"
          value={values.name}
          onChange={(event) => onChange({ ...values, name: event.target.value })}
          className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={`${idPrefix}-serving-size`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Serving size
          </label>
          <input
            id={`${idPrefix}-serving-size`}
            type="number"
            inputMode="decimal"
            value={values.servingSize}
            onChange={(event) => onChange({ ...values, servingSize: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-serving-unit`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Serving unit
          </label>
          <select
            id={`${idPrefix}-serving-unit`}
            value={values.servingUnit}
            disabled={servingUnitDisabled}
            onChange={(event) => onChange({ ...values, servingUnit: event.target.value as ServingUnit })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900"
          >
            {SERVING_UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
          {servingUnitDisabled ? (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Can&apos;t be changed after creation &mdash; add a new food instead.
            </p>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <label htmlFor={`${idPrefix}-calories`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Calories
          </label>
          <input
            id={`${idPrefix}-calories`}
            type="number"
            inputMode="decimal"
            value={values.calories}
            onChange={(event) => onChange({ ...values, calories: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-protein`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Protein (g)
          </label>
          <input
            id={`${idPrefix}-protein`}
            type="number"
            inputMode="decimal"
            value={values.proteinG}
            onChange={(event) => onChange({ ...values, proteinG: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-carbs`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Carbs (g)
          </label>
          <input
            id={`${idPrefix}-carbs`}
            type="number"
            inputMode="decimal"
            value={values.carbsG}
            onChange={(event) => onChange({ ...values, carbsG: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-fat`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Fat (g)
          </label>
          <input
            id={`${idPrefix}-fat`}
            type="number"
            inputMode="decimal"
            value={values.fatG}
            onChange={(event) => onChange({ ...values, fatG: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-fiber`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Fiber (g)
          </label>
          <input
            id={`${idPrefix}-fiber`}
            type="number"
            inputMode="decimal"
            value={values.fiberG}
            onChange={(event) => onChange({ ...values, fiberG: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-sat-fat`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Sat. fat (g)
          </label>
          <input
            id={`${idPrefix}-sat-fat`}
            type="number"
            inputMode="decimal"
            value={values.satFatG}
            onChange={(event) => onChange({ ...values, satFatG: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-sodium`} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Sodium (mg)
          </label>
          <input
            id={`${idPrefix}-sodium`}
            type="number"
            inputMode="decimal"
            value={values.sodiumMg}
            onChange={(event) => onChange({ ...values, sodiumMg: event.target.value })}
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
      </div>
    </>
  );
}

function EditFoodModal({
  food,
  values,
  onChange,
  onClose,
  onSubmit,
  error,
  isPending
}: {
  food: FoodSearchResult;
  values: FoodFormValues;
  onChange: (next: FoodFormValues) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent) => void;
  error: string | null;
  isPending: boolean;
}): JSX.Element {
  const titleId = useId();
  return (
    <Modal isOpen onClose={onClose} titleId={titleId}>
      <h2 id={titleId} className="mb-1 text-lg font-semibold">
        Edit {food.name}
      </h2>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
        Saving changes to calories, protein, carbs, fat, fiber, sat. fat, sodium, or serving size
        recomputes every past meal logged with this food (read-time calculation, no data is
        rewritten). This food has been logged in {food.loggedCount} meal item
        {food.loggedCount === 1 ? "" : "s"} so far &mdash; the exact number of past meals affected
        is confirmed once you save.
      </p>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <NutritionFields values={values} onChange={onChange} servingUnitDisabled idPrefix="edit-food" />
        {error ? (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="focus-ring rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {isPending ? "Saving..." : "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AddFoodModal({
  values,
  onChange,
  onClose,
  onSubmit,
  onForceAdd,
  error,
  duplicateCandidates,
  isPending
}: {
  values: FoodFormValues;
  onChange: (next: FoodFormValues) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent) => void;
  onForceAdd: () => void;
  error: string | null;
  duplicateCandidates: DomainErrorBody["candidates"];
  isPending: boolean;
}): JSX.Element {
  const titleId = useId();
  return (
    <Modal isOpen onClose={onClose} titleId={titleId}>
      <h2 id={titleId} className="mb-4 text-lg font-semibold">
        Add food
      </h2>
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <NutritionFields values={values} onChange={onChange} servingUnitDisabled={false} idPrefix="add-food" />
        {error ? (
          <div role="alert" className="space-y-2 text-sm text-red-700 dark:text-red-400">
            <p>{error}</p>
            {duplicateCandidates && duplicateCandidates.length > 0 ? (
              <ul className="list-inside list-disc">
                {duplicateCandidates.map((candidate) => (
                  <li key={candidate.id}>
                    {candidate.name} ({candidate.calories} cal)
                  </li>
                ))}
              </ul>
            ) : null}
            {duplicateCandidates ? (
              <button
                type="button"
                onClick={onForceAdd}
                disabled={isPending}
                className="focus-ring rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
              >
                Add anyway
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="focus-ring rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isPending}
            className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {isPending ? "Adding..." : "Add food"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

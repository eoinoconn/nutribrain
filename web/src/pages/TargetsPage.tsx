/**
 * Targets manager (T-080, spec §7): `/targets`.
 *
 * Targets are append-only and versioned (CLAUDE.md "Mutation Rules" /
 * spec §4 `set_target`): there is no `update_target`/`delete_target` domain
 * function, only `set_target`, which always inserts a new row and never
 * mutates an existing one. This page mirrors that in the UI:
 * - The list (`GET /api/targets`) is read-only — rows have no edit
 *   affordance, sorted `effective_from` descending (spec §7).
 * - The only mutation is "New target", which posts `CreateTargetRequest`
 *   (spec §3/§4 fields: base calories + macros + `effective_from`,
 *   defaulting to today per `set_target`'s own default).
 *
 * Inline form vs. modal (see task report for full reasoning): this page
 * uses an inline expand/collapse section (the same pattern as
 * `TodayPage`'s "Log a meal" toggle) rather than `Modal.tsx`. Unlike
 * Foods/Templates, Targets has no edit mode to share a form with, so there's
 * no modal-reuse benefit; the field set is a flat 5 inputs (no item
 * repeater), and the create flow doesn't need to visually block the list
 * behind a backdrop since there's nothing on the page it could clash with.
 *
 * `same_day_overlap`: `set_target`'s response can flag that the new target
 * replaces an earlier same-day version (spec §4). Surfaced via the success
 * toast rather than a separate banner, matching how `FoodsPage` surfaces
 * `recomputeCount` in its toast.
 */

import { useId, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createTarget, listTargets } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import { queryKeys } from "../lib/queryClient";
import { useToast } from "../design/useToast";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import type { CreateTargetRequest, Target } from "../lib/api/types";

function todayLocalDate(): string {
  // Form default only (per `set_target`'s own `effective_from` default);
  // the list itself always displays the API's `effectiveFrom` values as-is.
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

interface TargetFormValues {
  effectiveFrom: string;
  baseCalories: string;
  proteinG: string;
  carbsG: string;
  fatG: string;
}

function blankFormValues(): TargetFormValues {
  return {
    effectiveFrom: todayLocalDate(),
    baseCalories: "",
    proteinG: "",
    carbsG: "",
    fatG: ""
  };
}

function parseRequiredInt(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

function domainErrorMessage(error: unknown): string | null {
  if (error instanceof ApiError && error.body && typeof error.body === "object" && "message" in error.body) {
    const message = (error.body as { message?: unknown }).message;
    return typeof message === "string" ? message : null;
  }
  return null;
}

function buildCreatePayload(values: TargetFormValues): CreateTargetRequest | null {
  if (!values.effectiveFrom) {
    return null;
  }
  const baseCalories = parseRequiredInt(values.baseCalories);
  const proteinG = parseRequiredInt(values.proteinG);
  const carbsG = parseRequiredInt(values.carbsG);
  const fatG = parseRequiredInt(values.fatG);
  if (baseCalories === null || proteinG === null || carbsG === null || fatG === null) {
    return null;
  }
  return { effectiveFrom: values.effectiveFrom, baseCalories, proteinG, carbsG, fatG };
}

function sortedByEffectiveFromDesc(targets: Target[]): Target[] {
  return [...targets].sort((left, right) => right.effectiveFrom.localeCompare(left.effectiveFrom));
}

export default function TargetsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [values, setValues] = useState<TargetFormValues>(blankFormValues);
  const [formError, setFormError] = useState<string | null>(null);

  const targetsQuery = useQuery({
    queryKey: queryKeys.targetsList(),
    queryFn: () => listTargets()
  });

  const sortedTargets = useMemo(() => sortedByEffectiveFromDesc(targetsQuery.data ?? []), [targetsQuery.data]);

  const createTargetMutation = useMutation({
    mutationFn: (payload: CreateTargetRequest) => createTarget(payload),
    onSuccess: (result) => {
      showToast(
        result.sameDayOverlap
          ? "Target created — replaces an earlier target with the same effective date."
          : "Target created.",
        "success"
      );
      handleCloseCreate();
    },
    onError: (error) => {
      setFormError(domainErrorMessage(error) ?? "Could not create target.");
      showToast("Could not create target.", "error");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.targetsList() });
      // A new target can change today's effective target, which the
      // Today/Day views compute as part of `GET /api/day/{date}`.
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(todayLocalDate()) });
    }
  });

  function handleOpenCreate(): void {
    setValues(blankFormValues());
    setFormError(null);
    setIsCreateOpen(true);
  }

  function handleCloseCreate(): void {
    setIsCreateOpen(false);
    setValues(blankFormValues());
    setFormError(null);
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    const payload = buildCreatePayload(values);
    if (!payload) {
      setFormError("Effective date, base calories, protein, carbs, and fat are all required.");
      return;
    }
    setFormError(null);
    createTargetMutation.mutate(payload);
  }

  if (targetsQuery.isLoading) {
    return (
      <section className="space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Targets</h1>
        <Skeleton className="h-10 w-full max-w-sm" label="Loading targets" />
        <Skeleton className="h-48 w-full" />
      </section>
    );
  }

  if (targetsQuery.isError) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Targets</h1>
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load targets.
        </p>
        <button
          type="button"
          onClick={() => void targetsQuery.refetch()}
          className="focus-ring rounded-md border border-line px-3 py-2 text-sm font-medium hover:bg-canvas dark:border-line-dark dark:hover:bg-panel-dark"
        >
          Retry
        </button>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-bold tracking-tight">Targets</h1>
        <button
          type="button"
          onClick={() => (isCreateOpen ? handleCloseCreate() : handleOpenCreate())}
          aria-expanded={isCreateOpen}
          className="focus-ring rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent"
        >
          {isCreateOpen ? "Cancel" : "New target"}
        </button>
      </div>

      {isCreateOpen ? (
        <TargetForm
          values={values}
          onChange={setValues}
          onSubmit={handleSubmit}
          error={formError}
          isPending={createTargetMutation.isPending}
        />
      ) : null}

      {sortedTargets.length === 0 ? (
        <EmptyState
          message="no targets set yet"
          nudge="tell Claude, or set one"
          action={{ label: "New target", onClick: handleOpenCreate }}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line dark:border-line-dark">
          <table className="w-full min-w-[520px] text-left text-sm">
            <caption className="sr-only">Versioned targets, most recent effective date first</caption>
            <thead className="border-b border-line text-xs uppercase tracking-wide text-ink-tertiary dark:border-line-dark dark:text-ink-secondary-dark">
              <tr>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Effective from
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Calories
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Protein (g)
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Carbs (g)
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Fat (g)
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedTargets.map((target, index) => (
                <tr key={target.id} className="border-b border-line last:border-0 dark:border-line-dark/60">
                  <td className="px-3 py-2 font-medium">
                    {target.effectiveFrom}
                    {index === 0 ? (
                      <span className="ml-2 rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent dark:bg-accent-soft-dark dark:text-accent-dark">
                        Current
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">{target.baseCalories}</td>
                  <td className="px-3 py-2">{target.proteinG}</td>
                  <td className="px-3 py-2">{target.carbsG}</td>
                  <td className="px-3 py-2">{target.fatG}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function TargetForm({
  values,
  onChange,
  onSubmit,
  error,
  isPending
}: {
  values: TargetFormValues;
  onChange: (next: TargetFormValues) => void;
  onSubmit: (event: FormEvent) => void;
  error: string | null;
  isPending: boolean;
}): JSX.Element {
  const headingId = useId();
  const effectiveFromId = useId();
  const caloriesId = useId();
  const proteinId = useId();
  const carbsId = useId();
  const fatId = useId();

  return (
    <div
      role="region"
      aria-labelledby={headingId}
      className="space-y-4 rounded-lg border border-line p-4 dark:border-line-dark"
    >
      <h2 id={headingId} className="text-lg font-medium">
        New target
      </h2>
      <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
        Creates a new versioned target. It never edits an earlier one &mdash; past targets stay as
        they were logged.
      </p>
      <form onSubmit={onSubmit} noValidate className="space-y-4" aria-label="New target">
        <div>
          <label htmlFor={effectiveFromId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
            Effective from
          </label>
          <input
            id={effectiveFromId}
            type="date"
            value={values.effectiveFrom}
            onChange={(event) => onChange({ ...values, effectiveFrom: event.target.value })}
            className="focus-ring w-full max-w-xs rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label htmlFor={caloriesId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
              Base calories
            </label>
            <input
              id={caloriesId}
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={values.baseCalories}
              onChange={(event) => onChange({ ...values, baseCalories: event.target.value })}
              className="focus-ring w-full rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
            />
          </div>
          <div>
            <label htmlFor={proteinId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
              Protein (g)
            </label>
            <input
              id={proteinId}
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={values.proteinG}
              onChange={(event) => onChange({ ...values, proteinG: event.target.value })}
              className="focus-ring w-full rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
            />
          </div>
          <div>
            <label htmlFor={carbsId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
              Carbs (g)
            </label>
            <input
              id={carbsId}
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={values.carbsG}
              onChange={(event) => onChange({ ...values, carbsG: event.target.value })}
              className="focus-ring w-full rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
            />
          </div>
          <div>
            <label htmlFor={fatId} className="mb-1 block text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">
              Fat (g)
            </label>
            <input
              id={fatId}
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={values.fatG}
              onChange={(event) => onChange({ ...values, fatG: event.target.value })}
              className="focus-ring w-full rounded-md border border-line px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
            />
          </div>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {error}
          </p>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            type="submit"
            disabled={isPending}
            className="focus-ring rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent disabled:opacity-50"
          >
            {isPending ? "Creating..." : "Create target"}
          </button>
        </div>
      </form>
    </div>
  );
}

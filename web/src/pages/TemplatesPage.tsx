/**
 * Templates manager (T-079, spec §7): `/templates`.
 *
 * A list of templates with item counts, a name + item-repeater edit form
 * (create and edit share the same modal), ad-hoc items with inline macro
 * fields, and a one-click "Log now" per template.
 *
 * Item-repeater reuse (per task instructions, don't duplicate T-073):
 * `TemplateItemRequest` is field-for-field identical to the meal editor's
 * `MealItemRequest`, so this page reuses `MealItemRow` (food search or
 * ad-hoc macro entry per row) and `MealEditorItem`/`createBlankItem`
 * directly from `components/MealEditor` — only the name+repeater shell
 * around those rows is template-specific (templates have a name instead of
 * a meal-type/time, per CLAUDE.md/spec, so the full `MealEditor` component
 * — which bundles meal-type/time pickers — isn't reused wholesale).
 *
 * "Log now" scale decision: spec §7's Templates manager section describes
 * "Log now" as a single button and doesn't mention `quantity_scale` there
 * (unlike §6/the MCP tool surface, which exposes it explicitly). This UI
 * therefore logs at the default scale (1) with one click — today, current
 * time, meal type inferred from the current time, matching how "Log a
 * meal" behaves elsewhere. A per-log scale input would double the surface
 * of every list row for a case the manager-page spec doesn't ask for;
 * scaled logging is already available via the MCP tool if needed. See the
 * task report for the full reasoning.
 *
 * Create/delete decision: the spec's "edit form" line only explicitly
 * covers editing, but `create_template`/`delete_template` both exist in the
 * domain layer (spec §4) and a manager page with no way to add or remove a
 * template isn't a manager, so this page adds a "New template" button
 * (opens the same form modal in create mode) and a per-row soft-delete
 * button, matching the direct-delete-button convention already used for
 * meals/items in `DayPage.tsx` (no separate confirmation dialog exists
 * anywhere else in this codebase to reuse).
 */

import { useId, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createTemplate, deleteTemplate, logTemplate, updateTemplate, listTemplates } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import { queryKeys } from "../lib/queryClient";
import { useToast } from "../design/useToast";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import Modal from "../design/Modal";
import { MealItemRow } from "../components/MealEditor";
import { createBlankItem, type MealEditorItem } from "../components/MealEditor/types";
import { inferMealTypeFromLocalTime } from "../components/MealEditor/mealTiming";
import {
  buildCreateTemplateRequest,
  buildUpdateTemplateRequest,
  summarizeTemplateItems,
  templateItemToEditorItem
} from "../lib/templateForms";
import type { DayResponse, LogTemplateRequest, Template } from "../lib/api/types";

function todayLocalDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function domainErrorMessage(error: unknown): string | null {
  if (error instanceof ApiError && error.body && typeof error.body === "object" && "message" in error.body) {
    const message = (error.body as { message?: unknown }).message;
    return typeof message === "string" ? message : null;
  }
  return null;
}

interface TemplateFormValues {
  name: string;
  items: MealEditorItem[];
}

function blankFormValues(): TemplateFormValues {
  return { name: "", items: [createBlankItem()] };
}

function formValuesFromTemplate(template: Template): TemplateFormValues {
  return { name: template.name, items: template.items.map(templateItemToEditorItem) };
}

export default function TemplatesPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createValues, setCreateValues] = useState<TemplateFormValues>(blankFormValues());
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null);
  const [editValues, setEditValues] = useState<TemplateFormValues | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  const [loggingTemplateId, setLoggingTemplateId] = useState<number | null>(null);

  const templatesQuery = useQuery({
    queryKey: queryKeys.templates(),
    queryFn: () => listTemplates()
  });

  const createTemplateMutation = useMutation({
    mutationFn: (payload: NonNullable<ReturnType<typeof buildCreateTemplateRequest>>) => createTemplate(payload),
    onSuccess: () => {
      showToast("Template created.", "success");
      handleCloseCreate();
    },
    onError: (error) => {
      setCreateError(domainErrorMessage(error) ?? "Could not create template.");
      showToast("Could not create template.", "error");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    }
  });

  const updateTemplateMutation = useMutation({
    mutationFn: ({ templateId, payload }: { templateId: number; payload: NonNullable<ReturnType<typeof buildUpdateTemplateRequest>> }) =>
      updateTemplate(templateId, payload),
    onSuccess: () => {
      showToast("Template updated.", "success");
      handleCloseEdit();
    },
    onError: (error) => {
      setEditError(domainErrorMessage(error) ?? "Could not update template.");
      showToast("Could not update template.", "error");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    }
  });

  const deleteTemplateMutation = useMutation({
    mutationFn: (templateId: number) => deleteTemplate(templateId),
    onMutate: async (templateId: number) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.templates() });
      const previous = queryClient.getQueryData<Template[]>(queryKeys.templates());
      if (previous) {
        queryClient.setQueryData(
          queryKeys.templates(),
          previous.filter((template) => template.id !== templateId)
        );
      }
      return { previous };
    },
    onError: (_error, _templateId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.templates(), context.previous);
      }
      showToast("Could not delete template.", "error");
    },
    onSuccess: () => {
      showToast("Template deleted.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.templates() });
    }
  });

  const logTemplateMutation = useMutation({
    mutationFn: ({ templateId, payload }: { templateId: number; payload: LogTemplateRequest }) =>
      logTemplate(templateId, payload),
    onMutate: async () => {
      const localDate = todayLocalDate();
      await queryClient.cancelQueries({ queryKey: queryKeys.day(localDate) });
      const previous = queryClient.getQueryData<DayResponse>(queryKeys.day(localDate));
      return { previous, localDate };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.day(context.localDate), context.previous);
      }
      showToast("Could not log template.", "error");
    },
    onSuccess: () => {
      showToast("Logged today's meal.", "success");
    },
    onSettled: (_data, _error, _vars, context) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.day(context?.localDate ?? todayLocalDate()) });
      setLoggingTemplateId(null);
    }
  });

  function handleOpenCreate(): void {
    setCreateValues(blankFormValues());
    setCreateError(null);
    setIsCreateOpen(true);
  }

  function handleCloseCreate(): void {
    setIsCreateOpen(false);
    setCreateValues(blankFormValues());
    setCreateError(null);
  }

  function handleSubmitCreate(event: FormEvent): void {
    event.preventDefault();
    const payload = buildCreateTemplateRequest(createValues.name, createValues.items);
    if (!payload) {
      setCreateError("Add a name and at least one item with a quantity.");
      return;
    }
    setCreateError(null);
    createTemplateMutation.mutate(payload);
  }

  function handleOpenEdit(template: Template): void {
    setEditingTemplate(template);
    setEditValues(formValuesFromTemplate(template));
    setEditError(null);
  }

  function handleCloseEdit(): void {
    setEditingTemplate(null);
    setEditValues(null);
    setEditError(null);
  }

  function handleSubmitEdit(event: FormEvent): void {
    event.preventDefault();
    if (!editingTemplate || !editValues) {
      return;
    }
    const payload = buildUpdateTemplateRequest(editValues.name, editValues.items);
    if (!payload) {
      setEditError("Add a name and at least one item with a quantity.");
      return;
    }
    setEditError(null);
    updateTemplateMutation.mutate({ templateId: editingTemplate.id, payload });
  }

  function handleLogNow(template: Template): void {
    setLoggingTemplateId(template.id);
    const now = new Date();
    logTemplateMutation.mutate({
      templateId: template.id,
      payload: {
        loggedAt: now.toISOString(),
        localTz: Intl.DateTimeFormat().resolvedOptions().timeZone,
        mealType: inferMealTypeFromLocalTime(now),
        quantityScale: 1
      }
    });
  }

  if (templatesQuery.isLoading) {
    return (
      <section className="space-y-6">
        <h1 className="text-3xl font-bold tracking-tight">Templates</h1>
        <Skeleton className="h-10 w-full max-w-sm" label="Loading templates" />
        <Skeleton className="h-48 w-full" />
      </section>
    );
  }

  if (templatesQuery.isError) {
    return (
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Templates</h1>
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load templates.
        </p>
        <button
          type="button"
          onClick={() => void templatesQuery.refetch()}
          className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Retry
        </button>
      </section>
    );
  }

  const templates = templatesQuery.data ?? [];

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-bold tracking-tight">Templates</h1>
        <button
          type="button"
          onClick={handleOpenCreate}
          className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700"
        >
          New template
        </button>
      </div>

      {templates.length === 0 ? (
        <EmptyState
          message="no templates yet"
          nudge="tell Claude, or add one"
          action={{ label: "New template", onClick: handleOpenCreate }}
        />
      ) : (
        <ul className="space-y-3">
          {templates.map((template) => (
            <li
              key={template.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800"
            >
              <div>
                <button
                  type="button"
                  onClick={() => handleOpenEdit(template)}
                  className="focus-ring rounded-md text-left font-medium text-sky-700 hover:underline dark:text-sky-400"
                >
                  {template.name}
                </button>
                <p className="text-sm text-slate-500 dark:text-slate-400">{summarizeTemplateItems(template)}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleLogNow(template)}
                  disabled={logTemplateMutation.isPending && loggingTemplateId === template.id}
                  className="focus-ring rounded-md bg-sky-600 px-3 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
                >
                  {logTemplateMutation.isPending && loggingTemplateId === template.id ? "Logging..." : "Log now"}
                </button>
                <button
                  type="button"
                  onClick={() => deleteTemplateMutation.mutate(template.id)}
                  disabled={deleteTemplateMutation.isPending}
                  className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {isCreateOpen ? (
        <TemplateFormModal
          title="New template"
          values={createValues}
          onChange={setCreateValues}
          onClose={handleCloseCreate}
          onSubmit={handleSubmitCreate}
          error={createError}
          isPending={createTemplateMutation.isPending}
          submitLabel="Create template"
          pendingLabel="Creating..."
        />
      ) : null}

      {editingTemplate && editValues ? (
        <TemplateFormModal
          title={`Edit ${editingTemplate.name}`}
          values={editValues}
          onChange={setEditValues}
          onClose={handleCloseEdit}
          onSubmit={handleSubmitEdit}
          error={editError}
          isPending={updateTemplateMutation.isPending}
          submitLabel="Save changes"
          pendingLabel="Saving..."
          note="Editing items here only affects future uses of this template — meals already logged from it are unaffected."
        />
      ) : null}
    </section>
  );
}

function TemplateFormModal({
  title,
  values,
  onChange,
  onClose,
  onSubmit,
  error,
  isPending,
  submitLabel,
  pendingLabel,
  note
}: {
  title: string;
  values: TemplateFormValues;
  onChange: (next: TemplateFormValues) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent) => void;
  error: string | null;
  isPending: boolean;
  submitLabel: string;
  pendingLabel: string;
  note?: string;
}): JSX.Element {
  const titleId = useId();
  const nameId = useId();

  function handleItemChange(index: number, next: MealEditorItem): void {
    onChange({ ...values, items: values.items.map((item, itemIndex) => (itemIndex === index ? next : item)) });
  }

  function handleAddItem(): void {
    onChange({ ...values, items: [...values.items, createBlankItem()] });
  }

  function handleRemoveItem(index: number): void {
    if (values.items.length <= 1) {
      return;
    }
    onChange({ ...values, items: values.items.filter((_, itemIndex) => itemIndex !== index) });
  }

  return (
    <Modal isOpen onClose={onClose} titleId={titleId}>
      <h2 id={titleId} className="mb-1 text-lg font-semibold">
        {title}
      </h2>
      {note ? <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">{note}</p> : null}
      <form onSubmit={onSubmit} noValidate className="space-y-4" aria-label="Template editor">
        <div>
          <label htmlFor={nameId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Template name
          </label>
          <input
            id={nameId}
            type="text"
            value={values.name}
            onChange={(event) => onChange({ ...values, name: event.target.value })}
            placeholder="e.g. Weekday breakfast"
            className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          />
        </div>

        <div className="space-y-3">
          {values.items.map((item, index) => (
            <MealItemRow
              key={item.key}
              item={item}
              index={index}
              canRemove={values.items.length > 1}
              onChange={(next) => handleItemChange(index, next)}
              onRemove={() => handleRemoveItem(index)}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={handleAddItem}
          className="focus-ring rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Add item
        </button>

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
            {isPending ? pendingLabel : submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

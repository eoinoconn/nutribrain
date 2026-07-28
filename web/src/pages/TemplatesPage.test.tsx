import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TemplatesPage from "./TemplatesPage";
import { ToastProvider } from "../design/Toast";
import {
  createTemplate,
  deleteTemplate,
  listFoods,
  listTemplates,
  logTemplate,
  updateTemplate
} from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import type { Template } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  listTemplates: vi.fn(),
  createTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  deleteTemplate: vi.fn(),
  logTemplate: vi.fn(),
  listFoods: vi.fn()
}));

const mockedListTemplates = vi.mocked(listTemplates);
const mockedCreateTemplate = vi.mocked(createTemplate);
const mockedUpdateTemplate = vi.mocked(updateTemplate);
const mockedDeleteTemplate = vi.mocked(deleteTemplate);
const mockedLogTemplate = vi.mocked(logTemplate);
const mockedListFoods = vi.mocked(listFoods);

function makeTemplate(overrides: Partial<Template> = {}): Template {
  return {
    id: 1,
    name: "Weekday breakfast",
    createdAt: "2026-01-01T00:00:00Z",
    deletedAt: null,
    items: [
      {
        id: 10,
        foodId: 5,
        name: "Oatmeal",
        quantity: 100,
        quantityUnit: "g",
        calories: null,
        proteinG: null,
        carbsG: null,
        fatG: null,
        fiberG: null,
        satFatG: null,
        sodiumMg: null
      }
    ],
    ...overrides
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
  return render(<TemplatesPage />, { wrapper });
}

describe("TemplatesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListFoods.mockResolvedValue([]);
  });

  it("shows a loading skeleton on first paint", () => {
    mockedListTemplates.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state with retry when the query fails", async () => {
    mockedListTemplates.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load templates/i);
  });

  it("shows an empty state nudge with a new-template action when there are no templates", async () => {
    mockedListTemplates.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("no templates yet")).toBeInTheDocument();
    expect(screen.getByText(/tell claude, or add one/i)).toBeInTheDocument();
  });

  it("shows item counts and a summary of item names", async () => {
    mockedListTemplates.mockResolvedValue([
      makeTemplate({
        items: [
          { ...makeTemplate().items[0]!, name: "Oatmeal" },
          { ...makeTemplate().items[0]!, id: 11, name: "Blueberries" }
        ]
      })
    ]);
    renderPage();
    expect(await screen.findByText(/2 items: Oatmeal, Blueberries/i)).toBeInTheDocument();
  });

  it("opens the create modal, validates, and submits a new template", async () => {
    mockedListTemplates.mockResolvedValue([]);
    mockedCreateTemplate.mockResolvedValue(makeTemplate());
    renderPage();
    await screen.findByText("no templates yet");

    fireEvent.click(screen.getAllByRole("button", { name: /new template/i })[0]!);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    // Submitting without a name or quantity shows a validation message instead of calling the API.
    const dialog = screen.getByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: /create template/i }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/add a name and at least one item/i);
    expect(mockedCreateTemplate).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/template name/i), { target: { value: "Weekday breakfast" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));
    fireEvent.change(screen.getByLabelText(/name \(item 1\)/i), { target: { value: "Oatmeal" } });
    fireEvent.change(screen.getByLabelText(/quantity/i), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "150" } });

    fireEvent.click(screen.getByRole("button", { name: /create template/i }));

    await waitFor(() =>
      expect(mockedCreateTemplate).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Weekday breakfast",
          items: [expect.objectContaining({ name: "Oatmeal", quantity: 100, calories: 150 })]
        })
      )
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("opens the edit modal prefilled with the template's existing items and submits an update", async () => {
    const template = makeTemplate();
    mockedListTemplates.mockResolvedValue([template]);
    mockedUpdateTemplate.mockResolvedValue(template);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /weekday breakfast/i }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/only affects future uses of this template/i);
    expect(screen.getByLabelText(/template name/i)).toHaveValue("Weekday breakfast");

    fireEvent.change(screen.getByLabelText(/template name/i), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() =>
      expect(mockedUpdateTemplate).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ name: "Renamed" })
      )
    );
  });

  it("shows a domain error message on a failed update instead of closing the modal", async () => {
    const template = makeTemplate();
    mockedListTemplates.mockResolvedValue([template]);
    mockedUpdateTemplate.mockRejectedValue(new ApiError(422, "validation error", { message: "Something went wrong" }));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /weekday breakfast/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("deletes a template optimistically with a success toast", async () => {
    mockedListTemplates.mockResolvedValueOnce([makeTemplate()]);
    mockedListTemplates.mockResolvedValue([]);
    mockedDeleteTemplate.mockResolvedValue({ deleted: true });
    renderPage();

    await screen.findByText("Weekday breakfast");
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(screen.queryByText("Weekday breakfast")).not.toBeInTheDocument());
    await waitFor(() => expect(mockedDeleteTemplate).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/template deleted/i)).toBeInTheDocument();
  });

  it("rolls back an optimistic delete on failure and shows an error toast", async () => {
    mockedListTemplates.mockResolvedValue([makeTemplate()]);
    mockedDeleteTemplate.mockRejectedValue(new Error("boom"));
    renderPage();

    await screen.findByText("Weekday breakfast");
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));

    expect(await screen.findByText(/could not delete template/i)).toBeInTheDocument();
    expect(await screen.findByText("Weekday breakfast")).toBeInTheDocument();
  });

  it("logs a template now at the default scale with a success toast", async () => {
    mockedListTemplates.mockResolvedValue([makeTemplate()]);
    mockedLogTemplate.mockResolvedValue({
      id: 99,
      loggedAt: "2026-07-28T12:00:00Z",
      localTz: "UTC",
      localDate: "2026-07-28",
      mealType: "lunch",
      notes: null,
      items: [],
      totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null },
      deltaVsTarget: null
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /log now/i }));

    await waitFor(() =>
      expect(mockedLogTemplate).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ quantityScale: 1 })
      )
    );
    expect(await screen.findByText(/logged today's meal/i)).toBeInTheDocument();
  });

  it("shows an error toast when logging a template fails", async () => {
    mockedListTemplates.mockResolvedValue([makeTemplate()]);
    mockedLogTemplate.mockRejectedValue(new Error("boom"));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /log now/i }));

    expect(await screen.findByText(/could not log template/i)).toBeInTheDocument();
  });
});

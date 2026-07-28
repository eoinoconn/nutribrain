import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MealEditor from "./MealEditor";
import type { MealEditorValue } from "./types";
import { listFoods } from "../../lib/api/client";
import type { FoodSearchResult } from "../../lib/api/types";

vi.mock("../../lib/api/client", () => ({
  listFoods: vi.fn()
}));

const mockedListFoods = vi.mocked(listFoods);

function makeFood(overrides: Partial<FoodSearchResult>): FoodSearchResult {
  return {
    id: 1,
    name: "Chicken breast",
    servingSize: 100,
    servingUnit: "g",
    calories: 165,
    proteinG: 31,
    carbsG: 0,
    fatG: 3.6,
    fiberG: null,
    satFatG: null,
    sodiumMg: null,
    densityGPerMl: null,
    isFavorite: false,
    createdAt: "2026-01-01T00:00:00Z",
    lastLoggedAt: null,
    loggedCount: 0,
    ...overrides
  };
}

function renderEditor(props: Partial<React.ComponentProps<typeof MealEditor>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<MealEditor {...props} />, { wrapper });
}

describe("MealEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListFoods.mockResolvedValue([]);
  });

  it("renders one blank item by default and adds/removes items", () => {
    renderEditor();

    expect(screen.getAllByRole("group")).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: /add item/i }));
    expect(screen.getAllByRole("group")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /remove item 2/i }));
    expect(screen.getAllByRole("group")).toHaveLength(1);
  });

  it("disables removing the last remaining item", () => {
    renderEditor();

    const removeButton = screen.getByRole("button", { name: /remove item 1/i });
    expect(removeButton).toBeDisabled();
  });

  it("defaults the meal-type dropdown from the injected local time (breakfast window)", () => {
    renderEditor({ now: new Date(2026, 0, 1, 8, 0) });

    expect(screen.getByLabelText(/meal type/i)).toHaveValue("breakfast");
  });

  it("defaults to lunch inside the 11:00-15:59 window", () => {
    renderEditor({ now: new Date(2026, 0, 1, 12, 30) });
    expect(screen.getByLabelText(/meal type/i)).toHaveValue("lunch");
  });

  it("defaults to dinner inside the 16:00-21:59 window", () => {
    renderEditor({ now: new Date(2026, 0, 1, 20, 0) });
    expect(screen.getByLabelText(/meal type/i)).toHaveValue("dinner");
  });

  it("defaults to snack outside the natural windows", () => {
    renderEditor({ now: new Date(2026, 0, 1, 2, 0) });
    expect(screen.getByLabelText(/meal type/i)).toHaveValue("snack");
  });

  it("lets the user override the meal-type default", () => {
    renderEditor({ now: new Date(2026, 0, 1, 8, 0) });

    fireEvent.change(screen.getByLabelText(/meal type/i), { target: { value: "dinner" } });
    expect(screen.getByLabelText(/meal type/i)).toHaveValue("dinner");
  });

  it("defaults the time picker to the injected now", () => {
    renderEditor({ now: new Date(2026, 0, 1, 8, 5) });
    expect(screen.getByLabelText(/^time$/i)).toHaveValue("08:05");
  });

  it("toggles ad-hoc mode: macro fields appear and food search disappears, and vice versa", () => {
    renderEditor();

    expect(screen.getByRole("combobox", { name: /food \(item 1\)/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^calories$/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));

    expect(screen.queryByRole("combobox", { name: /food \(item 1\)/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/name \(item 1\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^calories$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/protein \(g\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/carbs \(g\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^fat \(g\)$/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));

    expect(screen.getByRole("combobox", { name: /food \(item 1\)/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^calories$/i)).not.toBeInTheDocument();
  });

  it("clears the picked foodId when switching to ad-hoc, and clears macro fields when switching back", () => {
    const handleChange = vi.fn<(value: MealEditorValue) => void>();
    renderEditor({ onChange: handleChange });

    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));
    fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "200" } });

    let lastValue = handleChange.mock.calls.at(-1)?.[0];
    expect(lastValue?.items[0]).toMatchObject({ isAdHoc: true, foodId: null, calories: 200 });

    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));

    lastValue = handleChange.mock.calls.at(-1)?.[0];
    expect(lastValue?.items[0]).toMatchObject({ isAdHoc: false, foodId: null, calories: null });
  });

  it("updates quantity and unit fields", () => {
    const handleChange = vi.fn<(value: MealEditorValue) => void>();
    renderEditor({ onChange: handleChange });

    fireEvent.change(screen.getByLabelText(/quantity/i), { target: { value: "150" } });
    fireEvent.change(screen.getByLabelText(/unit/i), { target: { value: "cup" } });

    const lastValue = handleChange.mock.calls.at(-1)?.[0];
    expect(lastValue?.items[0]).toMatchObject({ quantity: 150, quantityUnit: "cup" });
  });

  it("shows food search results with a favorite marker and lets the user pick one", async () => {
    mockedListFoods.mockResolvedValue([
      makeFood({ id: 1, name: "Chicken breast", isFavorite: true }),
      makeFood({ id: 2, name: "Chickpeas", isFavorite: false })
    ]);
    const handleChange = vi.fn<(value: MealEditorValue) => void>();
    renderEditor({ onChange: handleChange });

    const searchBox = screen.getByRole("combobox", { name: /food \(item 1\)/i });
    fireEvent.focus(searchBox);
    fireEvent.change(searchBox, { target: { value: "chick" } });

    await waitFor(() => expect(mockedListFoods).toHaveBeenCalledWith({ q: "chick" }), { timeout: 1000 });

    const favoriteOption = await screen.findByRole("option", { name: /favorite chicken breast/i });
    expect(within(favoriteOption).getByLabelText("Favorite")).toBeInTheDocument();

    const nonFavoriteOption = screen.getByRole("option", { name: "Chickpeas" });
    expect(within(nonFavoriteOption).queryByLabelText("Favorite")).not.toBeInTheDocument();

    fireEvent.mouseDown(within(favoriteOption).getByRole("button"));

    const lastValue = handleChange.mock.calls.at(-1)?.[0];
    expect(lastValue?.items[0]).toMatchObject({ foodId: 1, name: "Chicken breast", isAdHoc: false });
  });

  it("lets the user pick a food search result with the keyboard alone (Arrow keys + Enter)", async () => {
    mockedListFoods.mockResolvedValue([
      makeFood({ id: 1, name: "Chicken breast", isFavorite: true }),
      makeFood({ id: 2, name: "Chickpeas", isFavorite: false })
    ]);
    const handleChange = vi.fn<(value: MealEditorValue) => void>();
    renderEditor({ onChange: handleChange });

    const searchBox = screen.getByRole("combobox", { name: /food \(item 1\)/i });
    fireEvent.focus(searchBox);
    fireEvent.change(searchBox, { target: { value: "chick" } });

    await screen.findByRole("option", { name: /favorite chicken breast/i });

    // ArrowDown twice wraps back to the first option; Enter picks whatever is highlighted.
    fireEvent.keyDown(searchBox, { key: "ArrowDown" });
    fireEvent.keyDown(searchBox, { key: "ArrowDown" });
    fireEvent.keyDown(searchBox, { key: "ArrowUp" });
    expect(searchBox).toHaveAttribute("aria-activedescendant");

    fireEvent.keyDown(searchBox, { key: "Enter" });

    const lastValue = handleChange.mock.calls.at(-1)?.[0];
    expect(lastValue?.items[0]).toMatchObject({ foodId: 1, name: "Chicken breast", isAdHoc: false });
  });

  it("closes the food search results on Escape without picking anything", async () => {
    mockedListFoods.mockResolvedValue([makeFood({ id: 1, name: "Chicken breast" })]);
    renderEditor();

    const searchBox = screen.getByRole("combobox", { name: /food \(item 1\)/i });
    fireEvent.focus(searchBox);
    fireEvent.change(searchBox, { target: { value: "chick" } });

    await screen.findByRole("option", { name: "Chicken breast" });
    fireEvent.keyDown(searchBox, { key: "Escape" });

    expect(screen.queryByRole("option", { name: "Chicken breast" })).not.toBeInTheDocument();
  });
});

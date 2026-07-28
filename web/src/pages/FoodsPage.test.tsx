import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FoodsPage from "./FoodsPage";
import { ToastProvider } from "../design/Toast";
import { createFood, listFoods, setFavoriteFood, updateFood } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import type { FoodSearchResult } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  listFoods: vi.fn(),
  createFood: vi.fn(),
  updateFood: vi.fn(),
  setFavoriteFood: vi.fn()
}));

const mockedListFoods = vi.mocked(listFoods);
const mockedCreateFood = vi.mocked(createFood);
const mockedUpdateFood = vi.mocked(updateFood);
const mockedSetFavoriteFood = vi.mocked(setFavoriteFood);

function makeFood(overrides: Partial<FoodSearchResult> = {}): FoodSearchResult {
  return {
    id: 1,
    name: "Chicken breast",
    servingSize: 100,
    servingUnit: "g",
    calories: 165,
    proteinG: 31,
    carbsG: 0,
    fatG: 3.6,
    fiberG: 0,
    satFatG: 1,
    sodiumMg: 74,
    densityGPerMl: null,
    isFavorite: false,
    createdAt: "2026-01-01T00:00:00Z",
    lastLoggedAt: null,
    loggedCount: 3,
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
  return render(<FoodsPage />, { wrapper });
}

describe("FoodsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading skeleton on first paint", () => {
    mockedListFoods.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state with retry when the query fails", async () => {
    mockedListFoods.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load foods/i);
  });

  it("shows an empty state nudge with an add-food action when there are no foods", async () => {
    mockedListFoods.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("no foods yet")).toBeInTheDocument();
    expect(screen.getByText(/tell claude, or add one/i)).toBeInTheDocument();
  });

  it("re-queries with the search term", async () => {
    mockedListFoods.mockResolvedValue([makeFood()]);
    renderPage();
    await screen.findByText("Chicken breast");

    fireEvent.change(screen.getByLabelText(/search foods/i), { target: { value: "chick" } });

    await waitFor(() => expect(mockedListFoods).toHaveBeenCalledWith({ q: "chick" }));
  });

  it("sorts the table by column on header click, toggling direction", async () => {
    mockedListFoods.mockResolvedValue([
      makeFood({ id: 1, name: "Banana", calories: 90 }),
      makeFood({ id: 2, name: "Apple", calories: 52 })
    ]);
    renderPage();
    await screen.findByText("Apple");

    const rowsInOrder = () => screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell"));
    // Default sort: name ascending.
    expect(rowsInOrder()[0]?.[1]).toHaveTextContent("Apple");

    fireEvent.click(screen.getByRole("button", { name: /^name/i }));
    expect(rowsInOrder()[0]?.[1]).toHaveTextContent("Banana");

    fireEvent.click(screen.getByRole("button", { name: /calories/i }));
    expect(rowsInOrder()[0]?.[1]).toHaveTextContent("Apple");
  });

  it("toggles favorite optimistically and shows a success toast", async () => {
    // First fetch has the food unfavorited; the post-mutation refetch (triggered by the
    // mutation's onSettled invalidate) reflects the authoritative favorited state, so the
    // optimistic update isn't clobbered by a stale re-fetch reverting it.
    mockedListFoods.mockResolvedValueOnce([makeFood({ isFavorite: false })]);
    mockedListFoods.mockResolvedValue([makeFood({ isFavorite: true })]);
    mockedSetFavoriteFood.mockResolvedValue({ ...makeFood(), isFavorite: true });
    renderPage();
    await screen.findByText("Chicken breast");

    const star = screen.getByRole("button", { name: /add chicken breast to favorites/i });
    fireEvent.click(star);

    expect(await screen.findByRole("button", { name: /remove chicken breast from favorites/i })).toBeInTheDocument();
    await waitFor(() => expect(mockedSetFavoriteFood).toHaveBeenCalledWith(1, true));
    expect(await screen.findByText(/added to favorites/i)).toBeInTheDocument();
  });

  it("rolls back the favorite toggle and shows an error toast on failure", async () => {
    mockedListFoods.mockResolvedValue([makeFood({ isFavorite: false })]);
    mockedSetFavoriteFood.mockRejectedValue(new Error("boom"));
    renderPage();
    await screen.findByText("Chicken breast");

    fireEvent.click(screen.getByRole("button", { name: /add chicken breast to favorites/i }));

    expect(await screen.findByText(/could not update favorite/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add chicken breast to favorites/i })).toBeInTheDocument();
  });

  it("opens the edit modal on row click, prefilled, with serving unit disabled", async () => {
    mockedListFoods.mockResolvedValue([makeFood()]);
    renderPage();
    await screen.findByText("Chicken breast");

    fireEvent.click(screen.getByRole("button", { name: "Chicken breast" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/^calories$/i)).toHaveValue(165);
    expect(within(dialog).getByLabelText(/serving unit/i)).toBeDisabled();
    expect(within(dialog).getByText(/logged in 3 meal items/i)).toBeInTheDocument();
  });

  it("submits only changed fields on save and shows the recompute count in the toast", async () => {
    mockedListFoods.mockResolvedValue([makeFood()]);
    mockedUpdateFood.mockResolvedValue({ food: makeFood({ calories: 200 }), recomputeCount: 4 });
    renderPage();
    await screen.findByText("Chicken breast");

    fireEvent.click(screen.getByRole("button", { name: "Chicken breast" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^calories$/i), { target: { value: "200" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(mockedUpdateFood).toHaveBeenCalledWith(1, { calories: 200 }));
    expect(await screen.findByText(/4 past meals recomputed/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the edit modal on Escape without saving", async () => {
    mockedListFoods.mockResolvedValue([makeFood()]);
    renderPage();
    await screen.findByText("Chicken breast");

    fireEvent.click(screen.getByRole("button", { name: "Chicken breast" }));
    await screen.findByRole("dialog");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockedUpdateFood).not.toHaveBeenCalled();
  });

  it("validates required fields in the add-food form without calling the API", async () => {
    mockedListFoods.mockResolvedValue([]);
    renderPage();
    await screen.findByText("no foods yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^add food$/i })[0]!);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^add food$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/required/i);
    expect(mockedCreateFood).not.toHaveBeenCalled();
  });

  it("adds a food and closes the modal with a success toast", async () => {
    mockedListFoods.mockResolvedValue([]);
    mockedCreateFood.mockResolvedValue(makeFood({ name: "Oats" }));
    renderPage();
    await screen.findByText("no foods yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^add food$/i })[0]!);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^name$/i), { target: { value: "Oats" } });
    fireEvent.change(within(dialog).getByLabelText(/serving size/i), { target: { value: "40" } });
    fireEvent.change(within(dialog).getByLabelText(/^calories$/i), { target: { value: "150" } });
    fireEvent.change(within(dialog).getByLabelText(/protein/i), { target: { value: "5" } });
    fireEvent.change(within(dialog).getByLabelText(/carbs/i), { target: { value: "27" } });
    fireEvent.change(within(dialog).getByLabelText(/^fat/i), { target: { value: "3" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^add food$/i }));

    await waitFor(() => expect(mockedCreateFood).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/food added/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("surfaces a food_duplicate error with a force-add retry", async () => {
    mockedListFoods.mockResolvedValue([]);
    mockedCreateFood.mockRejectedValueOnce(
      new ApiError(409, "Conflict", {
        error: "food_duplicate",
        message: "A food similar to 'Oats' already exists. Use force to override.",
        candidates: [{ id: 9, name: "Oatmeal", calories: 150 }]
      })
    );
    mockedCreateFood.mockResolvedValueOnce(makeFood({ name: "Oats" }));
    renderPage();
    await screen.findByText("no foods yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^add food$/i })[0]!);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^name$/i), { target: { value: "Oats" } });
    fireEvent.change(within(dialog).getByLabelText(/serving size/i), { target: { value: "40" } });
    fireEvent.change(within(dialog).getByLabelText(/^calories$/i), { target: { value: "150" } });
    fireEvent.change(within(dialog).getByLabelText(/protein/i), { target: { value: "5" } });
    fireEvent.change(within(dialog).getByLabelText(/carbs/i), { target: { value: "27" } });
    fireEvent.change(within(dialog).getByLabelText(/^fat/i), { target: { value: "3" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^add food$/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/oatmeal/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: /add anyway/i }));

    await waitFor(() => expect(mockedCreateFood).toHaveBeenCalledTimes(2));
    const secondCall = mockedCreateFood.mock.calls[1];
    expect(secondCall?.[0]?.force).toBe(true);
    expect(await screen.findByText(/food added/i)).toBeInTheDocument();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DayView from "./DayView";
import { ToastProvider } from "../design/Toast";
import {
  createMeal,
  deleteMeal,
  deleteMealItem,
  getDay,
  listFoods,
  setManualCaloriesOut,
  syncIntervals
} from "../lib/api/client";
import type { DayResponse, MealItem } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  getDay: vi.fn(),
  createMeal: vi.fn(),
  deleteMeal: vi.fn(),
  deleteMealItem: vi.fn(),
  setManualCaloriesOut: vi.fn(),
  syncIntervals: vi.fn(),
  listFoods: vi.fn()
}));

const mockedGetDay = vi.mocked(getDay);
const mockedCreateMeal = vi.mocked(createMeal);
const mockedDeleteMeal = vi.mocked(deleteMeal);
const mockedDeleteMealItem = vi.mocked(deleteMealItem);
const mockedSetManualCaloriesOut = vi.mocked(setManualCaloriesOut);
const mockedSyncIntervals = vi.mocked(syncIntervals);
const mockedListFoods = vi.mocked(listFoods);

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(
    2,
    "0"
  )}`;
}

function makeItem(overrides: Partial<MealItem> = {}): MealItem {
  return {
    id: 1,
    foodId: 10,
    name: "Chicken breast",
    quantity: 150,
    quantityUnit: "g",
    source: "label",
    macros: {
      calories: 250,
      proteinG: 40,
      carbsG: 0,
      fatG: 8,
      fiberG: 0,
      satFatG: 2,
      sodiumMg: 300
    },
    ...overrides
  };
}

function makeDay(overrides: Partial<DayResponse> = {}): DayResponse {
  return {
    date: "2026-07-20",
    meals: {},
    dayTotals: {
      calories: 0,
      proteinG: 0,
      carbsG: 0,
      fatG: 0,
      fiberG: null,
      satFatG: null,
      sodiumMg: null
    },
    effectiveTarget: null,
    deltaVsTarget: null,
    ...overrides
  };
}

function renderPage(route = "/day/2026-07-20") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/" element={<DayView />} />
        <Route path="/day/:date" element={<DayView />} />
      </Routes>
    </MemoryRouter>,
    { wrapper }
  );
}

describe("DayView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListFoods.mockResolvedValue([]);
  });

  describe("date routing", () => {
    it("resolves `/` to today's local date", async () => {
      mockedGetDay.mockResolvedValue(makeDay({ date: todayIso() }));
      renderPage("/");

      await waitFor(() => expect(mockedGetDay).toHaveBeenCalledWith(todayIso()));
      expect(await screen.findByRole("heading", { name: new RegExp(`Today.*${todayIso()}`) })).toBeInTheDocument();
    });

    it("renders the given date for `/day/:date`", async () => {
      mockedGetDay.mockResolvedValue(makeDay({ date: "2026-07-20" }));
      renderPage("/day/2026-07-20");

      await waitFor(() => expect(mockedGetDay).toHaveBeenCalledWith("2026-07-20"));
      expect(await screen.findByRole("heading", { name: /Day detail.*2026-07-20/ })).toBeInTheDocument();
    });

    it("rejects a malformed date route param without calling the API", async () => {
      renderPage("/day/not-a-date");
      expect(await screen.findByRole("alert")).toHaveTextContent(/isn't a valid date/i);
      expect(mockedGetDay).not.toHaveBeenCalled();
    });
  });

  it("shows a loading skeleton on first paint", () => {
    mockedGetDay.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state when the day query fails", async () => {
    mockedGetDay.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load/i);
  });

  it("renders the empty state with day-detail copy for a non-today date", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    renderPage();

    expect(await screen.findByText("no meals logged this day")).toBeInTheDocument();
  });

  it("renders the empty state with today copy when the route resolves to today", async () => {
    mockedGetDay.mockResolvedValue(makeDay({ date: todayIso() }));
    renderPage("/");

    expect(await screen.findByText("no meals logged today")).toBeInTheDocument();
  });

  it("only shows the sync button when the route date is today", async () => {
    mockedGetDay.mockResolvedValue(makeDay({ date: "2026-07-20" }));
    renderPage("/day/2026-07-20");

    await screen.findByText("no meals logged this day");
    expect(screen.queryByRole("button", { name: /sync intervals now/i })).not.toBeInTheDocument();
  });

  it("shows the sync button when the route resolves to today", async () => {
    mockedGetDay.mockResolvedValue(makeDay({ date: todayIso() }));
    mockedSyncIntervals.mockResolvedValue({ fromDate: todayIso(), toDate: todayIso(), daysSynced: 1, failures: [] });
    renderPage("/");

    expect(await screen.findByRole("button", { name: /sync intervals now/i })).toBeInTheDocument();
  });

  it("shows and submits the manual calories-out override on a non-today date", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        effectiveTarget: {
          effectiveFrom: "2026-07-01",
          baseCalories: 2000,
          proteinG: 150,
          carbsG: 200,
          fatG: 60,
          caloriesOut: 300,
          effectiveCalories: 2300
        }
      })
    );
    mockedSetManualCaloriesOut.mockResolvedValue({
      date: "2026-07-20",
      caloriesOut: 450,
      fetchedAt: "2026-07-20T12:00:00Z"
    });
    renderPage();

    const input = await screen.findByLabelText(/calories out \(manual\)/i);
    expect(input).toHaveValue(300);

    fireEvent.change(input, { target: { value: "450" } });
    fireEvent.click(screen.getByRole("button", { name: /^set$/i }));

    await waitFor(() =>
      expect(mockedSetManualCaloriesOut).toHaveBeenCalledWith({ date: "2026-07-20", caloriesOut: 450 })
    );
    expect(await screen.findByText(/calories-out override saved/i)).toBeInTheDocument();
  });

  it("deletes a meal item on today's route: optimistic removal, API call, success toast", async () => {
    const dayWithItem = makeDay({
      date: todayIso(),
      meals: {
        breakfast: [
          {
            id: 5,
            loggedAt: `${todayIso()}T08:00:00Z`,
            mealType: "breakfast",
            notes: null,
            items: [makeItem()],
            totals: { calories: 250, proteinG: 40, carbsG: 0, fatG: 8, fiberG: 0, satFatG: 2, sodiumMg: 300 }
          }
        ]
      }
    });
    mockedGetDay.mockResolvedValueOnce(dayWithItem);
    mockedGetDay.mockResolvedValue(makeDay({ date: todayIso() }));
    mockedDeleteMealItem.mockResolvedValue({ deleted: true });
    renderPage("/");

    fireEvent.click(await screen.findByRole("button", { name: /breakfast/i }));
    expect(await screen.findByText("Chicken breast")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));

    await waitFor(() => expect(screen.queryByText("Chicken breast")).not.toBeInTheDocument());
    await waitFor(() => expect(mockedDeleteMealItem).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/item deleted/i)).toBeInTheDocument();
  });

  it("deletes a whole meal group", async () => {
    const dayWithMeal = makeDay({
      meals: {
        breakfast: [
          {
            id: 5,
            loggedAt: "2026-07-20T08:00:00Z",
            mealType: "breakfast",
            notes: null,
            items: [makeItem()],
            totals: { calories: 250, proteinG: 40, carbsG: 0, fatG: 8, fiberG: 0, satFatG: 2, sodiumMg: 300 }
          }
        ]
      }
    });
    mockedGetDay.mockResolvedValueOnce(dayWithMeal);
    mockedGetDay.mockResolvedValue(makeDay());
    mockedDeleteMeal.mockResolvedValue({ deleted: true });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /breakfast/i }));
    fireEvent.click(await screen.findByRole("button", { name: /delete meal/i }));

    await waitFor(() => expect(screen.queryByText("Chicken breast")).not.toBeInTheDocument());
    await waitFor(() => expect(mockedDeleteMeal).toHaveBeenCalledWith(5));
    expect(await screen.findByText(/meal deleted/i)).toBeInTheDocument();
  });

  it("edits an item: delete-then-relog via delete_meal_item + create_meal, success toast", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        meals: {
          breakfast: [
            {
              id: 5,
              loggedAt: "2026-07-20T08:00:00Z",
              mealType: "breakfast",
              notes: null,
              items: [makeItem()],
              totals: { calories: 250, proteinG: 40, carbsG: 0, fatG: 8, fiberG: 0, satFatG: 2, sodiumMg: 300 }
            }
          ]
        }
      })
    );
    mockedDeleteMealItem.mockResolvedValue({ deleted: true });
    mockedCreateMeal.mockResolvedValue({
      id: 42,
      loggedAt: "2026-07-20T08:00:00",
      localTz: "UTC",
      localDate: "2026-07-20",
      mealType: "breakfast",
      notes: null,
      items: [],
      totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null },
      deltaVsTarget: null
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /breakfast/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^edit$/i }));

    const quantityInput = await screen.findByLabelText(/quantity/i);
    fireEvent.change(quantityInput, { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: /save item/i }));

    await waitFor(() => expect(mockedDeleteMealItem).toHaveBeenCalledWith(1));
    await waitFor(() => expect(mockedCreateMeal).toHaveBeenCalledTimes(1));

    const [request] = mockedCreateMeal.mock.calls[0]!;
    expect(request.items[0]?.quantity).toBe(200);
    expect(request.items[0]?.foodId).toBe(10);
    expect(request.mealType).toBe("breakfast");

    expect(await screen.findByText(/item updated/i)).toBeInTheDocument();
  });

  it("logs a new meal via the shared MealEditor for this date", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    mockedCreateMeal.mockResolvedValue({
      id: 99,
      loggedAt: "2026-07-20T08:00:00",
      localTz: "UTC",
      localDate: "2026-07-20",
      mealType: "breakfast",
      notes: null,
      items: [],
      totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null },
      deltaVsTarget: null
    });
    renderPage();

    fireEvent.click((await screen.findAllByRole("button", { name: /log a meal/i }))[0]!);
    fireEvent.change(screen.getByLabelText(/quantity/i), { target: { value: "150" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));
    fireEvent.change(screen.getByLabelText(/name \(item 1\)/i), { target: { value: "Snack bar" } });
    fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "200" } });

    fireEvent.click(screen.getByRole("button", { name: /save meal/i }));

    await waitFor(() => expect(mockedCreateMeal).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/meal logged/i)).toBeInTheDocument();

    // POST /api/meals rejects a naive (offset-less) logged_at.
    const [request] = mockedCreateMeal.mock.calls[0]!;
    expect(request.loggedAt).toMatch(/Z$|[+-]\d{2}:\d{2}$/);
  });
});

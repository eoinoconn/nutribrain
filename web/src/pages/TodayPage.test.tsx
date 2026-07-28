import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TodayPage from "./TodayPage";
import { ToastProvider } from "../design/Toast";
import { createMeal, getDay, listFoods, syncIntervals } from "../lib/api/client";
import type { DayResponse, MealItem } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  getDay: vi.fn(),
  createMeal: vi.fn(),
  syncIntervals: vi.fn(),
  listFoods: vi.fn()
}));

const mockedGetDay = vi.mocked(getDay);
const mockedCreateMeal = vi.mocked(createMeal);
const mockedSyncIntervals = vi.mocked(syncIntervals);
const mockedListFoods = vi.mocked(listFoods);

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
    date: "2026-07-27",
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

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
  return render(<TodayPage />, { wrapper });
}

describe("TodayPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListFoods.mockResolvedValue([]);
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

  it("renders the empty state with exact spec copy when there are no meals", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    renderPage();

    expect(await screen.findByText("no meals logged today")).toBeInTheDocument();
    expect(screen.getByText("tell Claude, or use the button")).toBeInTheDocument();
  });

  it("shows the target breakdown with calories-out data", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        effectiveTarget: {
          effectiveFrom: "2026-07-01",
          baseCalories: 2000,
          proteinG: 150,
          carbsG: 200,
          fatG: 60,
          caloriesOut: 500,
          effectiveCalories: 2500
        }
      })
    );
    renderPage();

    expect(await screen.findByText(/target 2,500 \(2,000 base \+ 500 out\)/i)).toBeInTheDocument();
  });

  it("shows the no-activity-data breakdown when calories-out is absent", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        effectiveTarget: {
          effectiveFrom: "2026-07-01",
          baseCalories: 2000,
          proteinG: 150,
          carbsG: 200,
          fatG: 60,
          caloriesOut: null,
          effectiveCalories: 2000
        }
      })
    );
    renderPage();

    expect(await screen.findByText(/target 2,000 \(no activity data\)/i)).toBeInTheDocument();
  });

  it("renders day totals and the calorie text summary", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        dayTotals: {
          calories: 1450,
          proteinG: 100.4,
          carbsG: 120,
          fatG: 40,
          fiberG: 20,
          satFatG: 10,
          sodiumMg: 1800
        },
        effectiveTarget: {
          effectiveFrom: "2026-07-01",
          baseCalories: 2200,
          proteinG: 150,
          carbsG: 200,
          fatG: 60,
          caloriesOut: null,
          effectiveCalories: 2200
        }
      })
    );
    renderPage();

    expect(await screen.findByText("1,450 / 2,200 calories")).toBeInTheDocument();
    expect(screen.getByText("100.4 / 150.0 g")).toBeInTheDocument();
    expect(screen.getByText("20.0 g")).toBeInTheDocument();
    expect(screen.getByText("1,800 mg")).toBeInTheDocument();
  });

  it("shows macro bars with progress against the effective target", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        dayTotals: {
          calories: 1450,
          proteinG: 120,
          carbsG: 100,
          fatG: 40,
          fiberG: 20,
          satFatG: 10,
          sodiumMg: 1800
        },
        effectiveTarget: {
          effectiveFrom: "2026-07-01",
          baseCalories: 2200,
          proteinG: 150,
          carbsG: 200,
          fatG: 60,
          caloriesOut: null,
          effectiveCalories: 2200
        }
      })
    );
    renderPage();

    expect(await screen.findByText("120.0 / 150.0 g")).toBeInTheDocument();
    expect(screen.getByText("100.0 / 200.0 g")).toBeInTheDocument();
    expect(screen.getByText("40.0 / 60.0 g")).toBeInTheDocument();
    expect(screen.getByText("120.0 / 150.0 g protein")).toBeInTheDocument();
    expect(screen.getByText("100.0 / 200.0 g carbs")).toBeInTheDocument();
    expect(screen.getByText("40.0 / 60.0 g fat")).toBeInTheDocument();
  });

  it("shows macro totals without a progress fraction when no target is set", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        dayTotals: {
          calories: 1450,
          proteinG: 120,
          carbsG: 100,
          fatG: 40,
          fiberG: 20,
          satFatG: 10,
          sodiumMg: 1800
        },
        effectiveTarget: null
      })
    );
    renderPage();

    expect(await screen.findByText("120.0 g")).toBeInTheDocument();
    expect(screen.getByText("100.0 g")).toBeInTheDocument();
    expect(screen.getByText("40.0 g")).toBeInTheDocument();
    expect(screen.getByText("120.0 g protein (no target set)")).toBeInTheDocument();
    expect(screen.getByText("100.0 g carbs (no target set)")).toBeInTheDocument();
    expect(screen.getByText("40.0 g fat (no target set)")).toBeInTheDocument();
  });

  it("expands and collapses a meal group", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        meals: {
          breakfast: [
            {
              id: 1,
              loggedAt: "2026-07-27T08:00:00Z",
              mealType: "breakfast",
              notes: null,
              items: [makeItem()],
              totals: {
                calories: 250,
                proteinG: 40,
                carbsG: 0,
                fatG: 8,
                fiberG: 0,
                satFatG: 2,
                sodiumMg: 300
              }
            }
          ]
        }
      })
    );
    renderPage();

    const toggle = await screen.findByRole("button", { name: /breakfast/i });
    expect(screen.queryByText("Chicken breast")).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.getByText("Chicken breast")).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(screen.queryByText("Chicken breast")).not.toBeInTheDocument();
  });

  it("logs a meal: opens editor, submits, shows success toast, invalidates day query", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    mockedCreateMeal.mockResolvedValue({
      id: 99,
      loggedAt: "2026-07-27T08:00:00",
      localTz: "UTC",
      localDate: "2026-07-27",
      mealType: "breakfast",
      notes: null,
      items: [],
      totals: {
        calories: 0,
        proteinG: 0,
        carbsG: 0,
        fatG: 0,
        fiberG: null,
        satFatG: null,
        sodiumMg: null
      },
      deltaVsTarget: null
    });
    renderPage();

    fireEvent.click((await screen.findAllByRole("button", { name: /log a meal/i }))[0]!);
    expect(screen.getByRole("form", { name: /meal editor/i })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/quantity/i), { target: { value: "150" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));
    fireEvent.change(screen.getByLabelText(/name \(item 1\)/i), { target: { value: "Snack bar" } });
    fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "200" } });

    fireEvent.click(screen.getByRole("button", { name: /save meal/i }));

    await waitFor(() => expect(mockedCreateMeal).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/meal logged/i)).toBeInTheDocument();
    await waitFor(() => expect(mockedGetDay).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("form", { name: /meal editor/i })).not.toBeInTheDocument();

    // POST /api/meals rejects a naive (offset-less) logged_at as a domain
    // error — guard against regressing to string-concatenating one.
    const [request] = mockedCreateMeal.mock.calls[0]!;
    expect(request.loggedAt).toMatch(/Z$|[+-]\d{2}:\d{2}$/);
  });

  it("shows an error toast and keeps the editor open when logging a meal fails", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    mockedCreateMeal.mockRejectedValue(new Error("failed"));
    renderPage();

    fireEvent.click((await screen.findAllByRole("button", { name: /log a meal/i }))[0]!);
    fireEvent.change(screen.getByLabelText(/quantity/i), { target: { value: "150" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /ad-hoc/i }));
    fireEvent.change(screen.getByLabelText(/name \(item 1\)/i), { target: { value: "Snack bar" } });
    fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "200" } });

    fireEvent.click(screen.getByRole("button", { name: /save meal/i }));

    expect(await screen.findByText(/could not log meal/i)).toBeInTheDocument();
    expect(screen.getByRole("form", { name: /meal editor/i })).toBeInTheDocument();
  });

  it("syncs intervals: calls the endpoint, shows success toast, invalidates day query", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    mockedSyncIntervals.mockResolvedValue({
      fromDate: "2026-07-27",
      toDate: "2026-07-27",
      daysSynced: 1,
      failures: []
    });
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /sync intervals now/i }));

    await waitFor(() => expect(mockedSyncIntervals).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/synced with intervals/i)).toBeInTheDocument();
    await waitFor(() => expect(mockedGetDay).toHaveBeenCalledTimes(2));
  });

  it("shows an error toast when sync fails", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    mockedSyncIntervals.mockRejectedValue(new Error("nope"));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /sync intervals now/i }));

    expect(await screen.findByText(/sync failed/i)).toBeInTheDocument();
  });
});

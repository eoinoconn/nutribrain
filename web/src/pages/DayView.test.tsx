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
    energy: null,
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
      // 2026-07-20 is a Monday.
      expect(await screen.findByRole("heading", { name: /Monday.*2026-07-20/ })).toBeInTheDocument();
    });

    it("rejects a malformed date route param without calling the API", async () => {
      renderPage("/day/not-a-date");
      expect(await screen.findByRole("alert")).toHaveTextContent(/isn't a valid date/i);
      expect(mockedGetDay).not.toHaveBeenCalled();
    });
  });

  describe("date picker", () => {
    it("steps to the previous day and navigates to /day/:date", async () => {
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-20" }));
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-19" }));
      renderPage("/day/2026-07-20");

      await screen.findByRole("heading", { name: /2026-07-20/ });
      fireEvent.click(screen.getByRole("button", { name: /previous day/i }));

      await waitFor(() => expect(mockedGetDay).toHaveBeenCalledWith("2026-07-19"));
      expect(await screen.findByRole("heading", { name: /2026-07-19/ })).toBeInTheDocument();
    });

    it("steps to the next day and navigates to /day/:date", async () => {
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-20" }));
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-21" }));
      renderPage("/day/2026-07-20");

      await screen.findByRole("heading", { name: /2026-07-20/ });
      fireEvent.click(screen.getByRole("button", { name: /next day/i }));

      await waitFor(() => expect(mockedGetDay).toHaveBeenCalledWith("2026-07-21"));
      expect(await screen.findByRole("heading", { name: /2026-07-21/ })).toBeInTheDocument();
    });

    it("rolls over a month boundary correctly when stepping forward", async () => {
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-31" }));
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-08-01" }));
      renderPage("/day/2026-07-31");

      await screen.findByRole("heading", { name: /2026-07-31/ });
      fireEvent.click(screen.getByRole("button", { name: /next day/i }));

      await waitFor(() => expect(mockedGetDay).toHaveBeenCalledWith("2026-08-01"));
    });

    it("dims the body and shows an updating indicator while a date-step fetch is in flight, without unmounting the date picker", async () => {
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-20" }));
      let resolveSecondFetch: ((day: DayResponse) => void) | undefined;
      mockedGetDay.mockReturnValueOnce(
        new Promise<DayResponse>((resolve) => {
          resolveSecondFetch = resolve;
        })
      );
      renderPage("/day/2026-07-20");

      await screen.findByRole("heading", { name: /2026-07-20/ });
      fireEvent.click(screen.getByRole("button", { name: /previous day/i }));

      // While the new date's fetch is pending, the previous date's content
      // stays on screen (dimmed) rather than being replaced by the
      // first-paint skeleton or a blank page, and the date picker itself
      // (needed to navigate further, or back) stays mounted and usable.
      expect(await screen.findByText(/updating/i)).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /2026-07-20/ })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /previous day/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /next day/i })).toBeInTheDocument();

      resolveSecondFetch?.(makeDay({ date: "2026-07-19" }));

      expect(await screen.findByRole("heading", { name: /2026-07-19/ })).toBeInTheDocument();
      expect(screen.queryByText(/updating/i)).not.toBeInTheDocument();
    });

    it("jumps to a directly-entered date via the native date input", async () => {
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-20" }));
      mockedGetDay.mockResolvedValueOnce(makeDay({ date: "2026-07-10" }));
      renderPage("/day/2026-07-20");

      await screen.findByRole("heading", { name: /2026-07-20/ });
      fireEvent.change(screen.getByLabelText(/select date/i), { target: { value: "2026-07-10" } });

      await waitFor(() => expect(mockedGetDay).toHaveBeenCalledWith("2026-07-10"));
      expect(await screen.findByRole("heading", { name: /2026-07-10/ })).toBeInTheDocument();
    });

    it("shows the weekday-name title for a non-today date and \"Today\" for today", async () => {
      mockedGetDay.mockResolvedValue(makeDay({ date: "2026-07-29" }));
      renderPage("/day/2026-07-29");

      // 2026-07-29 is a Wednesday.
      expect(await screen.findByRole("heading", { name: /^Wednesday.*2026-07-29/ })).toBeInTheDocument();
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

  describe("energy balance chart (EC-10)", () => {
    function makeEnergy(): NonNullable<DayResponse["energy"]> {
      return {
        points: [{ at: `${todayIso()}T08:00:00Z`, balance: 200 }],
        forecastPoints: [{ at: `${todayIso()}T20:00:00Z`, balance: 500 }],
        events: [],
        currentBalance: 200,
        predictedEndOfDay: 500,
        endOfDayTarget: 600,
        fuelingFlags: []
      };
    }

    it("renders the Live Energy section on today's date when energy data is present", async () => {
      mockedGetDay.mockResolvedValue(makeDay({ date: todayIso(), energy: makeEnergy() }));
      renderPage("/");

      expect(await screen.findByRole("heading", { name: /live energy/i })).toBeInTheDocument();
    });

    it("does not render the Live Energy section on a non-today date", async () => {
      mockedGetDay.mockResolvedValue(makeDay({ date: "2026-07-20", energy: makeEnergy() }));
      renderPage("/day/2026-07-20");

      await screen.findByText("no meals logged this day");
      expect(screen.queryByRole("heading", { name: /live energy/i })).not.toBeInTheDocument();
    });
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

    const toggle = await screen.findByRole("button", { name: /calories out/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

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

  it("expands and collapses a meal group", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        meals: {
          breakfast: [
            {
              id: 1,
              loggedAt: "2026-07-20T08:00:00Z",
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
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Chicken breast")).not.toBeInTheDocument();

    // aria-controls must point at the id of the panel it reveals (§9
    // accessibility audit), not just toggle aria-expanded on its own.
    const controlsId = toggle.getAttribute("aria-controls");
    expect(controlsId).toBeTruthy();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Chicken breast")).toBeInTheDocument();
    expect(document.getElementById(controlsId as string)).toContainElement(screen.getByText("Chicken breast"));

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Chicken breast")).not.toBeInTheDocument();
  });

  it("lists meal instances chronologically by loggedAt, flattened across meal types (not grouped by type)", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        meals: {
          // Deliberately out of chronological order and interleaved across
          // types, and includes two instances of the same type (snack), to
          // assert the flat list sorts by `loggedAt` rather than by type or
          // by insertion order.
          breakfast: [
            {
              id: 2,
              loggedAt: "2026-07-20T12:00:00Z",
              mealType: "breakfast",
              notes: null,
              items: [makeItem({ id: 21, name: "Late breakfast item" })],
              totals: { calories: 300, proteinG: 20, carbsG: 30, fatG: 10, fiberG: 0, satFatG: 0, sodiumMg: 0 }
            }
          ],
          snack: [
            {
              id: 1,
              loggedAt: "2026-07-20T07:00:00Z",
              mealType: "snack",
              notes: null,
              items: [makeItem({ id: 11, name: "Early snack item" })],
              totals: { calories: 100, proteinG: 5, carbsG: 10, fatG: 2, fiberG: 0, satFatG: 0, sodiumMg: 0 }
            },
            {
              id: 3,
              loggedAt: "2026-07-20T18:00:00Z",
              mealType: "snack",
              notes: null,
              items: [makeItem({ id: 31, name: "Late snack item" })],
              totals: { calories: 150, proteinG: 5, carbsG: 15, fatG: 3, fiberG: 0, satFatG: 0, sodiumMg: 0 }
            }
          ]
        }
      })
    );
    renderPage();

    const toggles = await screen.findAllByRole("button", { name: /snack|breakfast/i });
    // Three meal-instance rows, ordered by loggedAt ascending: 7am snack
    // (100 cal), 12pm breakfast (300 cal), 6pm snack (150 cal) — irrespective
    // of meal type. Distinguish rows by their per-meal calorie total (fixed
    // fixture values, unlike the wall-clock-formatted time which shifts with
    // the test runner's local timezone) rather than by exact time text.
    expect(toggles).toHaveLength(3);
    expect(toggles[0]).toHaveAccessibleName(/snack/i);
    expect(toggles[0]).toHaveAccessibleName(/100 cal/);
    expect(toggles[1]).toHaveAccessibleName(/breakfast/i);
    expect(toggles[1]).toHaveAccessibleName(/300 cal/);
    expect(toggles[2]).toHaveAccessibleName(/snack/i);
    expect(toggles[2]).toHaveAccessibleName(/150 cal/);
  });

  it("expands multiple meal rows independently (per-row local state)", async () => {
    mockedGetDay.mockResolvedValue(
      makeDay({
        meals: {
          breakfast: [
            {
              id: 1,
              loggedAt: "2026-07-20T07:00:00Z",
              mealType: "breakfast",
              notes: null,
              items: [makeItem({ id: 11, name: "Oats" })],
              totals: { calories: 300, proteinG: 20, carbsG: 30, fatG: 10, fiberG: 0, satFatG: 0, sodiumMg: 0 }
            }
          ],
          lunch: [
            {
              id: 2,
              loggedAt: "2026-07-20T12:00:00Z",
              mealType: "lunch",
              notes: null,
              items: [makeItem({ id: 21, name: "Chicken salad" })],
              totals: { calories: 400, proteinG: 30, carbsG: 20, fatG: 15, fiberG: 0, satFatG: 0, sodiumMg: 0 }
            }
          ]
        }
      })
    );
    renderPage();

    const breakfastToggle = await screen.findByRole("button", { name: /breakfast/i });
    const lunchToggle = await screen.findByRole("button", { name: /lunch/i });

    fireEvent.click(breakfastToggle);
    expect(screen.getByText("Oats")).toBeInTheDocument();
    expect(screen.queryByText("Chicken salad")).not.toBeInTheDocument();

    fireEvent.click(lunchToggle);
    // Both rows stay open independently.
    expect(screen.getByText("Oats")).toBeInTheDocument();
    expect(screen.getByText("Chicken salad")).toBeInTheDocument();

    fireEvent.click(breakfastToggle);
    expect(screen.queryByText("Oats")).not.toBeInTheDocument();
    expect(screen.getByText("Chicken salad")).toBeInTheDocument();
  });

  it("shows per-meal P/C/F totals and per-food macros/quantity in the expanded detail", async () => {
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
              totals: { calories: 250, proteinG: 40, carbsG: 1, fatG: 8, fiberG: 0, satFatG: 2, sodiumMg: 300 }
            }
          ]
        }
      })
    );
    renderPage();

    const toggle = await screen.findByRole("button", { name: /breakfast/i });
    // Per-meal totals shown on the collapsed row itself.
    expect(toggle).toHaveAccessibleName(/250 cal/);
    expect(toggle).toHaveAccessibleName(/P 40\.0g/);
    expect(toggle).toHaveAccessibleName(/C 1\.0g/);
    expect(toggle).toHaveAccessibleName(/F 8\.0g/);

    fireEvent.click(toggle);
    // Per-food quantity/unit and macros in the expanded detail (the row
    // header above already shows the same P 40.0g total, so there are two
    // matches once expanded — assert at least one rather than a single one).
    expect(screen.getByText("150.0 g")).toBeInTheDocument();
    expect(screen.getAllByText(/P 40\.0g/).length).toBeGreaterThanOrEqual(1);
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
    mockedGetDay.mockResolvedValue(makeDay({ date: todayIso() }));
    mockedSyncIntervals.mockResolvedValue({
      fromDate: todayIso(),
      toDate: todayIso(),
      daysSynced: 1,
      failures: []
    });
    renderPage("/");

    fireEvent.click(await screen.findByRole("button", { name: /sync intervals now/i }));

    await waitFor(() => expect(mockedSyncIntervals).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/synced with intervals/i)).toBeInTheDocument();
    await waitFor(() => expect(mockedGetDay).toHaveBeenCalledTimes(2));
  });

  it("shows an error toast when sync fails", async () => {
    mockedGetDay.mockResolvedValue(makeDay({ date: todayIso() }));
    mockedSyncIntervals.mockRejectedValue(new Error("nope"));
    renderPage("/");

    fireEvent.click(await screen.findByRole("button", { name: /sync intervals now/i }));

    expect(await screen.findByText(/sync failed/i)).toBeInTheDocument();
  });

  it("keeps the calories-out override panel collapsed by default and hides its form", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    renderPage();

    await screen.findByRole("button", { name: /calories out/i });
    expect(screen.queryByLabelText(/calories out \(manual\)/i)).not.toBeInTheDocument();
  });

  it("rejects a negative manual override without calling the API", async () => {
    mockedGetDay.mockResolvedValue(makeDay());
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /calories out/i }));
    const input = await screen.findByLabelText(/calories out \(manual\)/i);
    fireEvent.change(input, { target: { value: "-5" } });
    fireEvent.click(screen.getByRole("button", { name: /^set$/i }));

    expect(await screen.findByText(/non-negative/i)).toBeInTheDocument();
    expect(mockedSetManualCaloriesOut).not.toHaveBeenCalled();
  });

  it("rolls back an optimistic item delete and shows an error toast on failure", async () => {
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
    mockedDeleteMealItem.mockRejectedValue(new Error("boom"));
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /breakfast/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));

    expect(await screen.findByText(/could not delete item/i)).toBeInTheDocument();
    expect(await screen.findByText("Chicken breast")).toBeInTheDocument();
  });

  describe("Log macros (quick ad-hoc entry)", () => {
    it("is mutually exclusive with the meal editor panel — opening one closes the other", async () => {
      mockedGetDay.mockResolvedValue(makeDay());
      renderPage();

      const mealButton = (await screen.findAllByRole("button", { name: /^log a meal$/i }))[0]!;
      const macroButton = await screen.findByRole("button", { name: /^log macros$/i });

      fireEvent.click(macroButton);
      expect(screen.getByRole("form", { name: /log macros/i })).toBeInTheDocument();
      expect(screen.queryByRole("form", { name: /^meal editor$/i })).not.toBeInTheDocument();

      fireEvent.click(mealButton);
      expect(screen.getByRole("form", { name: /^meal editor$/i })).toBeInTheDocument();
      // Opening the meal editor closes the macros panel.
      expect(screen.queryByRole("form", { name: /log macros/i })).not.toBeInTheDocument();

      fireEvent.click(macroButton);
      expect(screen.getByRole("form", { name: /log macros/i })).toBeInTheDocument();
      // Opening the macros panel closes the meal editor.
      expect(screen.queryByRole("form", { name: /^meal editor$/i })).not.toBeInTheDocument();
    });

    it("defaults meal_type=snack and logged_at=now, and submits a single ad-hoc item via createMeal", async () => {
      mockedGetDay.mockResolvedValue(makeDay());
      mockedCreateMeal.mockResolvedValue({
        id: 7,
        loggedAt: "2026-07-20T12:00:00Z",
        localTz: "UTC",
        localDate: "2026-07-20",
        mealType: "snack",
        notes: null,
        items: [],
        totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null },
        deltaVsTarget: null
      });
      renderPage();

      fireEvent.click(await screen.findByRole("button", { name: /^log macros$/i }));
      expect(screen.getByLabelText(/meal type/i)).toHaveValue("snack");

      fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "250" } });
      fireEvent.change(screen.getByLabelText(/protein/i), { target: { value: "20" } });
      fireEvent.change(screen.getByLabelText(/carbs/i), { target: { value: "30" } });
      fireEvent.change(screen.getByLabelText(/^fat/i), { target: { value: "5" } });

      fireEvent.click(screen.getByRole("button", { name: /save macros/i }));

      await waitFor(() => expect(mockedCreateMeal).toHaveBeenCalledTimes(1));
      const [request] = mockedCreateMeal.mock.calls[0]!;
      expect(request.mealType).toBe("snack");
      expect(request.items).toEqual([
        {
          name: "Quick entry",
          quantity: 1,
          quantityUnit: "serving",
          foodId: null,
          calories: 250,
          proteinG: 20,
          carbsG: 30,
          fatG: 5,
          fiberG: null,
          satFatG: null,
          sodiumMg: null
        }
      ]);
      expect(request.loggedAt).toMatch(/Z$|[+-]\d{2}:\d{2}$/);

      expect(await screen.findByText(/macros logged/i)).toBeInTheDocument();
    });

    it("requires calories, protein, carbs, and fat before submitting", async () => {
      mockedGetDay.mockResolvedValue(makeDay());
      renderPage();

      fireEvent.click(await screen.findByRole("button", { name: /^log macros$/i }));
      fireEvent.click(screen.getByRole("button", { name: /save macros/i }));

      expect(await screen.findByText(/enter calories, protein, carbs, and fat/i)).toBeInTheDocument();
      expect(mockedCreateMeal).not.toHaveBeenCalled();
    });

    it("shows an error toast and keeps the panel open when logging macros fails", async () => {
      mockedGetDay.mockResolvedValue(makeDay());
      mockedCreateMeal.mockRejectedValue(new Error("failed"));
      renderPage();

      fireEvent.click(await screen.findByRole("button", { name: /^log macros$/i }));
      fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "250" } });
      fireEvent.change(screen.getByLabelText(/protein/i), { target: { value: "20" } });
      fireEvent.change(screen.getByLabelText(/carbs/i), { target: { value: "30" } });
      fireEvent.change(screen.getByLabelText(/^fat/i), { target: { value: "5" } });

      fireEvent.click(screen.getByRole("button", { name: /save macros/i }));

      expect(await screen.findByText(/could not log macros/i)).toBeInTheDocument();
      expect(screen.getByRole("form", { name: /log macros/i })).toBeInTheDocument();
    });
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

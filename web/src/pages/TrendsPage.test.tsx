import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TrendsPage from "./TrendsPage";
import { getRange } from "../lib/api/client";
import type { PeriodTotals, RangeResponse } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  getRange: vi.fn()
}));

const mockedGetRange = vi.mocked(getRange);

function makePeriod(overrides: Partial<PeriodTotals> = {}): PeriodTotals {
  return {
    periodStart: "2026-07-27",
    periodEnd: "2026-07-27",
    totals: { calories: 2000, proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null },
    effectiveTarget: {
      effectiveFrom: "2026-06-01",
      baseCalories: 2000,
      proteinG: 150,
      carbsG: 200,
      fatG: 60,
      caloriesOut: null,
      effectiveCalories: 2000
    },
    adherence: true,
    ...overrides
  };
}

function makeRange(periods: PeriodTotals[]): RangeResponse {
  return {
    fromDate: "2026-06-28",
    toDate: "2026-07-28",
    granularity: "day",
    periods
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(<TrendsPage />, { wrapper });
}

describe("TrendsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading skeleton on first paint", () => {
    mockedGetRange.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state with a retry button when the range query fails", async () => {
    mockedGetRange.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load trend data/i);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows the empty state with a nudge when no meals were logged in range", async () => {
    mockedGetRange.mockResolvedValue(
      makeRange([
        makePeriod({
          totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null },
          adherence: null,
          effectiveTarget: null
        })
      ])
    );
    renderPage();

    expect(await screen.findByText(/no meals logged in the last 30 days/i)).toBeInTheDocument();
    expect(screen.getByText(/tell claude, or log a meal on today/i)).toBeInTheDocument();
  });

  it("defaults to the 30-day range and requests it from the API", async () => {
    mockedGetRange.mockResolvedValue(makeRange([makePeriod()]));
    renderPage();

    await waitFor(() => expect(mockedGetRange).toHaveBeenCalledTimes(1));
    const [params] = mockedGetRange.mock.calls[0]!;
    expect(params.granularity).toBe("day");
    // 30-day inclusive window: exactly 30 calendar days apart.
    const from = new Date(params.from);
    const to = new Date(params.to);
    const diffDays = Math.round((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24));
    expect(diffDays).toBe(29);
  });

  it("switches range and re-fetches when a different selector button is clicked", async () => {
    mockedGetRange.mockResolvedValue(makeRange([makePeriod()]));
    renderPage();

    await waitFor(() => expect(mockedGetRange).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "7d" }));

    await waitFor(() => expect(mockedGetRange).toHaveBeenCalledTimes(2));
    const [secondCallParams] = mockedGetRange.mock.calls[1]!;
    const from = new Date(secondCallParams.from);
    const to = new Date(secondCallParams.to);
    const diffDays = Math.round((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24));
    expect(diffDays).toBe(6);

    expect(screen.getByRole("button", { name: "7d" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "30d" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows stat tiles computed from the backend's adherence flags", async () => {
    mockedGetRange.mockResolvedValue(
      makeRange([
        makePeriod({ periodStart: "2026-07-26", adherence: true }),
        makePeriod({ periodStart: "2026-07-27", adherence: false, totals: { calories: 2600, proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null } })
      ])
    );
    renderPage();

    expect(await screen.findByText("50%")).toBeInTheDocument();
    expect(screen.getByText("1 day")).toBeInTheDocument();
    expect(screen.getByText("2026-07-27")).toBeInTheDocument();
    expect(screen.getByText(/\+600 calories vs\. target/i)).toBeInTheDocument();
  });

  it("renders a text summary beneath the calorie chart and the macro chart", async () => {
    mockedGetRange.mockResolvedValue(
      makeRange([makePeriod({ periodStart: "2026-07-27" }), makePeriod({ periodStart: "2026-07-28" })])
    );
    renderPage();

    expect(
      await screen.findByText(/from 2026-07-27 to 2026-07-28, calories averaged 2,000 per day/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/averaged over 2 days: 150\.0 g protein, 200\.0 g carbs, and 60\.0 g fat/i)).toBeInTheDocument();
  });
});

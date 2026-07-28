import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CalendarPage from "./CalendarPage";
import { getRange } from "../lib/api/client";
import type { PeriodTotals, RangeResponse } from "../lib/api/types";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

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
    fromDate: "2025-07-29",
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
  return render(<CalendarPage />, { wrapper });
}

describe("CalendarPage", () => {
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
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load calendar data/i);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows the empty state with a nudge when nothing was logged in the whole window", async () => {
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

    expect(await screen.findByText(/no meals logged in the last twelve months/i)).toBeInTheDocument();
    expect(screen.getByText(/tell claude, or log a meal on today/i)).toBeInTheDocument();
  });

  it("requests a 365-day day-granularity range ending today", async () => {
    mockedGetRange.mockResolvedValue(makeRange([makePeriod()]));
    renderPage();

    await screen.findByText(/day.*in target/i);
    expect(mockedGetRange).toHaveBeenCalledTimes(1);
    const [params] = mockedGetRange.mock.calls[0]!;
    expect(params.granularity).toBe("day");
    const from = new Date(params.from);
    const to = new Date(params.to);
    const diffDays = Math.round((to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24));
    expect(diffDays).toBe(364);
  });

  it("renders a text summary beneath the heatmap", async () => {
    mockedGetRange.mockResolvedValue(
      makeRange([
        makePeriod({ periodStart: "2026-07-27", adherence: true }),
        makePeriod({
          periodStart: "2026-07-28",
          adherence: false,
          totals: { calories: 2600, proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null }
        })
      ])
    );
    renderPage();

    expect(await screen.findByText(/1 day in target over the last 2 days/i)).toBeInTheDocument();
    expect(screen.getByText(/longest in-target streak 1 day\./i)).toBeInTheDocument();
  });

  it("navigates to /day/:date when a cell is clicked", async () => {
    mockedGetRange.mockResolvedValue(makeRange([makePeriod({ periodStart: "2026-07-27" })]));
    const { container } = renderPage();

    await screen.findByText(/day.*in target/i);
    const cell = container.querySelector('rect[aria-label*="2026-07-27"]');
    expect(cell).not.toBeNull();

    fireEvent.click(cell as Element);
    expect(mockNavigate).toHaveBeenCalledWith("/day/2026-07-27");
  });

  it("navigates to /day/:date when a cell is activated with the keyboard", async () => {
    mockedGetRange.mockResolvedValue(makeRange([makePeriod({ periodStart: "2026-07-27" })]));
    const { container } = renderPage();

    await screen.findByText(/day.*in target/i);
    const cell = container.querySelector('rect[aria-label*="2026-07-27"]');
    expect(cell).not.toBeNull();

    fireEvent.keyDown(cell as Element, { key: "Enter" });
    expect(mockNavigate).toHaveBeenCalledWith("/day/2026-07-27");
  });

  it("shows a hover tooltip with that day's totals", async () => {
    mockedGetRange.mockResolvedValue(makeRange([makePeriod({ periodStart: "2026-07-27" })]));
    const { container } = renderPage();

    await screen.findByText(/day.*in target/i);
    const cell = container.querySelector('rect[aria-label*="2026-07-27"]');
    expect(cell).not.toBeNull();

    fireEvent.mouseOver(cell as Element, { clientX: 10, clientY: 20 });
    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent(/2026-07-27/);
    expect(tooltip).toHaveTextContent(/2,000 calories/);
    expect(tooltip).toHaveTextContent(/in target/i);

    fireEvent.mouseLeave(cell as Element);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});

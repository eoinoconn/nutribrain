import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { TOKEN_STORAGE_KEY } from "./lib/tokenStore";
import { getDay } from "./lib/api/client";
import { ToastProvider } from "./design/Toast";

vi.mock("./lib/api/client", () => ({
  getDay: vi.fn(),
  createMeal: vi.fn(),
  syncIntervals: vi.fn(),
  listFoods: vi.fn()
}));

const mockedGetDay = vi.mocked(getDay);

function todayLocalDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    mockedGetDay.mockResolvedValue({
      // The "/" route's DayView shows a "Today" heading only when the
      // fetched day's date matches the browser's local today, so this must
      // track the real date rather than a hardcoded string.
      date: todayLocalDate(),
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
      energy: null
    });
  });

  it("renders dashboard heading once a token is present", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "test-token");
    const queryClient = new QueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ToastProvider>
            <App />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /today/i
      })
    ).toBeInTheDocument();
  });

  it("shows the token paste screen instead of the app when no token is stored", () => {
    const queryClient = new QueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 1, name: /nutribrain dashboard/i })
    ).not.toBeInTheDocument();
  });
});

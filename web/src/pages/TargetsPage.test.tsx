import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TargetsPage from "./TargetsPage";
import { ToastProvider } from "../design/Toast";
import { createTarget, listTargets } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import type { Target } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  listTargets: vi.fn(),
  createTarget: vi.fn()
}));

const mockedListTargets = vi.mocked(listTargets);
const mockedCreateTarget = vi.mocked(createTarget);

function makeTarget(overrides: Partial<Target> = {}): Target {
  return {
    id: 1,
    effectiveFrom: "2026-01-01",
    baseCalories: 2200,
    proteinG: 180,
    carbsG: 220,
    fatG: 70,
    createdAt: "2026-01-01T00:00:00Z",
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
  return render(<TargetsPage />, { wrapper });
}

describe("TargetsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading skeleton on first paint", () => {
    mockedListTargets.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByRole("status", { name: /loading/i }).length).toBeGreaterThan(0);
  });

  it("shows an error state with retry when the query fails", async () => {
    mockedListTargets.mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load targets/i);
  });

  it("shows an empty state nudge with a new-target action when there are none", async () => {
    mockedListTargets.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText("no targets set yet")).toBeInTheDocument();
    expect(screen.getByText(/tell claude, or set one/i)).toBeInTheDocument();
  });

  it("lists targets sorted by effective_from descending, marking the most recent as current", async () => {
    mockedListTargets.mockResolvedValue([
      makeTarget({ id: 1, effectiveFrom: "2026-01-01", baseCalories: 2000 }),
      makeTarget({ id: 2, effectiveFrom: "2026-06-15", baseCalories: 2400 }),
      makeTarget({ id: 3, effectiveFrom: "2026-03-10", baseCalories: 2100 })
    ]);
    renderPage();

    const rows = await screen.findAllByRole("row");
    const dataRows = rows.slice(1);
    expect(within(dataRows[0]!).getByText("2026-06-15")).toBeInTheDocument();
    expect(within(dataRows[0]!).getByText("Current")).toBeInTheDocument();
    expect(within(dataRows[1]!).getByText("2026-03-10")).toBeInTheDocument();
    expect(within(dataRows[2]!).getByText("2026-01-01")).toBeInTheDocument();
    // Past targets have no edit affordance — read-only rows.
    expect(within(dataRows[2]!).queryByRole("button")).not.toBeInTheDocument();
  });

  it("toggles the inline create form open and closed", async () => {
    mockedListTargets.mockResolvedValue([]);
    renderPage();
    await screen.findByText("no targets set yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^new target$/i })[0]!);
    expect(screen.getByRole("region", { name: /new target/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("region", { name: /new target/i })).not.toBeInTheDocument();
  });

  it("validates required fields without calling the API", async () => {
    mockedListTargets.mockResolvedValue([]);
    renderPage();
    await screen.findByText("no targets set yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^new target$/i })[0]!);
    fireEvent.click(screen.getByRole("button", { name: /^create target$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/required/i);
    expect(mockedCreateTarget).not.toHaveBeenCalled();
  });

  it("submits a new target and shows a success toast", async () => {
    mockedListTargets.mockResolvedValue([]);
    mockedCreateTarget.mockResolvedValue({
      id: 9,
      effectiveFrom: "2026-07-28",
      baseCalories: 2200,
      proteinG: 180,
      carbsG: 220,
      fatG: 70,
      sameDayOverlap: false
    });
    renderPage();
    await screen.findByText("no targets set yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^new target$/i })[0]!);
    fireEvent.change(screen.getByLabelText(/base calories/i), { target: { value: "2200" } });
    fireEvent.change(screen.getByLabelText(/protein/i), { target: { value: "180" } });
    fireEvent.change(screen.getByLabelText(/carbs/i), { target: { value: "220" } });
    fireEvent.change(screen.getByLabelText(/fat/i), { target: { value: "70" } });
    fireEvent.click(screen.getByRole("button", { name: /^create target$/i }));

    await waitFor(() => expect(mockedCreateTarget).toHaveBeenCalledTimes(1));
    expect(mockedCreateTarget.mock.calls[0]?.[0]).toMatchObject({
      baseCalories: 2200,
      proteinG: 180,
      carbsG: 220,
      fatG: 70
    });
    expect(await screen.findByText(/^target created\.$/i)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /new target/i })).not.toBeInTheDocument();
  });

  it("surfaces the same-day overlap note in the success toast", async () => {
    mockedListTargets.mockResolvedValue([]);
    mockedCreateTarget.mockResolvedValue({
      id: 9,
      effectiveFrom: "2026-07-28",
      baseCalories: 2200,
      proteinG: 180,
      carbsG: 220,
      fatG: 70,
      sameDayOverlap: true
    });
    renderPage();
    await screen.findByText("no targets set yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^new target$/i })[0]!);
    fireEvent.change(screen.getByLabelText(/base calories/i), { target: { value: "2200" } });
    fireEvent.change(screen.getByLabelText(/protein/i), { target: { value: "180" } });
    fireEvent.change(screen.getByLabelText(/carbs/i), { target: { value: "220" } });
    fireEvent.change(screen.getByLabelText(/fat/i), { target: { value: "70" } });
    fireEvent.click(screen.getByRole("button", { name: /^create target$/i }));

    expect(await screen.findByText(/replaces an earlier target/i)).toBeInTheDocument();
  });

  it("shows a domain error message and an error toast on failure, keeping the form open", async () => {
    mockedListTargets.mockResolvedValue([]);
    mockedCreateTarget.mockRejectedValue(
      new ApiError(422, "Unprocessable", { message: "base_calories must be non-negative" })
    );
    renderPage();
    await screen.findByText("no targets set yet");

    fireEvent.click(screen.getAllByRole("button", { name: /^new target$/i })[0]!);
    fireEvent.change(screen.getByLabelText(/base calories/i), { target: { value: "2200" } });
    fireEvent.change(screen.getByLabelText(/protein/i), { target: { value: "180" } });
    fireEvent.change(screen.getByLabelText(/carbs/i), { target: { value: "220" } });
    fireEvent.change(screen.getByLabelText(/fat/i), { target: { value: "70" } });
    fireEvent.click(screen.getByRole("button", { name: /^create target$/i }));

    expect(await screen.findByText(/base_calories must be non-negative/i)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /new target/i })).toBeInTheDocument();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "./SettingsPage";
import { ToastProvider } from "../design/Toast";
import { getSyncStatus, syncIntervals } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import { TOKEN_STORAGE_KEY, maskToken } from "../lib/tokenStore";
import type { SyncStatusResponse } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  getSyncStatus: vi.fn(),
  syncIntervals: vi.fn()
}));

const mockedGetSyncStatus = vi.mocked(getSyncStatus);
const mockedSyncIntervals = vi.mocked(syncIntervals);

function statusResponse(overrides: Partial<SyncStatusResponse> = {}): SyncStatusResponse {
  return { lastSyncedAt: "2026-07-27T12:00:00Z", lastError: null, ...overrides };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
  return render(<SettingsPage />, { wrapper });
}

let mockedWriteText: ReturnType<typeof vi.fn>;

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    mockedGetSyncStatus.mockResolvedValue(statusResponse());
    mockedWriteText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText: mockedWriteText } });
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("shows 'No token stored' when there is no token", async () => {
    renderPage();
    expect(await screen.findByText("No token stored.")).toBeInTheDocument();
  });

  it("shows the masked token, never the raw value, when a token is stored", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "sk-abcdef123456");
    renderPage();
    expect(await screen.findByText(maskToken("sk-abcdef123456"))).toBeInTheDocument();
    expect(screen.queryByText("sk-abcdef123456")).not.toBeInTheDocument();
  });

  it("copies the raw token to the clipboard via the Copy button", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "sk-abcdef123456");
    renderPage();
    await screen.findByText(maskToken("sk-abcdef123456"));

    fireEvent.click(screen.getByRole("button", { name: /^copy$/i }));

    await waitFor(() => expect(mockedWriteText).toHaveBeenCalledWith("sk-abcdef123456"));
    expect(await screen.findByText(/copied to clipboard/i)).toBeInTheDocument();
  });

  it("disables Copy when there is no token", async () => {
    renderPage();
    await screen.findByText("No token stored.");
    expect(screen.getByRole("button", { name: /^copy$/i })).toBeDisabled();
  });

  it("rotates the token by re-storing a newly pasted value", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "sk-old000000000");
    renderPage();
    await screen.findByText(maskToken("sk-old000000000"));

    fireEvent.click(screen.getByRole("button", { name: /rotate token/i }));
    fireEvent.change(screen.getByLabelText(/new token/i), { target: { value: "sk-newtoken999999" } });
    fireEvent.click(screen.getByRole("button", { name: /save new token/i }));

    expect(await screen.findByText(maskToken("sk-newtoken999999"))).toBeInTheDocument();
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBe("sk-newtoken999999");
    expect(await screen.findByText(/token updated/i)).toBeInTheDocument();
  });

  it("test connection succeeds via the authenticated sync-status endpoint", async () => {
    renderPage();
    await screen.findByText(/last synced/i);
    mockedGetSyncStatus.mockClear();
    mockedGetSyncStatus.mockResolvedValueOnce(statusResponse());

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));

    await waitFor(() => expect(mockedGetSyncStatus).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText(/^connection ok\.$/i).length).toBeGreaterThan(0));
  });

  it("test connection surfaces an error when the authenticated request fails", async () => {
    renderPage();
    await screen.findByText(/last synced/i);
    mockedGetSyncStatus.mockRejectedValueOnce(new ApiError(500, "Server error", null));

    fireEvent.click(screen.getByRole("button", { name: /test connection/i }));

    expect(await screen.findByText(/server responded with 500/i)).toBeInTheDocument();
  });

  it("defaults the timezone override to the browser timezone and persists edits", async () => {
    renderPage();
    const input = await screen.findByLabelText<HTMLInputElement>(/timezone override/i);
    const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(input.value).toBe(browserTz);

    fireEvent.change(input, { target: { value: "America/New_York" } });
    expect(window.localStorage.getItem("nutribrain:timezone-override")).toBe("America/New_York");
  });

  it("shows the last synced timestamp from GET /api/sync/status", async () => {
    mockedGetSyncStatus.mockResolvedValue(statusResponse({ lastSyncedAt: "2026-07-20T08:00:00Z" }));
    renderPage();
    expect(await screen.findByText(/last synced: 2026-07-20t08:00:00z/i)).toBeInTheDocument();
  });

  it("triggers a real Intervals sync via 'Sync now' and shows a success toast", async () => {
    mockedSyncIntervals.mockResolvedValue({ fromDate: "2026-07-28", toDate: "2026-07-28", daysSynced: 1, failures: [] });
    renderPage();
    await screen.findByText(/last synced/i);

    fireEvent.click(screen.getByRole("button", { name: /^sync now$/i }));

    await waitFor(() => expect(mockedSyncIntervals).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/synced with intervals/i)).toBeInTheDocument();
  });

  it("shows an error toast when 'Sync now' fails", async () => {
    mockedSyncIntervals.mockRejectedValue(new Error("boom"));
    renderPage();
    await screen.findByText(/last synced/i);

    fireEvent.click(screen.getByRole("button", { name: /^sync now$/i }));

    expect(await screen.findByText(/^sync failed\.$/i)).toBeInTheDocument();
  });

  it("diagnostic panel reports the DB connection healthy when sync status loads successfully", async () => {
    mockedGetSyncStatus.mockResolvedValue(statusResponse({ lastError: null }));
    renderPage();
    expect(await screen.findByText(/db connection: healthy/i)).toBeInTheDocument();
    expect(screen.getByText(/last error: none/i)).toBeInTheDocument();
  });

  it("diagnostic panel reports the DB connection unreachable and shows the last error when sync status fails", async () => {
    mockedGetSyncStatus.mockRejectedValue(new Error("db down"));
    renderPage();
    expect(await screen.findByText(/db connection: unreachable/i)).toBeInTheDocument();
  });

  it("diagnostic panel surfaces the last sync error from GET /api/sync/status", async () => {
    mockedGetSyncStatus.mockResolvedValue(statusResponse({ lastError: "Intervals API timed out" }));
    renderPage();
    expect(await screen.findByText(/last error: intervals api timed out/i)).toBeInTheDocument();
  });
});

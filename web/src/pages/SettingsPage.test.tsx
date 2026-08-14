import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "./SettingsPage";
import { ToastProvider } from "../design/Toast";
import { getSettings, getSyncStatus, syncIntervals, updateSettings } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import { TOKEN_STORAGE_KEY, maskToken } from "../lib/tokenStore";
import type { AppSettings, SyncStatusResponse } from "../lib/api/types";

vi.mock("../lib/api/client", () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  getSyncStatus: vi.fn(),
  syncIntervals: vi.fn()
}));

const mockedGetSettings = vi.mocked(getSettings);
const mockedUpdateSettings = vi.mocked(updateSettings);
const mockedGetSyncStatus = vi.mocked(getSyncStatus);
const mockedSyncIntervals = vi.mocked(syncIntervals);

function statusResponse(overrides: Partial<SyncStatusResponse> = {}): SyncStatusResponse {
  return { lastSyncedAt: "2026-07-27T12:00:00Z", lastError: null, ...overrides };
}

function settingsResponse(overrides: Partial<AppSettings> = {}): AppSettings {
  return { localTimezone: "UTC", ...overrides };
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
    mockedGetSettings.mockResolvedValue(settingsResponse());
    mockedUpdateSettings.mockImplementation((payload) => Promise.resolve(settingsResponse(payload)));
    mockedWriteText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText: mockedWriteText } });
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it("shows a loading skeleton (not bare text) for the sync status section on first paint", () => {
    mockedGetSyncStatus.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole("status", { name: /loading sync status/i })).toBeInTheDocument();
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

  it("shows a success toast when the token is cleared", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "sk-abcdef123456");
    renderPage();
    await screen.findByText(maskToken("sk-abcdef123456"));

    fireEvent.click(screen.getByRole("button", { name: /clear token/i }));

    expect(await screen.findByText("No token stored.")).toBeInTheDocument();
    expect(await screen.findByText(/token cleared/i)).toBeInTheDocument();
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

  it("shows the browser timezone as the displayed default while the settings query is loading", async () => {
    mockedGetSettings.mockReturnValue(new Promise(() => {}));
    renderPage();
    const input = await screen.findByLabelText<HTMLInputElement>(/timezone override/i);
    const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(input.value).toBe(browserTz);
  });

  it("loads the persisted timezone from GET /api/settings once it resolves", async () => {
    mockedGetSettings.mockResolvedValue(settingsResponse({ localTimezone: "Europe/Dublin" }));
    renderPage();
    const input = await screen.findByLabelText<HTMLInputElement>(/timezone override/i);
    await waitFor(() => expect(input.value).toBe("Europe/Dublin"));
  });

  it("saves an edited timezone via PATCH /api/settings and shows a success toast", async () => {
    renderPage();
    const input = await screen.findByLabelText<HTMLInputElement>(/timezone override/i);
    await waitFor(() => expect(input.value).toBe("UTC"));

    fireEvent.change(input, { target: { value: "America/New_York" } });
    fireEvent.click(screen.getByRole("button", { name: /save timezone/i }));

    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenCalledWith({ localTimezone: "America/New_York" }));
    expect(await screen.findByText(/timezone updated/i)).toBeInTheDocument();
  });

  it("rolls back to the previous timezone and shows an error when the save fails", async () => {
    mockedGetSettings.mockResolvedValue(settingsResponse({ localTimezone: "UTC" }));
    mockedUpdateSettings.mockRejectedValueOnce(
      new ApiError(422, "Invalid timezone", { error: "invalid_timezone", message: "Not a real timezone." })
    );
    renderPage();
    const input = await screen.findByLabelText<HTMLInputElement>(/timezone override/i);
    await waitFor(() => expect(input.value).toBe("UTC"));

    fireEvent.change(input, { target: { value: "Not/A_Timezone" } });
    fireEvent.click(screen.getByRole("button", { name: /save timezone/i }));

    expect(await screen.findByText(/not a real timezone\./i)).toBeInTheDocument();
    expect(await screen.findByText(/could not update timezone\./i)).toBeInTheDocument();
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

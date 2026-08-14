/**
 * Settings page (T-070 initial cut, T-080 completes it): token management
 * (paste/mask/copy/rotate, test connection), timezone override, sync
 * status + manual "sync now", diagnostic panel.
 *
 * Test-connection endpoint choice: spec §9 defines `GET /health` as
 * unauthenticated and deliberately without a DB check ("both would need
 * auth to be safe"), so it can't tell us whether *this* token is valid.
 * "Test connection" therefore hits `GET /api/sync/status` (via the typed
 * client's `getSyncStatus`) instead — the lightest authenticated GET already
 * in the API surface (T-045), reusing the existing `apiClient` 401 handling
 * rather than adding a bespoke check.
 *
 * Diagnostic panel "DB connection" resolution: `/health` returns only
 * `{"status": "ok"}` with no DB check (spec §9), and this task is explicitly
 * out of bounds for adding a backend DB-check endpoint. `GET /api/sync/status`
 * does query Postgres (`get_sync_status(session)`, `api/app/api/sync.py`), so
 * this panel treats that query's own success/failure as the DB-connectivity
 * signal: if the authenticated sync-status fetch succeeds, the DB round-trip
 * behind it succeeded too; if it fails (once past the 401 case, which
 * TokenGate already routes away from this page entirely), that's read as a
 * DB/server problem. "Last error" is `sync_status.last_error` (last
 * Intervals sync failure — the only "last error" surface the backend
 * exposes anywhere).
 *
 * Timezone override (EC-06): backed by `app_settings` (`GET`/`PATCH
 * /api/settings`, `api/app/api/settings.py`) rather than `localStorage`
 * now — the energy chart (EC-05) needs a durable "whose midnight is this"
 * answer that a second browser/session can also see, which a page-local
 * `localStorage` key can never provide. Follows the same
 * `useQuery`+`useMutation` optimistic-update-with-rollback pattern as
 * `FoodsPage`'s `updateFoodMutation` (`cancelQueries` → snapshot →
 * optimistic `setQueryData` → mutate → restore snapshot on error →
 * `invalidateQueries` on settle). The browser-detected timezone is still
 * used as the *displayed default* while the settings query is loading, so
 * the field never renders blank before the first fetch resolves.
 */

import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getSettings, getSyncStatus, syncIntervals, updateSettings } from "../lib/api/client";
import { ApiError } from "../lib/apiClient";
import { queryKeys } from "../lib/queryClient";
import { useToast } from "../design/useToast";
import Skeleton from "../design/Skeleton";
import { clearToken, getToken, maskToken, setToken } from "../lib/tokenStore";
import type { AppSettings } from "../lib/api/types";

type ConnectionState =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok" }
  | { status: "error"; message: string };

export default function SettingsPage(): JSX.Element {
  return (
    <section className="space-y-8">
      <h2 className="text-2xl font-semibold">Settings</h2>
      <TokenSection />
      <TimezoneSection />
      <SyncStatusSection />
      <DiagnosticsSection />
    </section>
  );
}

function TokenSection(): JSX.Element {
  const { showToast } = useToast();
  const [currentToken, setCurrentToken] = useState<string | null>(() => getToken());
  const [rotateValue, setRotateValue] = useState("");
  const [rotating, setRotating] = useState(false);
  const [connection, setConnection] = useState<ConnectionState>({ status: "idle" });

  async function handleTestConnection(): Promise<void> {
    setConnection({ status: "testing" });
    try {
      await getSyncStatus();
      setConnection({ status: "ok" });
      showToast("Connection OK.", "success");
    } catch (error) {
      const message =
        error instanceof ApiError ? `Server responded with ${error.status}.` : "Could not reach the API.";
      setConnection({ status: "error", message });
      showToast("Test connection failed.", "error");
    }
  }

  async function handleCopy(): Promise<void> {
    if (!currentToken) return;
    try {
      await navigator.clipboard.writeText(currentToken);
      showToast("Copied to clipboard.", "success");
    } catch {
      showToast("Copy failed — select and copy manually.", "error");
    }
  }

  function handleRotateSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const trimmed = rotateValue.trim();
    if (!trimmed) return;
    // "Rotate" here is client-only: there's no server-side token rotation
    // (APP_TOKEN is one shared env var, spec §9) — this just re-stores the
    // pasted token, clearing the old one from localStorage.
    setToken(trimmed);
    setCurrentToken(trimmed);
    setRotateValue("");
    setRotating(false);
    setConnection({ status: "idle" });
    showToast("Token updated.", "success");
  }

  function handleClearToken(): void {
    clearToken("manual");
    setCurrentToken(null);
    showToast("Token cleared.", "success");
  }

  return (
    <div className="space-y-3 rounded-lg border border-line p-4 dark:border-line-dark">
      <h3 className="text-lg font-medium">API token</h3>

      {currentToken ? (
        <p className="font-mono text-sm text-ink-secondary dark:text-ink-secondary-dark">{maskToken(currentToken)}</p>
      ) : (
        <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">No token stored.</p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleCopy()}
          disabled={!currentToken}
          className="focus-ring rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:hover:bg-panel-dark"
        >
          Copy
        </button>
        <button
          type="button"
          onClick={() => setRotating((prev) => !prev)}
          aria-expanded={rotating}
          className="focus-ring rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas dark:border-line-dark dark:hover:bg-panel-dark"
        >
          Rotate token
        </button>
        <button
          type="button"
          onClick={() => void handleTestConnection()}
          disabled={connection.status === "testing"}
          className="focus-ring rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:hover:bg-panel-dark"
        >
          {connection.status === "testing" ? "Testing..." : "Test connection"}
        </button>
        <button
          type="button"
          onClick={handleClearToken}
          className="focus-ring rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
        >
          Clear token
        </button>
      </div>

      {connection.status === "ok" ? (
        <p role="status" className="text-sm text-green-700 dark:text-green-400">
          Connection OK.
        </p>
      ) : null}
      {connection.status === "error" ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {connection.message}
        </p>
      ) : null}

      {rotating ? (
        <form className="space-y-2" onSubmit={handleRotateSubmit}>
          <label className="block text-sm font-medium" htmlFor="rotate-token">
            New token
          </label>
          <input
            id="rotate-token"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={rotateValue}
            onChange={(event) => setRotateValue(event.target.value)}
            className="focus-ring w-full max-w-sm rounded-md border border-line bg-white px-3 py-2 text-sm dark:border-line-dark dark:bg-canvas-dark"
          />
          <button
            type="submit"
            className="focus-ring rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent"
          >
            Save new token
          </button>
        </form>
      ) : null}
    </div>
  );
}

function TimezoneSection(): JSX.Element {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  // Displayed default before the settings query resolves (or if it's still
  // unset server-side) — see module doc comment.
  const [timezone, setTimezone] = useState<string>(browserTimezone);
  const [formError, setFormError] = useState<string | null>(null);

  const settingsQuery = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: () => getSettings()
  });

  useEffect(() => {
    if (settingsQuery.data) {
      setTimezone(settingsQuery.data.localTimezone);
    }
  }, [settingsQuery.data]);

  const updateSettingsMutation = useMutation({
    mutationFn: (localTimezone: string) => updateSettings({ localTimezone }),
    onMutate: async (localTimezone) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.settings() });
      const previous = queryClient.getQueryData<AppSettings>(queryKeys.settings());
      queryClient.setQueryData<AppSettings>(queryKeys.settings(), { localTimezone });
      return { previous };
    },
    onError: (error, _localTimezone, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.settings(), context.previous);
        setTimezone(context.previous.localTimezone);
      }
      const rawMessage =
        error instanceof ApiError && error.body && typeof error.body === "object" && "message" in error.body
          ? (error.body as { message?: unknown }).message
          : undefined;
      setFormError(typeof rawMessage === "string" ? rawMessage : "Could not update timezone.");
      showToast("Could not update timezone.", "error");
    },
    onSuccess: () => {
      setFormError(null);
      showToast("Timezone updated.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings() });
    }
  });

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();
    const trimmed = timezone.trim();
    if (!trimmed) {
      setFormError("Timezone is required.");
      return;
    }
    updateSettingsMutation.mutate(trimmed);
  }

  return (
    <div className="space-y-2 rounded-lg border border-line p-4 dark:border-line-dark">
      <h3 className="text-lg font-medium">Timezone</h3>
      <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
        Defaults to your browser timezone ({browserTimezone}) until you set an override. Saved to your
        account, so it applies across devices and sessions.
      </p>
      <form className="space-y-2" onSubmit={handleSubmit}>
        <label className="block text-sm font-medium" htmlFor="timezone-override">
          Timezone override
        </label>
        <input
          id="timezone-override"
          type="text"
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          disabled={settingsQuery.isLoading}
          className="focus-ring w-full max-w-sm rounded-md border border-line bg-white px-3 py-2 text-sm disabled:opacity-50 dark:border-line-dark dark:bg-canvas-dark"
        />
        <button
          type="submit"
          disabled={updateSettingsMutation.isPending || settingsQuery.isLoading}
          className="focus-ring rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent disabled:opacity-50"
        >
          {updateSettingsMutation.isPending ? "Saving..." : "Save timezone"}
        </button>
      </form>
      {formError ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {formError}
        </p>
      ) : null}
      {settingsQuery.isError ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load saved timezone.
        </p>
      ) : null}
    </div>
  );
}

function SyncStatusSection(): JSX.Element {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  const statusQuery = useQuery({
    queryKey: queryKeys.syncStatus(),
    queryFn: () => getSyncStatus()
  });

  // Same mutation pattern as `TodayPage`/`DayPage`'s "Sync intervals now"
  // (T-074/T-075): `POST /api/sync/intervals` for today's date, toast on
  // settle, invalidate sync status so this page's own display picks up the
  // new `lastSyncedAt`/`lastError`.
  const syncMutation = useMutation({
    mutationFn: () => syncIntervals(),
    onError: () => {
      showToast("Sync failed.", "error");
    },
    onSuccess: () => {
      showToast("Synced with Intervals.", "success");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.syncStatus() });
    }
  });

  return (
    <div className="space-y-2 rounded-lg border border-line p-4 dark:border-line-dark">
      <h3 className="text-lg font-medium">Intervals sync</h3>
      {statusQuery.isLoading ? (
        <Skeleton className="h-5 w-48" label="Loading sync status" />
      ) : statusQuery.isError ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load sync status.
        </p>
      ) : (
        <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
          Last synced: {statusQuery.data?.lastSyncedAt ?? "never"}
        </p>
      )}
      <button
        type="button"
        onClick={() => syncMutation.mutate()}
        disabled={syncMutation.isPending}
        className="focus-ring rounded-md border border-line px-3 py-1.5 text-sm hover:bg-canvas disabled:opacity-50 dark:border-line-dark dark:hover:bg-panel-dark"
      >
        {syncMutation.isPending ? "Syncing..." : "Sync now"}
      </button>
    </div>
  );
}

function DiagnosticsSection(): JSX.Element {
  // Reuses the same `syncStatus` query as the section above (TanStack Query
  // dedupes same-key queries, so this doesn't add a second network call).
  // See the module doc comment for why this query's success/failure stands
  // in for a DB-connectivity check.
  const statusQuery = useQuery({
    queryKey: queryKeys.syncStatus(),
    queryFn: () => getSyncStatus()
  });

  const dbStatus = statusQuery.isLoading ? "checking" : statusQuery.isError ? "unreachable" : "healthy";

  return (
    <div className="space-y-2 rounded-lg border border-line p-4 dark:border-line-dark">
      <h3 className="text-lg font-medium">Diagnostics</h3>
      <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
        DB connection: {dbStatus === "checking" ? "checking..." : dbStatus}
      </p>
      <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
        Last error: {statusQuery.data?.lastError ?? "none"}
      </p>
    </div>
  );
}

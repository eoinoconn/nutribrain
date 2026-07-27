/**
 * Settings page (T-070): token management (paste/mask/copy/rotate,
 * test connection), timezone override, sync status, diagnostics.
 *
 * Timezone override and the sync-status/diagnostic panels are lightweight
 * for this task: timezone is stored in localStorage only (no backend field
 * exists yet to persist it); sync status calls the real `/api/sync/status`
 * endpoint (T-045); the diagnostic panel reuses `/health` (DB connectivity)
 * plus the last sync error as a stand-in "last error" surface. A richer
 * diagnostic panel is out of scope here.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiFetchJson } from "../lib/apiClient";
import { queryKeys } from "../lib/queryClient";
import { clearToken, getToken, maskToken, setToken } from "../lib/tokenStore";

const TIMEZONE_STORAGE_KEY = "nutrition:timezone-override";

interface SyncStatusResponse {
  last_synced_at: string | null;
  last_error: string | null;
}

type ConnectionState = { status: "idle" } | { status: "testing" } | { status: "ok" } | { status: "error"; message: string };

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
  const [currentToken, setCurrentToken] = useState<string | null>(() => getToken());
  const [rotateValue, setRotateValue] = useState("");
  const [rotating, setRotating] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>({ status: "idle" });

  async function handleTestConnection(): Promise<void> {
    setConnection({ status: "testing" });
    try {
      const response = await apiFetch("/api/sync/status");
      if (!response.ok) {
        setConnection({ status: "error", message: `Server responded with ${response.status}` });
        return;
      }
      setConnection({ status: "ok" });
    } catch {
      setConnection({ status: "error", message: "Could not reach the API." });
    }
  }

  async function handleCopy(): Promise<void> {
    if (!currentToken) return;
    try {
      await navigator.clipboard.writeText(currentToken);
      setCopyFeedback("Copied to clipboard.");
    } catch {
      setCopyFeedback("Copy failed — select and copy manually.");
    }
    window.setTimeout(() => setCopyFeedback(null), 3000);
  }

  function handleRotateSubmit(event: React.FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const trimmed = rotateValue.trim();
    if (!trimmed) return;
    setToken(trimmed);
    setCurrentToken(trimmed);
    setRotateValue("");
    setRotating(false);
    setConnection({ status: "idle" });
  }

  function handleClearToken(): void {
    clearToken("manual");
    setCurrentToken(null);
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="text-lg font-medium">API token</h3>

      {currentToken ? (
        <p className="font-mono text-sm text-slate-700 dark:text-slate-300">
          {maskToken(currentToken)}
        </p>
      ) : (
        <p className="text-sm text-slate-700 dark:text-slate-300">No token stored.</p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void handleCopy()}
          disabled={!currentToken}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Copy
        </button>
        <button
          type="button"
          onClick={() => setRotating((prev) => !prev)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Rotate token
        </button>
        <button
          type="button"
          onClick={() => void handleTestConnection()}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Test connection
        </button>
        <button
          type="button"
          onClick={handleClearToken}
          className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
        >
          Clear token
        </button>
      </div>

      {copyFeedback ? (
        <p role="status" className="text-sm text-slate-600 dark:text-slate-400">
          {copyFeedback}
        </p>
      ) : null}

      {connection.status === "testing" ? (
        <p role="status" className="text-sm text-slate-600 dark:text-slate-400">
          Testing...
        </p>
      ) : null}
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
            className="w-full max-w-sm rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900"
          />
          <button
            type="submit"
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2"
          >
            Save new token
          </button>
        </form>
      ) : null}
    </div>
  );
}

function TimezoneSection(): JSX.Element {
  const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [timezone, setTimezone] = useState<string>(
    () => window.localStorage.getItem(TIMEZONE_STORAGE_KEY) ?? browserTimezone
  );

  useEffect(() => {
    window.localStorage.setItem(TIMEZONE_STORAGE_KEY, timezone);
  }, [timezone]);

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="text-lg font-medium">Timezone</h3>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        Defaults to your browser timezone ({browserTimezone}). Stored locally only for now.
      </p>
      <label className="block text-sm font-medium" htmlFor="timezone-override">
        Timezone override
      </label>
      <input
        id="timezone-override"
        type="text"
        value={timezone}
        onChange={(event) => setTimezone(event.target.value)}
        className="w-full max-w-sm rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-900"
      />
    </div>
  );
}

function SyncStatusSection(): JSX.Element {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.syncStatus(),
    queryFn: () => apiFetchJson<SyncStatusResponse>("/api/sync/status")
  });

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="text-lg font-medium">Intervals sync</h3>
      {isLoading ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">Loading sync status...</p>
      ) : isError ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          Could not load sync status.
        </p>
      ) : (
        <p className="text-sm text-slate-700 dark:text-slate-300">
          Last synced: {data?.last_synced_at ?? "never"}
        </p>
      )}
      <button
        type="button"
        onClick={() => void refetch()}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:hover:bg-slate-800"
      >
        Sync now
      </button>
      <p className="text-xs text-slate-500 dark:text-slate-500">
        &quot;Sync now&quot; currently re-checks status; triggering a live Intervals sync from here is
        wired up in a later task.
      </p>
    </div>
  );
}

function DiagnosticsSection(): JSX.Element {
  const [health, setHealth] = useState<"unknown" | "ok" | "down">("unknown");
  const { data: syncStatus } = useQuery({
    queryKey: queryKeys.syncStatus(),
    queryFn: () => apiFetchJson<SyncStatusResponse>("/api/sync/status")
  });

  useEffect(() => {
    let cancelled = false;
    fetch("/health")
      .then((response) => {
        if (!cancelled) setHealth(response.ok ? "ok" : "down");
      })
      .catch(() => {
        if (!cancelled) setHealth("down");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="text-lg font-medium">Diagnostics</h3>
      <p className="text-sm text-slate-700 dark:text-slate-300">
        DB connection:{" "}
        {health === "unknown" ? "checking..." : health === "ok" ? "healthy" : "unreachable"}
      </p>
      <p className="text-sm text-slate-700 dark:text-slate-300">
        Last error: {syncStatus?.last_error ?? "none"}
      </p>
    </div>
  );
}

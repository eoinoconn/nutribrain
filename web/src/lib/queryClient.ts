/**
 * TanStack Query client + query-key convention (T-070).
 *
 * Query-key convention
 * --------------------
 * Keys are tuples with a stable string prefix identifying the resource,
 * followed by any parameters that scope the query. Keep all key factories
 * here so the shape of a resource's key can't drift between call sites.
 *
 *   queryKeys.day(localDate)        -> ['day', localDate]
 *   queryKeys.meals(localDate)      -> ['meals', localDate]
 *   queryKeys.targets(localDate)    -> ['targets', localDate]
 *   queryKeys.targetsList()         -> ['targets', 'list']
 *   queryKeys.foods(filters)        -> ['foods', filters]
 *   queryKeys.templates()           -> ['templates']
 *   queryKeys.syncStatus()          -> ['sync', 'status']
 *   queryKeys.range(from, to, g)    -> ['range', from, to, g]
 *   queryKeys.settings()            -> ['settings']
 *
 * `queryKeys.targets(localDate)` scopes the per-day *effective* target
 * (`GET /api/targets/effective?date=`, a different shape from the raw
 * versioned list — spec §4). `queryKeys.targetsList()` scopes the raw
 * versioned list (`GET /api/targets`) shown on the `/targets` manager page
 * (T-080). Keep these distinct: invalidating one must not stomp on the
 * other's cache entry.
 *
 * Always use `localDate` (the API-provided local date string), never a
 * client-derived UTC date, per docs/style.md.
 *
 * Invalidate with the narrowest matching prefix, e.g.
 * `queryClient.invalidateQueries({ queryKey: ['day', localDate] })`.
 */

import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./apiClient";

export const queryKeys = {
  day: (localDate: string) => ["day", localDate] as const,
  meals: (localDate: string) => ["meals", localDate] as const,
  targets: (localDate: string) => ["targets", localDate] as const,
  targetsList: () => ["targets", "list"] as const,
  foods: (filters?: Record<string, unknown>) => ["foods", filters ?? {}] as const,
  templates: () => ["templates"] as const,
  syncStatus: () => ["sync", "status"] as const,
  range: (from: string, to: string, granularity: string = "day") =>
    ["range", from, to, granularity] as const,
  settings: () => ["settings"] as const
};

function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/**
 * This is a single-user, low-traffic dashboard talking to one Postgres
 * instance we control, so:
 * - Retries are limited (network blips only) and never happen for 401s,
 *   since a 401 means the token itself is bad and clearing it (handled in
 *   apiClient) already redirects to the token gate.
 * - `refetchOnWindowFocus` is off to avoid surprising refetches while
 *   editing forms; data is refetched via explicit invalidation after
 *   mutations instead.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => {
          if (isAuthError(error)) {
            return false;
          }
          return failureCount < 2;
        },
        refetchOnWindowFocus: false,
        staleTime: 30_000
      },
      mutations: {
        retry: (failureCount, error) => {
          if (isAuthError(error)) {
            return false;
          }
          return failureCount < 1;
        }
      }
    }
  });
}

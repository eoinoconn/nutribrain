import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { listFoods } from "../../lib/api/client";
import type { FoodSearchResult } from "../../lib/api/types";
import { queryKeys } from "../../lib/queryClient";

const DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 1;

/**
 * Debounces `query` and runs a food search against `GET /api/foods?q=...`
 * once it settles, using the shared `queryKeys.foods` factory (T-070) so
 * the cache key stays consistent with any other food-search consumer.
 * Returns no results for an empty/whitespace query without hitting the network.
 */
export function useFoodSearch(query: string): {
  results: FoodSearchResult[];
  isLoading: boolean;
  isError: boolean;
} {
  const [debouncedQuery, setDebouncedQuery] = useState(query);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const trimmed = debouncedQuery.trim();
  const enabled = trimmed.length >= MIN_QUERY_LENGTH;

  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.foods({ q: trimmed }),
    queryFn: () => listFoods({ q: trimmed }),
    enabled,
    staleTime: 30_000
  });

  return {
    results: enabled ? (data ?? []) : [],
    isLoading: enabled && isLoading,
    isError: enabled && isError
  };
}

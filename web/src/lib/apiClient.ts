/**
 * Fetch wrapper for the `/api` backend (T-070).
 *
 * - Attaches `Authorization: Bearer <token>` from localStorage to every call.
 * - On a 401 response, clears the stored token (dispatching
 *   `TOKEN_CLEARED_EVENT` with reason "invalid") and throws an `ApiError`
 *   so callers/React Query stop treating the response as data.
 * - Never logs the Authorization header or token value.
 */

import { clearToken, getToken } from "./tokenStore";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
}

async function parseErrorBody(response: Response): Promise<unknown> {
  try {
    return await response.clone().json();
  } catch {
    return null;
  }
}

function errorDetail(body: unknown): string | undefined {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as Record<string, unknown>).detail;
    return typeof detail === "string" ? detail : undefined;
  }
  return undefined;
}

/**
 * Performs a fetch against the NutriBrain API, attaching the bearer token
 * and normalizing auth failures. `path` should start with `/` (e.g. `/api/day/2026-07-27`).
 */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
    ...options.headers
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(path, { ...options, headers });

  if (response.status === 401) {
    const body = await parseErrorBody(response);
    clearToken("invalid");
    throw new ApiError(401, errorDetail(body) ?? "invalid token", body);
  }

  return response;
}

/** Convenience helper for JSON GET/POST/etc. Throws `ApiError` on non-2xx (including 401). */
export async function apiFetchJson<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw new ApiError(response.status, errorDetail(body) ?? response.statusText, body);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

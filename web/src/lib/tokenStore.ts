/**
 * Bearer token storage for the single-user dashboard (T-070).
 *
 * Key name follows spec §9 (`nutribrain:token`) per D-004 — backlog task
 * T-070's own text said `nutrition:token`, but the backlog's stated
 * tie-break rule is that the spec wins on disagreements.
 */

export const TOKEN_STORAGE_KEY = "nutribrain:token";

/** Fired on `window` whenever the stored token is cleared (e.g. after a 401). */
export const TOKEN_CLEARED_EVENT = "nutribrain:token-cleared";

export interface TokenClearedDetail {
  reason: "manual" | "invalid";
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearToken(reason: TokenClearedDetail["reason"] = "manual"): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.dispatchEvent(
    new CustomEvent<TokenClearedDetail>(TOKEN_CLEARED_EVENT, { detail: { reason } })
  );
}

/** Masks a token for display, e.g. `sk-abc123def456` -> `sk-a...f456`. Never log the raw token. */
export function maskToken(token: string): string {
  if (token.length <= 8) {
    return "*".repeat(token.length);
  }
  const head = token.slice(0, 4);
  const tail = token.slice(-4);
  return `${head}...${tail}`;
}

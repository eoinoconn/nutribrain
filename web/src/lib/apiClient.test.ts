import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, apiFetchJson } from "./apiClient";
import { TOKEN_CLEARED_EVENT, TOKEN_STORAGE_KEY } from "./tokenStore";

describe("apiFetch", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the bearer token from localStorage", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "secret-token");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/foods");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer secret-token");
  });

  it("does not attach an Authorization header when no token is stored", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/foods");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("clears the token and throws ApiError on a 401 response", async () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "secret-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "invalid token" }), { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    const clearedEvents: string[] = [];
    window.addEventListener(TOKEN_CLEARED_EVENT, (event) => {
      clearedEvents.push((event as CustomEvent<{ reason: string }>).detail.reason);
    });

    await expect(apiFetch("/api/foods")).rejects.toBeInstanceOf(ApiError);
    expect(window.localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(clearedEvents).toEqual(["invalid"]);
  });

  it("propagates the error detail from a non-401 error response via apiFetchJson", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "not found" }), { status: 404 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetchJson("/api/foods/999")).rejects.toMatchObject({
      status: 404,
      message: "not found"
    });
  });

  it("returns parsed JSON for a successful response via apiFetchJson", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetchJson("/api/foods")).resolves.toEqual({ ok: true });
  });
});

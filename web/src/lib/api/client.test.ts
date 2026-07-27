import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TOKEN_STORAGE_KEY } from "../tokenStore";
import {
  createFood,
  createMeal,
  getDay,
  getEffectiveTarget,
  getRange,
  listFoods,
  listTemplates,
  setFavoriteFood,
  setManualCaloriesOut
} from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

/** Extracts the `[path, init]` args of the nth `fetch` call, typed. */
function fetchCall(fetchMock: ReturnType<typeof vi.fn>, callIndex = 0): [string, RequestInit] {
  const call = fetchMock.mock.calls[callIndex] as [string, RequestInit] | undefined;
  if (!call) {
    throw new Error(`fetch was not called at index ${callIndex}`);
  }
  return call;
}

describe("typed API client", () => {
  beforeEach(() => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "secret-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("builds the query string for listFoods only when q is provided", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse([])));
    vi.stubGlobal("fetch", fetchMock);

    await listFoods();
    expect(fetchCall(fetchMock, 0)[0]).toBe("/api/foods");

    await listFoods({ q: "chicken breast" });
    expect(fetchCall(fetchMock, 1)[0]).toBe("/api/foods?q=chicken+breast");
  });

  it("builds the query string for getRange with from/to/granularity", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ from_date: "2026-07-01", to_date: "2026-07-27", granularity: "week", periods: [] })
    );
    vi.stubGlobal("fetch", fetchMock);

    await getRange({ from: "2026-07-01", to: "2026-07-27", granularity: "week" });

    expect(fetchCall(fetchMock, 0)[0]).toBe(
      "/api/range?from=2026-07-01&to=2026-07-27&granularity=week"
    );
  });

  it("omits granularity from the query string when not provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ from_date: "2026-07-01", to_date: "2026-07-27", granularity: "day", periods: [] })
    );
    vi.stubGlobal("fetch", fetchMock);

    await getRange({ from: "2026-07-01", to: "2026-07-27" });

    expect(fetchCall(fetchMock, 0)[0]).toBe("/api/range?from=2026-07-01&to=2026-07-27");
  });

  it("builds the path for getDay and getEffectiveTarget", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ date: "2026-07-27", meals: {}, day_totals: {}, effective_target: null, delta_vs_target: null })
      )
      .mockResolvedValueOnce(jsonResponse(null));
    vi.stubGlobal("fetch", fetchMock);

    await getDay("2026-07-27");
    expect(fetchCall(fetchMock, 0)[0]).toBe("/api/day/2026-07-27");

    await getEffectiveTarget("2026-07-27");
    expect(fetchCall(fetchMock, 1)[0]).toBe("/api/targets/effective?date=2026-07-27");
  });

  it("decodes snake_case response bodies into camelCase typed objects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        {
          id: 1,
          name: "Chicken breast",
          serving_size: "100",
          serving_unit: "g",
          calories: "165",
          protein_g: "31",
          carbs_g: "0",
          fat_g: "3.6",
          fiber_g: null,
          sat_fat_g: null,
          sodium_mg: null,
          density_g_per_ml: null,
          is_favorite: false,
          created_at: "2026-01-01T00:00:00Z",
          last_logged_at: null,
          logged_count: 0
        }
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    const foods = await listFoods();

    expect(foods[0]).toMatchObject({
      servingSize: "100",
      servingUnit: "g",
      proteinG: "31",
      isFavorite: false,
      lastLoggedAt: null,
      loggedCount: 0
    });
  });

  it("encodes camelCase request bodies into snake_case JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 1 }, 201));
    vi.stubGlobal("fetch", fetchMock);

    await createFood({
      name: "Oats",
      servingSize: 40,
      servingUnit: "g",
      calories: 150,
      proteinG: 5,
      carbsG: 27,
      fatG: 3
    });

    const [, init] = fetchCall(fetchMock, 0);
    const sentBody = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(sentBody).toEqual({
      name: "Oats",
      serving_size: 40,
      serving_unit: "g",
      calories: 150,
      protein_g: 5,
      carbs_g: 27,
      fat_g: 3
    });
  });

  it("sends a favorite toggle with the correct method, path, and body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 1, is_favorite: true }));
    vi.stubGlobal("fetch", fetchMock);

    await setFavoriteFood(1, true);

    const [path, init] = fetchCall(fetchMock, 0);
    expect(path).toBe("/api/foods/1/favorite");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ is_favorite: true });
  });

  it("nests item arrays correctly when encoding createMeal", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: 1,
        logged_at: "2026-07-27T12:00:00Z",
        local_tz: "UTC",
        local_date: "2026-07-27",
        meal_type: "lunch",
        notes: null,
        items: [],
        totals: {},
        delta_vs_target: null
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await createMeal({
      items: [{ name: "Rice", quantity: 200, quantityUnit: "g", foodId: 3 }],
      loggedAt: "2026-07-27T12:00:00Z",
      localTz: "UTC"
    });

    const [, init] = fetchCall(fetchMock, 0);
    const body = JSON.parse(init.body as string) as { items: Record<string, unknown>[] };
    expect(body.items[0]).toEqual({
      name: "Rice",
      quantity: 200,
      quantity_unit: "g",
      food_id: 3
    });
  });

  it("decodes list responses (listTemplates) into camelCase arrays", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        {
          id: 1,
          name: "Breakfast",
          created_at: "2026-01-01T00:00:00Z",
          deleted_at: null,
          items: [{ id: 1, food_id: null, name: "Oats", quantity: "40", quantity_unit: "g" }]
        }
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    const templates = await listTemplates({ q: "breakfast" });

    expect(fetchCall(fetchMock, 0)[0]).toBe("/api/templates?q=breakfast");
    const [template] = templates;
    expect(template).toBeDefined();
    expect(template?.deletedAt).toBeNull();
    expect(template?.items[0]).toMatchObject({ foodId: null, quantityUnit: "g" });
  });

  it("encodes setManualCaloriesOut request body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ date: "2026-07-27", calories_out: 500, fetched_at: "2026-07-27T00:00:00Z" })
    );
    vi.stubGlobal("fetch", fetchMock);

    await setManualCaloriesOut({ date: "2026-07-27", caloriesOut: 500 });

    const [path, init] = fetchCall(fetchMock, 0);
    expect(path).toBe("/api/sync/intervals/manual");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ date: "2026-07-27", calories_out: 500 });
  });
});

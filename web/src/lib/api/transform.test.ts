import { describe, expect, it } from "vitest";
import { keysToCamel, keysToSnake } from "./transform";

describe("keysToCamel", () => {
  it("converts snake_case keys to camelCase, recursively", () => {
    const input = {
      food_id: 1,
      quantity_unit: "g",
      macros: { sat_fat_g: "1.5", sodium_mg: null }
    };

    expect(keysToCamel(input)).toEqual({
      foodId: 1,
      quantityUnit: "g",
      macros: { satFatG: 1.5, sodiumMg: null }
    });
  });

  it("converts keys inside arrays of objects", () => {
    const input = [{ meal_type: "lunch" }, { meal_type: "dinner" }];

    expect(keysToCamel(input)).toEqual([{ mealType: "lunch" }, { mealType: "dinner" }]);
  });

  it("leaves primitives and non-plain values unchanged", () => {
    expect(keysToCamel(null)).toBeNull();
    expect(keysToCamel(42)).toBe(42);
    expect(keysToCamel("effective_from")).toBe("effective_from");
  });

  it("coerces Decimal-serialized numeric strings to numbers, but leaves non-numeric strings alone", () => {
    const input = {
      calories: "350.000",
      quantity: "-12.5",
      local_date: "2026-07-27",
      logged_at: "2026-07-27T08:30:00+01:00",
      quantity_unit: "g",
      name: "Overnight Oats"
    };

    expect(keysToCamel(input)).toEqual({
      calories: 350,
      quantity: -12.5,
      localDate: "2026-07-27",
      loggedAt: "2026-07-27T08:30:00+01:00",
      quantityUnit: "g",
      name: "Overnight Oats"
    });
  });
});

describe("keysToSnake", () => {
  it("converts camelCase keys to snake_case, recursively", () => {
    const input = {
      foodId: 1,
      quantityUnit: "g",
      macros: { satFatG: 1.5, sodiumMg: null }
    };

    expect(keysToSnake(input)).toEqual({
      food_id: 1,
      quantity_unit: "g",
      macros: { sat_fat_g: 1.5, sodium_mg: null }
    });
  });

  it("round-trips through camel and back to snake", () => {
    const original = { effective_from: "2026-07-27", base_calories: 2000 };
    expect(keysToSnake(keysToCamel(original))).toEqual(original);
  });
});

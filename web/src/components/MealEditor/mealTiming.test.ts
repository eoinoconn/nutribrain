import { describe, expect, it } from "vitest";
import { formatTimeInputValue, inferMealTypeFromLocalTime } from "./mealTiming";

describe("inferMealTypeFromLocalTime", () => {
  it("mirrors the backend's breakfast window (04:00-10:59)", () => {
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 4, 0))).toBe("breakfast");
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 10, 59))).toBe("breakfast");
  });

  it("mirrors the backend's lunch window (11:00-15:59)", () => {
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 11, 0))).toBe("lunch");
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 15, 59))).toBe("lunch");
  });

  it("mirrors the backend's dinner window (16:00-21:59)", () => {
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 16, 0))).toBe("dinner");
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 21, 59))).toBe("dinner");
  });

  it("defaults to snack outside the natural windows", () => {
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 22, 0))).toBe("snack");
    expect(inferMealTypeFromLocalTime(new Date(2026, 0, 1, 3, 59))).toBe("snack");
  });
});

describe("formatTimeInputValue", () => {
  it("formats as zero-padded HH:mm", () => {
    expect(formatTimeInputValue(new Date(2026, 0, 1, 8, 5))).toBe("08:05");
    expect(formatTimeInputValue(new Date(2026, 0, 1, 23, 45))).toBe("23:45");
  });
});

import { describe, expect, it } from "vitest";
import {
  averageTargetCalories,
  computeAdherenceStats,
  formatSignedCalories,
  rangeDates,
  toTrendRows,
  type TrendRow
} from "./trends";
import type { PeriodTotals } from "./api/types";

function makePeriod(overrides: Partial<PeriodTotals> = {}): PeriodTotals {
  return {
    periodStart: "2026-07-01",
    periodEnd: "2026-07-01",
    totals: { calories: 2000, proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null },
    effectiveTarget: {
      effectiveFrom: "2026-06-01",
      baseCalories: 2000,
      proteinG: 150,
      carbsG: 200,
      fatG: 60,
      caloriesOut: null,
      effectiveCalories: 2000
    },
    adherence: true,
    ...overrides
  };
}

describe("rangeDates", () => {
  it("computes an inclusive 7-day window ending today", () => {
    const now = new Date(2026, 6, 28); // 2026-07-28 local
    expect(rangeDates(7, now)).toEqual({ from: "2026-07-22", to: "2026-07-28" });
  });

  it("computes a 30-day window that can cross a month boundary", () => {
    const now = new Date(2026, 0, 15); // 2026-01-15 local
    expect(rangeDates(30, now)).toEqual({ from: "2025-12-17", to: "2026-01-15" });
  });

  it("computes a 90-day window", () => {
    const now = new Date(2026, 6, 28);
    expect(rangeDates(90, now)).toEqual({ from: "2026-04-30", to: "2026-07-28" });
  });
});

describe("toTrendRows", () => {
  it("flattens periods into rows keyed by periodStart", () => {
    const rows = toTrendRows([
      makePeriod({ periodStart: "2026-07-01" }),
      makePeriod({ periodStart: "2026-07-02", adherence: false })
    ]);
    expect(rows).toEqual([
      {
        date: "2026-07-01",
        calories: 2000,
        proteinG: 150,
        carbsG: 200,
        fatG: 60,
        targetCalories: 2000,
        adherence: true
      },
      {
        date: "2026-07-02",
        calories: 2000,
        proteinG: 150,
        carbsG: 200,
        fatG: 60,
        targetCalories: 2000,
        adherence: false
      }
    ]);
  });

  it("carries a null target through when a period has no effective target", () => {
    const rows = toTrendRows([makePeriod({ effectiveTarget: null, adherence: null })]);
    expect(rows[0]!.targetCalories).toBeNull();
    expect(rows[0]!.adherence).toBeNull();
  });
});

describe("averageTargetCalories", () => {
  it("averages only rows that have a target", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true },
      { date: "2026-07-02", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2400, adherence: true },
      { date: "2026-07-03", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: null, adherence: null }
    ];
    expect(averageTargetCalories(rows)).toBe(2200);
  });

  it("returns null when no row has a target", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: null, adherence: null }
    ];
    expect(averageTargetCalories(rows)).toBeNull();
  });
});

describe("computeAdherenceStats", () => {
  it("computes average adherence percent over judged days only", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 2000, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true },
      { date: "2026-07-02", calories: 2500, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: false },
      { date: "2026-07-03", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: null, adherence: null }
    ];
    const stats = computeAdherenceStats(rows);
    expect(stats.averageAdherencePct).toBe(50);
  });

  it("returns null average adherence when no day has a target", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 2000, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: null, adherence: null }
    ];
    expect(computeAdherenceStats(rows).averageAdherencePct).toBeNull();
  });

  it("finds the longest consecutive in-target streak, resetting on a miss or unjudged day", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true },
      { date: "2026-07-02", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true },
      { date: "2026-07-03", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: false },
      { date: "2026-07-04", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true },
      { date: "2026-07-05", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true },
      { date: "2026-07-06", calories: 0, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true }
    ];
    expect(computeAdherenceStats(rows).longestStreakDays).toBe(3);
  });

  it("picks the day with the largest absolute miss vs. target as the worst miss", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 2600, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: false },
      { date: "2026-07-02", calories: 1200, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: false },
      { date: "2026-07-03", calories: 2050, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: false }
    ];
    const stats = computeAdherenceStats(rows);
    expect(stats.worstMiss).toEqual({ date: "2026-07-02", deltaCalories: -800 });
  });

  it("returns null worst miss when there are no misses", () => {
    const rows: TrendRow[] = [
      { date: "2026-07-01", calories: 2000, proteinG: 0, carbsG: 0, fatG: 0, targetCalories: 2000, adherence: true }
    ];
    expect(computeAdherenceStats(rows).worstMiss).toBeNull();
  });
});

describe("formatSignedCalories", () => {
  it("prefixes a plus sign for positive values", () => {
    expect(formatSignedCalories(342.6)).toBe("+343");
  });

  it("keeps the minus sign for negative values", () => {
    expect(formatSignedCalories(-800)).toBe("-800");
  });

  it("shows no sign for zero", () => {
    expect(formatSignedCalories(0)).toBe("0");
  });
});

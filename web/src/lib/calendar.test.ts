import { describe, expect, it } from "vitest";
import {
  NEAR_TARGET_OVER_FRACTION,
  calendarRange,
  classifyDay,
  computeCalendarSummary,
  toHeatmapDays
} from "./calendar";
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

describe("calendarRange", () => {
  it("computes an inclusive 365-day window ending today", () => {
    const now = new Date(2026, 6, 28); // 2026-07-28 local
    const { from, to } = calendarRange(now);
    expect(to).toBe("2026-07-28");
    const fromDate = new Date(from);
    const toDate = new Date(to);
    const diffDays = Math.round((toDate.getTime() - fromDate.getTime()) / (1000 * 60 * 60 * 24));
    expect(diffDays).toBe(364);
  });
});

describe("classifyDay", () => {
  it("is in-target when the backend adherence flag is true and something was logged", () => {
    expect(classifyDay(makePeriod({ adherence: true }))).toBe("in-target");
  });

  it("is no-log when nothing was logged that day, even with a target set", () => {
    const period = makePeriod({
      totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null },
      adherence: true // 0 <= target is technically "true" from the backend, but nothing was logged
    });
    expect(classifyDay(period)).toBe("no-log");
  });

  it("is no-log when there is no effective target, even if food was logged", () => {
    const period = makePeriod({ effectiveTarget: null, adherence: null });
    expect(classifyDay(period)).toBe("no-log");
  });

  it("is near when over target by up to NEAR_TARGET_OVER_FRACTION", () => {
    const period = makePeriod({
      totals: { calories: 2000 * (1 + NEAR_TARGET_OVER_FRACTION), proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null },
      adherence: false
    });
    expect(classifyDay(period)).toBe("near");
  });

  it("is outside when over target by more than NEAR_TARGET_OVER_FRACTION", () => {
    const period = makePeriod({
      totals: { calories: 2000 * (1 + NEAR_TARGET_OVER_FRACTION) + 50, proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null },
      adherence: false
    });
    expect(classifyDay(period)).toBe("outside");
  });
});

describe("toHeatmapDays", () => {
  it("reshapes periods into HeatmapDay rows keyed by periodStart", () => {
    const days = toHeatmapDays([makePeriod({ periodStart: "2026-07-15" })]);
    expect(days).toEqual([
      {
        date: "2026-07-15",
        state: "in-target",
        calories: 2000,
        proteinG: 150,
        carbsG: 200,
        fatG: 60,
        targetCalories: 2000,
        hasLog: true
      }
    ]);
  });
});

describe("computeCalendarSummary", () => {
  it("counts logged days, in-target days, and the longest in-target streak", () => {
    const days = toHeatmapDays([
      makePeriod({ periodStart: "2026-07-01", adherence: true }),
      makePeriod({ periodStart: "2026-07-02", adherence: true }),
      makePeriod({
        periodStart: "2026-07-03",
        adherence: false,
        totals: { calories: 3000, proteinG: 150, carbsG: 200, fatG: 60, fiberG: null, satFatG: null, sodiumMg: null }
      }),
      makePeriod({
        periodStart: "2026-07-04",
        effectiveTarget: null,
        adherence: null,
        totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null }
      }),
      makePeriod({ periodStart: "2026-07-05", adherence: true })
    ]);

    const summary = computeCalendarSummary(days);
    expect(summary.daysLogged).toBe(4);
    expect(summary.daysInTarget).toBe(3);
    expect(summary.longestStreakDays).toBe(2);
  });

  it("reports zero streak and zero in-target days for an all-no-log range", () => {
    const days = toHeatmapDays([
      makePeriod({
        periodStart: "2026-07-01",
        effectiveTarget: null,
        adherence: null,
        totals: { calories: 0, proteinG: 0, carbsG: 0, fatG: 0, fiberG: null, satFatG: null, sodiumMg: null }
      })
    ]);
    const summary = computeCalendarSummary(days);
    expect(summary).toEqual({ daysLogged: 0, daysInTarget: 0, longestStreakDays: 0 });
  });
});

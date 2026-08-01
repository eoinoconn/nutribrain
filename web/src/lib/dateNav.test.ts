import { describe, expect, it } from "vitest";
import { addDays, dayTitleLabel, weekdayName } from "./dateNav";

describe("addDays", () => {
  it("steps forward one day within a month", () => {
    expect(addDays("2026-07-20", 1)).toBe("2026-07-21");
  });

  it("steps backward one day within a month", () => {
    expect(addDays("2026-07-20", -1)).toBe("2026-07-19");
  });

  it("rolls forward across a month boundary", () => {
    expect(addDays("2026-07-31", 1)).toBe("2026-08-01");
  });

  it("rolls backward across a month boundary", () => {
    expect(addDays("2026-08-01", -1)).toBe("2026-07-31");
  });

  it("rolls forward across a year boundary", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("rolls backward across a year boundary", () => {
    expect(addDays("2027-01-01", -1)).toBe("2026-12-31");
  });

  it("handles the Feb 29 leap-year boundary", () => {
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDays("2028-02-29", 1)).toBe("2028-03-01");
  });

  it("skips Feb 29 on a non-leap year", () => {
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");
  });

  it("supports multi-day deltas", () => {
    expect(addDays("2026-01-01", 40)).toBe("2026-02-10");
  });

  it("throws on a malformed input date", () => {
    expect(() => addDays("not-a-date", 1)).toThrow(/Invalid YYYY-MM-DD/);
  });
});

describe("weekdayName", () => {
  it("resolves the correct weekday regardless of host timezone", () => {
    expect(weekdayName("2026-07-29")).toBe("Wednesday");
    expect(weekdayName("2026-07-20")).toBe("Monday");
    expect(weekdayName("2026-08-01")).toBe("Saturday");
  });
});

describe("dayTitleLabel", () => {
  it("returns \"Today\" when the date matches today", () => {
    expect(dayTitleLabel("2026-08-01", "2026-08-01")).toBe("Today");
  });

  it("returns the weekday name for any other date", () => {
    expect(dayTitleLabel("2026-07-29", "2026-08-01")).toBe("Wednesday");
  });
});

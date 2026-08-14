import { afterEach, describe, expect, it, vi } from "vitest";
import { formatWallClockTime } from "./wallClockTime";

describe("formatWallClockTime", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves the literal wall-clock time from an ISO string with an offset", () => {
    const spy = vi.spyOn(Date.prototype, "toLocaleTimeString").mockImplementation(function (
      this: Date,
      _locales?: Intl.LocalesArgument,
      options?: Intl.DateTimeFormatOptions
    ): string {
      return `${String(this.getUTCHours()).padStart(2, "0")}:${String(this.getUTCMinutes()).padStart(2, "0")}|${options?.timeZone ?? "local"}`;
    });

    expect(formatWallClockTime("2026-07-20T10:15:00+01:00")).toBe("10:15|UTC");
    expect(spy).toHaveBeenCalledWith([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  });

  it("falls back to native Date parsing when no time component is present", () => {
    const spy = vi.spyOn(Date.prototype, "toLocaleTimeString").mockImplementation(function (
      this: Date,
      _locales?: Intl.LocalesArgument,
      options?: Intl.DateTimeFormatOptions
    ): string {
      return `${String(this.getUTCHours()).padStart(2, "0")}:${String(this.getUTCMinutes()).padStart(2, "0")}|${options?.timeZone ?? "local"}`;
    });

    expect(formatWallClockTime("2026-07-20")).toBe("00:00|local");
    expect(spy).toHaveBeenCalledWith([], { hour: "2-digit", minute: "2-digit" });
  });
});

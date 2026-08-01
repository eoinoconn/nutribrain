/**
 * Pure calendar-day arithmetic for the day-view date picker (§3 of
 * docs/features/today_ui_redesign.md). Operates only on `YYYY-MM-DD`
 * strings using `Date.UTC`-anchored arithmetic, so it never touches the
 * browser's local timezone — this avoids the day-shift bug docs/style.md
 * §5 warns about (deriving a local day from a UTC-parsed `Date`). We're not
 * deriving a local day from a timestamp here; we're doing calendar math on
 * an already-resolved `YYYY-MM-DD` string, anchoring it to UTC purely so
 * `Date`'s month/year-rollover arithmetic can't be perturbed by the host's
 * own timezone offset.
 */

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

function parseDateParts(date: string): { year: number; month: number; day: number } {
  const match = DATE_PATTERN.exec(date);
  if (!match) {
    throw new Error(`Invalid YYYY-MM-DD date: "${date}"`);
  }
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * Adds `deltaDays` (may be negative) calendar days to a `YYYY-MM-DD`
 * string, returning a new `YYYY-MM-DD` string. Handles month/year
 * boundaries correctly since `Date.UTC` normalizes out-of-range day values.
 */
export function addDays(date: string, deltaDays: number): string {
  const { year, month, day } = parseDateParts(date);
  const shifted = new Date(Date.UTC(year, month - 1, day + deltaDays));
  return `${shifted.getUTCFullYear()}-${pad2(shifted.getUTCMonth() + 1)}-${pad2(shifted.getUTCDate())}`;
}

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** Full weekday name (e.g. "Wednesday") for a `YYYY-MM-DD` string. */
export function weekdayName(date: string): string {
  const { year, month, day } = parseDateParts(date);
  const asDate = new Date(Date.UTC(year, month - 1, day));
  return WEEKDAY_NAMES[asDate.getUTCDay()]!;
}

/**
 * Day-view page-title label (§3): "Today" when `date` matches `today`,
 * otherwise the weekday name (e.g. "Wednesday"). Callers append the
 * `&mdash; YYYY-MM-DD` date suffix themselves (`DayHeader` already does) —
 * this only returns the leading label.
 */
export function dayTitleLabel(date: string, today: string): string {
  return date === today ? "Today" : weekdayName(date);
}

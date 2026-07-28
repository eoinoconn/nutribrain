/**
 * Pure computation helpers for the Calendar heatmap view (T-077, spec §7):
 * `/calendar`.
 *
 * Like Trends (T-076, `./trends.ts`), this reshapes `GET /api/range`
 * (`PeriodTotals[]`, day granularity) into view-friendly rows. It does not
 * recompute macros or effective targets — those are already-computed backend
 * output (CLAUDE.md/docs/style.md: business rules live only in the domain
 * layer).
 *
 * One thing this module *does* decide, because the backend doesn't expose
 * it: which of the spec's four heatmap buckets (green in target / yellow
 * near / red outside / grey no log) a day falls into. The backend's
 * `PeriodTotals.adherence` is a plain boolean (`calories <= effectiveTarget`,
 * see `api/app/domain/day_aggregation.py`) with no magnitude — a day 5%
 * over target and a day 50% over target both come back `adherence: false`.
 * To distinguish "yellow near" from "red outside" per the spec, this module
 * buckets `adherence: false` days by how far over target they were, using
 * `NEAR_TARGET_OVER_FRACTION` as the single named threshold (see doc comment
 * on that constant). This is a display-bucketing decision, not a new
 * business rule about what "adherence" means — the underlying `true/false`
 * flag is left untouched and still comes straight from the backend.
 */

import type { PeriodTotals } from "./api/types";
import type { AdherenceState } from "../design/adherence";

/**
 * A day whose logged calories exceed target by up to this fraction is
 * bucketed "near" (yellow) rather than "outside" (red). Chosen as a round
 * number in the same spirit as a "close enough" nutrition-app tolerance —
 * roughly the size of a small snack (e.g. ~200 kcal against a 2000 kcal
 * target) — rather than derived from any spec value, since the spec leaves
 * "near" undefined. Days at or under target are always "in-target" (green),
 * matching the backend's own `adherence` flag and Trends' streak/adherence
 * math, so this threshold only ever affects the false-adherence days.
 */
export const NEAR_TARGET_OVER_FRACTION = 0.1;

/** Twelve-month heatmap window length. See doc comment on `calendarRange`. */
export const CALENDAR_WINDOW_DAYS = 365;

export interface HeatmapDay {
  date: string;
  state: AdherenceState;
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  targetCalories: number | null;
  /** True when nothing at all was logged this day (all macro totals are zero). */
  hasLog: boolean;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function formatLocalDate(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/**
 * Computes the `[from, to]` bounds (inclusive, `YYYY-MM-DD`) for the
 * twelve-month heatmap, ending today. Uses local calendar arithmetic (never
 * UTC-parses a date string), same rationale as `./trends.ts#rangeDates`.
 *
 * A single `get_range(day)` call over 365 days was checked against the
 * domain implementation (`api/app/domain/day_aggregation.py#get_range`):
 * it loads all meals in range with one bounded query (`local_date` range
 * filter, eager-loaded items) plus one batch food query, then aggregates
 * in memory — no per-day query loop. The response is ~365 small
 * `PeriodTotals` objects (no meal items included, just totals), so a
 * single 365-day call is reasonably sized and does not need to be split
 * into monthly requests.
 */
export function calendarRange(now: Date = new Date()): { from: string; to: string } {
  const to = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const from = new Date(to.getFullYear(), to.getMonth(), to.getDate() - (CALENDAR_WINDOW_DAYS - 1));
  return { from: formatLocalDate(from), to: formatLocalDate(to) };
}

/** Buckets a single day's period into one of the four heatmap colors. */
export function classifyDay(period: PeriodTotals): AdherenceState {
  const hasLog =
    period.totals.calories > 0 ||
    period.totals.proteinG > 0 ||
    period.totals.carbsG > 0 ||
    period.totals.fatG > 0;

  const targetCalories = period.effectiveTarget?.effectiveCalories ?? null;

  // No target to judge against: grey, same bucket as "no log", since there's
  // nothing to color green/yellow/red without a target (documented above).
  if (targetCalories === null) {
    return "no-log";
  }

  if (!hasLog) {
    return "no-log";
  }

  if (period.adherence === true) {
    return "in-target";
  }

  const overFraction = (period.totals.calories - targetCalories) / targetCalories;
  return overFraction <= NEAR_TARGET_OVER_FRACTION ? "near" : "outside";
}

export function toHeatmapDays(periods: PeriodTotals[]): HeatmapDay[] {
  return periods.map((period) => ({
    date: period.periodStart,
    state: classifyDay(period),
    calories: period.totals.calories,
    proteinG: period.totals.proteinG,
    carbsG: period.totals.carbsG,
    fatG: period.totals.fatG,
    targetCalories: period.effectiveTarget?.effectiveCalories ?? null,
    hasLog:
      period.totals.calories > 0 ||
      period.totals.proteinG > 0 ||
      period.totals.carbsG > 0 ||
      period.totals.fatG > 0
  }));
}

export interface CalendarSummary {
  daysLogged: number;
  daysInTarget: number;
  longestStreakDays: number;
}

/**
 * Aggregates a text summary for the accessibility floor (spec §7: charts
 * need a text summary beneath them, same principle as Recharts since
 * react-calendar-heatmap has the same screen-reader problem). Mirrors the
 * shape of `./trends.ts#computeAdherenceStats` but scoped to what's
 * meaningful for a whole-year day grid: total days logged, days in target,
 * and the longest in-target streak (streak breaks on any day that isn't
 * "in-target", including no-log days — a gap in logging isn't a maintained
 * streak).
 */
export function computeCalendarSummary(days: HeatmapDay[]): CalendarSummary {
  const daysLogged = days.filter((day) => day.hasLog).length;
  const daysInTarget = days.filter((day) => day.state === "in-target").length;

  let longestStreakDays = 0;
  let currentStreak = 0;
  for (const day of days) {
    if (day.state === "in-target") {
      currentStreak += 1;
      longestStreakDays = Math.max(longestStreakDays, currentStreak);
    } else {
      currentStreak = 0;
    }
  }

  return { daysLogged, daysInTarget, longestStreakDays };
}

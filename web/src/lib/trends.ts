/**
 * Pure computation helpers for the Trends view (T-076, spec §7).
 *
 * `GET /api/range` (see `./api/client#getRange`, `./api/types#RangeResponse`)
 * already returns per-period totals, each period's own effective target, and
 * a per-period `adherence` boolean|null flag computed by the backend domain
 * layer. Per CLAUDE.md/docs/style.md, business rules (what counts as "in
 * target") live only in that domain layer — this module does not invent its
 * own threshold. It only reshapes/aggregates the already-computed flags and
 * totals for charting and the stat tiles.
 *
 * `adherence` is `null` when a period had no effective target (nothing to
 * judge against); those periods are excluded from the adherence-percentage,
 * streak, and worst-miss calculations below, since there's no "miss" to
 * measure without a target.
 */

import type { PeriodTotals } from "./api/types";

export type TrendRangeDays = 7 | 30 | 90;

export const TREND_RANGE_OPTIONS: readonly TrendRangeDays[] = [7, 30, 90];

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function formatLocalDate(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/**
 * Computes the `[from, to]` bounds (inclusive, `YYYY-MM-DD`) for a range
 * selector option, ending today. Uses local calendar arithmetic (never
 * UTC-parses a date string) to avoid the classic off-by-one-day bug — see
 * `docs/style.md` §5 on never deriving local days from UTC.
 */
export function rangeDates(days: TrendRangeDays, now: Date = new Date()): { from: string; to: string } {
  const to = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const from = new Date(to.getFullYear(), to.getMonth(), to.getDate() - (days - 1));
  return { from: formatLocalDate(from), to: formatLocalDate(to) };
}

export interface TrendRow {
  date: string;
  calories: number;
  proteinG: number;
  carbsG: number;
  fatG: number;
  targetCalories: number | null;
  adherence: boolean | null;
}

/** Reshapes `RangeResponse.periods` into flat rows keyed by `periodStart` for charting. */
export function toTrendRows(periods: PeriodTotals[]): TrendRow[] {
  return periods.map((period) => ({
    date: period.periodStart,
    calories: period.totals.calories,
    proteinG: period.totals.proteinG,
    carbsG: period.totals.carbsG,
    fatG: period.totals.fatG,
    targetCalories: period.effectiveTarget?.effectiveCalories ?? null,
    adherence: period.adherence
  }));
}

/**
 * A day-to-day varying target can't be drawn as Recharts' single-value
 * `ReferenceLine` (spec §7 asks for `ReferenceLine`, which is a flat line).
 * Rather than adding N reference lines (one per day, illegible past a week)
 * or a second target series (spec explicitly names `ReferenceLine`), this
 * averages the effective target across days that have one and draws that
 * average as the flat overlay. The text summary beneath the chart calls out
 * that it's an average, since actual daily targets vary with calories-out.
 */
export function averageTargetCalories(rows: TrendRow[]): number | null {
  const withTarget = rows.filter((row) => row.targetCalories !== null);
  if (withTarget.length === 0) {
    return null;
  }
  const total = withTarget.reduce((sum, row) => sum + (row.targetCalories ?? 0), 0);
  return total / withTarget.length;
}

export interface WorstMiss {
  date: string;
  deltaCalories: number;
}

export interface AdherenceStats {
  /** Null when no period in range has a target to judge adherence against. */
  averageAdherencePct: number | null;
  longestStreakDays: number;
  worstMiss: WorstMiss | null;
}

/**
 * Aggregates the backend's per-period `adherence` flags into the three stat
 * tiles. All three ignore periods with `adherence === null` (no target set
 * that day), since there's nothing to score.
 */
export function computeAdherenceStats(rows: TrendRow[]): AdherenceStats {
  const judged = rows.filter((row) => row.adherence !== null);

  const averageAdherencePct =
    judged.length === 0 ? null : (judged.filter((row) => row.adherence === true).length / judged.length) * 100;

  let longestStreakDays = 0;
  let currentStreak = 0;
  for (const row of rows) {
    if (row.adherence === true) {
      currentStreak += 1;
      longestStreakDays = Math.max(longestStreakDays, currentStreak);
    } else {
      currentStreak = 0;
    }
  }

  let worstMiss: WorstMiss | null = null;
  for (const row of judged) {
    if (row.adherence !== false || row.targetCalories === null) {
      continue;
    }
    const deltaCalories = row.calories - row.targetCalories;
    if (worstMiss === null || Math.abs(deltaCalories) > Math.abs(worstMiss.deltaCalories)) {
      worstMiss = { date: row.date, deltaCalories };
    }
  }

  return { averageAdherencePct, longestStreakDays, worstMiss };
}

export function formatSignedCalories(value: number): string {
  const rounded = Math.round(value);
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded.toLocaleString()}`;
}

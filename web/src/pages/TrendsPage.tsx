/**
 * Trends view (T-076, spec §7): `/trends`.
 *
 * Fetches `GET /api/range` (day granularity) for a 7/30/90-day window ending
 * today and renders a calorie line chart with a target overlay, a stacked
 * protein/carbs/fat bar chart, and three stat tiles (average adherence,
 * longest in-target streak, worst-miss day). Each chart has a plain-text
 * summary beneath it per the accessibility floor (spec §7) — Recharts alone
 * isn't screen-reader-friendly.
 *
 * This is a read-only view: no mutations, so no optimistic-update/rollback
 * pattern is needed, just loading/error/success query states matching the
 * rest of the app (see TodayPage/DayPage).
 *
 * All computation here operates on already-computed backend output
 * (`PeriodTotals.adherence`, `PeriodTotals.effectiveTarget`) — it does not
 * invent its own adherence threshold or recompute macros (CLAUDE.md).
 */

import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getRange } from "../lib/api/client";
import { queryKeys } from "../lib/queryClient";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import {
  TREND_RANGE_OPTIONS,
  averageTargetCalories,
  computeAdherenceStats,
  formatSignedCalories,
  rangeDates,
  toTrendRows,
  type TrendRangeDays,
  type TrendRow
} from "../lib/trends";

const CALORIE_COLOR = "#c2410c"; // accent (orange-700, tailwind.config.ts `accent`), the app's brand accent
const TARGET_COLOR = "#71717a"; // ink-tertiary (zinc-500), muted so it reads as an overlay, not a series
const PROTEIN_COLOR = "#0284c7"; // sky-600, kept distinct from CALORIE_COLOR/accent so it doesn't read as the
// same series as the calorie line, and distinct from CARBS_COLOR (amber-600) so adjacent stacked-bar
// segments aren't both orange-family hues
const CARBS_COLOR = "#d97706"; // amber-600
const FAT_COLOR = "#7c3aed"; // violet-600

function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatShortDate(value: string): string {
  const [, month, day] = value.split("-");
  return `${month}/${day}`;
}

function RangeSelector({
  value,
  onChange
}: {
  value: TrendRangeDays;
  onChange: (days: TrendRangeDays) => void;
}): JSX.Element {
  return (
    <div role="group" aria-label="Trend range" className="flex gap-2">
      {TREND_RANGE_OPTIONS.map((days) => {
        const isSelected = days === value;
        return (
          <button
            key={days}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onChange(days)}
            className={`focus-ring rounded-md border px-3 py-1.5 text-sm font-medium ${
              isSelected
                ? "border-accent bg-accent text-white"
                : "border-line text-ink-secondary hover:bg-canvas dark:border-line-dark dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
            }`}
          >
            {days}d
          </button>
        );
      })}
    </div>
  );
}

function CalorieTrendChart({ rows }: { rows: TrendRow[] }): JSX.Element {
  const avgTarget = averageTargetCalories(rows);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const avgCalories = rows.reduce((sum, row) => sum + row.calories, 0) / rows.length;
  const targetsVary =
    new Set(rows.map((row) => row.targetCalories).filter((value): value is number => value !== null)).size > 1;

  return (
    <div className="space-y-2">
      <h3 className="text-lg font-semibold">Calories per day</h3>
      <div className="h-64 w-full" role="img" aria-label="Line chart of daily calories against target">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-line dark:stroke-line-dark" />
            <XAxis dataKey="date" tickFormatter={formatShortDate} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} width={48} />
            <Tooltip
              labelFormatter={(label: string) => label}
              formatter={(value: number, name: string) => [formatCalories(value), name]}
            />
            <Legend />
            {avgTarget !== null ? (
              <ReferenceLine
                y={avgTarget}
                stroke={TARGET_COLOR}
                strokeDasharray="4 4"
                label={{ value: "Avg target", position: "insideTopRight", fontSize: 12, fill: TARGET_COLOR }}
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="calories"
              name="Calories"
              stroke={CALORIE_COLOR}
              strokeWidth={2}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
        {first && last ? (
          <>
            From {first.date} to {last.date}, calories averaged {formatCalories(avgCalories)} per day
            {avgTarget !== null
              ? `, against a target that averaged ${formatCalories(avgTarget)} per day${
                  targetsVary ? " (the daily target varies with calories burned)" : ""
                }.`
              : " (no target was set for this range)."}
          </>
        ) : null}
      </p>
    </div>
  );
}

function MacroStackedBarChart({ rows }: { rows: TrendRow[] }): JSX.Element {
  const totals = rows.reduce(
    (acc, row) => ({
      proteinG: acc.proteinG + row.proteinG,
      carbsG: acc.carbsG + row.carbsG,
      fatG: acc.fatG + row.fatG
    }),
    { proteinG: 0, carbsG: 0, fatG: 0 }
  );
  const count = rows.length || 1;
  const avgProtein = totals.proteinG / count;
  const avgCarbs = totals.carbsG / count;
  const avgFat = totals.fatG / count;

  return (
    <div className="space-y-2">
      <h3 className="text-lg font-semibold">Protein / carbs / fat per day</h3>
      <div
        className="h-64 w-full"
        role="img"
        aria-label="Stacked bar chart of daily protein, carbs, and fat grams"
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-line dark:stroke-line-dark" />
            <XAxis dataKey="date" tickFormatter={formatShortDate} tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} width={48} />
            <Tooltip formatter={(value: number, name: string) => [`${value.toFixed(1)} g`, name]} />
            <Legend />
            <Bar dataKey="proteinG" name="Protein" stackId="macros" fill={PROTEIN_COLOR} />
            <Bar dataKey="carbsG" name="Carbs" stackId="macros" fill={CARBS_COLOR} />
            <Bar dataKey="fatG" name="Fat" stackId="macros" fill={FAT_COLOR} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
        Averaged over {rows.length} day{rows.length === 1 ? "" : "s"}: {avgProtein.toFixed(1)} g protein,{" "}
        {avgCarbs.toFixed(1)} g carbs, and {avgFat.toFixed(1)} g fat per day.
      </p>
    </div>
  );
}

function StatTile({ label, value, detail }: { label: string; value: string; detail?: string }): JSX.Element {
  return (
    <div className="rounded-lg border border-line p-4 dark:border-line-dark">
      <dt className="text-sm font-medium text-ink-secondary dark:text-ink-secondary-dark">{label}</dt>
      <dd className="mt-1 text-2xl font-bold tracking-tight">{value}</dd>
      {detail ? <p className="mt-1 text-xs text-ink-tertiary dark:text-ink-tertiary-dark">{detail}</p> : null}
    </div>
  );
}

function StatTiles({ rows }: { rows: TrendRow[] }): JSX.Element {
  const stats = computeAdherenceStats(rows);

  return (
    <dl className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatTile
        label="Average adherence"
        value={stats.averageAdherencePct !== null ? `${Math.round(stats.averageAdherencePct)}%` : "—"}
        detail={stats.averageAdherencePct !== null ? "of days with a target were in target" : "no target set in range"}
      />
      <StatTile
        label="Longest in-target streak"
        value={`${stats.longestStreakDays} day${stats.longestStreakDays === 1 ? "" : "s"}`}
      />
      <StatTile
        label="Worst miss"
        value={stats.worstMiss ? stats.worstMiss.date : "—"}
        detail={
          stats.worstMiss
            ? `${formatSignedCalories(stats.worstMiss.deltaCalories)} calories vs. target`
            : "no misses in range"
        }
      />
    </dl>
  );
}

export default function TrendsPage(): JSX.Element {
  const navigate = useNavigate();
  const [rangeDays, setRangeDays] = useState<TrendRangeDays>(30);
  const { from, to } = useMemo(() => rangeDates(rangeDays), [rangeDays]);

  const rangeQuery = useQuery({
    queryKey: queryKeys.range(from, to, "day"),
    queryFn: () => getRange({ from, to, granularity: "day" })
  });

  const rows = useMemo(() => (rangeQuery.data ? toTrendRows(rangeQuery.data.periods) : []), [rangeQuery.data]);
  const hasData = rows.some((row) => row.calories > 0 || row.proteinG > 0 || row.carbsG > 0 || row.fatG > 0);

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold tracking-tight">Trends</h1>
        <RangeSelector value={rangeDays} onChange={setRangeDays} />
      </header>

      {rangeQuery.isLoading ? (
        <div className="space-y-6">
          <Skeleton className="h-8 w-64" label="Loading trends" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : rangeQuery.isError || !rangeQuery.data ? (
        <div className="space-y-4">
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            Could not load trend data.
          </p>
          <button
            type="button"
            onClick={() => void rangeQuery.refetch()}
            className="focus-ring rounded-md border border-line px-3 py-2 text-sm font-medium hover:bg-canvas dark:border-line-dark dark:hover:bg-panel-dark"
          >
            Retry
          </button>
        </div>
      ) : hasData ? (
        <div className="space-y-8">
          <StatTiles rows={rows} />
          <CalorieTrendChart rows={rows} />
          <MacroStackedBarChart rows={rows} />
        </div>
      ) : (
        <EmptyState
          message={`no meals logged in the last ${rangeDays} days`}
          nudge="tell Claude, or log a meal on Today"
          action={{
            label: "Go to Today",
            onClick: () => {
              void navigate("/");
            }
          }}
        />
      )}
    </section>
  );
}

/**
 * Standalone energy-balance chart (EC-09, docs/features/energy_balance_chart.md §8).
 *
 * Renders a recharts `LineChart` combining the "so far" energy balance
 * (`points`, solid line) with the rest-of-day forecast (`forecastPoints`,
 * dashed line), a `ReferenceLine` marking "now", scatter markers for
 * meal/workout events, and a categorical fueling badge for any
 * `fuelingFlags` entry (never a bare signed number framed as loss/gain —
 * spec §8 explicit constraint).
 *
 * Pure presentational component: it accepts already-fetched energy timeline
 * data and a loading flag as props and does no data-fetching of its own
 * (CLAUDE.md: business logic and TanStack Query wiring belong to the caller
 * — EC-10 wires this into `DayView.tsx` with the query/isToday gating).
 *
 * Follows the same "chart + plain-text summary beneath" accessibility
 * pattern already established by `TrendsPage.tsx` (spec §7): recharts alone
 * isn't screen-reader-friendly, so a text-equivalent summary of current
 * balance, predicted end-of-day vs. target, and fueling status in words is
 * always rendered beneath the chart.
 */

import type { TooltipProps } from "recharts";
import { ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { EnergyEvent, EnergyTimeline, FuelingFlag } from "../lib/api/types";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import { computeHourTicks, computeYTicks } from "./energyChartTicks";

const BALANCE_COLOR = "#c2410c"; // accent (orange-700, matches TrendsPage's calorie line)
const FORECAST_COLOR = "#c2410c"; // same hue, dashed strokeDasharray distinguishes it as forecast
const NOW_LINE_COLOR = "#71717a"; // ink-tertiary (zinc-500), matches TrendsPage's target overlay muting
const ZERO_LINE_COLOR = "#d4d4d8"; // zinc-300, a light neutral baseline
const EVENT_MEAL_COLOR = "#0284c7"; // sky-600, distinct series from the balance/forecast line
const EVENT_WORKOUT_COLOR = "#7c3aed"; // violet-600, distinct from meal markers

function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatTimeMs(ms: number): string {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Categorical, non-alarming copy for each fueling status — never a bare signed number. */
const FUELING_LABELS: Record<FuelingFlag["status"], string> = {
  well_fueled: "Well fueled",
  under_fueled: "Could use more fuel"
};

const FUELING_BADGE_CLASSES: Record<FuelingFlag["status"], string> = {
  well_fueled:
    "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  under_fueled: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
};

function FuelingBadge({ flag }: { flag: FuelingFlag }): JSX.Element {
  return (
    <span
      data-testid="fueling-badge"
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${FUELING_BADGE_CLASSES[flag.status]}`}
    >
      {FUELING_LABELS[flag.status]}
    </span>
  );
}

interface ChartRow {
  /** Epoch milliseconds, nudged by whole milliseconds to be unique across
   * the whole row set (see the comment above `dedupeStepTimestamp` below) —
   * a numeric x value so the axis spaces points by actual elapsed time, not
   * evenly-by-index (a category axis on formatted time labels was the
   * original bug: recharts spaces category ticks by count, not by the real
   * gaps between timestamps). */
  at: number;
  /** The real, un-nudged timestamp — what a step's own event should match
   * against and what tick/domain-adjacent rounding should use for display. */
  originalAt: number;
  actualBalance: number | null;
  forecastBalance: number | null;
  /** The balance to plot a marker at for this row's event, or null for rows
   * with no event. Kept in the *same* shared row array as the Line series
   * (rather than a separate array handed to `<Scatter>`) so every series
   * shares one index space — see the comment on `<Scatter>` below for why
   * that matters. */
  eventMarker: number | null;
  event: EnergyEvent | null;
}

/** Every step (a meal or workout) contributes two rows at the *same*
 * instant — the balance immediately before and immediately after the jump
 * — to render the vertical part of the step. Recharts' hover/tooltip
 * lookup assumes strictly-increasing x values on a numeric axis; with
 * several tied pairs across the dataset, hovering near one step could
 * resolve to a neighboring step's data instead (observed: the tooltip and
 * "now"-style crosshair snapping to the wrong point). Nudging each row in a
 * tied pair by whole milliseconds keeps them visually identical (a
 * millisecond is imperceptible against an hours-wide axis) while making
 * every x value on the axis unique. */
function dedupeStepTimestamp(originalAt: number, lastOriginalAt: number | null, dupCount: number): number {
  return originalAt === lastOriginalAt ? originalAt + dupCount : originalAt;
}

function buildChartRows(energy: EnergyTimeline): ChartRow[] {
  const rows: ChartRow[] = [];
  let lastOriginalAt: number | null = null;
  let dupCount = 0;

  function pushRow(originalAt: number, actualBalance: number | null, forecastBalance: number | null): void {
    dupCount = originalAt === lastOriginalAt ? dupCount + 1 : 0;
    const at = dedupeStepTimestamp(originalAt, lastOriginalAt, dupCount);
    lastOriginalAt = originalAt;
    rows.push({ at, originalAt, actualBalance, forecastBalance, eventMarker: null, event: null });
  }

  energy.points.forEach((point) => {
    pushRow(new Date(point.at).getTime(), point.balance, null);
  });

  const lastActual = energy.points[energy.points.length - 1];

  energy.forecastPoints.forEach((point, index) => {
    const originalAt = new Date(point.at).getTime();
    // The first forecast point shares its timestamp with the last actual
    // point (per spec §8, "now" boundary) — bridge the two lines there
    // instead of leaving a gap, rather than pushing a duplicate row.
    if (index === 0 && lastActual && point.at === lastActual.at) {
      rows[rows.length - 1] = { ...rows[rows.length - 1]!, forecastBalance: point.balance };
      return;
    }
    pushRow(originalAt, null, point.balance);
  });

  // Second pass: attach each event to its matching row (the later of the
  // two same-timestamp rows for that step — the post-step balance) rather
  // than building a separate array. `<Scatter>` reading from this same
  // shared array, instead of its own independently-indexed `data` prop, is
  // what actually fixes the tooltip-snaps-to-the-wrong-point bug: recharts
  // resolves the hovered index separately per data source, so a Line series
  // (chart-level `data`, ~a dozen rows) and a Scatter series (a handful of
  // sparse event rows) could each resolve a *different* "nearest" row for
  // the same mouse position and disagree on what the tooltip shows.
  energy.events.forEach((event) => {
    const atMs = new Date(event.at).getTime();
    const matches = rows.filter((row) => row.originalAt === atMs);
    const row = matches[matches.length - 1];
    if (row) {
      row.eventMarker = row.actualBalance ?? row.forecastBalance ?? 0;
      row.event = event;
    }
  });

  return rows;
}

/** Meal vs. workout, and completed vs. still-only-planned, are distinguished
 * by shape and fill (not color alone) — color is never the sole state signal
 * (web/CLAUDE.md accessibility floor). A planned workout renders hollow to
 * flag it hasn't happened yet (and could still drop off after its 4-hour
 * grace period if never confirmed completed). */
function EventMarkerShape(props: { cx?: number; cy?: number; payload?: ChartRow }): JSX.Element {
  const { cx, cy, payload } = props;
  const event = payload?.event;
  if (cx === undefined || cy === undefined || !event) {
    return <g />;
  }

  if (event.kind === "meal") {
    return <circle cx={cx} cy={cy} r={5} fill={EVENT_MEAL_COLOR} stroke="white" strokeWidth={1} />;
  }

  const isCompleted = event.status === "completed";
  const size = 6;
  const points = [
    [cx, cy - size],
    [cx + size, cy + size],
    [cx - size, cy + size]
  ]
    .map(([x, y]) => `${x},${y}`)
    .join(" ");
  return (
    <polygon
      points={points}
      fill={isCompleted ? EVENT_WORKOUT_COLOR : "white"}
      stroke={EVENT_WORKOUT_COLOR}
      strokeWidth={1.5}
      strokeDasharray={isCompleted ? undefined : "2 2"}
    />
  );
}

function EventLegend(): JSX.Element {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-secondary dark:text-ink-secondary-dark">
      <li className="flex items-center gap-1.5">
        <svg width="12" height="12" aria-hidden="true">
          <circle cx="6" cy="6" r="5" fill={EVENT_MEAL_COLOR} stroke="white" strokeWidth={1} />
        </svg>
        Meal
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="12" height="12" aria-hidden="true">
          <polygon points="6,1 11,11 1,11" fill={EVENT_WORKOUT_COLOR} />
        </svg>
        Workout (completed)
      </li>
      <li className="flex items-center gap-1.5">
        <svg width="12" height="12" aria-hidden="true">
          <polygon points="6,1 11,11 1,11" fill="white" stroke={EVENT_WORKOUT_COLOR} strokeWidth={1.5} strokeDasharray="2 2" />
        </svg>
        Workout (planned)
      </li>
    </ul>
  );
}

const SERIES_LABELS: Record<string, string> = {
  actualBalance: "So far",
  forecastBalance: "Forecast"
};

/** Explicit sign even on a positive value (`+296`, not `296`) -- unlike the
 * running-balance lines, an event's own figure is a delta, and a bare
 * unsigned number reads ambiguously as "gained or spent?". A negative delta
 * already carries its own "-" from `toLocaleString`, so nothing extra is
 * added there. */
function formatSignedCalories(value: number): string {
  const rounded = Math.round(value);
  return rounded > 0 ? `+${rounded.toLocaleString()}` : rounded.toLocaleString();
}

/** Custom Tooltip content instead of the default `formatter`/`labelFormatter`
 * combo: with all three series now sharing one row, most rows have `null`
 * for two of the three fields (a row is either an actual-balance point, a
 * forecast point, or an event marker), and the default renderer would list
 * every series regardless, showing distracting "Forecast: —" / "Event: —"
 * lines. Filters those out and only prints series with a real value. The
 * event row also gets special treatment: labeled by its kind ("Meal" /
 * "Workout") rather than the generic series name, and shown as its own
 * signed delta_kcal rather than the running balance it happens to sit at
 * (which is already covered by the "So far"/"Forecast" line right above it).
 */
export function EnergyChartTooltip({ active, payload, label }: TooltipProps<number, string>): JSX.Element | null {
  if (!active || !payload || payload.length === 0 || typeof label !== "number") {
    return null;
  }
  const entries = payload.filter((entry) => entry.value !== null && entry.value !== undefined);
  if (entries.length === 0) {
    return null;
  }
  return (
    <div className="rounded-md border border-line bg-white px-3 py-2 text-sm shadow-md dark:border-line-dark dark:bg-canvas-dark">
      <p className="font-medium">{formatTimeMs(label)}</p>
      {entries.map((entry) => {
        const row = entry.payload as ChartRow | undefined;
        if (entry.dataKey === "eventMarker") {
          if (!row?.event) {
            return null;
          }
          const kindLabel = row.event.kind === "meal" ? "Meal" : "Workout";
          const color = row.event.kind === "meal" ? EVENT_MEAL_COLOR : EVENT_WORKOUT_COLOR;
          return (
            <p key="eventMarker" style={{ color }}>
              {kindLabel} {formatSignedCalories(row.event.deltaKcal)}
            </p>
          );
        }
        return (
          <p key={entry.dataKey} style={{ color: entry.color }}>
            {SERIES_LABELS[entry.dataKey ?? ""] ?? entry.name}: {formatCalories(Number(entry.value))}
          </p>
        );
      })}
    </div>
  );
}

function EnergyTextSummary({ energy, isToday }: { energy: EnergyTimeline; isToday: boolean }): JSX.Element {
  return (
    <div className="space-y-2 text-sm text-ink-secondary dark:text-ink-secondary-dark">
      <p>
        {isToday ? (
          <>
            Current energy balance is {formatCalories(energy.currentBalance)} calories. Predicted end of day:{" "}
            {formatCalories(energy.predictedEndOfDay)} calories, against a target of{" "}
            {formatCalories(energy.endOfDayTarget)} calories.
          </>
        ) : (
          <>
            Energy balance for the day is {formatCalories(energy.predictedEndOfDay)} calories, against a target of{" "}
            {formatCalories(energy.endOfDayTarget)} calories.
          </>
        )}
      </p>
      {energy.fuelingFlags.length > 0 ? (
        <ul className="space-y-1">
          {energy.fuelingFlags.map((flag) => (
            <li key={`${flag.workoutId}-${flag.at}`} className="flex items-center gap-2">
              <span>
                Workout at {formatTime(flag.at)}: {FUELING_LABELS[flag.status]}.
              </span>
              <FuelingBadge flag={flag} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export interface EnergyChartProps {
  energy: EnergyTimeline | null;
  isLoading: boolean;
  /** Whether the viewed day is today. The "now" reference line and its
   * "Live Energy" label only make sense for today — compute_energy_timeline
   * clamps its solid/dashed split to the viewed day's own bounds for any
   * other date (EC-05), so a past day is already fully solid and a future
   * day fully forecast; there's no meaningful "now" point to mark on either. */
  isToday: boolean;
}

/**
 * Standalone, prop-driven energy balance chart. Data-fetching and the
 * isToday determination both belong to the caller (`DayView.tsx`).
 */
export default function EnergyChart({ energy, isLoading, isToday }: EnergyChartProps): JSX.Element {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" label="Loading energy balance" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!energy) {
    return <EmptyState message="No target set for this day" nudge="set a target to see your energy balance" />;
  }

  const rows = buildChartRows(energy);
  const nowAt = energy.points[energy.points.length - 1]?.at ?? energy.forecastPoints[0]?.at ?? null;
  const nowAtMs = nowAt ? new Date(nowAt).getTime() : null;
  const rowTimes = rows.map((row) => row.at);
  const xDomain: [number, number] | undefined =
    rowTimes.length > 0 ? [Math.min(...rowTimes), Math.max(...rowTimes)] : undefined;
  const xTicks = xDomain ? computeHourTicks(xDomain[0], xDomain[1]) : undefined;

  // recharts' auto min/max for a shared axis was unreliable across mixed
  // data sources (see the `<Scatter>` comment above — now moot, since every
  // series shares this one array), and even with one source, the default
  // auto-scale doesn't round to clean numbers. Computing our own "nice"
  // domain/ticks (mirroring computeHourTicks for the X axis) fixes both.
  const yValues = rows.flatMap((row) =>
    [row.actualBalance, row.forecastBalance, row.eventMarker].filter((v): v is number => v !== null)
  );
  const yMin = yValues.length > 0 ? Math.min(...yValues) : 0;
  const yMax = yValues.length > 0 ? Math.max(...yValues) : 0;
  const yPadding = Math.max(10, (yMax - yMin) * 0.1);
  const { domain: yDomain, ticks: yTicks } = computeYTicks(yMin - yPadding, yMax + yPadding);

  return (
    <div className="space-y-3">
      <div className="h-64 w-full" role="img" aria-label="Line chart of energy balance for the day, actual and forecast">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 28, right: 24, left: 0, bottom: 8 }}>
            <XAxis
              dataKey="at"
              type="number"
              domain={xDomain ?? ["dataMin", "dataMax"]}
              ticks={xTicks}
              tickFormatter={formatTimeMs}
              tick={{ fontSize: 12 }}
            />
            <YAxis domain={yDomain} ticks={yTicks} tick={{ fontSize: 12 }} width={48} />
            <ReferenceLine y={0} stroke={ZERO_LINE_COLOR} />
            <Tooltip content={<EnergyChartTooltip />} />
            {isToday && nowAtMs !== null ? (
              <ReferenceLine
                x={nowAtMs}
                stroke={NOW_LINE_COLOR}
                strokeDasharray="4 4"
                label={{
                  value: `Live Energy: ${formatCalories(energy.currentBalance)}`,
                  position: "top",
                  fontSize: 12,
                  fill: NOW_LINE_COLOR
                }}
              />
            ) : null}
            <Line
              type="linear"
              dataKey="actualBalance"
              name="So far"
              stroke={BALANCE_COLOR}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey="forecastBalance"
              name="Forecast"
              stroke={FORECAST_COLOR}
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={{ r: 3 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            {energy.events.length > 0 ? (
              <Scatter name="Events" dataKey="eventMarker" shape={EventMarkerShape} isAnimationActive={false} />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {energy.events.length > 0 ? <EventLegend /> : null}
      <EnergyTextSummary energy={energy} isToday={isToday} />
    </div>
  );
}

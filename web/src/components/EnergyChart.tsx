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

import {
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import type { EnergyEvent, EnergyTimeline, FuelingFlag } from "../lib/api/types";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";

const BALANCE_COLOR = "#c2410c"; // accent (orange-700, matches TrendsPage's calorie line)
const FORECAST_COLOR = "#c2410c"; // same hue, dashed strokeDasharray distinguishes it as forecast
const NOW_LINE_COLOR = "#71717a"; // ink-tertiary (zinc-500), matches TrendsPage's target overlay muting
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

const HOUR_MS = 60 * 60 * 1000;

/** Recharts' default numeric-axis ticks are evenly spaced by *count* across
 * the domain, not snapped to any meaningful boundary — for a ~24h domain
 * that lands on arbitrary times like "7:56 AM" instead of round hours.
 * Builds ticks on the hour instead, spaced so there are roughly 5-7 of them
 * regardless of how long the domain span is. */
function computeHourTicks(minMs: number, maxMs: number): number[] {
  if (!(maxMs > minMs)) {
    return [minMs];
  }
  const spanHours = (maxMs - minMs) / HOUR_MS;
  const stepHours = spanHours > 18 ? 4 : spanHours > 9 ? 2 : 1;
  const stepMs = stepHours * HOUR_MS;

  const first = new Date(minMs);
  first.setMinutes(0, 0, 0);
  if (first.getTime() < minMs) {
    first.setHours(first.getHours() + stepHours);
  }

  const ticks: number[] = [];
  for (let t = first.getTime(); t <= maxMs; t += stepMs) {
    ticks.push(t);
  }
  return ticks.length > 0 ? ticks : [minMs];
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
  /** Epoch milliseconds — a numeric x value so the axis spaces points by
   * actual elapsed time, not evenly-by-index (a category axis on formatted
   * time labels was the original bug: recharts spaces category ticks by
   * count, not by the real gaps between timestamps). */
  at: number;
  actualBalance: number | null;
  forecastBalance: number | null;
}

function buildChartRows(energy: EnergyTimeline): ChartRow[] {
  const rows: ChartRow[] = energy.points.map((point) => ({
    at: new Date(point.at).getTime(),
    actualBalance: point.balance,
    forecastBalance: null
  }));

  const lastActual = energy.points[energy.points.length - 1];

  energy.forecastPoints.forEach((point, index) => {
    // The first forecast point shares its timestamp with the last actual
    // point (per spec §8, "now" boundary) — bridge the two lines there
    // instead of leaving a gap, rather than pushing a duplicate row.
    if (index === 0 && lastActual && point.at === lastActual.at) {
      rows[rows.length - 1] = { ...rows[rows.length - 1]!, forecastBalance: point.balance };
      return;
    }
    rows.push({
      at: new Date(point.at).getTime(),
      actualBalance: null,
      forecastBalance: point.balance
    });
  });

  return rows;
}

/** The balance the line is actually at when this event fires, so its marker
 * sits on the line instead of floating at the event's raw delta_kcal (the
 * previous bug: markers were positioned by step size, not by the balance
 * they occurred at). compute_energy_timeline emits two points at a step's
 * timestamp (before/after the jump) — take the later (post-step) one. */
function balanceAtEvent(event: EnergyEvent, rows: ChartRow[]): number {
  const atMs = new Date(event.at).getTime();
  const matches = rows.filter((row) => row.at === atMs);
  const last = matches[matches.length - 1];
  if (!last) {
    return 0;
  }
  return last.actualBalance ?? last.forecastBalance ?? 0;
}

/** Meal vs. workout, and completed vs. still-only-planned, are distinguished
 * by shape and fill (not color alone) — color is never the sole state signal
 * (web/CLAUDE.md accessibility floor). A planned workout renders hollow to
 * flag it hasn't happened yet (and could still drop off after its 4-hour
 * grace period if never confirmed completed). */
function EventMarkerShape(props: {
  cx?: number;
  cy?: number;
  payload?: { event: EnergyEvent };
}): JSX.Element {
  const { cx, cy, payload } = props;
  if (cx === undefined || cy === undefined || !payload) {
    return <g />;
  }
  const { event } = payload;

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

interface EventScatterDatum {
  at: number;
  balance: number;
  event: EnergyEvent;
}

/** Recharts' `ComposedChart` inspects its own `props.children` by element
 * type (Line/Scatter/etc.) to build the chart's layers — it does this
 * statically, before rendering, so it only recognizes chart primitives that
 * are *direct* JSX children. A `<Scatter>` wrapped inside a custom
 * component (as this used to be) is invisible to that scan: the component
 * type in the children array is the wrapper, not `Scatter`, so recharts
 * silently drops the whole layer — no error, just nothing rendered. Kept as
 * a plain data-builder function instead of a component for that reason;
 * `<Scatter>` itself must stay inlined directly under `<ComposedChart>`. */
function buildEventScatterData(events: EnergyEvent[], rows: ChartRow[]): EventScatterDatum[] {
  return events.map((event) => ({
    at: new Date(event.at).getTime(),
    balance: balanceAtEvent(event, rows),
    event
  }));
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
  const domain: [number, number] | undefined =
    rowTimes.length > 0 ? [Math.min(...rowTimes), Math.max(...rowTimes)] : undefined;
  const ticks = domain ? computeHourTicks(domain[0], domain[1]) : undefined;
  const eventData = buildEventScatterData(energy.events, rows);

  // recharts computes a shared axis's auto min/max from whichever series
  // happen to feed it, and mixing a chart-level-`data` Line series with a
  // separately-`data`-provided Scatter series (as here) makes that
  // computation unreliable -- observed dropping the Line's true range in
  // favor of just the Scatter's, clipping the line off the bottom/top of
  // the plot instead of scaling to fit it. Computing the Y domain
  // ourselves, from every value actually rendered, sidesteps that entirely
  // rather than depending on recharts to get it right across mixed sources.
  const yValues = [
    ...rows.flatMap((row) => [row.actualBalance, row.forecastBalance].filter((v): v is number => v !== null)),
    ...eventData.map((d) => d.balance)
  ];
  const yMin = yValues.length > 0 ? Math.min(...yValues) : 0;
  const yMax = yValues.length > 0 ? Math.max(...yValues) : 0;
  const yPadding = Math.max(10, (yMax - yMin) * 0.1);
  const yDomain: [number, number] = [Math.floor(yMin - yPadding), Math.ceil(yMax + yPadding)];

  return (
    <div className="space-y-3">
      <div className="h-64 w-full" role="img" aria-label="Line chart of energy balance for the day, actual and forecast">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 28, right: 24, left: 0, bottom: 8 }}>
            <XAxis
              dataKey="at"
              type="number"
              domain={domain ?? ["dataMin", "dataMax"]}
              ticks={ticks}
              tickFormatter={formatTimeMs}
              tick={{ fontSize: 12 }}
            />
            <YAxis domain={yDomain} tick={{ fontSize: 12 }} width={48} />
            <Tooltip
              labelFormatter={(label: number) => formatTimeMs(label)}
              formatter={(value: number | string | Array<number | string>, name: string | number) =>
                value === null || value === undefined
                  ? ["—", name]
                  : [formatCalories(Number(value)), name]
              }
            />
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
            {eventData.length > 0 ? (
              <Scatter name="Events" data={eventData} dataKey="balance" shape={EventMarkerShape} />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {energy.events.length > 0 ? <EventLegend /> : null}
      <EnergyTextSummary energy={energy} isToday={isToday} />
    </div>
  );
}

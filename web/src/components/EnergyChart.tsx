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
  at: string;
  atLabel: string;
  actualBalance: number | null;
  forecastBalance: number | null;
}

function buildChartRows(energy: EnergyTimeline): ChartRow[] {
  const rows: ChartRow[] = energy.points.map((point) => ({
    at: point.at,
    atLabel: formatTime(point.at),
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
      at: point.at,
      atLabel: formatTime(point.at),
      actualBalance: null,
      forecastBalance: point.balance
    });
  });

  return rows;
}

function eventColor(event: EnergyEvent): string {
  return event.kind === "meal" ? EVENT_MEAL_COLOR : EVENT_WORKOUT_COLOR;
}

function EnergyEventMarkers({ events }: { events: EnergyEvent[] }): JSX.Element | null {
  if (events.length === 0) {
    return null;
  }
  const data = events.map((event) => ({
    at: event.at,
    atLabel: formatTime(event.at),
    balance: event.deltaKcal,
    event
  }));
  return (
    <Scatter
      name="Events"
      data={data}
      dataKey="balance"
      shape={(props: { cx?: number; cy?: number; payload?: { event: EnergyEvent } }) => {
        const { cx, cy, payload } = props;
        if (cx === undefined || cy === undefined || !payload) {
          return <g />;
        }
        return <circle cx={cx} cy={cy} r={5} fill={eventColor(payload.event)} stroke="white" strokeWidth={1} />;
      }}
    />
  );
}

function EnergyTextSummary({ energy }: { energy: EnergyTimeline }): JSX.Element {
  return (
    <div className="space-y-2 text-sm text-ink-secondary dark:text-ink-secondary-dark">
      <p>
        Current energy balance is {formatCalories(energy.currentBalance)} calories. Predicted end of day:{" "}
        {formatCalories(energy.predictedEndOfDay)} calories, against a target of{" "}
        {formatCalories(energy.endOfDayTarget)} calories.
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
}

/**
 * Standalone, prop-driven energy balance chart. Not wired into `DayView.tsx`
 * yet (EC-10) — this component only renders whatever it's handed.
 */
export default function EnergyChart({ energy, isLoading }: EnergyChartProps): JSX.Element {
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

  return (
    <div className="space-y-4">
      <div className="h-64 w-full" role="img" aria-label="Line chart of energy balance for the day, actual and forecast">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <XAxis dataKey="atLabel" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} width={48} />
            <Tooltip
              formatter={(value: number | string | Array<number | string>, name: string | number) =>
                value === null || value === undefined
                  ? ["—", name]
                  : [formatCalories(Number(value)), name]
              }
            />
            {nowAt ? (
              <ReferenceLine
                x={formatTime(nowAt)}
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
              type="monotone"
              dataKey="actualBalance"
              name="So far"
              stroke={BALANCE_COLOR}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="forecastBalance"
              name="Forecast"
              stroke={FORECAST_COLOR}
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={{ r: 3 }}
              connectNulls={false}
              isAnimationActive={false}
            />
            <EnergyEventMarkers events={energy.events} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <EnergyTextSummary energy={energy} />
    </div>
  );
}

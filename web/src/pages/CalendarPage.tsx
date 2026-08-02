/**
 * Calendar heatmap view (T-077, spec §7): `/calendar`.
 *
 * Fetches `GET /api/range` (day granularity, T-076's established pattern —
 * see `../lib/api/client#getRange`) for a rolling twelve-month window ending
 * today and renders it as a `react-calendar-heatmap` grid, one cell per day,
 * colored by the four-bucket adherence scale from `../design/adherence.ts`
 * (green in target / yellow near / red outside / grey no log — see
 * `../lib/calendar.ts#classifyDay` for how "near" is derived, since the
 * backend only exposes a boolean `adherence` flag).
 *
 * This is a read-only view: no mutations, so no optimistic-update/rollback
 * pattern is needed — just loading/error/success query states matching
 * TrendsPage/DayPage. Clicking (or activating via keyboard) a day cell
 * navigates to `/day/:date` (T-075).
 *
 * `react-calendar-heatmap` renders a bare SVG grid with no built-in
 * tooltip, keyboard support, or text summary, so all three are added here:
 * a controlled hover/focus tooltip, a `transformDayElement` pass that makes
 * each cell a focusable, keyboard-activatable button (Enter/Space navigates,
 * same as click), and a plain-text summary paragraph beneath the grid per
 * the accessibility floor (spec §7) — the same principle TrendsPage applies
 * to its Recharts charts.
 */

import {
  cloneElement,
  useMemo,
  useState,
  type FocusEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactElement,
  type SVGProps
} from "react";
import CalendarHeatmap from "react-calendar-heatmap";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getRange } from "../lib/api/client";
import { queryKeys } from "../lib/queryClient";
import Skeleton from "../design/Skeleton";
import EmptyState from "../design/EmptyState";
import { ADHERENCE_ORDER, ADHERENCE_STYLES, type AdherenceState } from "../design/adherence";
import { calendarRange, computeCalendarSummary, toHeatmapDays, type HeatmapDay } from "../lib/calendar";

/** Tailwind `fill-*` utility per bucket — same tokens as `ADHERENCE_STYLES`' `bgClass`, verified for WCAG AA contrast in `tailwind.config.ts`. */
const FILL_CLASS: Record<AdherenceState, string> = {
  "in-target": "fill-adherence-in-target",
  near: "fill-adherence-near",
  outside: "fill-adherence-outside",
  "no-log": "fill-adherence-no-log"
};

function formatCalories(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatGrams(value: number): string {
  return value.toFixed(1);
}

/** Full text used for both the native SVG `<title>` (accessible name / native tooltip) and the custom floating tooltip. */
function describeDay(day: HeatmapDay): string {
  const label = ADHERENCE_STYLES[day.state].label;
  if (!day.hasLog) {
    return `${day.date}: no meals logged (${label.toLowerCase()})`;
  }
  const targetText = day.targetCalories !== null ? ` of ${formatCalories(day.targetCalories)} target` : " (no target set)";
  return (
    `${day.date}: ${formatCalories(day.calories)} calories${targetText} — ${label}. ` +
    `${formatGrams(day.proteinG)} g protein, ${formatGrams(day.carbsG)} g carbs, ${formatGrams(day.fatG)} g fat.`
  );
}

interface HoverTooltip {
  text: string;
  x: number;
  y: number;
}

function Legend(): JSX.Element {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-2 text-sm" aria-hidden="true">
      {ADHERENCE_ORDER.map((state) => (
        <li key={state} className="flex items-center gap-1.5">
          <span className={`h-3 w-3 rounded-sm ${ADHERENCE_STYLES[state].bgClass}`} />
          <span className="text-ink-secondary dark:text-ink-secondary-dark">{ADHERENCE_STYLES[state].label}</span>
        </li>
      ))}
    </ul>
  );
}

function CalendarSummaryText({ days }: { days: HeatmapDay[] }): JSX.Element {
  const summary = computeCalendarSummary(days);
  return (
    <p className="text-sm text-ink-secondary dark:text-ink-secondary-dark">
      {summary.daysInTarget} day{summary.daysInTarget === 1 ? "" : "s"} in target over the last {days.length} days
      {summary.daysLogged > 0 ? ` (${summary.daysLogged} day${summary.daysLogged === 1 ? "" : "s"} logged)` : ""},
      longest in-target streak {summary.longestStreakDays} day{summary.longestStreakDays === 1 ? "" : "s"}.
    </p>
  );
}

export default function CalendarPage(): JSX.Element {
  const navigate = useNavigate();
  const { from, to } = useMemo(() => calendarRange(), []);
  const [tooltip, setTooltip] = useState<HoverTooltip | null>(null);

  const rangeQuery = useQuery({
    queryKey: queryKeys.range(from, to, "day"),
    queryFn: () => getRange({ from, to, granularity: "day" })
  });

  const days = useMemo(() => (rangeQuery.data ? toHeatmapDays(rangeQuery.data.periods) : []), [rangeQuery.data]);
  const hasData = days.some((day) => day.hasLog);

  const goToDay = (day: HeatmapDay | null): void => {
    if (day) {
      void navigate(`/day/${day.date}`);
    }
  };

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Calendar</h1>
        <p className="mt-1 text-sm text-ink-secondary dark:text-ink-secondary-dark">Adherence over the last twelve months.</p>
      </header>

      {rangeQuery.isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" label="Loading calendar" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-6 w-96" />
        </div>
      ) : rangeQuery.isError || !rangeQuery.data ? (
        <div className="space-y-4">
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            Could not load calendar data.
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
        <div className="space-y-4">
          <Legend />
          <div className="relative">
            <div role="img" aria-label={`Heatmap of daily adherence from ${from} to ${to}`}>
              <CalendarHeatmap
                startDate={from}
                endDate={to}
                values={days}
                showWeekdayLabels
                gutterSize={2}
                classForValue={(day) =>
                  day ? `${FILL_CLASS[day.state]} stroke-white dark:stroke-canvas-dark` : "fill-adherence-no-log"
                }
                titleForValue={(day) => (day ? describeDay(day) : null)}
                onClick={(day) => goToDay(day)}
                onMouseOver={(event, day) => {
                  if (day) {
                    setTooltip({ text: describeDay(day), x: event.clientX, y: event.clientY });
                  }
                }}
                onMouseLeave={() => setTooltip(null)}
                transformDayElement={(element, day, index) => makeDayCellFocusable(element, day, index, goToDay, setTooltip)}
              />
            </div>
            {tooltip ? (
              <div
                role="tooltip"
                className="pointer-events-none fixed z-10 max-w-xs rounded-md border border-line bg-white px-3 py-2 text-xs text-ink-secondary shadow-lg dark:border-line-dark dark:bg-canvas-dark dark:text-ink-secondary-dark"
                style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
              >
                {tooltip.text}
              </div>
            ) : null}
          </div>
          <CalendarSummaryText days={days} />
        </div>
      ) : (
        <EmptyState
          message="no meals logged in the last twelve months"
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

/**
 * Makes a heatmap day cell keyboard-accessible: focusable, announced as a
 * button with the same text as the hover tooltip, and activatable with
 * Enter/Space (mirroring the click handler) — `react-calendar-heatmap`
 * renders plain non-interactive `<rect>`s by default. Also shows/hides the
 * hover-style tooltip on focus/blur so keyboard users get the same totals
 * that mouse users see on hover. Focus ring uses `outline` (not the app's
 * usual `focus-ring` box-shadow-based ring utility, since box-shadow does
 * not render reliably on SVG shapes) but preserves the same visible,
 * high-contrast, focus-visible-only behavior.
 */
function makeDayCellFocusable(
  element: ReactElement<SVGProps<SVGRectElement>>,
  day: HeatmapDay | null,
  index: number,
  goToDay: (day: HeatmapDay | null) => void,
  setTooltip: (tooltip: HoverTooltip | null) => void
): ReactElement {
  const label = day ? describeDay(day) : "No data";
  return cloneElement(element, {
    key: element.key ?? index,
    tabIndex: 0,
    role: "button",
    "aria-label": label,
    className: `${element.props.className ?? ""} cursor-pointer outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent`,
    onFocus: (event: FocusEvent<SVGRectElement>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      if (day) {
        setTooltip({ text: label, x: rect.left, y: rect.bottom });
      }
    },
    onBlur: () => setTooltip(null),
    onKeyDown: (event: ReactKeyboardEvent<SVGRectElement>) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        goToDay(day);
      }
    }
  });
}

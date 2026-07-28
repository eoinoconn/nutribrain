/**
 * Minimal type shim for `react-calendar-heatmap` (T-077).
 *
 * The package ships no types and there is no `@types/react-calendar-heatmap`
 * on npm (checked before adding this — CLAUDE.md forbids new dependencies
 * without justification, and this repo has no existing untyped-dependency
 * shim pattern to follow, so this is the minimal module declaration needed).
 * Only the props this codebase actually uses are typed; everything else is
 * left permissive (`unknown`/optional) since this is a shim, not a full
 * upstream type contribution.
 */
declare module "react-calendar-heatmap" {
  import type { ReactElement, SVGProps } from "react";

  export interface HeatmapValue {
    date: string | number | Date;
  }

  export interface CalendarHeatmapProps<TValue extends HeatmapValue = HeatmapValue> {
    startDate: string | number | Date;
    endDate: string | number | Date;
    values: TValue[];
    showMonthLabels?: boolean;
    showWeekdayLabels?: boolean;
    showOutOfRangeDays?: boolean;
    horizontal?: boolean;
    gutterSize?: number;
    onClick?: (value: TValue | null) => void;
    onMouseOver?: (event: React.MouseEvent, value: TValue | null) => void;
    onMouseLeave?: (event: React.MouseEvent, value: TValue | null) => void;
    titleForValue?: (value: TValue | null) => string | null;
    tooltipDataAttrs?: Record<string, string> | ((value: TValue | null) => Record<string, string>);
    classForValue?: (value: TValue | null) => string;
    monthLabels?: string[];
    weekdayLabels?: string[];
    transformDayElement?: (
      element: ReactElement<SVGProps<SVGRectElement>>,
      value: TValue | null,
      index: number
    ) => ReactElement;
  }

  export default function CalendarHeatmap<TValue extends HeatmapValue = HeatmapValue>(
    props: CalendarHeatmapProps<TValue>
  ): ReactElement;
}

/**
 * UI-local state for the "Plan a workout" manual fallback form (EC-04, §6 of
 * docs/features/energy_balance_chart.md): a small, focused input — start
 * time + estimated kcal — for days without an intervals.icu event, not a
 * full workout editor. `durationMinutes` isn't part of the spec's minimal
 * form; it's optional here too and left blank by default so the backend's
 * documented default (60 minutes, `app/domain/planned_workouts.py`) applies
 * unless the user opts to override it.
 */
export interface PlannedWorkoutValue {
  /** `HH:mm` local time-of-day, as produced by `<input type="time">`. */
  time: string;
  estimatedCalories: number | null;
  durationMinutes: number | null;
}

export function createBlankPlannedWorkoutValue(time: string): PlannedWorkoutValue {
  return {
    time,
    estimatedCalories: null,
    durationMinutes: null
  };
}

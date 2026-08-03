import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import EnergyChart from "./EnergyChart";
import type { EnergyTimeline } from "../lib/api/types";

// recharts' ResponsiveContainer measures via getBoundingClientRect; jsdom
// returns an all-zero rect by default, which makes it skip rendering the
// chart body entirely (so a test that only queries text content can pass
// even if a chart layer is silently dropped, as recharts does for a chart
// primitive wrapped in a non-chart component instead of a direct child —
// exactly the bug this file's marker tests below are guarding against).
beforeEach(() => {
  Element.prototype.getBoundingClientRect = () =>
    ({
      width: 600,
      height: 300,
      top: 0,
      left: 0,
      bottom: 300,
      right: 600,
      x: 0,
      y: 0,
      toJSON() {
        return {};
      }
    });
});

function makeEnergy(overrides: Partial<EnergyTimeline> = {}): EnergyTimeline {
  return {
    points: [
      { at: "2026-08-03T08:00:00Z", balance: 0 },
      { at: "2026-08-03T12:00:00Z", balance: -400 }
    ],
    forecastPoints: [
      { at: "2026-08-03T12:00:00Z", balance: -400 },
      { at: "2026-08-03T20:00:00Z", balance: 200 }
    ],
    events: [{ at: "2026-08-03T12:00:00Z", deltaKcal: -600, kind: "meal", status: "completed" }],
    currentBalance: -400,
    predictedEndOfDay: 200,
    endOfDayTarget: 0,
    fuelingFlags: [],
    ...overrides
  };
}

describe("EnergyChart", () => {
  it("renders a loading skeleton when isLoading is true", () => {
    render(<EnergyChart energy={null} isLoading={true} isToday={true} />);

    expect(screen.getByRole("status", { name: /loading energy balance/i })).toBeInTheDocument();
  });

  it("renders an empty-state message when energy is null and not loading", () => {
    render(<EnergyChart energy={null} isLoading={false} isToday={true} />);

    expect(screen.getByText(/no target set for this day/i)).toBeInTheDocument();
  });

  it("renders one visible marker per event on the chart itself, not just in the legend", () => {
    // Regression test: `<Scatter>` was previously wrapped in a custom
    // component, which recharts silently fails to recognize as a chart
    // child (it inspects direct JSX children by type before rendering), so
    // no markers appeared on the chart at all despite the legend/summary
    // text below it looking correct. Assert against the actual rendered
    // marker shapes, not just presentational text.
    const energy = makeEnergy({
      events: [
        { at: "2026-08-03T08:00:00Z", deltaKcal: 350, kind: "meal", status: null },
        { at: "2026-08-03T11:00:00Z", deltaKcal: -320, kind: "workout", status: "completed" },
        { at: "2026-08-03T20:00:00Z", deltaKcal: -400, kind: "workout", status: "planned" }
      ]
    });
    const { container } = render(<EnergyChart energy={energy} isLoading={false} isToday={true} />);

    const scatterLayer = container.querySelector(".recharts-scatter");
    expect(scatterLayer).not.toBeNull();
    expect(scatterLayer?.querySelectorAll(".recharts-scatter-symbol")).toHaveLength(3);
  });

  it("keeps the whole line within the plotted chart area, including a deep dip between sparse meals", () => {
    // Regression test: recharts computes a shared axis's auto min/max
    // unreliably when a chart-level-`data` Line series and a
    // separately-`data` Scatter series both feed it — observed dropping the
    // Line's true range in favor of the Scatter's narrower one, clipping a
    // deep basal-drain dip off the bottom of the plot (it would render, then
    // get cut off by the chart's clipPath, then jump back in from off-screen
    // at the next point). The Y domain is now computed explicitly from every
    // rendered value instead of trusting recharts' auto-scale here.
    const energy = makeEnergy({
      points: [
        { at: "2026-08-03T01:00:00Z", balance: 0 },
        { at: "2026-08-03T09:00:00Z", balance: -600 },
        { at: "2026-08-03T09:00:00Z", balance: -200 }
      ],
      forecastPoints: [{ at: "2026-08-03T09:00:00Z", balance: -200 }],
      events: [{ at: "2026-08-03T09:00:00Z", deltaKcal: 400, kind: "meal", status: null }],
      currentBalance: -200
    });
    const { container } = render(<EnergyChart energy={energy} isLoading={false} isToday={false} />);

    const svg = container.querySelector("svg.recharts-surface");
    const height = Number(svg?.getAttribute("height"));
    const linePath = container.querySelector("path.recharts-line-curve");
    const pathD = linePath?.getAttribute("d") ?? "";
    // Every "y" coordinate in the path's M/L commands (every other number
    // after the leading x) must fall within the SVG's own height -- if the
    // domain were wrong, the -600 dip would produce a y value far past it.
    const numbers = pathD.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
    const yCoords = numbers.filter((_, i) => i % 2 === 1);
    expect(yCoords.length).toBeGreaterThan(0);
    for (const y of yCoords) {
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(height);
    }
  });

  it("gives every step's before/after pair a distinct x coordinate on the line", () => {
    // Regression test: two rows at the exact same timestamp (a step's
    // before/after balance) made the x axis non-strictly-increasing, which
    // confused recharts' hover/tooltip point lookup -- hovering near one
    // step could show a neighboring step's data instead. Every x coordinate
    // in the rendered line path must be strictly increasing.
    const energy = makeEnergy({
      points: [
        { at: "2026-08-03T01:00:00Z", balance: 0 },
        { at: "2026-08-03T08:00:00Z", balance: -350 },
        { at: "2026-08-03T08:00:00Z", balance: -50 },
        { at: "2026-08-03T11:00:00Z", balance: -260 },
        { at: "2026-08-03T11:00:00Z", balance: 40 }
      ],
      forecastPoints: [{ at: "2026-08-03T11:00:00Z", balance: 40 }],
      events: [
        { at: "2026-08-03T08:00:00Z", deltaKcal: 300, kind: "meal", status: null },
        { at: "2026-08-03T11:00:00Z", deltaKcal: 300, kind: "meal", status: null }
      ]
    });
    const { container } = render(<EnergyChart energy={energy} isLoading={false} isToday={true} />);

    const linePath = container.querySelector("path.recharts-line-curve");
    const pathD = linePath?.getAttribute("d") ?? "";
    const numbers = pathD.match(/-?\d+(\.\d+)?/g)?.map(Number) ?? [];
    const xCoords = numbers.filter((_, i) => i % 2 === 0);
    expect(xCoords.length).toBeGreaterThan(1);
    for (let i = 1; i < xCoords.length; i++) {
      expect(xCoords[i]).toBeGreaterThan(xCoords[i - 1]!);
    }
  });

  it("renders a zero-calorie reference line", () => {
    const { container } = render(<EnergyChart energy={makeEnergy()} isLoading={false} isToday={true} />);

    const zeroLine = Array.from(container.querySelectorAll(".recharts-reference-line-line")).find(
      (el) => el.getAttribute("stroke") === "#d4d4d8"
    );
    expect(zeroLine).toBeTruthy();
  });

  it("renders the text-equivalent summary with current balance and predicted end of day", () => {
    render(<EnergyChart energy={makeEnergy()} isLoading={false} isToday={true} />);

    expect(
      screen.getByText(/current energy balance is -400 calories\. predicted end of day: 200 calories, against a target of 0 calories\./i)
    ).toBeInTheDocument();
  });

  it("renders a well_fueled flag with categorical, non-alarming copy", () => {
    const energy = makeEnergy({
      fuelingFlags: [{ workoutId: 1, at: "2026-08-03T17:00:00Z", status: "well_fueled" }]
    });
    render(<EnergyChart energy={energy} isLoading={false} isToday={true} />);

    const badge = screen.getByTestId("fueling-badge");
    expect(badge).toHaveTextContent(/well fueled/i);
    expect(badge.textContent).not.toMatch(/-?\d+/);
  });

  it("renders an under_fueled flag with categorical, non-alarming copy (not a bare negative number)", () => {
    const energy = makeEnergy({
      fuelingFlags: [{ workoutId: 2, at: "2026-08-03T17:00:00Z", status: "under_fueled" }]
    });
    render(<EnergyChart energy={energy} isLoading={false} isToday={true} />);

    const badge = screen.getByTestId("fueling-badge");
    expect(badge).toHaveTextContent(/could use more fuel/i);
    expect(badge.textContent).not.toMatch(/-?\d+/);
  });

  it("renders a legend distinguishing meal, completed-workout, and planned-workout markers when events are present", () => {
    const energy = makeEnergy({
      events: [
        { at: "2026-08-03T08:00:00Z", deltaKcal: 350, kind: "meal", status: null },
        { at: "2026-08-03T11:00:00Z", deltaKcal: -320, kind: "workout", status: "completed" },
        { at: "2026-08-03T20:00:00Z", deltaKcal: -400, kind: "workout", status: "planned" }
      ]
    });
    render(<EnergyChart energy={energy} isLoading={false} isToday={true} />);

    expect(screen.getByText("Meal")).toBeInTheDocument();
    expect(screen.getByText("Workout (completed)")).toBeInTheDocument();
    expect(screen.getByText("Workout (planned)")).toBeInTheDocument();
  });

  it("does not render a marker legend when there are no events", () => {
    render(<EnergyChart energy={makeEnergy({ events: [] })} isLoading={false} isToday={true} />);

    expect(screen.queryByText("Meal")).not.toBeInTheDocument();
    expect(screen.queryByText("Workout (completed)")).not.toBeInTheDocument();
  });

  it("uses whole-day phrasing (not 'current'/'predicted') and omits the Live Energy marker for a non-today date", () => {
    // compute_energy_timeline clamps its solid/dashed split to the viewed
    // day's own bounds for any day other than today (backend fix alongside
    // this), so current_balance and predicted_end_of_day are equal there —
    // the copy should read as one whole-day figure, not two.
    render(<EnergyChart energy={makeEnergy()} isLoading={false} isToday={false} />);

    expect(screen.getByText(/energy balance for the day is 200 calories, against a target of 0 calories\./i)).toBeInTheDocument();
    expect(screen.queryByText(/current energy balance/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/live energy/i)).not.toBeInTheDocument();
  });
});

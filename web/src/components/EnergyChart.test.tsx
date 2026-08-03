import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EnergyChart from "./EnergyChart";
import type { EnergyTimeline } from "../lib/api/types";

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
    render(<EnergyChart energy={null} isLoading={true} />);

    expect(screen.getByRole("status", { name: /loading energy balance/i })).toBeInTheDocument();
  });

  it("renders an empty-state message when energy is null and not loading", () => {
    render(<EnergyChart energy={null} isLoading={false} />);

    expect(screen.getByText(/no target set for this day/i)).toBeInTheDocument();
  });

  it("renders the text-equivalent summary with current balance and predicted end of day", () => {
    render(<EnergyChart energy={makeEnergy()} isLoading={false} />);

    expect(
      screen.getByText(/current energy balance is -400 calories\. predicted end of day: 200 calories, against a target of 0 calories\./i)
    ).toBeInTheDocument();
  });

  it("renders a well_fueled flag with categorical, non-alarming copy", () => {
    const energy = makeEnergy({
      fuelingFlags: [{ workoutId: 1, at: "2026-08-03T17:00:00Z", status: "well_fueled" }]
    });
    render(<EnergyChart energy={energy} isLoading={false} />);

    const badge = screen.getByTestId("fueling-badge");
    expect(badge).toHaveTextContent(/well fueled/i);
    expect(badge.textContent).not.toMatch(/-?\d+/);
  });

  it("renders an under_fueled flag with categorical, non-alarming copy (not a bare negative number)", () => {
    const energy = makeEnergy({
      fuelingFlags: [{ workoutId: 2, at: "2026-08-03T17:00:00Z", status: "under_fueled" }]
    });
    render(<EnergyChart energy={energy} isLoading={false} />);

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
    render(<EnergyChart energy={energy} isLoading={false} />);

    expect(screen.getByText("Meal")).toBeInTheDocument();
    expect(screen.getByText("Workout (completed)")).toBeInTheDocument();
    expect(screen.getByText("Workout (planned)")).toBeInTheDocument();
  });

  it("does not render a marker legend when there are no events", () => {
    render(<EnergyChart energy={makeEnergy({ events: [] })} isLoading={false} />);

    expect(screen.queryByText("Meal")).not.toBeInTheDocument();
    expect(screen.queryByText("Workout (completed)")).not.toBeInTheDocument();
  });
});

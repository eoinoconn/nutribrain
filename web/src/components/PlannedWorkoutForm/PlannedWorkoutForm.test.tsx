import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PlannedWorkoutForm from "./PlannedWorkoutForm";
import type { PlannedWorkoutValue } from "./types";

describe("PlannedWorkoutForm", () => {
  it("defaults start time to now and leaves calories/duration blank", () => {
    render(<PlannedWorkoutForm now={new Date(2026, 0, 1, 7, 30)} />);

    expect(screen.getByLabelText(/start time/i)).toHaveValue("07:30");
    expect(screen.getByLabelText(/estimated calories/i)).toHaveValue(null);
    expect(screen.getByLabelText(/duration/i)).toHaveValue(null);
  });

  it("reports start time and estimated calorie edits via onChange", () => {
    const onChange = vi.fn<(value: PlannedWorkoutValue) => void>();
    render(<PlannedWorkoutForm now={new Date(2026, 0, 1, 7, 30)} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/start time/i), { target: { value: "06:15" } });
    fireEvent.change(screen.getByLabelText(/estimated calories/i), { target: { value: "450" } });

    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last).toEqual({
      time: "06:15",
      estimatedCalories: 450,
      durationMinutes: null
    });
  });

  it("accepts an optional duration", () => {
    const onChange = vi.fn<(value: PlannedWorkoutValue) => void>();
    render(<PlannedWorkoutForm now={new Date(2026, 0, 1, 7, 30)} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/estimated calories/i), { target: { value: "600" } });
    fireEvent.change(screen.getByLabelText(/duration/i), { target: { value: "90" } });

    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last).toMatchObject({ estimatedCalories: 600, durationMinutes: 90 });
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import QuickMacroEntry from "./QuickMacroEntry";
import type { QuickMacroValue } from "./types";

describe("QuickMacroEntry", () => {
  it("defaults meal_type to snack and time to now, regardless of time of day", () => {
    render(<QuickMacroEntry now={new Date(2026, 0, 1, 8, 0)} />);

    expect(screen.getByLabelText(/meal type/i)).toHaveValue("snack");
    expect(screen.getByLabelText(/^time$/i)).toHaveValue("08:00");
  });

  it("reports macro, meal_type, and time edits via onChange", () => {
    const onChange = vi.fn<(value: QuickMacroValue) => void>();
    render(<QuickMacroEntry now={new Date(2026, 0, 1, 12, 30)} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/^calories$/i), { target: { value: "300" } });
    fireEvent.change(screen.getByLabelText(/protein/i), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText(/carbs/i), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText(/^fat/i), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText(/meal type/i), { target: { value: "lunch" } });
    fireEvent.change(screen.getByLabelText(/^time$/i), { target: { value: "13:00" } });
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "Protein shake" } });

    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last).toEqual({
      name: "Protein shake",
      mealType: "lunch",
      time: "13:00",
      calories: 300,
      proteinG: 20,
      carbsG: 30,
      fatG: 10,
      fiberG: null,
      satFatG: null,
      sodiumMg: null
    });
  });

  it("accepts optional fiber, sat fat, and sodium", () => {
    const onChange = vi.fn<(value: QuickMacroValue) => void>();
    render(<QuickMacroEntry now={new Date(2026, 0, 1, 12, 30)} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/fiber/i), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText(/sat\. fat/i), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText(/sodium/i), { target: { value: "400" } });

    const last = onChange.mock.calls.at(-1)?.[0];
    expect(last).toMatchObject({ fiberG: 5, satFatG: 2, sodiumMg: 400 });
  });
});

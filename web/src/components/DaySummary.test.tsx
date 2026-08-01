import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SummaryRow } from "./DaySummary";
import type { ItemMacros } from "../lib/api/types";

const totals: ItemMacros = {
  calories: 1200,
  proteinG: 80,
  carbsG: 100,
  fatG: 40,
  fiberG: 10,
  satFatG: 8,
  sodiumMg: 900
};

const target = {
  effectiveFrom: "2026-07-01",
  baseCalories: 2000,
  proteinG: 150,
  carbsG: 200,
  fatG: 60,
  caloriesOut: null,
  effectiveCalories: 2000
};

describe("SummaryRow", () => {
  it("composes the calorie ring, macro bars, and micro row into one section", () => {
    render(<SummaryRow totals={totals} target={target} />);

    expect(screen.getByText(/1,200 \/ 2,000 calories/i)).toBeInTheDocument();
    expect(screen.getByText("Protein")).toBeInTheDocument();
    expect(screen.getByText("Carbs")).toBeInTheDocument();
    expect(screen.getByText("Fat")).toBeInTheDocument();
    expect(screen.getByText("Fiber")).toBeInTheDocument();
    expect(screen.getByText("Sat fat")).toBeInTheDocument();
    expect(screen.getByText("Sodium")).toBeInTheDocument();
  });

  it("wraps to a stacked column below md and rows above it", () => {
    const { container } = render(<SummaryRow totals={totals} target={target} />);
    const row = container.firstElementChild;

    expect(row).toHaveClass("flex-col");
    expect(row).toHaveClass("md:flex-row");
  });
});

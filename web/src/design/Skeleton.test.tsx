import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Skeleton from "./Skeleton";

describe("Skeleton", () => {
  it("renders a status role with a default loading label", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
  });

  it("accepts a custom accessible label", () => {
    render(<Skeleton label="Loading meals" />);
    expect(screen.getByRole("status", { name: "Loading meals" })).toBeInTheDocument();
  });

  it("applies custom sizing classes", () => {
    render(<Skeleton className="h-24 w-full custom-class" />);
    expect(screen.getByRole("status")).toHaveClass("h-24", "w-full", "custom-class");
  });
});

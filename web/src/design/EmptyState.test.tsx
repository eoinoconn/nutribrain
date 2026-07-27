import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("renders the message", () => {
    render(<EmptyState message="No meals logged today" />);
    expect(screen.getByText("No meals logged today")).toBeInTheDocument();
  });

  it("renders an optional nudge", () => {
    render(<EmptyState message="No meals logged today" nudge="tell Claude, or use the button" />);
    expect(screen.getByText("tell Claude, or use the button")).toBeInTheDocument();
  });

  it("omits the nudge when not provided", () => {
    render(<EmptyState message="No meals logged today" />);
    expect(screen.queryByText(/tell claude/i)).not.toBeInTheDocument();
  });

  it("renders an action button and calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(<EmptyState message="No meals logged today" action={{ label: "Log a meal", onClick }} />);

    screen.getByRole("button", { name: "Log a meal" }).click();

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("omits the action button when not provided", () => {
    render(<EmptyState message="No meals logged today" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

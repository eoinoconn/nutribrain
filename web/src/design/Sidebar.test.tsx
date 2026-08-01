import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import Sidebar, { SIDEBAR_COLLAPSED_STORAGE_KEY } from "./Sidebar";

function renderSidebar(initialPath: string): void {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Sidebar />
    </MemoryRouter>
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("marks the active route with aria-current and not solely via color", () => {
    renderSidebar("/trends");

    const trendsLink = screen.getByRole("link", { name: "Trends" });
    const todayLink = screen.getByRole("link", { name: "Today" });

    expect(trendsLink).toHaveAttribute("aria-current", "page");
    expect(todayLink).not.toHaveAttribute("aria-current");
  });

  it("treats /day/:date routes as the Today item being active", () => {
    renderSidebar("/day/2026-08-01");

    expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute("aria-current", "page");
  });

  it("starts expanded by default and shows visible labels", () => {
    renderSidebar("/");

    const toggle = screen.getByRole("button", { name: /collapse sidebar/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    const todayLink = screen.getByRole("link", { name: "Today" });
    expect(within(todayLink).getByText("Today")).not.toHaveClass("sr-only");
  });

  it("toggling the collapse control hides labels, updates aria-expanded, and persists to localStorage", () => {
    renderSidebar("/");

    const toggle = screen.getByRole("button", { name: /collapse sidebar/i });
    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: /expand sidebar/i })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    const todayLink = screen.getByRole("link", { name: "Today" });
    expect(within(todayLink).getByText("Today")).toHaveClass("sr-only");
    expect(window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe("1");
  });

  it("restores collapsed state from localStorage on mount", () => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "1");

    renderSidebar("/");

    expect(screen.getByRole("button", { name: /expand sidebar/i })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("expanding again after a collapse restores labels and persists the change", () => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, "1");
    renderSidebar("/");

    const toggle = screen.getByRole("button", { name: /expand sidebar/i });
    fireEvent.click(toggle);

    expect(screen.getByRole("button", { name: /collapse sidebar/i })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    const todayLink = screen.getByRole("link", { name: "Today" });
    expect(within(todayLink).getByText("Today")).not.toHaveClass("sr-only");
    expect(window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY)).toBe("0");
  });

  it("renders every primary nav item as a link", () => {
    renderSidebar("/");

    for (const label of [
      "Today",
      "Trends",
      "Calendar",
      "Foods",
      "Templates",
      "Targets",
      "Settings"
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });
});

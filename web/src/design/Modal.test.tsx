import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Modal from "./Modal";

function Harness(): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div>
      <button type="button" onClick={() => setIsOpen(true)}>
        Open
      </button>
      <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} titleId="harness-title">
        <h2 id="harness-title">Harness modal</h2>
        <button type="button">First</button>
        <button type="button">Last</button>
      </Modal>
    </div>
  );
}

describe("Modal", () => {
  it("renders nothing when closed", () => {
    render(
      <Modal isOpen={false} onClose={() => undefined} titleId="t">
        <p>content</p>
      </Modal>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders as an accessible dialog labelled by titleId when open", () => {
    render(
      <Modal isOpen onClose={() => undefined} titleId="t">
        <h2 id="t">Title</h2>
      </Modal>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "t");
  });

  it("calls onClose on Escape", () => {
    let closed = false;
    render(
      <Modal isOpen onClose={() => (closed = true)} titleId="t">
        <h2 id="t">Title</h2>
        <button type="button">Ok</button>
      </Modal>
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(closed).toBe(true);
  });

  it("traps focus: Tab from the last focusable element wraps to the first", () => {
    render(
      <Modal isOpen onClose={() => undefined} titleId="t">
        <h2 id="t">Title</h2>
        <button type="button">First</button>
        <button type="button">Last</button>
      </Modal>
    );
    const last = screen.getByRole("button", { name: "Last" });
    const first = screen.getByRole("button", { name: "First" });
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
  });

  it("returns focus to the trigger element after closing", () => {
    render(<Harness />);
    const openButton = screen.getByRole("button", { name: "Open" });
    openButton.focus();
    fireEvent.click(openButton);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(openButton);
  });
});

import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "./Toast";
import { useToast } from "./useToast";

function ToastTrigger({
  text = "Saved",
  variant,
  durationMs
}: {
  text?: string;
  variant?: "success" | "error";
  durationMs?: number;
}) {
  const { showToast } = useToast();
  return (
    <button type="button" onClick={() => showToast(text, variant, durationMs)}>
      Trigger
    </button>
  );
}

function ToastOutsideProvider() {
  useToast();
  return null;
}

describe("ToastProvider / useToast", () => {
  it("shows a success toast when triggered", () => {
    render(
      <ToastProvider>
        <ToastTrigger text="Meal saved" variant="success" />
      </ToastProvider>
    );

    act(() => {
      screen.getByRole("button", { name: "Trigger" }).click();
    });

    expect(screen.getByRole("status")).toHaveTextContent("Meal saved");
  });

  it("uses an alert role for error toasts", () => {
    render(
      <ToastProvider>
        <ToastTrigger text="Save failed" variant="error" />
      </ToastProvider>
    );

    act(() => {
      screen.getByRole("button", { name: "Trigger" }).click();
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Save failed");
  });

  it("auto-dismisses a toast after its duration elapses", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <ToastTrigger text="Gone soon" durationMs={1000} />
      </ToastProvider>
    );

    act(() => {
      screen.getByRole("button", { name: "Trigger" }).click();
    });
    expect(screen.getByText("Gone soon")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.queryByText("Gone soon")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("stacks multiple toasts rather than replacing", () => {
    render(
      <ToastProvider>
        <ToastTrigger text="First" />
        <ToastTrigger text="Second" />
      </ToastProvider>
    );

    const buttons = screen.getAllByRole("button", { name: "Trigger" });
    act(() => {
      buttons[0]!.click();
      buttons[1]!.click();
    });

    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.getByText("Second")).toBeInTheDocument();
  });

  it("dismisses a toast when its close button is clicked", () => {
    render(
      <ToastProvider>
        <ToastTrigger text="Dismiss me" />
      </ToastProvider>
    );

    act(() => {
      screen.getByRole("button", { name: "Trigger" }).click();
    });
    act(() => {
      screen.getByRole("button", { name: /dismiss notification/i }).click();
    });

    expect(screen.queryByText("Dismiss me")).not.toBeInTheDocument();
  });

  it("throws when useToast is used outside a ToastProvider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => render(<ToastOutsideProvider />)).toThrow(
      /useToast must be used within a ToastProvider/
    );

    consoleError.mockRestore();
  });
});

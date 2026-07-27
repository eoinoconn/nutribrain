import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import TokenGate from "./TokenGate";
import { TOKEN_STORAGE_KEY, clearToken, getToken } from "../lib/tokenStore";

describe("TokenGate", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows the paste screen when no token is stored", () => {
    render(
      <TokenGate>
        <div>protected content</div>
      </TokenGate>
    );

    expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });

  it("renders children once a token exists in storage", () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "abc123");

    render(
      <TokenGate>
        <div>protected content</div>
      </TokenGate>
    );

    expect(screen.getByText("protected content")).toBeInTheDocument();
  });

  it("stores the pasted token and reveals children on submit", () => {
    render(
      <TokenGate>
        <div>protected content</div>
      </TokenGate>
    );

    fireEvent.change(screen.getByLabelText(/api token/i), { target: { value: "  my-token  " } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByText("protected content")).toBeInTheDocument();
    expect(getToken()).toBe("my-token");
  });

  it("shows a required-field error when submitting an empty token", () => {
    render(
      <TokenGate>
        <div>protected content</div>
      </TokenGate>
    );

    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    expect(screen.getByText(/a token is required/i)).toBeInTheDocument();
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });

  it("drops back to the paste screen with an invalid-token message when the token is cleared as invalid", () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "abc123");

    render(
      <TokenGate>
        <div>protected content</div>
      </TokenGate>
    );

    expect(screen.getByText("protected content")).toBeInTheDocument();

    act(() => {
      clearToken("invalid");
    });

    expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/rejected/i);
    expect(getToken()).toBeNull();
  });

  it("does not show an invalid-token message when the token is cleared manually", () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "abc123");

    render(
      <TokenGate>
        <div>protected content</div>
      </TokenGate>
    );

    act(() => {
      clearToken("manual");
    });

    expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

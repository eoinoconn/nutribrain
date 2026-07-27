import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";
import App from "./App";
import { TOKEN_STORAGE_KEY } from "./lib/tokenStore";

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders dashboard heading once a token is present", () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, "test-token");
    const queryClient = new QueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /nutribrain dashboard/i
      })
    ).toBeInTheDocument();
  });

  it("shows the token paste screen instead of the app when no token is stored", () => {
    const queryClient = new QueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 1, name: /nutribrain dashboard/i })
    ).not.toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders dashboard heading", () => {
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
});

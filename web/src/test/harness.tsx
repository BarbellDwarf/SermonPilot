import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location-search">{location.search}</span>;
}

/**
 * Every page that reads live data goes through TanStack Query, so the provider
 * has to exist in tests even when each query is disabled. Retries are off and
 * the cache is discarded per test so nothing leaks between cases.
 */
export function withProviders(ui: ReactNode, route = "/"): RenderResult {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <LocationProbe />
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
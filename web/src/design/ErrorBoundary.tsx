import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * App-wide render-error boundary (T-081, spec §7). Before this, an uncaught
 * render error anywhere in a page (e.g. a bad API response shape reaching a
 * component that doesn't guard for it) unmounted the whole React tree and
 * left a blank white screen with no way back short of reloading.
 *
 * This is deliberately the only boundary in the app: single-user, seven
 * routed pages, no widget-level isolation requirement (per task scope) — one
 * boundary wrapping the routed page content is enough. It's a class
 * component because `componentDidCatch`/`getDerivedStateFromError` are the
 * only way to catch render errors in React; no library needed.
 *
 * "Try again" resets local state and re-renders; it does not retry any
 * network request itself — if the error came from bad query data, the
 * individual page's own query/retry affordance handles that once the
 * boundary steps aside.
 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Dev-visibility only; no request bodies or tokens are ever logged here (CLAUDE.md).
    console.error("Unhandled render error caught by ErrorBoundary:", error, info.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    if (this.state.error) {
      return (
        <section
          role="alert"
          className="mx-auto max-w-lg space-y-4 rounded-lg border border-red-300 bg-white p-6 text-center shadow-sm dark:border-red-800 dark:bg-slate-900"
        >
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Something went wrong</h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            This page hit an unexpected error and couldn&apos;t render. Your data is safe &mdash; nothing was
            saved from this broken state.
          </p>
          <div className="flex justify-center gap-3">
            <button
              type="button"
              onClick={this.handleReset}
              className="focus-ring rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => window.location.assign("/")}
              className="focus-ring rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              Go to Today
            </button>
          </div>
        </section>
      );
    }

    return this.props.children;
  }
}

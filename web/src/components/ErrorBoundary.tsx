import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "./ui";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled console error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="mx-auto flex min-h-[60vh] w-full max-w-xl flex-col justify-center gap-4 p-6">
          <div role="alert" className="rounded-lg border border-danger/50 bg-surface p-6">
            <h1 className="text-lg font-semibold">The console hit an error</h1>
            <p className="mt-2 text-sm text-muted">
              Your work on the server is safe. Reload to return to the console.
            </p>
            <p className="mt-2 break-words font-mono text-xs text-danger">
              {this.state.error.message}
            </p>
            <div className="mt-4">
              <Button variant="primary" onClick={() => window.location.reload()}>
                Reload
              </Button>
            </div>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

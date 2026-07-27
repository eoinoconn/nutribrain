import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { ToastContext } from "./useToast";

export type ToastVariant = "success" | "error";

export interface ToastMessage {
  id: string;
  variant: ToastVariant;
  text: string;
}

const DEFAULT_DURATION_MS = 4000;

function createToastId(): string {
  return `toast-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

/**
 * Provides `useToast()` app-wide. Design choice: toasts stack (each shown in the list until its
 * own timer fires) rather than replacing one another, since success/error events for different
 * mutations can overlap and the user should see all of them.
 */
export function ToastProvider({ children }: { children: ReactNode }): JSX.Element {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const showToast = useCallback(
    (text: string, variant: ToastVariant = "success", durationMs: number = DEFAULT_DURATION_MS): string => {
      const id = createToastId();
      setToasts((current) => [...current, { id, variant, text }]);
      const timer = setTimeout(() => dismissToast(id), durationMs);
      timers.current.set(id, timer);
      return id;
    },
    [dismissToast]
  );

  const value = useMemo(() => ({ showToast, dismissToast }), [showToast, dismissToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.variant === "error" ? "alert" : "status"}
            className={`focus-ring pointer-events-auto flex w-full max-w-sm items-center justify-between gap-3 rounded-md px-4 py-3 text-sm font-medium text-white shadow-lg ${
              toast.variant === "error" ? "bg-adherence-outside" : "bg-adherence-in-target"
            }`}
          >
            <span>{toast.text}</span>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              className="focus-ring rounded px-1 text-white/80 hover:text-white"
              aria-label="Dismiss notification"
            >
              &times;
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

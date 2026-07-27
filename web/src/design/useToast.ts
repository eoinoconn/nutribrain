import { createContext, useContext } from "react";
import type { ToastVariant } from "./Toast";

export interface ToastContextValue {
  /** Show a toast. Auto-dismisses after `durationMs` (default 4000ms). Returns the toast id. */
  showToast: (text: string, variant?: ToastVariant, durationMs?: number) => string;
  dismissToast: (id: string) => void;
}

// eslint-disable-next-line @typescript-eslint/naming-convention -- React context objects are conventionally PascalCase.
export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

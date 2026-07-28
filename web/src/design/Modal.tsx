import { useEffect, useRef, type ReactNode } from "react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Element id for the modal's heading; supplied by the caller so it can render its own <h2>. */
  titleId: string;
  children: ReactNode;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Minimal accessible modal (no existing modal component in this codebase to
 * reuse as of T-078). Handles the three things the spec's accessibility
 * floor asks for that a bare `<div>` doesn't give you for free:
 * - Escape closes it.
 * - Tab/Shift+Tab is trapped inside the dialog while it's open.
 * - Focus moves into the dialog on open and returns to whatever triggered
 *   it (e.g. the table row's "Edit" affordance) on close.
 *
 * Presentational + behavior only — no data fetching, no domain logic.
 */
export default function Modal({ isOpen, onClose, titleId, children }: ModalProps): JSX.Element | null {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    previouslyFocusedRef.current = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const firstFocusable = dialog?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (firstFocusable ?? dialog)?.focus();

    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialog) {
        return;
      }
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocusedRef.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    // The backdrop's click-to-close is a mouse-only convenience affordance; it has no
    // interactive semantics of its own (not a button, not focusable) and the equivalent
    // keyboard path is Escape, handled above. `role="presentation"` documents that this div
    // isn't meant to be treated as an interactive control by assistive tech.
    <div
      role="presentation"
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/50 px-4 py-8"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="focus-ring max-h-full w-full max-w-lg overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-slate-900"
      >
        {children}
      </div>
    </div>
  );
}

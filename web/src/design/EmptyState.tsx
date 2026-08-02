import type { ReactNode } from "react";

interface EmptyStateAction {
  label: string;
  onClick: () => void;
}

interface EmptyStateProps {
  /** Primary message, e.g. "No meals logged today". */
  message: string;
  /** Optional secondary nudge text, e.g. "tell Claude, or use the button below". */
  nudge?: string;
  /** Optional call-to-action button. */
  action?: EmptyStateAction;
  /** Optional icon/illustration rendered above the message. */
  icon?: ReactNode;
}

/**
 * Reusable empty-state block per spec §7's "no meals logged today — tell Claude, or use the
 * button" pattern. Purely presentational: no data fetching, no domain logic.
 */
export default function EmptyState({ message, nudge, action, icon }: EmptyStateProps): JSX.Element {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line px-6 py-10 text-center dark:border-line-dark">
      {icon ? <div aria-hidden="true">{icon}</div> : null}
      <p className="text-base font-medium text-ink-secondary dark:text-ink-secondary-dark">{message}</p>
      {nudge ? <p className="text-sm text-ink-tertiary dark:text-ink-secondary-dark">{nudge}</p> : null}
      {action ? (
        <button
          type="button"
          onClick={action.onClick}
          className="focus-ring mt-2 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent"
        >
          {action.label}
        </button>
      ) : null}
    </div>
  );
}

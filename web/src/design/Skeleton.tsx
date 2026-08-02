interface SkeletonProps {
  /** Extra Tailwind classes for sizing (e.g. "h-4 w-32", "h-24 w-full"). */
  className?: string;
  /** Accessible label announced by screen readers while content is loading. Defaults to "Loading". */
  label?: string;
}

/**
 * A shimmering placeholder block for first-paint loading states. Dumb/presentational only —
 * callers decide when to render it (e.g. `isLoading ? <Skeleton /> : <RealContent />`).
 */
export default function Skeleton({ className = "h-4 w-full", label = "Loading" }: SkeletonProps): JSX.Element {
  return (
    <span
      role="status"
      aria-label={label}
      className={`relative inline-block overflow-hidden rounded-md bg-line dark:bg-panel-dark ${className}`}
    >
      <span
        aria-hidden="true"
        className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/40 to-transparent dark:via-white/10"
      />
    </span>
  );
}

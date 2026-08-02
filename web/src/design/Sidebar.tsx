/**
 * Primary navigation sidebar (feature: today_ui_redesign §1).
 *
 * Fixed-width left sidebar on desktop (>= Tailwind `md`), collapsible to an
 * icon-only rail; below `md` it becomes a horizontal scrollable bar instead
 * of a permanent sidebar, reusing the project's existing breakpoint rather
 * than introducing a new one.
 *
 * Collapsed/expanded state persists across page loads and navigation via
 * `localStorage` (key: `nutribrain:sidebarCollapsed`).
 */

import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

export const SIDEBAR_COLLAPSED_STORAGE_KEY = "nutribrain:sidebarCollapsed";

interface NavItem {
  to: string;
  label: string;
  icon: (props: { className?: string }) => JSX.Element;
  /** Returns true when `pathname` should highlight this item as active. */
  isActive: (pathname: string) => boolean;
}

const NAV_ITEMS: NavItem[] = [
  {
    to: "/",
    label: "Today",
    icon: TodayIcon,
    isActive: (pathname) => pathname === "/" || pathname.startsWith("/day/")
  },
  {
    to: "/trends",
    label: "Trends",
    icon: TrendsIcon,
    isActive: (pathname) => pathname.startsWith("/trends")
  },
  {
    to: "/calendar",
    label: "Calendar",
    icon: CalendarIcon,
    isActive: (pathname) => pathname.startsWith("/calendar")
  },
  {
    to: "/foods",
    label: "Foods",
    icon: FoodsIcon,
    isActive: (pathname) => pathname.startsWith("/foods")
  },
  {
    to: "/templates",
    label: "Templates",
    icon: TemplatesIcon,
    isActive: (pathname) => pathname.startsWith("/templates")
  },
  {
    to: "/targets",
    label: "Targets",
    icon: TargetsIcon,
    isActive: (pathname) => pathname.startsWith("/targets")
  },
  {
    to: "/settings",
    label: "Settings",
    icon: SettingsIcon,
    isActive: (pathname) => pathname.startsWith("/settings")
  }
];

function readInitialCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export default function Sidebar(): JSX.Element {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<boolean>(readInitialCollapsed);

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // Ignore storage failures (e.g. private browsing) — collapse state just
      // won't persist for this session.
    }
  }, [collapsed]);

  return (
    <nav
      aria-label="Primary"
      className={
        "flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-canvas p-2 text-sm dark:border-line-dark dark:bg-canvas-dark md:sticky md:top-0 md:h-screen md:flex-col md:gap-1 md:overflow-x-visible md:overflow-y-auto md:border-b-0 md:border-r md:p-3" +
        (collapsed ? " md:w-16" : " md:w-56")
      }
    >
      <div className="hidden shrink-0 items-center justify-between md:flex">
        {collapsed ? null : (
          <span className="px-2 text-xs font-semibold uppercase tracking-wide text-ink-tertiary dark:text-ink-secondary-dark">
            NutriBrain
          </span>
        )}
        <button
          type="button"
          className="focus-ring rounded-md p-2 text-ink-secondary hover:bg-line dark:text-ink-secondary-dark dark:hover:bg-panel-dark"
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setCollapsed((current) => !current)}
        >
          <CollapseIcon className="h-5 w-5" />
        </button>
      </div>

      {NAV_ITEMS.map((item) => {
        const active = item.isActive(location.pathname);
        return (
          <Link
            key={item.to}
            to={item.to}
            aria-current={active ? "page" : undefined}
            title={collapsed ? item.label : undefined}
            className={
              "focus-ring flex shrink-0 items-center gap-3 whitespace-nowrap rounded-md border-b-4 border-l-0 px-2 py-2 md:border-b-0 md:border-l-4" +
              (active
                ? " bg-accent-soft font-medium text-accent dark:bg-accent-soft-dark dark:text-ink-primary-dark border-accent md:border-l-accent"
                : " border-transparent text-ink-secondary hover:bg-line dark:text-ink-secondary-dark dark:hover:bg-panel-dark")
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            <span className={collapsed ? "sr-only" : ""}>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function iconProps(className?: string) {
  return {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true
  };
}

function TodayIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function TrendsIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </svg>
  );
}

function CalendarIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  );
}

function FoodsIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <path d="M6 2v7a3 3 0 003 3v10M6 2v20M18 2c-2 0-3 2-3 5v2a2 2 0 002 2h1v11" />
    </svg>
  );
}

function TemplatesIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <rect x="4" y="2" width="16" height="20" rx="2" />
      <path d="M8 7h8M8 12h8M8 17h5" />
    </svg>
  );
}

function TargetsIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" />
      <circle cx="12" cy="12" r="1" />
    </svg>
  );
}

function SettingsIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z" />
    </svg>
  );
}

function CollapseIcon({ className }: { className?: string }): JSX.Element {
  return (
    <svg {...iconProps(className)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </svg>
  );
}

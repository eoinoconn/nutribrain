import { Link, Route, Routes, useLocation } from "react-router-dom";
import TokenGate from "./auth/TokenGate";
import ErrorBoundary from "./design/ErrorBoundary";
import TodayPage from "./pages/TodayPage";
import DayPage from "./pages/DayPage";
import TrendsPage from "./pages/TrendsPage";
import CalendarPage from "./pages/CalendarPage";
import FoodsPage from "./pages/FoodsPage";
import TemplatesPage from "./pages/TemplatesPage";
import TargetsPage from "./pages/TargetsPage";
import SettingsPage from "./pages/SettingsPage";

export default function App(): JSX.Element {
  const location = useLocation();

  return (
    <TokenGate>
      <main className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <div className="mx-auto max-w-5xl space-y-8 px-4 py-8">
          <nav aria-label="Primary" className="flex flex-wrap gap-3 text-sm">
            <Link className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800" to="/">
              Today
            </Link>
            <Link className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800" to="/trends">
              Trends
            </Link>
            <Link
              className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800"
              to="/calendar"
            >
              Calendar
            </Link>
            <Link className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800" to="/foods">
              Foods
            </Link>
            <Link
              className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800"
              to="/templates"
            >
              Templates
            </Link>
            <Link className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800" to="/targets">
              Targets
            </Link>
            <Link className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800" to="/settings">
              Settings
            </Link>
          </nav>

          {/* `key={location.pathname}` resets the boundary's caught-error state on navigation, so
              following "Go to Today" (or any nav link) out of a broken page doesn't leave the
              fallback UI stuck on screen for a route that isn't actually broken. */}
          <ErrorBoundary key={location.pathname}>
            <Routes>
              <Route path="/" element={<TodayPage />} />
              <Route path="/day/:date" element={<DayPage />} />
              <Route path="/trends" element={<TrendsPage />} />
              <Route path="/calendar" element={<CalendarPage />} />
              <Route path="/foods" element={<FoodsPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/targets" element={<TargetsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </ErrorBoundary>
        </div>
      </main>
    </TokenGate>
  );
}

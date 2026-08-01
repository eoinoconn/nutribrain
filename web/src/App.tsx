import { Route, Routes, useLocation } from "react-router-dom";
import TokenGate from "./auth/TokenGate";
import ErrorBoundary from "./design/ErrorBoundary";
import Sidebar from "./design/Sidebar";
import DayView from "./pages/DayView";
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
      <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100 md:flex">
        <Sidebar />
        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-5xl space-y-8 px-4 py-8">
            {/* `key={location.pathname}` resets the boundary's caught-error state on navigation, so
                following "Go to Today" (or any nav link) out of a broken page doesn't leave the
                fallback UI stuck on screen for a route that isn't actually broken. */}
            <ErrorBoundary key={location.pathname}>
              <Routes>
                <Route path="/" element={<DayView />} />
                <Route path="/day/:date" element={<DayView />} />
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
      </div>
    </TokenGate>
  );
}

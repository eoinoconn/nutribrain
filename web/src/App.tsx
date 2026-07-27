import { Link, Route, Routes } from "react-router-dom";
import TokenGate from "./auth/TokenGate";
import TodayPage from "./pages/TodayPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import SettingsPage from "./pages/SettingsPage";

export default function App(): JSX.Element {
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

          <Routes>
            <Route path="/" element={<TodayPage />} />
            <Route path="/day/:date" element={<PlaceholderPage title="Day Detail" />} />
            <Route path="/trends" element={<PlaceholderPage title="Trends" />} />
            <Route path="/calendar" element={<PlaceholderPage title="Calendar" />} />
            <Route path="/foods" element={<PlaceholderPage title="Foods" />} />
            <Route path="/templates" element={<PlaceholderPage title="Templates" />} />
            <Route path="/targets" element={<PlaceholderPage title="Targets" />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </div>
      </main>
    </TokenGate>
  );
}

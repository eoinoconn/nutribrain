import { Link, Route, Routes } from "react-router-dom";

function HomePage(): JSX.Element {
  return (
    <section className="space-y-3">
      <h1 className="text-3xl font-bold tracking-tight">NutriBrain Dashboard</h1>
      <p className="text-slate-700 dark:text-slate-300">
        Web scaffold is online. Route-level pages will be implemented in upcoming tasks.
      </p>
    </section>
  );
}

function PlaceholderPage({ title }: { title: string }): JSX.Element {
  return (
    <section>
      <h2 className="text-2xl font-semibold">{title}</h2>
      <p className="mt-2 text-slate-700 dark:text-slate-300">Coming soon.</p>
    </section>
  );
}

export default function App(): JSX.Element {
  return (
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
          <Link className="rounded-md px-2 py-1 hover:bg-slate-200 dark:hover:bg-slate-800" to="/settings">
            Settings
          </Link>
        </nav>

        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/day/:date" element={<PlaceholderPage title="Day Detail" />} />
          <Route path="/trends" element={<PlaceholderPage title="Trends" />} />
          <Route path="/calendar" element={<PlaceholderPage title="Calendar" />} />
          <Route path="/foods" element={<PlaceholderPage title="Foods" />} />
          <Route path="/templates" element={<PlaceholderPage title="Templates" />} />
          <Route path="/targets" element={<PlaceholderPage title="Targets" />} />
          <Route path="/settings" element={<PlaceholderPage title="Settings" />} />
        </Routes>
      </div>
    </main>
  );
}

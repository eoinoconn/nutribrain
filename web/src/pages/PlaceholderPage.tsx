/** Minimal routable stand-in for pages whose real UI lands in later backlog tasks (T-074..T-080). */
export default function PlaceholderPage({ title }: { title: string }): JSX.Element {
  return (
    <section>
      <h2 className="text-2xl font-semibold">{title}</h2>
      <p className="mt-2 text-ink-secondary dark:text-ink-secondary-dark">Coming soon.</p>
    </section>
  );
}

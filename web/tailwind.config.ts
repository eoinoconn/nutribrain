import type { Config } from "tailwindcss";

/**
 * Adherence colors were chosen and verified for WCAG AA contrast (see the T-072 report for the
 * full relative-luminance calculation):
 * - White text on the color itself: >= 4.5:1 (AA normal text)
 * - The color swatch against a white page background: >= 3:1 (AA non-text UI component)
 * - The color swatch against the dark-mode page background (slate-900, #0f172a): >= 3:1
 *
 * | token       | hex     | text-on-color | vs white bg | vs dark bg |
 * |-------------|---------|----------------|-------------|------------|
 * | in-target   | #15803d | 5.02           | 5.02        | 3.56       |
 * | near        | #b45309 | 5.02           | 5.02        | 3.56       |
 * | outside     | #dc2626 | 4.83           | 4.83        | 3.70       |
 * | no-log      | #64748b | 4.76           | 4.76        | 3.75       |
 *
 * ---
 *
 * §7 orange-on-grey redesign (docs/features/today_ui_redesign.md §7): app-wide background/
 * panel/border/text/accent tokens, replacing ad hoc slate/sky classes. Grey scale uses Tailwind's
 * neutral "zinc" ramp (no blue tint, per spec: "dark neutral grey, not navy-tinted") rather than
 * `slate`. Tokens are flat light/`-dark` pairs (darkMode is "media", so every dark value is opted
 * into explicitly via a `dark:` class variant, matching the existing `text-slate-600
 * dark:text-slate-400` convention — there is no automatic light/dark switching from the token
 * definition alone).
 *
 * `canvas` (light) is zinc-100 (#f4f4f5), not zinc-50/white — an earlier draft used #fafafa,
 * which read as plain white next to white `panel` cards and didn't satisfy "orange on grey."
 * `panel` stays white so cards still lift visibly off the grey page background.
 *
 * Dark-mode values are taken directly from the reference mockup (`nutrition-ui-redesign.html`),
 * the canonical source for this palette: `--bg: #1c1c1e`, `--bg-panel: #262628`,
 * `--border: #3a3a3c`, `--text: #f2f0ed`, `--text-dim: #a8a6a2`. `--accent` (mockup: #ff8a3d)
 * was swapped for #f78932 per user preference (the mockup value read too dark against the
 * progress ring/bars in dark mode).
 * `--text-faint` (#787672) was nudged to #868480 — the literal mockup value only clears 3.75:1
 * against #1c1c1e, short of the 4.5:1 AA text bar (it's used at `text-xs`, not large text); this
 * is the closest value in the same warm-grey hue direction that reaches 4.5:1.
 *
 * Contrast verification (relative-luminance, same WCAG bar as `adherence` above):
 *
 * | token                  | hex     | check                            | ratio |
 * |------------------------|---------|-----------------------------------|-------|
 * | accent (orange-700)    | #c2410c | white text on accent (AA text)    | 5.18  |
 * | accent (orange-700)    | #c2410c | vs canvas (#f4f4f5, light bg)     | 4.71  |
 * | accent-dark (#f78932)  | #f78932 | vs canvas-dark (#1c1c1e), text/UI | 6.95  |
 * | ink-primary            | #18181b | vs canvas (#f4f4f5)               | 16.12 |
 * | ink-primary-dark       | #f2f0ed | vs canvas-dark (#1c1c1e)          | 14.96 |
 * | ink-secondary          | #52525b | vs canvas (#f4f4f5)               | 7.03  |
 * | ink-secondary-dark     | #a8a6a2 | vs canvas-dark (#1c1c1e)          | 7.00  |
 * | ink-tertiary           | #64646d | vs canvas (#f4f4f5)               | 5.33  |
 * | ink-tertiary-dark      | #868480 | vs canvas-dark (#1c1c1e)          | 4.56  |
 *
 * `accent` (single color, #c2410c) is used for primary-button fill and focus/active borders in
 * both light and dark mode — it clears the 3:1 non-text bar against `canvas`, and clears 4.5:1
 * for white button text (both modes use the same accent fill for buttons, so this ratio doesn't
 * depend on canvas). Where accent is used as *foreground text/icon color directly on the page
 * background* (active nav label, link hover) or as a filled shape against the page background
 * (the calorie progress ring/bars in `DaySummary.tsx`), dark mode swaps to the lighter
 * `accent-dark` (#f78932) so it doesn't read as muddy against the dark canvas — it clears 4.5:1
 * for text-sized use and 3:1 for the ring/bar fills.
 *
 * Collision check vs `adherence`: `adherence.near` (#b45309, an amber) is the only adherence
 * token in the same orange/amber hue family as the new `accent` (#c2410c). They are confirmed
 * never visible together: `adherence.*` only renders on the Calendar heatmap (`CalendarPage.tsx`)
 * and the Trends stat tiles; `accent` renders on the Day view, sidebar, and buttons/forms
 * app-wide. The one adherence token that *does* appear app-wide — `Toast.tsx`'s success/error
 * variants — uses `in-target` (green) and `outside` (red) only, never `near`, so no screen ever
 * shows both an orange accent and an amber adherence swatch at once.
 */
export default {
  darkMode: "media",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        adherence: {
          "in-target": "#15803d",
          near: "#b45309",
          outside: "#dc2626",
          "no-log": "#64748b"
        },
        canvas: {
          DEFAULT: "#f4f4f5",
          dark: "#1c1c1e"
        },
        panel: {
          DEFAULT: "#ffffff",
          dark: "#262628"
        },
        line: {
          DEFAULT: "#e4e4e7",
          dark: "#3a3a3c"
        },
        ink: {
          primary: "#18181b",
          "primary-dark": "#f2f0ed",
          secondary: "#52525b",
          "secondary-dark": "#a8a6a2",
          tertiary: "#64646d",
          "tertiary-dark": "#868480"
        },
        accent: {
          DEFAULT: "#c2410c",
          dark: "#f78932",
          soft: "#ffedd5",
          "soft-dark": "#4a2a12"
        }
      },
      spacing: {
        18: "4.5rem"
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" }
        }
      },
      animation: {
        shimmer: "shimmer 1.5s infinite"
      }
    }
  },
  plugins: []
} satisfies Config;

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

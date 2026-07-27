/**
 * Shared adherence color scale used by the Calendar heatmap (T-077) and Trends view (T-076).
 *
 * Colors are defined as Tailwind theme tokens in `tailwind.config.ts` under the `adherence.*`
 * namespace, and were checked for WCAG AA contrast — see that file's doc comment for the
 * verified ratios.
 */
export type AdherenceState = "in-target" | "near" | "outside" | "no-log";

interface AdherenceStyle {
  /** Human-readable label, used as the non-color signal (e.g. in tooltips/legends). */
  label: string;
  /** Tailwind background-color utility class for the adherence token. */
  bgClass: string;
  /** Tailwind text-color utility class for the adherence token (e.g. dots, legend swatches). */
  textClass: string;
  /** Tailwind border-color utility class for the adherence token. */
  borderClass: string;
}

export const ADHERENCE_STYLES: Record<AdherenceState, AdherenceStyle> = {
  "in-target": {
    label: "In target",
    bgClass: "bg-adherence-in-target",
    textClass: "text-adherence-in-target",
    borderClass: "border-adherence-in-target"
  },
  near: {
    label: "Near target",
    bgClass: "bg-adherence-near",
    textClass: "text-adherence-near",
    borderClass: "border-adherence-near"
  },
  outside: {
    label: "Outside target",
    bgClass: "bg-adherence-outside",
    textClass: "text-adherence-outside",
    borderClass: "border-adherence-outside"
  },
  "no-log": {
    label: "No log",
    bgClass: "bg-adherence-no-log",
    textClass: "text-adherence-no-log",
    borderClass: "border-adherence-no-log"
  }
};

export const ADHERENCE_ORDER: readonly AdherenceState[] = [
  "in-target",
  "near",
  "outside",
  "no-log"
];

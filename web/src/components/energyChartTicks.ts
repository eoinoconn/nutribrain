const HOUR_MS = 60 * 60 * 1000;

/** Recharts' default numeric-axis ticks are evenly spaced by *count* across
 * the domain, not snapped to any meaningful boundary — for a ~24h domain
 * that lands on arbitrary times like "7:56 AM" instead of round hours.
 * Builds ticks on the hour instead, spaced so there are roughly 5-7 of them
 * regardless of how long the domain span is. */
export function computeHourTicks(minMs: number, maxMs: number): number[] {
  if (!(maxMs > minMs)) {
    return [minMs];
  }
  const spanHours = (maxMs - minMs) / HOUR_MS;
  const stepHours = spanHours > 18 ? 4 : spanHours > 9 ? 2 : 1;
  const stepMs = stepHours * HOUR_MS;

  const first = new Date(minMs);
  first.setMinutes(0, 0, 0);
  if (first.getTime() < minMs) {
    first.setHours(first.getHours() + stepHours);
  }

  const ticks: number[] = [];
  for (let t = first.getTime(); t <= maxMs; t += stepMs) {
    ticks.push(t);
  }
  return ticks.length > 0 ? ticks : [minMs];
}

/** Rounds a raw tick step up to a "nice" 1/2/5-times-a-power-of-ten value —
 * the standard nice-numbers axis algorithm — so gridlines land on round
 * calorie counts (100, 200, 500, ...) instead of an arbitrary fraction of
 * an odd data range. */
function niceStep(rawStep: number): number {
  if (!(rawStep > 0)) {
    return 1;
  }
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const niceResidual = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  return niceResidual * magnitude;
}

/** Y-axis equivalent of `computeHourTicks`: recharts' default auto-ticks on
 * an arbitrary min/max (as this chart's padded data range is) don't land on
 * round numbers or space evenly — observed jumps like 93, -402, -652, -902
 * (a 495-unit gap next to two 250-unit gaps). Snaps the whole domain to a
 * round step instead, so gridlines are evenly spaced round numbers. */
export function computeYTicks(min: number, max: number, targetCount = 5): { domain: [number, number]; ticks: number[] } {
  const safeMin = min === max ? min - 1 : min;
  const safeMax = min === max ? max + 1 : max;
  const step = niceStep((safeMax - safeMin) / targetCount);
  const niceMin = Math.floor(safeMin / step) * step;
  const niceMax = Math.ceil(safeMax / step) * step;

  const ticks: number[] = [];
  for (let t = niceMin; t <= niceMax + step / 2; t += step) {
    ticks.push(Math.round(t));
  }
  return { domain: [niceMin, niceMax], ticks };
}

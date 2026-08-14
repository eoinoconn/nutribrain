const ISO_TIME_PATTERN = /T(\d{2}):(\d{2})/;

/**
 * Formats the wall-clock time encoded in an ISO datetime string without
 * converting it through the browser's own timezone.
 */
export function formatWallClockTime(isoDateTime: string): string {
  const match = ISO_TIME_PATTERN.exec(isoDateTime);
  if (match) {
    const sample = new Date(Date.UTC(2000, 0, 1, Number(match[1]), Number(match[2])));
    return sample.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  }

  return new Date(isoDateTime).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

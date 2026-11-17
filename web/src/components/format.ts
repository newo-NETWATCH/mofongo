/** ISO timestamp -> the viewer's local date and time. Falls back to the raw string if it does not parse. */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** First `max` characters of text, with an ellipsis when cut. */
export function truncate(text: string, max = 140): string {
  return text.length <= max ? text : `${text.slice(0, max - 1).trimEnd()}…`;
}

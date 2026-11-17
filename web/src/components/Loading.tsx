/** Small "working on it" line. Announced politely to screen readers. */
export function Loading({ label = "Loading..." }: { label?: string }) {
  return (
    <p className="muted" role="status">
      {label}
    </p>
  );
}

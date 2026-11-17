import { categoryLabel, colorLabel } from "../vocab";

/** Category chip followed by one chip per color. */
export function CategoryColorChips({ category, colors }: { category: string; colors: readonly string[] }) {
  return (
    <div className="chips">
      <span className="chip selected">{categoryLabel(category)}</span>
      {colors.map((c) => (
        <span className="chip" key={c}>
          {colorLabel(c)}
        </span>
      ))}
    </div>
  );
}

/** OPEN / CLOSED (reports) or LISTED / RETURNED (items) as a chip. */
export function StatusChip({ status }: { status: string }) {
  return <span className="chip">{status.charAt(0) + status.slice(1).toLowerCase()}</span>;
}

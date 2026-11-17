import { Link } from "react-router-dom";
import type { Match } from "../api";
import { CategoryColorChips, StatusChip } from "./Chips";
import { formatDateTime } from "./format";

/** One matched found item inside a report (screen 1.6). The photo is always present here per match.json, but stay defensive. */
export function MatchCard({ match }: { match: Match }) {
  const { item } = match;
  return (
    <article className="card">
      {item.photo ? (
        <img className="thumb" src={item.photo.url} alt={`Photo of ${item.title}`} loading="lazy" />
      ) : (
        <div className="thumb-placeholder">No photo</div>
      )}
      <h3>
        <Link to={`/items/${encodeURIComponent(item.itemId)}`}>{item.title}</Link>
      </h3>
      <p>
        <strong>{match.score}% match</strong> <StatusChip status={item.status} />
      </p>
      <CategoryColorChips category={item.category} colors={item.colors} />
      <p className="muted">
        Found at {item.foundLocation}, {formatDateTime(item.foundAt)}
      </p>
      {match.why.length > 0 && (
        <ul>
          {match.why.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

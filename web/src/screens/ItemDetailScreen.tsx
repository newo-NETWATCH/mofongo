import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api, describeError, type ItemDetail } from "../api";
import { categoryLabel, colorLabel } from "../vocab";
import { Photo } from "./Photo";
import "./finder.css";

function formatDate(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

const TAG_TEXT: Record<ItemDetail["tagStatus"], string> = {
  PENDING: "The photo has not been analyzed yet.",
  TAGGED: "The photo has been analyzed.",
  FAILED: "The photo could not be analyzed.",
};

/** Screen 1.2. One item, with a "Mark returned" button for the finder while it is LISTED. */
export function ItemDetailScreen() {
  const { itemId = "" } = useParams<{ itemId: string }>();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      setItem(await api.getItem(itemId));
    } catch (err) {
      setItem(null);
      // 404 (and 400 for a malformed ID) both mean there is nothing to show here.
      if (err instanceof ApiError && (err.status === 404 || err.status === 400)) setNotFound(true);
      else setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function markReturned() {
    if (!item) return;
    if (!window.confirm("Mark this item as returned to its owner?")) return;
    setMarking(true);
    setActionError(null);
    try {
      setItem(await api.markItemReturned(item.itemId));
    } catch (err) {
      setActionError(describeError(err));
      // 409: already returned elsewhere. Reload so the view matches the server.
      if (err instanceof ApiError && err.status === 409) void load();
    } finally {
      setMarking(false);
    }
  }

  if (loading && !item) return <p className="muted" role="status">Loading...</p>;

  if (notFound) {
    return (
      <section>
        <h1>Item not found</h1>
        <p>This item does not exist.</p>
        <p><Link to="/">Back to browse</Link></p>
      </section>
    );
  }

  if (error || !item) {
    return (
      <section>
        <div className="notice notice-error" role="alert">
          <p>{error ?? "Something went wrong."}</p>
          <button type="button" onClick={() => void load()}>Try again</button>
        </div>
        <p><Link to="/">Back to browse</Link></p>
      </section>
    );
  }

  const returned = item.status === "RETURNED";

  return (
    <section>
      <p><Link to="/">&larr; Back to browse</Link></p>
      <div className="detail">
        <div>
          <Photo photo={item.photo} alt={item.title} className="thumb" />
          {item.photo && (
            <p className="muted" style={{ fontSize: "0.8125rem" }}>
              Photo links last 15 minutes. Reload the page if the photo disappears.
            </p>
          )}
        </div>
        <div>
          <div className="chips">
            <span className="chip">{categoryLabel(item.category)}</span>
            <span className={returned ? "badge badge-muted" : "badge"}>{returned ? "Returned" : "Listed"}</span>
            {item.isMine && <span className="badge">Yours</span>}
          </div>
          <h1 style={{ marginTop: "0.5rem" }}>{item.title}</h1>
          {item.description && <p style={{ whiteSpace: "pre-wrap" }}>{item.description}</p>}

          <dl>
            <dt>Colors</dt>
            <dd>
              <span className="chips">
                {item.colors.map((c) => (
                  <span key={c} className="chip">{colorLabel(c)}</span>
                ))}
              </span>
            </dd>
            <dt>Found at</dt>
            <dd>{item.foundLocation}</dd>
            <dt>Found on</dt>
            <dd>{formatDate(item.foundAt)}</dd>
            <dt>Posted</dt>
            <dd>{formatDate(item.createdAt)}</dd>
            {returned && item.returnedAt && (
              <>
                <dt>Returned</dt>
                <dd>{formatDate(item.returnedAt)}</dd>
              </>
            )}
          </dl>

          <p className="muted">{TAG_TEXT[item.tagStatus]}</p>
          {item.clipTags && (
            <>
              <h2>What the photo analysis saw</h2>
              <p className="muted" style={{ margin: 0 }}>Categories</p>
              <ul className="tag-list">
                {item.clipTags.categories.map((t) => (
                  <li key={t.value}>{categoryLabel(t.value)}: {t.score}%</li>
                ))}
              </ul>
              <p className="muted" style={{ margin: 0 }}>Colors</p>
              <ul className="tag-list">
                {item.clipTags.colors.map((t) => (
                  <li key={t.value}>{colorLabel(t.value)}: {t.score}%</li>
                ))}
              </ul>
            </>
          )}

          {actionError && <div className="notice notice-error" role="alert">{actionError}</div>}
          {item.isMine && item.status === "LISTED" && (
            <button type="button" className="primary" disabled={marking} onClick={() => void markReturned()}>
              {marking ? "Saving..." : "Mark returned"}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

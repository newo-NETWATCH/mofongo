import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, describeError, type ItemSummary } from "../api";
import { CATEGORIES, categoryLabel, colorLabel, type Category } from "../vocab";
import { Photo } from "./Photo";
import "./finder.css";

const PAGE_SIZE = 20;

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function ItemCard({ item }: { item: ItemSummary }) {
  return (
    <li className="card">
      <Link to={`/items/${item.itemId}`} className="card-link">
        <Photo photo={item.photo} alt={item.title} />
        <div className="card-top">
          <span className="chip">{categoryLabel(item.category)}</span>
          {item.isMine && <span className="badge">Yours</span>}
        </div>
        <h3>{item.title}</h3>
        <div className="chips">
          {item.colors.map((c) => (
            <span key={c} className="chip">{colorLabel(c)}</span>
          ))}
        </div>
        <p className="meta">Found at {item.foundLocation}</p>
        <p className="meta">{formatDate(item.foundAt)}</p>
      </Link>
    </li>
  );
}

/** Screen 1.1. Listed items, newest first, optional category filter, "Load more" with nextToken. */
export function BrowseScreen() {
  const [category, setCategory] = useState<Category | "">("");
  const [items, setItems] = useState<ItemSummary[]>([]);
  const [nextToken, setNextToken] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Ignore answers that belong to a category the user already switched away from.
  const requestId = useRef(0);

  const load = useCallback(async (cat: Category | "", token?: string) => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await api.listItems({
        category: cat || undefined,
        limit: PAGE_SIZE,
        nextToken: token,
      });
      if (id !== requestId.current) return;
      setItems((prev) => (token ? [...prev, ...page.items] : page.items));
      setNextToken(page.nextToken);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(describeError(err));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    setItems([]);
    setNextToken(undefined);
    void load(category);
  }, [category, load]);

  return (
    <section>
      <h1>Found items</h1>
      <div className="toolbar">
        <label htmlFor="category-filter">Category</label>
        <select
          id="category-filter"
          value={category}
          onChange={(e) => setCategory(e.target.value as Category | "")}
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>{c.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="notice notice-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => void load(category, nextToken)}>Try again</button>
        </div>
      )}

      {items.length > 0 && (
        <ul className="grid" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((item) => (
            <ItemCard key={item.itemId} item={item} />
          ))}
        </ul>
      )}

      {!loading && !error && items.length === 0 && (
        <p className="muted">No items listed{category ? " in this category" : ""} yet.</p>
      )}
      {loading && <p className="muted" role="status">Loading...</p>}

      {/* A page can be short or empty while nextToken is present: keep offering more. */}
      {!loading && nextToken && (
        <div className="more">
          <button type="button" onClick={() => void load(category, nextToken)}>Load more</button>
        </div>
      )}
    </section>
  );
}

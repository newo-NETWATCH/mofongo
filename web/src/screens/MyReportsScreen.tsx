import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AlertState, type Report } from "../api";
import { CategoryColorChips, StatusChip } from "../components/Chips";
import { ErrorBanner } from "../components/ErrorBanner";
import { Loading } from "../components/Loading";
import { formatDate, truncate } from "../components/format";

// Screen 1.5: my reports (newest first), with an email-alert banner.

const PAGE_SIZE = 20;

export function MyReportsScreen() {
  const [reports, setReports] = useState<Report[]>([]);
  const [nextToken, setNextToken] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [alertState, setAlertState] = useState<AlertState | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api
      .listReports({ limit: PAGE_SIZE })
      .then((page) => {
        if (cancelled) return;
        setReports(page.reports);
        setNextToken(page.nextToken);
      })
      .catch((err) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    // The banner is a nicety: if this call fails the list still works.
    api
      .getMyAlerts()
      .then((a) => !cancelled && setAlertState(a.state))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function loadMore() {
    if (!nextToken || loadingMore) return;
    setLoadingMore(true);
    setError(undefined);
    try {
      const page = await api.listReports({ limit: PAGE_SIZE, nextToken });
      setReports((prev) => [...prev, ...page.reports]);
      setNextToken(page.nextToken);
    } catch (err) {
      setError(err);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section>
      <h1>My reports</h1>

      {alertState && alertState !== "CONFIRMED" && (
        <div className="notice" role="status">
          Email alerts are not on yet, so you will not be emailed about matches.{" "}
          <Link to="/alerts">Check email alert status</Link>
        </div>
      )}

      <ErrorBanner error={error} />
      {loading && <Loading />}

      {!loading && reports.length === 0 && !error && (
        <p>
          You have not filed any lost reports. <Link to="/reports/new">File one now</Link>.
        </p>
      )}

      {reports.length > 0 && (
        <div className="grid">
          {reports.map((r) => (
            <article className="card" key={r.reportId}>
              <CategoryColorChips category={r.category} colors={r.colors} />
              <h3>
                <Link to={`/reports/${encodeURIComponent(r.reportId)}`}>{truncate(r.description, 80)}</Link>
              </h3>
              <p>
                <StatusChip status={r.status} />{" "}
                <span className="muted">Filed {formatDate(r.createdAt)}</span>
              </p>
            </article>
          ))}
        </div>
      )}

      {nextToken && (
        <p>
          <button type="button" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading..." : "Load more"}
          </button>
        </p>
      )}
    </section>
  );
}

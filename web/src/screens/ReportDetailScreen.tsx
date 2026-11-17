import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type Match, type Report } from "../api";
import { CategoryColorChips, StatusChip } from "../components/Chips";
import { ErrorBanner } from "../components/ErrorBanner";
import { Loading } from "../components/Loading";
import { MatchCard } from "../components/MatchCard";
import { formatDateTime } from "../components/format";

// Screen 1.6: report detail with matches (best score first, as the API sorts them).

export function ReportDetailScreen() {
  const { reportId = "" } = useParams();
  const [report, setReport] = useState<Report | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [closing, setClosing] = useState(false);
  const [closeError, setCloseError] = useState<unknown>(undefined);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setReport(null);
    setMatches([]);
    setNotFound(false);
    setError(undefined);
    api
      .getReport(reportId)
      .then((d) => {
        if (cancelled) return;
        setReport(d.report);
        setMatches(d.matches);
      })
      .catch((err) => {
        if (cancelled) return;
        // The API answers 404 for a missing report and for another owner's report alike.
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setError(err);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  async function closeReport() {
    if (!report || closing) return;
    if (!window.confirm("Close this report? We will stop looking for matches.")) return;
    setClosing(true);
    setCloseError(undefined);
    try {
      setReport(await api.closeReport(report.reportId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true);
      else setCloseError(err);
    } finally {
      setClosing(false);
    }
  }

  if (loading) return <Loading />;

  if (notFound) {
    return (
      <section>
        <h1>Report not found</h1>
        <p>
          This report does not exist, or it is not yours. <Link to="/reports">Back to my reports</Link>
        </p>
      </section>
    );
  }

  if (error || !report) {
    return (
      <section>
        <ErrorBanner error={error ?? new Error("The report could not be loaded.")} />
        <p>
          <Link to="/reports">Back to my reports</Link>
        </p>
      </section>
    );
  }

  return (
    <section>
      <p>
        <Link to="/reports">&larr; My reports</Link>
      </p>
      <h1>Lost report</h1>

      <div className="card">
        <CategoryColorChips category={report.category} colors={report.colors} />
        <p>{report.description}</p>
        <p className="muted">
          <StatusChip status={report.status} /> Filed {formatDateTime(report.createdAt)}
          {report.closedAt && <>, closed {formatDateTime(report.closedAt)}</>}
        </p>
        {(report.lostLocation || report.lostAt) && (
          <p className="muted">
            Lost
            {report.lostLocation && <> at {report.lostLocation}</>}
            {report.lostAt && <> around {formatDateTime(report.lostAt)}</>}
          </p>
        )}
        {report.status === "OPEN" && (
          <>
            <ErrorBanner error={closeError} />
            <button type="button" className="danger" onClick={() => void closeReport()} disabled={closing}>
              {closing ? "Closing..." : "Close report"}
            </button>
            <p className="hint muted">Close it when you have your item back or stop looking.</p>
          </>
        )}
      </div>

      <h2>Matches ({matches.length})</h2>
      {report.status === "CLOSED" && (
        <p className="muted">
          This report is closed, so no new matches are added. A match that was already being worked out when you
          closed it can still appear in the first few seconds.
        </p>
      )}
      {matches.length === 0 ? (
        <p className="muted">
          {report.status === "OPEN"
            ? "No matches yet. We check each new found item against your report, and email you if alerts are on."
            : "No matches were found."}
        </p>
      ) : (
        <div className="grid">
          {matches.map((m) => (
            <MatchCard key={m.item.itemId} match={m} />
          ))}
        </div>
      )}
    </section>
  );
}

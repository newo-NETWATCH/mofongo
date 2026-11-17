import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AlertState } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { Loading } from "../components/Loading";

// Screen 1.7: email alert status. The API sends four states (data-model 1.7); the page offers the matching action.

const COPY: Record<AlertState, { title: string; body: string; action?: string }> = {
  NONE: {
    title: "Alerts are off",
    body:
      "No email subscription is saved yet. File a lost report, or subscribe now, and we will email you when a " +
      "found item matches. This needs a verified email on your account.",
    action: "Subscribe",
  },
  UNCONFIRMED: {
    title: "Waiting for your confirmation",
    body:
      "We sent a confirmation email from Amazon Web Services. Open it and click \"Confirm subscription\". " +
      "The link works for 48 hours. Check your spam folder if you cannot find it.",
    action: "Send the confirmation email again",
  },
  CONFIRMED: {
    title: "Alerts are on",
    body: "You will get an email when a found item matches one of your open reports.",
  },
  GONE: {
    title: "Your subscription ended",
    body:
      "Your subscription is no longer active. It expired after 48 hours without confirmation, or you " +
      "unsubscribed from an alert email. Subscribe again to get match emails.",
    action: "Subscribe again",
  },
};

export function AlertsScreen() {
  const [state, setState] = useState<AlertState | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(undefined);

  async function load() {
    setError(undefined);
    setBusy(true);
    try {
      setState((await api.getMyAlerts()).state);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function subscribe() {
    if (busy) return;
    setError(undefined);
    setBusy(true);
    try {
      // The answer is the new state read back from SNS (usually UNCONFIRMED).
      setState((await api.subscribeMyAlerts()).state);
    } catch (err) {
      setError(err); // 403 = no verified email on the account; the API's message says so.
    } finally {
      setBusy(false);
    }
  }

  const copy = state ? COPY[state] : undefined;

  return (
    <section>
      <h1>Email alerts</h1>
      <ErrorBanner error={error} />
      {loading && <Loading />}

      {copy && (
        <div className="card" style={{ maxWidth: "36rem" }}>
          <h2 style={{ marginTop: 0 }}>{copy.title}</h2>
          <p>{copy.body}</p>
          <p>
            {copy.action && (
              <button type="button" className="primary" onClick={() => void subscribe()} disabled={busy}>
                {busy ? "Working..." : copy.action}
              </button>
            )}{" "}
            <button type="button" onClick={() => void load()} disabled={busy}>
              Refresh status
            </button>
          </p>
        </div>
      )}

      {!loading && !copy && (
        <p>
          <button type="button" onClick={() => void load()} disabled={busy}>
            Try again
          </button>
        </p>
      )}

      <p>
        <Link to="/reports">Back to my reports</Link>
      </p>
    </section>
  );
}

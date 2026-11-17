import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type AlertsOutcome, type CreatedReport } from "../api";
import { CATEGORIES, COLORS, COLOR_HINT, MAX_COLORS, type Category, type Color } from "../vocab";
import { ErrorBanner } from "../components/ErrorBanner";
import { Field } from "../components/Field";

// Screen 1.4: file a lost report.

const ALERT_MESSAGES: Record<AlertsOutcome, string> = {
  started:
    "We just sent a confirmation email from Amazon Web Services to your sign-in address. Open it and click " +
    "\"Confirm subscription\" once (the link works for 48 hours). Until you do, you will not get match emails.",
  existing:
    "You already have an email alert subscription, so you will be emailed when something matches. " +
    "Check the Alerts page if you have not confirmed it yet.",
  "no-verified-email":
    "Email alerts are not possible because the email on your account is not verified. " +
    "You can still open this report any time to see matches.",
  unavailable:
    "We could not set up email alerts right now. Your report is saved. Open it later to see matches, " +
    "or try subscribing again from the Alerts page.",
};

/** datetime-local value for "now", used as the max so the owner cannot pick a future time. */
function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function NewReportScreen() {
  const [category, setCategory] = useState<Category | "">("");
  const [colors, setColors] = useState<Color[]>([]);
  const [description, setDescription] = useState("");
  const [lostLocation, setLostLocation] = useState("");
  const [lostAt, setLostAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [created, setCreated] = useState<CreatedReport | null>(null);

  function toggleColor(color: Color) {
    setColors((prev) =>
      prev.includes(color) ? prev.filter((c) => c !== color) : prev.length < MAX_COLORS ? [...prev, color] : prev,
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(undefined);

    if (!category) return setError(new Error("Pick a category."));
    if (colors.length < 1) return setError(new Error("Pick at least one color."));
    if (description.trim() === "") return setError(new Error("Describe what you lost."));

    const body = {
      category,
      colors,
      description: description.trim(),
      // Optional fields are left out when empty: the API rejects empty strings.
      ...(lostLocation.trim() ? { lostLocation: lostLocation.trim() } : {}),
      ...(lostAt && !Number.isNaN(new Date(lostAt).getTime()) ? { lostAt: new Date(lostAt).toISOString() } : {}),
    };

    setSubmitting(true);
    try {
      setCreated(await api.createReport(body));
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <section>
        <h1>Report filed</h1>
        <div className="notice" role="status">
          {ALERT_MESSAGES[created.alerts]}
        </div>
        <p>
          We compare your report with found items as they are posted. Matches show up on the report.
        </p>
        <p>
          <Link to={`/reports/${encodeURIComponent(created.report.reportId)}`}>Open this report</Link>
          {" | "}
          <Link to="/reports">See all my reports</Link>
          {created.alerts !== "no-verified-email" && (
            <>
              {" | "}
              <Link to="/alerts">Email alert status</Link>
            </>
          )}
        </p>
      </section>
    );
  }

  const details = error instanceof ApiError ? error.details : [];

  return (
    <section>
      <h1>I lost something</h1>
      <p className="muted">
        Describe it and we will email you if a found item looks like a match. You get one confirmation email
        the first time; click the link in it to turn alerts on.
      </p>

      <form className="form" onSubmit={onSubmit} noValidate>
        <ErrorBanner error={error} />
        {details.length > 0 && (
          <ul className="muted">
            {details.map((d) => (
              <li key={`${d.field}:${d.issue}`}>
                <strong>{d.field}</strong>: {d.issue}
              </li>
            ))}
          </ul>
        )}

        <Field label="Category" htmlFor="category">
          <select
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value as Category | "")}
            required
          >
            <option value="">Choose a category...</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>

        <fieldset className="field">
          <legend>Colors (pick 1 to {MAX_COLORS})</legend>
          <div className="chips">
            {COLORS.map((c) => {
              const checked = colors.includes(c.value);
              const full = !checked && colors.length >= MAX_COLORS;
              return (
                <label key={c.value} className={checked ? "chip selected" : "chip"} style={full ? { opacity: 0.5 } : undefined}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={full}
                    onChange={() => toggleColor(c.value)}
                    style={{ marginRight: "0.35rem" }}
                  />
                  {c.label}
                </label>
              );
            })}
          </div>
          <span className="hint">{COLOR_HINT}</span>
        </fieldset>

        <Field label="Description" htmlFor="description" hint="Brand, size, marks, stickers, anything that identifies it. Up to 1000 characters.">
          <textarea
            id="description"
            value={description}
            maxLength={1000}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </Field>

        <Field label="Where did you lose it? (optional)" htmlFor="lostLocation">
          <input
            id="lostLocation"
            type="text"
            value={lostLocation}
            maxLength={200}
            onChange={(e) => setLostLocation(e.target.value)}
          />
        </Field>

        <Field label="When did you lose it? (optional)" htmlFor="lostAt">
          <input
            id="lostAt"
            type="datetime-local"
            value={lostAt}
            max={nowLocal()}
            onChange={(e) => setLostAt(e.target.value)}
          />
        </Field>

        <div>
          <button type="submit" className="primary" disabled={submitting}>
            {submitting ? "Filing..." : "File report"}
          </button>
        </div>
      </form>
    </section>
  );
}

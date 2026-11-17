import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api, describeError, uploadPhoto, type CreateItemBody } from "../api";
import { CATEGORIES, COLORS, COLOR_HINT, MAX_COLORS, type Category, type Color } from "../vocab";
import { convertToJpeg } from "../image";
import "./finder.css";

// Same limits as api/schemas/requests/create-item.json. The server stays the source of truth.
const MAX_TITLE = 80;
const MAX_DESCRIPTION = 1000;
const MAX_LOCATION = 200;

const FIELD_KEYS = ["title", "description", "category", "colors", "foundLocation", "foundAt"] as const;

type ErrorKey = (typeof FIELD_KEYS)[number] | "photo" | "form";
type Errors = Partial<Record<ErrorKey, string>>;

/** Value for <input type="datetime-local"> in the user's local time. */
function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Screen 1.3. Post a found item, then upload the photo straight to S3, then open the item. */
export function PostItemScreen() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<Category | "">("");
  const [colors, setColors] = useState<Color[]>([]);
  const [foundLocation, setFoundLocation] = useState("");
  const [foundAt, setFoundAt] = useState(() => toLocalInput(new Date()));
  const [photo, setPhoto] = useState<File | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [uploadFailedFor, setUploadFailedFor] = useState<string | null>(null);

  const previewUrl = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  function toggleColor(c: Color) {
    setColors((prev) => {
      if (prev.includes(c)) return prev.filter((x) => x !== c);
      return prev.length >= MAX_COLORS ? prev : [...prev, c];
    });
  }

  function validate(): Errors {
    const e: Errors = {};
    const t = title.trim();
    if (!t) e.title = "Enter a title.";
    else if (t.length > MAX_TITLE) e.title = `Use at most ${MAX_TITLE} characters.`;
    if (description.trim().length > MAX_DESCRIPTION) e.description = `Use at most ${MAX_DESCRIPTION} characters.`;
    if (!category) e.category = "Pick a category.";
    if (colors.length < 1 || colors.length > MAX_COLORS) e.colors = `Pick 1 to ${MAX_COLORS} colors.`;
    const loc = foundLocation.trim();
    if (!loc) e.foundLocation = "Enter where you found it.";
    else if (loc.length > MAX_LOCATION) e.foundLocation = `Use at most ${MAX_LOCATION} characters.`;
    const when = new Date(foundAt);
    if (!foundAt || Number.isNaN(when.getTime())) e.foundAt = "Enter when you found it.";
    else if (when.getTime() > Date.now()) e.foundAt = "The time cannot be in the future.";
    if (photo && !photo.type.startsWith("image/")) e.photo = "Pick an image file.";
    return e;
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (busy) return;
    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setBusy(true);
    setUploadFailedFor(null);

    // Convert first so a bad image fails before an item is created.
    let jpeg: Blob | null = null;
    if (photo) {
      try {
        jpeg = await convertToJpeg(photo);
      } catch (err) {
        setErrors({ photo: describeError(err) });
        setBusy(false);
        return;
      }
    }

    const body: CreateItemBody = {
      title: title.trim(),
      category: category as Category,
      colors,
      foundLocation: foundLocation.trim(),
      foundAt: new Date(foundAt).toISOString(),
    };
    const desc = description.trim();
    if (desc) body.description = desc; // leave an empty optional field out

    try {
      const created = await api.createItem(body);
      if (jpeg) {
        try {
          await uploadPhoto(created.upload, jpeg);
        } catch (err) {
          // The item exists but has no photo and there is no route for a new upload form (data-model 8.7).
          setUploadFailedFor(created.itemId);
          setErrors({ form: describeError(err) });
          setBusy(false);
          return;
        }
      }
      navigate(`/items/${created.itemId}`);
    } catch (err) {
      const next: Errors = {};
      if (err instanceof ApiError && err.details.length > 0) {
        for (const d of err.details) {
          const head = d.field.split(/[.[]/)[0];
          const key: ErrorKey = (FIELD_KEYS as readonly string[]).includes(head) ? (head as ErrorKey) : "form";
          next[key] = next[key] ? `${next[key]} ${d.issue}` : d.issue;
        }
      } else {
        next.form = describeError(err);
      }
      setErrors(next);
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Post a found item</h1>
      <form className="form" onSubmit={onSubmit} noValidate>
        {errors.form && (
          <div className="notice notice-error" role="alert">
            <p>{errors.form}</p>
            {uploadFailedFor && (
              <p>
                The item was saved without its photo. <Link to={`/items/${uploadFailedFor}`}>Open the item</Link>.
              </p>
            )}
          </div>
        )}

        <div className="field">
          <label htmlFor="title">Title</label>
          <input id="title" type="text" value={title} maxLength={MAX_TITLE} onChange={(e) => setTitle(e.target.value)} aria-invalid={!!errors.title} />
          {errors.title && <p className="field-error">{errors.title}</p>}
        </div>

        <div className="field">
          <label htmlFor="description">Description (optional)</label>
          <textarea id="description" value={description} maxLength={MAX_DESCRIPTION} onChange={(e) => setDescription(e.target.value)} aria-invalid={!!errors.description} />
          {errors.description && <p className="field-error">{errors.description}</p>}
        </div>

        <div className="field">
          <label htmlFor="category">Category</label>
          <select id="category" value={category} onChange={(e) => setCategory(e.target.value as Category | "")} aria-invalid={!!errors.category}>
            <option value="">Pick a category</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
          {errors.category && <p className="field-error">{errors.category}</p>}
        </div>

        <fieldset className="field">
          <legend>Colors (pick 1 to {MAX_COLORS})</legend>
          <div className="checks">
            {COLORS.map((c) => {
              const checked = colors.includes(c.value);
              return (
                <label key={c.value}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!checked && colors.length >= MAX_COLORS}
                    onChange={() => toggleColor(c.value)}
                  />
                  {c.label}
                </label>
              );
            })}
          </div>
          <span className="hint">{COLOR_HINT}</span>
          {errors.colors && <p className="field-error">{errors.colors}</p>}
        </fieldset>

        <div className="field">
          <label htmlFor="foundLocation">Where did you find it?</label>
          <input id="foundLocation" type="text" value={foundLocation} maxLength={MAX_LOCATION} onChange={(e) => setFoundLocation(e.target.value)} aria-invalid={!!errors.foundLocation} />
          {errors.foundLocation && <p className="field-error">{errors.foundLocation}</p>}
        </div>

        <div className="field">
          <label htmlFor="foundAt">When did you find it?</label>
          <input id="foundAt" type="datetime-local" value={foundAt} max={toLocalInput(new Date())} onChange={(e) => setFoundAt(e.target.value)} aria-invalid={!!errors.foundAt} />
          {errors.foundAt && <p className="field-error">{errors.foundAt}</p>}
        </div>

        <div className="field">
          <label htmlFor="photo">Photo (optional, converted to JPEG, up to 10 MB)</label>
          <input id="photo" type="file" accept="image/*" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} aria-invalid={!!errors.photo} />
          {previewUrl && <img className="photo-preview" src={previewUrl} alt="Selected photo preview" />}
          {errors.photo && <p className="field-error">{errors.photo}</p>}
          <span className="hint">Photos of wallets and ID cards are hidden from other people.</span>
        </div>

        <div className="form-actions">
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Posting..." : "Post item"}
          </button>
          <Link to="/">Cancel</Link>
        </div>
      </form>
    </section>
  );
}

// Typed fetch client for the 10 routes in api/openapi.yaml.
// Auth: the API wants the Cognito ID TOKEN (token_use "id"), never the access token.

import { config } from "./config";
import { userManager } from "./auth";
import type { Category, Color } from "./vocab";

// ---------- Types (from api/openapi.yaml components) ----------

export type ItemStatus = "LISTED" | "RETURNED";
export type TagStatus = "PENDING" | "TAGGED" | "FAILED";
export type ReportStatus = "OPEN" | "CLOSED";
export type AlertState = "NONE" | "UNCONFIRMED" | "CONFIRMED" | "GONE";
export type AlertsOutcome = "started" | "existing" | "no-verified-email" | "unavailable";

export interface PhotoLink {
  url: string;
  expiresAt: string;
}

export interface ItemSummary {
  itemId: string;
  title: string;
  category: Category;
  colors: Color[];
  foundLocation: string;
  foundAt: string;
  createdAt: string;
  status: ItemStatus;
  tagStatus: TagStatus;
  isMine: boolean;
  /** Absent for a wallet-id item posted by someone else (and when not available). Show a placeholder. */
  photo?: PhotoLink;
}

export interface ScoredValue<T> {
  value: T;
  score: number;
}

export interface ClipTags {
  categories: ScoredValue<Category>[];
  colors: ScoredValue<Color>[];
}

export interface ItemDetail extends ItemSummary {
  description?: string;
  returnedAt?: string;
  clipTags?: ClipTags;
}

export interface NewItem extends Omit<ItemSummary, "photo"> {
  description?: string;
}

export interface UploadForm {
  url: string;
  fields: Record<string, string>;
  expiresAt: string;
}

export interface CreatedItem {
  itemId: string;
  item: NewItem;
  upload: UploadForm;
}

export interface ItemList {
  items: ItemSummary[];
  nextToken?: string;
}

export interface Report {
  reportId: string;
  category: Category;
  colors: Color[];
  description: string;
  lostLocation?: string;
  lostAt?: string;
  status: ReportStatus;
  createdAt: string;
  closedAt?: string;
}

export interface ReportList {
  reports: Report[];
  nextToken?: string;
}

export interface CreatedReport {
  report: Report;
  alerts: AlertsOutcome;
}

export interface Match {
  item: ItemSummary;
  score: number;
  why: string[];
  createdAt: string;
}

export interface ReportDetail {
  report: Report;
  matches: Match[];
}

export interface AlertStatus {
  state: AlertState;
}

export interface CreateItemBody {
  title: string;
  description?: string;
  category: Category;
  colors: Color[];
  foundLocation: string;
  /** ISO 8601 with Z or an offset. Not in the future. */
  foundAt: string;
}

export interface CreateReportBody {
  category: Category;
  colors: Color[];
  description: string;
  lostLocation?: string;
  lostAt?: string;
}

export interface ListItemsParams {
  category?: Category;
  limit?: number;
  nextToken?: string;
}

export interface ListReportsParams {
  limit?: number;
  nextToken?: string;
}

// ---------- Errors ----------

export interface ErrorDetail {
  field: string;
  issue: string;
}

/** Thrown for every non-2xx answer. Test `status`, never `message`. */
export class ApiError extends Error {
  readonly status: number;
  readonly details: ErrorDetail[];

  constructor(status: number, message: string, details: ErrorDetail[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

// ---------- Core request ----------

async function idToken(forceRefresh = false): Promise<string> {
  let user = await userManager.getUser();
  if (!user || forceRefresh || user.expired) {
    try {
      user = await userManager.signinSilent(); // refresh-token grant
    } catch {
      user = null;
    }
  }
  if (!user?.id_token) {
    throw new ApiError(401, "You are signed out. Sign in again.");
  }
  return user.id_token;
}

async function readError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status}).`;
  let details: ErrorDetail[] = [];
  try {
    const body = (await res.json()) as { message?: unknown; details?: unknown };
    if (typeof body.message === "string") message = body.message;
    if (Array.isArray(body.details)) {
      details = body.details.filter(
        (d): d is ErrorDetail =>
          !!d && typeof d.field === "string" && typeof d.issue === "string",
      );
    }
  } catch {
    // Non-JSON error (gateway edge cases): keep the generic message.
  }
  return new ApiError(res.status, message, details);
}

function buildQuery(params?: Record<string, string | number | undefined>): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  opts: { query?: Record<string, string | number | undefined>; body?: unknown } = {},
): Promise<T> {
  const url = `${config.apiBaseUrl}${path}${buildQuery(opts.query)}`;

  const send = async (token: string) => {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    let body: string | undefined;
    if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
    return fetch(url, { method, headers, body });
  };

  let res = await send(await idToken());
  if (res.status === 401) {
    // Refresh the token and try once more (openapi.yaml, "Errors").
    res = await send(await idToken(true));
  }
  if (!res.ok) throw await readError(res);
  return (await res.json()) as T;
}

/** Path segment for an ID; the API only accepts UUIDs, so encode defensively. */
const seg = (id: string) => encodeURIComponent(id);

// ---------- The 10 routes ----------

export const api = {
  listItems: (params: ListItemsParams = {}) =>
    request<ItemList>("GET", "/items", { query: { ...params } }),
  createItem: (body: CreateItemBody) => request<CreatedItem>("POST", "/items", { body }),
  getItem: (itemId: string) => request<ItemDetail>("GET", `/items/${seg(itemId)}`),
  markItemReturned: (itemId: string) =>
    request<ItemDetail>("POST", `/items/${seg(itemId)}/returned`),

  listReports: (params: ListReportsParams = {}) =>
    request<ReportList>("GET", "/reports", { query: { ...params } }),
  createReport: (body: CreateReportBody) =>
    request<CreatedReport>("POST", "/reports", { body }),
  getReport: (reportId: string) => request<ReportDetail>("GET", `/reports/${seg(reportId)}`),
  closeReport: (reportId: string) =>
    request<Report>("POST", `/reports/${seg(reportId)}/closed`),

  getMyAlerts: () => request<AlertStatus>("GET", "/me/alerts"),
  subscribeMyAlerts: () => request<AlertStatus>("POST", "/me/alerts"),
};

// ---------- Photo upload (S3 presigned POST, not an API call) ----------

/**
 * POST multipart/form-data straight to S3. Every `upload.fields` entry goes first as a plain field,
 * the file goes last under the name "file". No Authorization header (S3 would reject it).
 * The file must already be a JPEG of 1 byte to 10 MB. S3 answers 204 on success.
 */
export async function uploadPhoto(upload: UploadForm, file: Blob): Promise<void> {
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) {
    form.append(name, value);
  }
  form.append("file", file); // must be last

  let res: Response;
  try {
    res = await fetch(upload.url, { method: "POST", body: form });
  } catch {
    throw new ApiError(0, "The photo upload could not reach the server. Check your connection.");
  }
  if (!res.ok) {
    // S3 answers with an XML error body; pull the <Message> if it is there.
    let message = `The photo upload failed (${res.status}).`;
    try {
      const xml = await res.text();
      const m = /<Message>([^<]*)<\/Message>/.exec(xml);
      if (m?.[1]) message = `${message} ${m[1]}`;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message);
  }
}

/** Message for a form: the error's message plus any per-field details. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.details.length > 0) {
      return `${err.message} ${err.details.map((d) => `${d.field}: ${d.issue}`).join(" ")}`;
    }
    return err.message;
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}

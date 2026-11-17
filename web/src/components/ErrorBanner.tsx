import { describeError } from "../api";

/** Red notice for a failed call. Pass the caught `error` (ApiError details are included) or a plain `message`. */
export function ErrorBanner({ error, message }: { error?: unknown; message?: string }) {
  if (error === undefined && !message) return null;
  return (
    <div className="notice notice-error" role="alert">
      {message ?? describeError(error)}
    </div>
  );
}

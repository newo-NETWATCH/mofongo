import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

/**
 * The configured Cognito redirect URI is "/", and <AuthProvider> finishes the code exchange there.
 * This /callback route exists only so a redirect URI of /callback would also work: it waits for the
 * exchange, then goes home.
 */
export function CallbackScreen() {
  const auth = useAuth();
  if (auth.error) {
    return (
      <div className="notice notice-error" role="alert">
        Sign-in failed: {auth.error.message}
      </div>
    );
  }
  if (auth.isLoading) return <p className="muted">Signing you in...</p>;
  return <Navigate to="/" replace />;
}

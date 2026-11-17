import { signIn, useAuth } from "../auth";

/** Shown at "/" to signed-out visitors. Signed-in users see Browse there instead (see App.tsx). */
export function LandingScreen() {
  const auth = useAuth();
  return (
    <section className="landing">
      <h1>Lost something? Found something?</h1>
      <p>
        Mofongo helps people get lost items back. Post what you found, or tell us what you lost and we will
        email you when something matches.
      </p>
      <button type="button" className="primary" onClick={() => void signIn(auth, "/")}>
        Sign in or create an account
      </button>
    </section>
  );
}

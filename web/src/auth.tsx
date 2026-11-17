import { useEffect, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useAuth as useOidcAuth, type AuthContextProps } from "react-oidc-context";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import { config } from "./config";

// Authorization-Code + PKCE against the Cognito user pool (public client, no secret).
// The API needs the ID token (not the access token), see api.ts.
// One shared UserManager so api.ts can read/refresh the current user outside React.
export const userManager = new UserManager({
  authority: config.cognito.authority,
  client_id: config.cognito.clientId,
  redirect_uri: config.redirectUri,
  post_logout_redirect_uri: config.postLogoutUri,
  response_type: "code",
  scope: "openid email profile",
  // sessionStorage: tokens vanish when the tab closes and are not shared across tabs.
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true, // uses the refresh token, no iframe
  loadUserInfo: false, // everything we need is in the ID token
});

/** Props for <AuthProvider>. After the code exchange, drop ?code&state and go back where the user was. */
export const authProviderProps = {
  userManager,
  onSigninCallback: (user: User | void) => {
    const state = (user && (user.state as { returnTo?: string } | undefined)) || undefined;
    const target = state?.returnTo && state.returnTo.startsWith("/") ? state.returnTo : "/";
    window.history.replaceState({}, document.title, target);
    // BrowserRouter does not see replaceState; nudge it.
    window.dispatchEvent(new PopStateEvent("popstate"));
  },
};

export function useAuth(): AuthContextProps {
  return useOidcAuth();
}

/** The signed-in user's email claim, for display only. */
export function currentEmail(auth: AuthContextProps): string | undefined {
  const email = auth.user?.profile?.email;
  return typeof email === "string" ? email : undefined;
}

export function signIn(auth: AuthContextProps, returnTo?: string): Promise<void> {
  return auth.signinRedirect({ state: { returnTo: returnTo ?? "/" } });
}

/**
 * Cognito's discovery document has no end_session_endpoint, so oidc-client-ts cannot sign out by itself.
 * Clear the local user, then send the browser to the hosted /logout endpoint.
 * The logout_uri must be one of the app client's allowed sign-out URLs.
 */
export async function signOut(auth: AuthContextProps): Promise<void> {
  await auth.removeUser();
  const url = new URL(`${config.cognito.domain}/logout`);
  url.searchParams.set("client_id", config.cognito.clientId);
  url.searchParams.set("logout_uri", config.postLogoutUri);
  window.location.assign(url.toString());
}

/** Wrap authenticated screens. Sends signed-out visitors to the Cognito hosted login. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useOidcAuth();
  const location = useLocation();
  const returnTo = location.pathname + location.search;

  const busy = auth.isLoading || !!auth.activeNavigator;
  const needsLogin = !busy && !auth.isAuthenticated && !auth.error;

  useEffect(() => {
    if (needsLogin) {
      void auth.signinRedirect({ state: { returnTo } });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsLogin, returnTo]);

  if (auth.error) {
    return (
      <div className="notice notice-error" role="alert">
        <p>Sign-in problem: {auth.error.message}</p>
        <button type="button" onClick={() => void signIn(auth, returnTo)}>
          Try signing in again
        </button>
      </div>
    );
  }
  if (!auth.isAuthenticated) {
    return <p className="muted">Taking you to sign in...</p>;
  }
  return <>{children}</>;
}

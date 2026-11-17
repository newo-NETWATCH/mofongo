import { NavLink, Route, Routes } from "react-router-dom";
import { RequireAuth, currentEmail, signIn, signOut, useAuth } from "./auth";
import { LandingScreen } from "./screens/LandingScreen";
import { CallbackScreen } from "./screens/CallbackScreen";
// The screens below are written by other agents. See src/screens/README.md for the exact names.
import { BrowseScreen } from "./screens/BrowseScreen";
import { ItemDetailScreen } from "./screens/ItemDetailScreen";
import { PostItemScreen } from "./screens/PostItemScreen";
import { NewReportScreen } from "./screens/NewReportScreen";
import { MyReportsScreen } from "./screens/MyReportsScreen";
import { ReportDetailScreen } from "./screens/ReportDetailScreen";
import { AlertsScreen } from "./screens/AlertsScreen";

function NavBar() {
  const auth = useAuth();
  const email = currentEmail(auth);
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : undefined);

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <NavLink to="/" className="brand">
          Mofongo
        </NavLink>
        {auth.isAuthenticated && (
          <nav aria-label="Main">
            <NavLink to="/" end className={link}>
              Browse
            </NavLink>
            <NavLink to="/post" className={link}>
              Post item
            </NavLink>
            <NavLink to="/reports/new" className={link}>
              I lost something
            </NavLink>
            <NavLink to="/reports" end className={link}>
              My reports
            </NavLink>
            <NavLink to="/alerts" className={link}>
              Alerts
            </NavLink>
          </nav>
        )}
        <div className="account">
          {auth.isAuthenticated ? (
            <>
              {email && <span className="muted email">{email}</span>}
              <button type="button" onClick={() => void signOut(auth)}>
                Sign out
              </button>
            </>
          ) : (
            <button
              type="button"
              className="primary"
              disabled={auth.isLoading}
              onClick={() => void signIn(auth, "/")}
            >
              Sign in
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

/** "/" is the landing page for visitors and Browse for signed-in users. */
function Home() {
  const auth = useAuth();
  if (auth.isLoading) return <p className="muted">Loading...</p>;
  return auth.isAuthenticated ? <BrowseScreen /> : <LandingScreen />;
}

function NotFound() {
  return (
    <div>
      <h1>Page not found</h1>
      <p>
        <NavLink to="/">Back to browse</NavLink>
      </p>
    </div>
  );
}

export function App() {
  return (
    <>
      <NavBar />
      <main className="page">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/callback" element={<CallbackScreen />} />
          <Route path="/items/:itemId" element={<RequireAuth><ItemDetailScreen /></RequireAuth>} />
          <Route path="/post" element={<RequireAuth><PostItemScreen /></RequireAuth>} />
          {/* "/reports/new" must stay above "/reports/:reportId" (React Router ranks static paths first anyway). */}
          <Route path="/reports/new" element={<RequireAuth><NewReportScreen /></RequireAuth>} />
          <Route path="/reports" element={<RequireAuth><MyReportsScreen /></RequireAuth>} />
          <Route path="/reports/:reportId" element={<RequireAuth><ReportDetailScreen /></RequireAuth>} />
          <Route path="/alerts" element={<RequireAuth><AlertsScreen /></RequireAuth>} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}

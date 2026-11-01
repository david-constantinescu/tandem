import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Page } from "./components/motion";
import { AppShell } from "./components/layout/AppShell";
import { PageLoader } from "./components/ui";
import { useAuth } from "./lib/auth";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";

const TripsPage = lazy(() => import("./pages/TripsPage"));
const TripDetailPage = lazy(() => import("./pages/TripDetailPage"));
const JoinPage = lazy(() => import("./pages/JoinPage"));
const InboxItemPage = lazy(() => import("./pages/InboxItemPage"));
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

/** adresele vechi inca stau in notificari, in raspunsurile asistentului si in marcajele de pe ecranul principal: le pastram functionale */
function Moved({ to, extra }: { to: string; extra?: Record<string, string> }) {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  for (const [k, v] of Object.entries(extra ?? {})) if (!params.has(k)) params.set(k, v);
  const q = params.toString();
  return <Navigate to={`${to}${q ? `?${q}` : ""}`} replace />;
}

/** paginile de citit (inbox, documente, setari) au loc jos; derularea o face shell-ul */
function Pane({ children }: { children: ReactNode }) {
  return <div className="pb-10">{children}</div>;
}

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return (
    <AppShell>
      <Suspense fallback={<PageLoader />}>
        <Page key={location.pathname}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/trips" element={<TripsPage />} />
          <Route path="/trips/:id" element={<TripDetailPage />} />
          <Route path="/join/:token" element={<Pane><JoinPage /></Pane>} />
          <Route path="/inbox" element={<Moved to="/assistant" />} />
          <Route path="/inbox/:id" element={<Pane><InboxItemPage /></Pane>} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/assistant/:id" element={<AssistantPage />} />
          <Route path="/settings" element={<Pane><SettingsPage /></Pane>} />
          <Route path="/settings/:section" element={<Pane><SettingsPage /></Pane>} />
          <Route path="/discover" element={<Moved to="/assistant" />} />
          <Route path="/websites" element={<Moved to="/assistant" />} />
          <Route path="/approvals" element={<Moved to="/assistant" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Page>
      </Suspense>
    </AppShell>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route path="/*" element={<Protected />} />
    </Routes>
  );
}

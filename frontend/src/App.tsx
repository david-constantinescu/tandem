import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Page } from "./components/motion";
import { AppShell } from "./components/layout/AppShell";
import { PageLoader } from "./components/ui";
import { useAuth } from "./lib/auth";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";

const TripsPage = lazy(() => import("./pages/TripsPage"));
const TripDetailPage = lazy(() => import("./pages/TripDetailPage"));
const InboxPage = lazy(() => import("./pages/InboxPage"));
const InboxItemPage = lazy(() => import("./pages/InboxItemPage"));
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

/** Old addresses live on in notifications, assistant answers and home-screen bookmarks: keep them working. */
function Moved({ to, extra }: { to: string; extra?: Record<string, string> }) {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  for (const [k, v] of Object.entries(extra ?? {})) if (!params.has(k)) params.set(k, v);
  const q = params.toString();
  return <Navigate to={`${to}${q ? `?${q}` : ""}`} replace />;
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
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/inbox/:id" element={<InboxItemPage />} />
          <Route path="/explore" element={<ExplorePage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/assistant/:id" element={<AssistantPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/:section" element={<SettingsPage />} />
          <Route path="/discover" element={<Moved to="/explore" />} />
          <Route path="/websites" element={<Moved to="/explore" extra={{ tab: "tickets" }} />} />
          <Route path="/approvals" element={<Moved to="/inbox" extra={{ tab: "approvals" }} />} />
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

import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { PageLoader } from "./components/ui";
import { useAuth } from "./lib/auth";
import AuthPage from "./pages/AuthPage";
import HomePage from "./pages/HomePage";

const TripsPage = lazy(() => import("./pages/TripsPage"));
const TripDetailPage = lazy(() => import("./pages/TripDetailPage"));
const InboxPage = lazy(() => import("./pages/InboxPage"));
const InboxItemPage = lazy(() => import("./pages/InboxItemPage"));
const DiscoverPage = lazy(() => import("./pages/DiscoverPage"));
const AssistantPage = lazy(() => import("./pages/AssistantPage"));
const ApprovalsPage = lazy(() => import("./pages/ApprovalsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return (
    <AppShell>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/trips" element={<TripsPage />} />
          <Route path="/trips/:id" element={<TripDetailPage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/inbox/:id" element={<InboxItemPage />} />
          <Route path="/discover" element={<DiscoverPage />} />
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/assistant/:id" element={<AssistantPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/:section" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
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

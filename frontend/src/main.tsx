import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { MotionConfig } from "motion/react";
import "leaflet/dist/leaflet.css";
import "./styles/index.css";
import App from "./App";
import { UpdatePrompt } from "./components/pwa";
import { ToastProvider } from "./components/ui/Toast";
import { ApiError } from "./lib/api";
import { AuthProvider } from "./lib/auth";
import { I18nProvider } from "./lib/i18n";
import { applyTheme } from "./lib/theme";

applyTheme(); // before the first paint, so a light-mode choice doesn't flash dark

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      // "always": offline requests fail straight away and the page says so, instead of a spinner that never ends.
      networkMode: "always",
      retry: (count, err) => !(err instanceof ApiError && err.status > 0 && err.status < 500) && count < 2 && navigator.onLine,
    },
    mutations: { networkMode: "always" },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ToastProvider>
            <MotionConfig reducedMotion="user">
              <App />
              <UpdatePrompt />
            </MotionConfig>
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
    </I18nProvider>
  </StrictMode>,
);

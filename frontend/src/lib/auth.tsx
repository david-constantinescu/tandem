import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, isNetworkError, setCsrf } from "./api";
import { isLocale, useT, type Locale } from "./i18n";
import { clearOffline, offlineUser, persistOffline, restoreOffline } from "./offline";
import type { User } from "./types";

type Session = { user: User | null; csrf_token: string | null };

type AuthState = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  startDemo: () => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  /** Switch the interface language; saved to the account when signed in so server text follows. */
  setLanguage: (l: Locale) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();
  const { locale, setLocale } = useT();

  // Signed in, the account's language wins; signed out, the device's last choice stays.
  const apply = useCallback((s: Session) => {
    setCsrf(s.csrf_token);
    setUser(s.user);
    if (s.user && isLocale(s.user.locale)) setLocale(s.user.locale);
  }, [setLocale]);

  const refresh = useCallback(async () => {
    try {
      const s = await api.get<Session>("/auth/me");
      if (s.user) restoreOffline(qc, s.user.id);
      else clearOffline();
      apply(s);
    } catch (err) {
      // Offline: open with the trips saved on this device. Any other failure means signed out.
      const saved = isNetworkError(err) ? offlineUser() : null;
      if (saved) {
        restoreOffline(qc, saved.id);
        apply({ user: saved, csrf_token: null });
      } else if (!isNetworkError(err)) {
        clearOffline();
      }
    } finally {
      setLoading(false);
    }
  }, [apply, qc]);

  useEffect(() => {
    refresh();
    // Back online: re-check the session (an offline start has no CSRF token yet).
    window.addEventListener("online", refresh);
    return () => window.removeEventListener("online", refresh);
  }, [refresh]);

  useEffect(() => (user ? persistOffline(qc, user) : undefined), [qc, user]);

  // A new session never sees the previous one's cached or saved data.
  const reset = () => {
    qc.clear();
    clearOffline();
  };

  const value: AuthState = {
    user,
    loading,
    refresh,
    login: async (email, password) => {
      reset();
      apply(await api.post<Session>("/auth/login", { email, password }));
    },
    register: async (email, password, display_name) => {
      reset();
      apply(await api.post<Session>("/auth/register", { email, password, display_name, locale }));
    },
    startDemo: async () => {
      reset();
      apply(await api.post<Session>("/auth/demo", { locale }));
    },
    logout: async () => {
      try {
        await api.post("/auth/logout");
      } finally {
        reset();
        apply({ user: null, csrf_token: null });
      }
    },
    setLanguage: async (l) => {
      if (l === locale) return;
      setLocale(l);
      if (user) {
        try {
          await api.patch("/settings/profile", { locale: l });
          setUser({ ...user, locale: l });
        } catch {
          // Offline or signed out meanwhile: the device keeps the choice and the account catches up next time.
        }
      }
      // Conflicts, notifications and assistant text come from the server in the account's language.
      qc.invalidateQueries();
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setCsrf } from "./api";
import { setLocale } from "./i18n";
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
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const apply = useCallback((s: Session) => {
    setCsrf(s.csrf_token);
    setUser(s.user);
    if (s.user) setLocale(s.user.locale);
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply(await api.get<Session>("/auth/me"));
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value: AuthState = {
    user,
    loading,
    refresh,
    login: async (email, password) => {
      qc.clear();
      apply(await api.post<Session>("/auth/login", { email, password }));
    },
    register: async (email, password, display_name) => {
      qc.clear();
      apply(await api.post<Session>("/auth/register", { email, password, display_name }));
    },
    startDemo: async () => {
      qc.clear();
      apply(await api.post<Session>("/auth/demo"));
    },
    logout: async () => {
      try {
        await api.post("/auth/logout");
      } finally {
        qc.clear();
        apply({ user: null, csrf_token: null });
      }
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

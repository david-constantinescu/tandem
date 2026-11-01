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
  /** schimba limba interfetei; se salveaza in cont cand esti conectat, ca textele de pe server sa urmeze */
  setLanguage: (l: Locale) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();
  const { locale, setLocale } = useT();

  // conectat, conteaza limba contului; deconectat, ramane ultima alegere de pe dispozitiv
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
      // fara net: deschidem cu calatoriile salvate pe dispozitiv. Orice alta eroare inseamna deconectat
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
    // iar online: verificam din nou sesiunea (o pornire fara net nu are inca token CSRF)
    window.addEventListener("online", refresh);
    return () => window.removeEventListener("online", refresh);
  }, [refresh]);

  useEffect(() => (user ? persistOffline(qc, user) : undefined), [qc, user]);

  // o sesiune noua nu vede niciodata datele salvate sau din cache ale celei dinainte
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
          // fara net sau deconectat intre timp: dispozitivul tine alegerea, iar contul se aliniaza data viitoare
        }
      }
      // suprapunerile, notificarile si textele asistentului vin de pe server in limba contului
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

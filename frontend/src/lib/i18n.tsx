/**
 * traduceri. Romana e implicita, engleza e alternativa. `en` e sursa de adevar tipizata, iar `ro`
 * trebuie sa traduca fiecare cheie, deci o traducere lipsa pica la verificarea de tipuri, nu apare engleza.
 *
 * Care limba castiga: deconectat, ultima alegere salvata pe dispozitiv (altfel romana); conectat, limba
 * contului. Schimbarea cat esti conectat se salveaza si in cont, ca textele scrise de server sa urmeze.
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { en, type Key } from "@/locales/en";
import { ro } from "@/locales/ro";

export type Locale = "ro" | "en";
export const LOCALES: { value: Locale; label: string; short: string }[] = [
  { value: "ro", label: "Română", short: "RO" },
  { value: "en", label: "English", short: "EN" },
];

const dictionaries: Record<Locale, Record<Key, string>> = { en, ro };
const STORE = "tandem.locale";

export type Vars = Record<string, string | number>;
/** numele de baza ale cheilor de plural: "trips.bookings" pentru "trips.bookings_one" / "_few" / "_other" */
export type PluralKey = { [K in Key]: K extends `${infer B}_one` ? B : never }[Key];

export function isLocale(v: unknown): v is Locale {
  return v === "ro" || v === "en";
}

function stored(): Locale {
  try {
    const v = localStorage.getItem(STORE);
    return isLocale(v) ? v : "ro";
  } catch {
    return "ro";
  }
}

let current: Locale = stored();

/** limba activa, pentru cod din afara React (formatari, mesaje de eroare) */
export function getLocale(): Locale {
  return current;
}

/** eticheta BCP 47 pentru formatarea Intl */
export function intlLocale(locale: Locale = current): string {
  return locale === "ro" ? "ro-RO" : "en-GB";
}

function apply(locale: Locale) {
  current = locale;
  try {
    localStorage.setItem(STORE, locale);
  } catch {
    // navigare privata: alegerea tine doar cat dureaza vizita
  }
  document.documentElement.lang = locale;
  document.title = dictionaries[locale]["app.title"];
}

export function translate(key: Key, vars?: Vars, locale: Locale = current): string {
  const text = dictionaries[locale][key] ?? en[key] ?? key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m)) : text;
}

/** cautare cu plural: romana are trei forme ("1 zi", "2 zile", "20 de zile"), engleza doua */
export function translatePlural(base: PluralKey, n: number, vars?: Vars, locale: Locale = current): string {
  const cat = new Intl.PluralRules(intlLocale(locale)).select(n);
  const form = cat === "one" ? "one" : cat === "few" ? "few" : "other";
  return translate(`${base}_${form}` as Key, { n, ...vars }, locale);
}

type I18n = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: Key, vars?: Vars) => string;
  tp: (base: PluralKey, n: number, vars?: Vars) => string;
};

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setState] = useState<Locale>(() => {
    apply(current);
    return current;
  });
  const setLocale = useCallback((l: Locale) => {
    if (!isLocale(l)) return;
    apply(l);
    setState(l);
  }, []);
  // `locale` e dependenta, ca orice consumator sa se redeseneze (si sa reformateze datele) dupa schimbare
  const value = useMemo<I18n>(() => ({
    locale,
    setLocale,
    t: (key, vars) => translate(key, vars, locale),
    tp: (base, n, vars) => translatePlural(base, n, vars, locale),
  }), [locale, setLocale]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useT(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useT outside I18nProvider");
  return ctx;
}

export type { Key };

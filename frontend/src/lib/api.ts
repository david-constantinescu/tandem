/** client subtire pentru API-ul Flask. Autentificare cu cookie de sesiune + header CSRF la fiecare cerere care schimba ceva.
 * Fiecare cerere spune limba interfetei, ca serverul sa raspunda in ea (erori, suprapuneri, asistent). */
import { getLocale, translate } from "./i18n";

let csrfToken: string | null = null;

export function setCsrf(token: string | null) {
  csrfToken = token;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type Options = { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal };

export async function request<T = unknown>(path: string, opts: Options = {}): Promise<{ data: T; meta?: any }> {
  const method = opts.method ?? (opts.body || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json", "X-Tandem-Locale": getLocale() };
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin", signal: opts.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    // fetch pica doar cand cererea n-a primit niciun raspuns: fara net, DNS, conexiune cazuta
    throw new ApiError(0, "network", translate(navigator.onLine ? "err.unreachable" : "err.offline"));
  }
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await res.json() : null;
  if (!res.ok && !(res.status === 422 && payload?.data)) {
    const err = payload?.error ?? {};
    throw new ApiError(res.status, err.code ?? "http_error", err.message ?? translate("err.status", { status: res.status }), err.details);
  }
  return payload ?? { data: null as T };
}

export const api = {
  get: <T,>(path: string) => request<T>(path).then((r) => r.data),
  getWithMeta: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body ?? {} }).then((r) => r.data),
  put: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: body ?? {} }).then((r) => r.data),
  patch: <T,>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body ?? {} }).then((r) => r.data),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }).then((r) => r.data),
  upload: <T,>(path: string, form: FormData) => request<T>(path, { method: "POST", form }).then((r) => r.data),
};

export const isNetworkError = (err: unknown) => err instanceof ApiError && err.status === 0;

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (Array.isArray(err.details) && err.details.length) {
      const first = err.details[0] as { field?: string; message?: string };
      if (first?.message) return `${err.message}: ${first.field ? `${first.field} — ` : ""}${first.message}`;
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return translate("err.generic");
}

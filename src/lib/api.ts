// API client for the Seven1tel admin panel.
// Configure VITE_API_BASE in .env (e.g. https://tg.nexus-x.site/api). Falls back to "/api".
/* eslint-disable @typescript-eslint/no-explicit-any */

const BASE = (import.meta.env.VITE_API_BASE as string) || "/api";

const numberStatus = (n: any) => {
  if (n.status) return n.status;
  if (n.enabled === false) return "disabled";
  if (n.last_otp) return "used";
  return n.assigned_user_id ? "reserved" : "available";
};

const fromNumber = (n: any) => ({
  ...n,
  msisdn: n.msisdn ?? n.phone,
  service_name: n.service_name ?? n.service,
  country_name: n.country_name ?? n.country,
  status: numberStatus(n),
});

const toNumber = (n: any) => ({
  phone: n.phone ?? n.msisdn,
  service_id: n.service_id,
  country_id: n.country_id,
  provider_id: n.provider_id || null,
  range_id: n.range_id || null,
  enabled: n.status ? n.status !== "disabled" : n.enabled ?? true,
});

const fromService = (s: any) => ({ ...s, code: s.code ?? s.keyword });
const toService = (s: any) => ({
  name: s.name,
  keyword: s.keyword ?? s.code,
  emoji: s.emoji ?? "📱",
  custom_emoji_id: s.custom_emoji_id || null,
  enabled: s.enabled ?? true,
  sort_order: s.sort_order ?? 0,
});
const fromCountry = (c: any) => ({ ...c, iso: c.iso, code: c.iso || c.code, dial_code: c.dial_code ?? `+${c.code}` });
const toCountry = (c: any) => ({
  name: c.name,
  iso: c.iso ?? (String(c.code).replace(/^\+?\d+$/, "") || c.code),
  code: String(c.dial_code ?? c.phone_code ?? c.code).replace(/\D/g, ""),
  flag: c.flag ?? "🌍",
  custom_emoji_id: c.custom_emoji_id || null,
  enabled: c.enabled ?? true,
});
const fromOtp = (o: any) => ({
  ...o,
  received_at: o.received_at ?? o.created_at,
  msisdn: o.msisdn ?? o.phone,
  otp_code: o.otp_code ?? o.code,
});

export function token(): string | null {
  return localStorage.getItem("token");
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem("token", t);
  else localStorage.removeItem("token");
}

async function req<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  const t = token();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  const res = await fetch(BASE + path, { ...init, headers });
  if (res.status === 401) {
    setToken(null);
    if (location.pathname !== "/login") location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch {
      // Keep the HTTP status text when the backend returns non-JSON errors.
    }
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

const mapReq = async <T, R>(promise: Promise<T>, mapper: (value: T) => R): Promise<R> => mapper(await promise);

export const api = {
  login: (email: string, password: string) =>
    req<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  dashboard: () => mapReq(req<any>("/dashboard"), (s) => ({
    ...s,
    users: s.users ?? s.total_users,
    numbers_available: s.numbers_available ?? s.available_numbers,
    numbers_total: s.numbers_total ?? s.total_numbers,
    otp_24h: s.otp_24h ?? s.otps_24h,
    otp_total: s.otp_total ?? s.total_otps,
    pending_withdrawals: s.pending_withdrawals ?? 0,
    paid_total: s.paid_total ?? 0,
  })),
  rangeStats: () => req<Array<{ country_id: number; country_name: string; country_flag: string; country_code: string; range_id: number | null; range_name: string | null; label: string; total: number; assigned: number; available: number; }>>("/dashboard/range-stats"),
  settings: {
    list: () => req<Record<string, any>>("/settings"),
    set: (key: string, value: any) =>
      req(`/settings/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  },
  services: {
    list: () => mapReq(req<any[]>("/services"), (rows) => rows.map(fromService)),
    create: (b: any) => req("/services", { method: "POST", body: JSON.stringify(toService(b)) }),
    update: (id: number, b: any) => req(`/services/${id}`, { method: "PUT", body: JSON.stringify(toService(b)) }),
    remove: (id: number) => req(`/services/${id}`, { method: "DELETE" }),
  },
  countries: {
    list: () => mapReq(req<any[]>("/countries"), (rows) => rows.map(fromCountry)),
    create: (b: any) => req("/countries", { method: "POST", body: JSON.stringify(toCountry(b)) }),
    update: (id: number, b: any) => req(`/countries/${id}`, { method: "PUT", body: JSON.stringify(toCountry(b)) }),
    remove: (id: number) => req(`/countries/${id}`, { method: "DELETE" }),
  },
  numbers: {
    list: (q: Record<string, any> = {}) => {
      const clean: Record<string, string> = {};
      Object.entries(q).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") clean[k] = String(v);
      });
      const p = new URLSearchParams(clean).toString();
      return mapReq(req<any>(`/numbers${p ? "?" + p : ""}`), (r) => {
        // backend may return either array (legacy) or {items,total}
        if (Array.isArray(r)) return { items: r.map(fromNumber), total: r.length };
        return { items: (r.items || []).map(fromNumber), total: r.total ?? 0, limit: r.limit, offset: r.offset };
      });
    },
    create: (b: any) => req("/numbers", { method: "POST", body: JSON.stringify(toNumber(b)) }),
    bulk: (b: any) => req<{ inserted: number; submitted: number }>("/numbers/bulk", {
      method: "POST",
      body: JSON.stringify({
        service_id: b.service_id,
        country_id: b.country_id,
        provider_id: b.provider_id || null,
        range_id: b.range_id || null,
        phones: Array.isArray(b.msisdns) ? b.msisdns.join("\n") : b.phones ?? b.msisdns ?? "",
      }),
    }),
    update: (id: number, b: any) => req(`/numbers/${id}`, { method: "PUT", body: JSON.stringify(toNumber(b)) }),
    remove: (id: number) => req(`/numbers/${id}`, { method: "DELETE" }),
    bulkDelete: (filters: Record<string, any>) =>
      req<{ deleted: number }>(`/numbers/bulk-delete`, { method: "POST", body: JSON.stringify(filters) }),
  },
  users: {
    list: (q?: string) => req<any[]>(`/users${q ? "?q=" + encodeURIComponent(q) : ""}`),
    adjust: (id: number, delta: number) =>
      req(`/users/${id}/adjust`, { method: "POST", body: JSON.stringify({ delta }) }),
    ban: (id: number) => req(`/users/${id}/ban`, { method: "POST" }),
    unban: (id: number) => req(`/users/${id}/unban`, { method: "POST" }),
  },
  withdrawals: {
    list: (status?: string) =>
      req<any[]>(`/withdrawals${status ? "?status=" + status : ""}`),
    pay: (id: number, note?: string) =>
      req(`/withdrawals/${id}/pay`, { method: "POST", body: JSON.stringify({ note }) }),
    reject: (id: number, note?: string) =>
      req(`/withdrawals/${id}/reject`, { method: "POST", body: JSON.stringify({ note }) }),
  },
  sms: {
    list: () => mapReq(req<any[]>("/sms"), (rows) => rows.map(fromOtp)),
    inject: (body: { number_id: number; code: string; raw_text?: string; notify?: boolean }) =>
      req<{ ok: boolean; otp_id: number; delivered: boolean }>("/sms/inject", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  providers: {
    list: () => req<any[]>("/providers"),
  },
  ranges: {
    list: (country_id?: number) =>
      req<any[]>(`/ranges${country_id ? `?country_id=${country_id}` : ""}`),
    create: (b: any) => req("/ranges", { method: "POST", body: JSON.stringify(b) }),
    update: (id: number, b: any) => req(`/ranges/${id}`, { method: "PUT", body: JSON.stringify(b) }),
    remove: (id: number) => req(`/ranges/${id}`, { method: "DELETE" }),
  },
  ims: {
    accounts: () => req<any[]>("/ims/accounts"),
    test: (slot: "1" | "2") =>
      req<{ ok: boolean; rows_seen: number; session_saved: boolean }>(`/ims/${slot}/test`, { method: "POST" }),
    toggle: (slot: "1" | "2", enabled: boolean) =>
      req<{ ok: boolean; enabled: boolean }>(`/ims/${slot}/toggle`, {
        method: "POST",
        body: JSON.stringify({ enabled }),
      }),
    updateConfig: (slot: "1" | "2", body: Record<string, any>) =>
      req<{ ok: boolean; updated: string[] }>(`/ims/${slot}/config`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    relogin: (slot: "1" | "2") =>
      req<{ ok: boolean }>(`/ims/${slot}/relogin`, { method: "POST" }),
    clearSession: (slot: "1" | "2") =>
      req<{ ok: boolean }>(`/ims/${slot}/clear-session`, { method: "POST" }),
  },
  feed: {
    channels: () =>
      req<{
        channels: Array<{
          id: number;
          ok: boolean;
          title?: string;
          username?: string | null;
          type?: string;
          members?: number | null;
          error?: string | null;
        }>;
        raw: string;
        total_otps: number;
      }>("/feed/channels"),
  },
};

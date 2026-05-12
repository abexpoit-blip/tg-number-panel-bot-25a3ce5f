import { useEffect, useState } from "react";
import { Users, UserPlus, Phone, Radio, Inbox, Wallet, DollarSign, Loader2, TrendingUp, Activity } from "lucide-react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Area, AreaChart } from "recharts";
import { api, token as authToken } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";

interface Stats {
  users?: number;
  users_24h?: number;
  numbers_available?: number;
  numbers_total?: number;
  otp_24h?: number;
  otp_total?: number;
  pending_withdrawals?: number;
  paid_total?: number;
}

interface ChartData {
  hourly: { hour: string; count: number }[];
  daily: { day: string; count: number }[];
  top_services: { name: string; emoji: string; count: number }[];
}

interface RangeStat {
  country_id: number;
  country_name: string;
  country_flag: string;
  country_code: string;
  range_id: number | null;
  range_name: string | null;
  label: string;
  total: number;
  assigned: number;
  available: number;
}

const STATS = [
  { key: "users", label: "Total users", icon: Users, accent: "from-primary to-primary-glow", glow: "shadow-glow" },
  { key: "numbers", label: "Numbers in pool", icon: Phone, accent: "from-primary to-accent", glow: "" },
  { key: "otp_24h", label: "OTPs (24h)", icon: Radio, accent: "from-accent to-accent-glow", glow: "shadow-glow-accent" },
  { key: "otp_total", label: "OTPs total", icon: Inbox, accent: "from-primary-glow to-accent", glow: "" },
  { key: "users_24h", label: "New users (24h)", icon: UserPlus, accent: "from-tertiary to-primary", glow: "" },
  { key: "pending_withdrawals", label: "Pending payouts", icon: Wallet, accent: "from-warning to-destructive", glow: "" },
  { key: "paid_total", label: "Paid out total", icon: DollarSign, accent: "from-success to-tertiary", glow: "" },
] as const;

// Mini API helper for the charts endpoint (not in api.ts)
async function fetchCharts(): Promise<ChartData | null> {
  try {
    const t = authToken();
    const r = await fetch(((import.meta.env.VITE_API_BASE as string) || "/api") + "/dashboard/charts", {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export default function Dashboard() {
  const [s, setS] = useState<Stats | null>(null);
  const [charts, setCharts] = useState<ChartData | null>(null);

  useEffect(() => {
    const load = () => {
      api.dashboard().then(setS).catch(() => setS({}));
      fetchCharts().then(setCharts);
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const value = (k: string) => {
    if (!s) return "—";
    if (k === "numbers") return `${s.numbers_available ?? 0}/${s.numbers_total ?? 0}`;
    if (k === "paid_total") return `৳${Number(s.paid_total ?? 0).toFixed(2)}`;
    return String((s as any)[k] ?? 0);
  };

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Real-time operational overview · Auto-refreshes every 15s"
        actions={
          <div className="flex items-center gap-2 rounded-full border border-border bg-card/60 px-3.5 py-1.5 text-xs text-muted-foreground backdrop-blur">
            <span className="live-dot" /> <span className="ml-2">Live</span>
          </div>
        }
      />

      {!s ? (
        <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
            {STATS.map(({ key, label, icon: Icon, accent, glow }, i) => (
              <div
                key={key}
                className="stat-card animate-fade-in-up"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <div className={`absolute -right-10 -top-10 h-32 w-32 rounded-full bg-gradient-to-br ${accent} opacity-20 blur-3xl transition-opacity group-hover:opacity-40`} />
                <div className="relative flex items-start justify-between">
                  <div>
                    <div className="label">{label}</div>
                    <div className="value">{value(key)}</div>
                  </div>
                  <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${accent} text-primary-foreground ${glow}`}>
                    <Icon className="h-4 w-4" strokeWidth={2.5} />
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Charts row */}
          <div className="grid gap-4 lg:grid-cols-3 mb-4">
            {/* Hourly area chart — spans 2 */}
            <div className="glass-card p-5 lg:col-span-2 animate-fade-in-up" style={{ animationDelay: "420ms" }}>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h3 className="font-display text-base font-semibold flex items-center gap-2">
                    <Activity className="h-4 w-4 text-primary" />
                    OTP traffic · last 24h
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">Hourly delivered OTPs</p>
                </div>
                <div className="text-2xl font-display font-bold text-gradient-primary tabular-nums">{s.otp_24h ?? 0}</div>
              </div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={charts?.hourly || []}>
                    <defs>
                      <linearGradient id="otp-area" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="hour" stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} interval={2} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(var(--card))",
                        border: "1px solid hsl(var(--border))",
                        borderRadius: "0.75rem",
                        boxShadow: "0 10px 30px -10px hsl(0 0% 0% / 0.5)",
                      }}
                      labelStyle={{ color: "hsl(var(--muted-foreground))", fontSize: "11px" }}
                      itemStyle={{ color: "hsl(var(--primary))", fontWeight: 600 }}
                    />
                    <Area type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={2} fill="url(#otp-area)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Top services */}
            <div className="glass-card p-5 animate-fade-in-up" style={{ animationDelay: "480ms" }}>
              <div className="mb-4">
                <h3 className="font-display text-base font-semibold flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-accent" />
                  Top services · 7d
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">By OTPs delivered</p>
              </div>
              <div className="space-y-3">
                {(charts?.top_services || []).length === 0 && (
                  <div className="text-xs text-muted-foreground py-8 text-center">No data yet</div>
                )}
                {(charts?.top_services || []).map((svc, i) => {
                  const max = Math.max(...(charts?.top_services || []).map((x) => x.count), 1);
                  const pct = (svc.count / max) * 100;
                  return (
                    <div key={i}>
                      <div className="flex justify-between text-xs mb-1.5">
                        <span className="font-medium">{svc.emoji} {svc.name}</span>
                        <span className="font-mono text-muted-foreground tabular-nums">{svc.count}</span>
                      </div>
                      <div className="h-1.5 bg-muted/50 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-primary to-accent rounded-full transition-all duration-700"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Daily bar chart */}
          <div className="glass-card p-5 animate-fade-in-up" style={{ animationDelay: "540ms" }}>
            <div className="mb-4">
              <h3 className="font-display text-base font-semibold">Daily volume · last 7 days</h3>
              <p className="text-xs text-muted-foreground mt-0.5">Daily OTP count</p>
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={charts?.daily || []}>
                  <defs>
                    <linearGradient id="bar-grad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="hsl(var(--accent))" />
                      <stop offset="100%" stopColor="hsl(var(--primary))" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--primary) / 0.05)" }}
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "0.75rem",
                    }}
                  />
                  <Bar dataKey="count" fill="url(#bar-grad)" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </>
  );
}

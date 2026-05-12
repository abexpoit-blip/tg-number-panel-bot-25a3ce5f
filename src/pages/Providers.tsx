import { useEffect, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  KeyRound,
  Loader2,
  Pencil,
  Plug,
  PowerOff,
  RefreshCw,
  Trash2,
  XCircle,
  Zap,
} from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";

type ImsStatus = {
  state?: string;
  logged_in?: boolean;
  interval?: number;
  rl_streak?: number;
  next_allowed_at?: number | null;
  last_success_at?: number | null;
  last_error?: string | null;
  consecutive_failures?: number;
  last_rows_seen?: number;
  last_otp_phone?: string;
  last_otp_at?: number | null;
  updated_at?: number;
  cooldown?: number;
};

type ImsAccount = {
  slot: string;
  prefix: string;
  enabled: boolean;
  base_url: string;
  username: string;
  has_password: boolean;
  otp_interval: number;
  has_session_cookie: boolean;
  has_cookie_header: boolean;
  status?: ImsStatus | null;
};

type Slot = "1" | "2";

const STATE_STYLE: Record<string, { label: string; cls: string }> = {
  disabled: { label: "Disabled", cls: "text-muted-foreground" },
  idle: { label: "Idle (waiting)", cls: "text-sky-400" },
  polling: { label: "Polling…", cls: "text-emerald-400" },
  login: { label: "Logging in…", cls: "text-amber-400" },
  rate_limited: { label: "Rate-limited", cls: "text-amber-400" },
  error: { label: "Error", cls: "text-rose-400" },
};

const fmtAgo = (ts?: number | null) => {
  if (!ts) return "—";
  const s = Math.max(0, Math.floor(Date.now() / 1000) - ts);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
};

const fmtIn = (ts?: number | null) => {
  if (!ts) return "—";
  const s = ts - Math.floor(Date.now() / 1000);
  if (s <= 0) return "now";
  if (s < 60) return `in ${s}s`;
  return `in ${Math.floor(s / 60)}m`;
};

export default function Providers() {
  const [rows, setRows] = useState<ImsAccount[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<ImsAccount | null>(null);
  const [, force] = useState(0);
  const tickRef = useRef<number | null>(null);

  const load = () =>
    api.ims.accounts().then(setRows).catch((e) => toast.error(e.message));

  useEffect(() => {
    load();
    const id = window.setInterval(load, 5000);
    // also re-render every second so "ago" timers stay live
    tickRef.current = window.setInterval(() => force((n) => n + 1), 1000) as unknown as number;
    return () => {
      window.clearInterval(id);
      if (tickRef.current) window.clearInterval(tickRef.current);
    };
  }, []);

  const withBusy = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try { await fn(); }
    finally { setBusy(null); }
  };

  const toggle = (a: ImsAccount) =>
    withBusy(`tg-${a.slot}`, async () => {
      try {
        await api.ims.toggle(a.slot as Slot, !a.enabled);
        toast.success(`IMS #${a.slot} ${!a.enabled ? "enabled" : "disabled"}`);
        await load();
      } catch (e: any) { toast.error(e.message); }
    });

  const test = (slot: Slot) =>
    withBusy(`test-${slot}`, async () => {
      try {
        const r = await api.ims.test(slot);
        toast.success(`IMS #${slot} OK — ${r.rows_seen} CDR rows fetched`);
        await load();
      } catch (e: any) { toast.error(`IMS #${slot}: ${e.message}`); }
    });

  const relogin = (slot: Slot) =>
    withBusy(`rl-${slot}`, async () => {
      try { await api.ims.relogin(slot); toast.success("Worker will relogin on next tick"); }
      catch (e: any) { toast.error(e.message); }
    });

  const clearSession = (slot: Slot) =>
    withBusy(`cs-${slot}`, async () => {
      try { await api.ims.clearSession(slot); toast.success("Session cleared"); await load(); }
      catch (e: any) { toast.error(e.message); }
    });

  return (
    <>
      <PageHeader
        title="IMS Accounts"
        subtitle="Two parallel imssms.org scrapers — full control + live monitoring"
      />

      <div className="grid gap-4 md:grid-cols-2">
        {rows.map((a) => {
          const st = a.status || {};
          const style = STATE_STYLE[st.state || (a.enabled ? "idle" : "disabled")] || STATE_STYLE.idle;
          return (
            <div key={a.slot} className="glass-card p-5 space-y-4">
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-primary shadow-glow">
                    <Plug className="h-5 w-5 text-primary-foreground" />
                  </div>
                  <div>
                    <div className="font-semibold">IMS Account #{a.slot}</div>
                    <div className="text-xs text-muted-foreground">
                      prefix: <span className="code-pill">{a.prefix}_*</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={a.enabled}
                    disabled={busy === `tg-${a.slot}`}
                    onCheckedChange={() => toggle(a)}
                  />
                  <span className={`text-xs font-medium ${a.enabled ? "text-emerald-400" : "text-muted-foreground"}`}>
                    {a.enabled ? "ON" : "OFF"}
                  </span>
                </div>
              </div>

              {/* Live status bar */}
              <div className="rounded-xl border border-border/40 bg-card/40 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity className={`h-4 w-4 ${style.cls}`} />
                    <span className={`text-sm font-medium ${style.cls}`}>{style.label}</span>
                    {st.logged_in ? (
                      <span className="ml-2 inline-flex items-center gap-1 text-[11px] text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" /> session live
                      </span>
                    ) : a.enabled ? (
                      <span className="ml-2 inline-flex items-center gap-1 text-[11px] text-amber-400">
                        <XCircle className="h-3 w-3" /> not logged in
                      </span>
                    ) : null}
                  </div>
                  <span className="text-[10px] text-muted-foreground">
                    upd {fmtAgo(st.updated_at)}
                  </span>
                </div>

                <div className="mt-2 grid grid-cols-3 gap-2 text-[11px] text-muted-foreground">
                  <Stat label="Last OK" value={fmtAgo(st.last_success_at)} />
                  <Stat label="Next poll" value={fmtIn(st.next_allowed_at)} />
                  <Stat label="Rows last tick" value={String(st.last_rows_seen ?? 0)} />
                  <Stat label="RL streak" value={String(st.rl_streak ?? 0)} tone={st.rl_streak ? "warn" : ""} />
                  <Stat label="Failures" value={String(st.consecutive_failures ?? 0)} tone={st.consecutive_failures ? "warn" : ""} />
                  <Stat label="Last OTP" value={st.last_otp_phone ? `+${st.last_otp_phone}` : "—"} />
                </div>

                {st.last_error && (
                  <div className="mt-2 truncate rounded bg-rose-500/10 px-2 py-1 text-[11px] text-rose-300">
                    {st.last_error}
                  </div>
                )}
              </div>

              {/* Config readout */}
              <div className="grid grid-cols-2 gap-2 text-sm">
                <Field label="Base URL" value={a.base_url} />
                <Field label="Username" value={a.username || "—"} />
                <Field label="Password" value={a.has_password ? "•••••" : "(unset)"} />
                <Field label="Interval" value={`${a.otp_interval}s (min 16)`} />
                <Field
                  label="Saved PHPSESSID"
                  value={a.has_session_cookie
                    ? <CheckCircle2 className="inline h-4 w-4 text-emerald-400" />
                    : <XCircle className="inline h-4 w-4 text-muted-foreground" />}
                />
                <Field
                  label="Manual Cookie"
                  value={a.has_cookie_header
                    ? <CheckCircle2 className="inline h-4 w-4 text-emerald-400" />
                    : <XCircle className="inline h-4 w-4 text-muted-foreground" />}
                />
              </div>

              {/* Action toolbar */}
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" onClick={() => test(a.slot as Slot)} disabled={busy !== null}
                        className="bg-gradient-primary text-primary-foreground">
                  {busy === `test-${a.slot}`
                    ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                  Test
                </Button>
                <Button size="sm" variant="secondary" onClick={() => relogin(a.slot as Slot)} disabled={busy !== null}>
                  {busy === `rl-${a.slot}` ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <KeyRound className="mr-1 h-3.5 w-3.5" />}
                  Re-login
                </Button>
                <Button size="sm" variant="secondary" onClick={() => clearSession(a.slot as Slot)} disabled={busy !== null}>
                  {busy === `cs-${a.slot}` ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1 h-3.5 w-3.5" />}
                  Clear session
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(a)} disabled={busy !== null}>
                  <Pencil className="mr-1 h-3.5 w-3.5" /> Edit
                </Button>
                {a.enabled && (
                  <Button size="sm" variant="ghost" className="text-rose-400 hover:text-rose-300"
                          onClick={() => toggle(a)} disabled={busy !== null}>
                    <PowerOff className="mr-1 h-3.5 w-3.5" /> Stop
                  </Button>
                )}
              </div>
            </div>
          );
        })}
        {rows.length === 0 && <div className="text-muted-foreground">Loading accounts…</div>}
      </div>

      <div className="glass-card mt-4 flex items-start gap-3 p-4 text-sm text-muted-foreground">
        <Zap className="mt-0.5 h-4 w-4 text-primary" />
        <div>
          IMS hard-rate-limits to one CDR refresh every ~15s. The interval floor is
          enforced at <span className="code-pill">16s</span>. Worker auto-publishes
          live status every tick — this panel auto-refreshes every 5s.
        </div>
      </div>

      <EditDialog
        account={editing}
        onClose={() => setEditing(null)}
        onSaved={async () => { setEditing(null); await load(); }}
      />
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-md bg-background/40 px-2 py-1">
      <div className="text-[9px] uppercase tracking-wider opacity-70">{label}</div>
      <div className={`font-mono text-[11px] ${tone === "warn" ? "text-amber-400" : "text-foreground"}`}>{value}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/40 bg-card/40 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="truncate font-mono text-xs">{value}</div>
    </div>
  );
}

function EditDialog({
  account, onClose, onSaved,
}: { account: ImsAccount | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (account) {
      setForm({
        base_url: account.base_url || "https://www.imssms.org",
        username: account.username || "",
        password: "",
        otp_interval: String(account.otp_interval || 18),
        cookie_header: "",
        session_cookie: "",
      });
    }
  }, [account]);

  if (!account) return null;

  const save = async () => {
    setSaving(true);
    try {
      const payload: Record<string, any> = {
        base_url: form.base_url,
        username: form.username,
        otp_interval: Number(form.otp_interval) || 18,
      };
      if (form.password) payload.password = form.password;
      if (form.cookie_header) payload.cookie_header = form.cookie_header;
      if (form.session_cookie) payload.session_cookie = form.session_cookie;
      await api.ims.updateConfig(account.slot as Slot, payload);
      toast.success("IMS config saved");
      onSaved();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={!!account} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit IMS Account #{account.slot}</DialogTitle>
          <DialogDescription>
            Updates apply on the worker's next tick. Leave password blank to keep current.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <Row label="Base URL">
            <Input value={form.base_url || ""} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
          </Row>
          <Row label="Username">
            <Input value={form.username || ""} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </Row>
          <Row label="Password">
            <Input type="password" placeholder={account.has_password ? "•••• (unchanged)" : ""}
                   value={form.password || ""} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Row>
          <Row label="Poll interval (sec, min 16)">
            <Input type="number" min={16} value={form.otp_interval || ""}
                   onChange={(e) => setForm({ ...form, otp_interval: e.target.value })} />
          </Row>
          <Row label="Manual Cookie header (optional)">
            <Input placeholder="PHPSESSID=...; Path=/" value={form.cookie_header || ""}
                   onChange={(e) => setForm({ ...form, cookie_header: e.target.value })} />
          </Row>
          <Row label="Override saved PHPSESSID (optional)">
            <Input placeholder="PHPSESSID=..." value={form.session_cookie || ""}
                   onChange={(e) => setForm({ ...form, session_cookie: e.target.value })} />
          </Row>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving} className="bg-gradient-primary text-primary-foreground">
            {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

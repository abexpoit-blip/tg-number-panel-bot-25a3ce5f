import { useEffect, useState } from "react";
import { Plug, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

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
};

export default function Providers() {
  const [rows, setRows] = useState<ImsAccount[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () =>
    api.ims.accounts().then(setRows).catch((e) => toast.error(e.message));
  useEffect(() => {
    load();
  }, []);

  const test = async (slot: "1" | "2") => {
    setBusy(slot);
    try {
      const r = await api.ims.test(slot);
      toast.success(`IMS #${slot} OK — ${r.rows_seen} CDR rows fetched`);
      await load();
    } catch (e: any) {
      toast.error(`IMS #${slot} failed: ${e.message}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="IMS Accounts"
        subtitle="Two parallel imssms.org scrapers — credentials live in Settings (ims_* / ims2_*)"
      />

      <div className="grid gap-4 md:grid-cols-2">
        {rows.map((a) => (
          <div key={a.slot} className="glass-card p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-primary shadow-glow">
                  <Plug className="h-5 w-5 text-primary-foreground" />
                </div>
                <div>
                  <div className="font-semibold">IMS Account #{a.slot}</div>
                  <div className="text-xs text-muted-foreground">prefix: <span className="code-pill">{a.prefix}_*</span></div>
                </div>
              </div>
              <div className={`text-xs font-medium ${a.enabled ? "text-emerald-400" : "text-muted-foreground"}`}>
                {a.enabled ? "● Enabled" : "○ Disabled"}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm">
              <Field label="Base URL" value={a.base_url} />
              <Field label="Username" value={a.username || "—"} />
              <Field label="Password" value={a.has_password ? "•••••" : "(unset)"} />
              <Field label="Interval" value={`${a.otp_interval}s (min 16)`} />
              <Field
                label="Saved PHPSESSID"
                value={a.has_session_cookie ? <CheckCircle2 className="inline h-4 w-4 text-emerald-400" /> : <XCircle className="inline h-4 w-4 text-muted-foreground" />}
              />
              <Field
                label="Manual Cookie"
                value={a.has_cookie_header ? <CheckCircle2 className="inline h-4 w-4 text-emerald-400" /> : <XCircle className="inline h-4 w-4 text-muted-foreground" />}
              />
            </div>

            <div className="flex gap-2 pt-2">
              <Button
                size="sm"
                onClick={() => test(a.slot as "1" | "2")}
                disabled={busy !== null}
                className="bg-gradient-primary text-primary-foreground"
              >
                <RefreshCw className={`mr-1 h-3.5 w-3.5 ${busy === a.slot ? "animate-spin" : ""}`} />
                Test login + fetch
              </Button>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <div className="text-muted-foreground">Loading accounts…</div>
        )}
      </div>

      <div className="glass-card mt-4 p-4 text-sm text-muted-foreground">
        Edit credentials and toggle <span className="code-pill">ims_enabled</span> /{" "}
        <span className="code-pill">ims2_enabled</span> in the{" "}
        <a className="text-primary underline" href="/settings">Settings</a> page.
        IMS hard-rate-limits to one CDR refresh every ~15s — don't drop the
        interval below 16.
      </div>
    </>
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

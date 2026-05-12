import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import EmojiIdField from "@/components/EmojiIdField";
import { toast } from "sonner";

const LABELS: Record<string, string> = {
  reward_enabled: "Pay rewards per OTP",
  reward_per_otp: "Reward amount per OTP (BDT)",
  min_withdraw: "Minimum withdrawal (BDT)",
  ref_bonus_pct: "Referral bonus %",
  bot_panel_url: "Bot panel URL (Bot Pnl button)",
  support_url: "Support URL (All Support button)",
  welcome_text: "Welcome message text",
  reserve_minutes: "Number reservation timeout (minutes)",
  // OTP delivery — premium look (matches IMS Panel reference)
  main_channel_url: "Main Channel button URL",
  number_channel_url: "Number Channel button URL",
  main_channel_emoji_id: "Main Channel button — premium emoji ID",
  number_channel_emoji_id: "Number Channel button — premium emoji ID",
  otp_button_emoji_id: "OTP code button — premium emoji ID",
  // IMS account #1 (imssms.org)
  ims_enabled: "IMS #1 — Enabled",
  ims_base_url: "IMS #1 — Base URL",
  ims_username: "IMS #1 — Username",
  ims_password: "IMS #1 — Password",
  ims_otp_interval: "IMS #1 — Poll interval (sec, min 16)",
  ims_session_cookie: "IMS #1 — Saved PHPSESSID (auto)",
  ims_cookie_header: "IMS #1 — Manual Cookie header (optional)",
  // IMS account #2
  ims2_enabled: "IMS #2 — Enabled",
  ims2_base_url: "IMS #2 — Base URL",
  ims2_username: "IMS #2 — Username",
  ims2_password: "IMS #2 — Password",
  ims2_otp_interval: "IMS #2 — Poll interval (sec, min 16)",
  ims2_session_cookie: "IMS #2 — Saved PHPSESSID (auto)",
  ims2_cookie_header: "IMS #2 — Manual Cookie header (optional)",
};

// Always-visible keys (so admin can configure even if empty in DB)
const ALWAYS_KEYS = [
  "reward_enabled",
  "reward_per_otp",
  "main_channel_url",
  "number_channel_url",
  "main_channel_emoji_id",
  "number_channel_emoji_id",
  "otp_button_emoji_id",
  // IMS #1
  "ims_enabled", "ims_base_url", "ims_username", "ims_password",
  "ims_otp_interval", "ims_session_cookie", "ims_cookie_header",
  // IMS #2
  "ims2_enabled", "ims2_base_url", "ims2_username", "ims2_password",
  "ims2_otp_interval", "ims2_session_cookie", "ims2_cookie_header",
];

export default function Settings() {
  const [s, setS] = useState<Record<string, any>>({});
  useEffect(() => {
    api.settings.list().then((data) => {
      const merged = { ...data };
      for (const k of ALWAYS_KEYS) if (!(k in merged)) merged[k] = "";
      setS(merged);
    }).catch((e) => toast.error(e.message));
  }, []);

  const save = async (k: string) => {
    try { await api.settings.set(k, s[k]); toast.success(`Saved: ${k}`); }
    catch (e: any) { toast.error(e.message); }
  };

  const renderInput = (k: string) => {
    const v = s[k];
    if (typeof v === "boolean")
      return (
        <div className="flex items-center gap-3">
          <Switch checked={v} onCheckedChange={(c) => setS({ ...s, [k]: c })} />
          <span className="text-sm text-muted-foreground">{v ? "Enabled" : "Disabled"}</span>
        </div>
      );
    if (typeof v === "number")
      return <Input type="number" step="0.01" value={v} onChange={(e) => setS({ ...s, [k]: Number(e.target.value) })} />;
    if (k.endsWith("_emoji_id"))
      return (
        <EmojiIdField
          value={String(v ?? "")}
          onChange={(nv) => setS({ ...s, [k]: nv })}
          className="h-9 w-full font-mono text-xs"
          placeholder="paste numeric custom_emoji_id"
        />
      );
    return <Input value={v ?? ""} onChange={(e) => setS({ ...s, [k]: e.target.value })} />;
  };

  // Hide reward keys from generic grid — rendered in dedicated card below
  const hidden = new Set(["reward_enabled", "reward_per_otp"]);

  return (
    <>
      <PageHeader title="Settings" subtitle="All values are live — bot reads them from DB on every action" />

      <RewardsCard s={s} setS={setS} />

      <div className="grid gap-4 md:grid-cols-2">
        {Object.keys(s).filter((k) => !hidden.has(k)).map((k) => (
          <div key={k} className="glass-card p-5">
            <div className="mb-3 text-sm font-medium text-foreground">{LABELS[k] || k}</div>
            <div className="flex items-center gap-3">
              <div className="flex-1">{renderInput(k)}</div>
              <Button size="sm" onClick={() => save(k)} className="bg-gradient-primary text-primary-foreground">
                <Save className="mr-1 h-3.5 w-3.5" /> Save
              </Button>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">key: <span className="code-pill">{k}</span></div>
          </div>
        ))}
        {Object.keys(s).length === 0 && (
          <div className="text-muted-foreground">No settings loaded.</div>
        )}
      </div>
    </>
  );
}

function RewardsCard({ s, setS }: { s: Record<string, any>; setS: (v: Record<string, any>) => void }) {
  const enabledRaw = s.reward_enabled;
  const enabled = enabledRaw === true || String(enabledRaw ?? "").toLowerCase() === "true";
  const amountStr = String(s.reward_per_otp ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Accept up to 4 fractional digits (BDT typically 2, but allow precision).
  const validate = (raw: string): { ok: boolean; value?: number; error?: string } => {
    const v = raw.trim();
    if (!v) return { ok: false, error: "Amount is required" };
    if (!/^\d+(\.\d{1,4})?$/.test(v)) return { ok: false, error: "Use a decimal like 0.40 (max 4 decimals)" };
    const n = Number(v);
    if (!Number.isFinite(n) || n < 0) return { ok: false, error: "Amount must be ≥ 0" };
    if (n > 1000) return { ok: false, error: "Amount looks too high (>1000 BDT per OTP)" };
    return { ok: true, value: n };
  };

  const saveAll = async () => {
    const v = validate(amountStr);
    if (!v.ok) { setError(v.error!); toast.error(v.error!); return; }
    setError(null);
    setSaving(true);
    try {
      await api.settings.set("reward_enabled", enabled ? "true" : "false");
      await api.settings.set("reward_per_otp", v.value!.toFixed(2));
      toast.success(`Rewards saved — ৳${v.value!.toFixed(2)} BDT per successful OTP (${enabled ? "ON" : "OFF"})`);
    } catch (e: any) {
      toast.error(e.message || "Failed to save rewards");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-6 glass-card p-5 border border-primary/30">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-base">💰</span>
        <h3 className="font-display text-base font-semibold">OTP Reward (BDT)</h3>
      </div>
      <p className="mb-4 text-xs text-muted-foreground">
        Each successful IMS OTP delivered to a user credits this amount to their balance automatically.
      </p>

      <div className="grid gap-4 sm:grid-cols-[auto_1fr_auto] sm:items-end">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">Enabled</div>
          <div className="flex items-center gap-2 h-9">
            <Switch checked={enabled} onCheckedChange={(c) => setS({ ...s, reward_enabled: c ? "true" : "false" })} />
            <span className={`text-xs font-medium ${enabled ? "text-emerald-400" : "text-muted-foreground"}`}>
              {enabled ? "ON" : "OFF"}
            </span>
          </div>
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-muted-foreground">Reward per OTP (BDT)</div>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">৳</span>
            <Input
              inputMode="decimal"
              placeholder="0.40"
              className={`pl-7 font-mono ${error ? "border-destructive focus-visible:ring-destructive" : ""}`}
              value={amountStr}
              onChange={(e) => { setS({ ...s, reward_per_otp: e.target.value }); setError(null); }}
              onBlur={() => { const v = validate(amountStr); setError(v.ok ? null : v.error!); }}
            />
          </div>
          {error
            ? <div className="mt-1 text-xs text-destructive">{error}</div>
            : <div className="mt-1 text-xs text-muted-foreground">Default <span className="code-pill">0.40</span> · max 4 decimals</div>}
        </div>
        <Button onClick={saveAll} disabled={saving} className="h-9 bg-gradient-primary text-primary-foreground">
          <Save className="mr-1 h-3.5 w-3.5" /> {saving ? "Saving…" : "Save rewards"}
        </Button>
      </div>
    </div>
  );
}

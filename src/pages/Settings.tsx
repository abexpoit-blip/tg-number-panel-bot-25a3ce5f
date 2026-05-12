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

  return (
    <>
      <PageHeader title="Settings" subtitle="All values are live — bot reads them from DB on every action" />

      <div className="grid gap-4 md:grid-cols-2">
        {Object.keys(s).map((k) => (
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

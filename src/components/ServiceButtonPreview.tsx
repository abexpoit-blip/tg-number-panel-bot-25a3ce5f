/**
 * Renders a service icon + name exactly as it will appear inside a Telegram
 * inline-keyboard button. Telegram never renders premium <tg-emoji> entities
 * inside buttons, so we mirror that limitation: only plain unicode is shown.
 *
 * The preview is purely visual — it does not call the bot.
 */

const BRAND_EMOJI: Record<string, string> = {
  whatsapp: "🟢", wa: "🟢",
  facebook: "🔵", fb: "🔵",
  instagram: "🟣", ig: "🟣",
  telegram: "✈️", tg: "✈️",
  tiktok: "🎵", tt: "🎵",
  twitter: "🐦", x: "🐦",
  google: "🔴", gmail: "📧",
  discord: "💬", signal: "📞",
  viber: "🟪", wechat: "💚", line: "💚",
  snapchat: "👻", youtube: "📺",
};

export type IconMode = "auto" | "custom" | "brand" | "default";

export function brandEmojiFor(input: { keyword?: string | null; name?: string | null }): string | null {
  const key = `${input.keyword ?? ""} ${input.name ?? ""}`.toLowerCase();
  for (const k of Object.keys(BRAND_EMOJI)) {
    if (key.includes(k)) return BRAND_EMOJI[k];
  }
  return null;
}

export function resolveButtonEmoji(s: { emoji?: string | null; keyword?: string | null; name?: string | null; icon_mode?: string | null }): string {
  const mode = ((s.icon_mode ?? "auto") as IconMode);
  const raw = (s.emoji ?? "").trim();
  const brand = brandEmojiFor(s);
  if (mode === "custom") return raw || "📱";
  if (mode === "brand") return brand || raw || "📱";
  if (mode === "default") return "📱";
  if (raw && raw !== "📱") return raw;
  return brand || "📱";
}

interface Props {
  service: { name?: string | null; emoji?: string | null; keyword?: string | null; icon_mode?: string | null };
  className?: string;
}

/** Telegram-style inline button preview. */
export default function ServiceButtonPreview({ service, className = "" }: Props) {
  const emo = resolveButtonEmoji(service);
  return (
    <div
      className={`inline-flex min-w-[180px] items-center justify-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-sm font-medium text-emerald-100 shadow-sm ${className}`}
      title="Live preview of the inline button as it appears in Telegram"
    >
      <span className="text-base leading-none">{emo}</span>
      <span className="truncate">{service.name || "Service"}</span>
    </div>
  );
}

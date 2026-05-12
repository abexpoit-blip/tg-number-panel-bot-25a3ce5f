import { useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import EmojiIdField from "@/components/EmojiIdField";
import ServiceBadge from "@/components/ServiceBadge";
import ServiceButtonPreview, { brandEmojiFor, type IconMode } from "@/components/ServiceButtonPreview";
import { toast } from "sonner";

interface Service { id: number; code?: string; keyword?: string; name: string; emoji: string; custom_emoji_id?: string | null; icon_mode?: IconMode; enabled: boolean; sort_order: number }

export default function Services() {
  const [list, setList] = useState<Service[]>([]);
  const [draft, setDraft] = useState({ code: "", name: "", emoji: "📱", custom_emoji_id: "", icon_mode: "auto" as IconMode, enabled: true, sort_order: 0 });

  const load = () => api.services.list().then(setList).catch((e) => toast.error(e.message));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!draft.code || !draft.name) return toast.error("Code and name required");
    try { await api.services.create(draft); setDraft({ code: "", name: "", emoji: "📱", custom_emoji_id: "", enabled: true, sort_order: 0 }); load(); toast.success("Service added"); }
    catch (e: any) { toast.error(e.message); }
  };
  const save = async (s: Service) => {
    if (s.enabled && !s.custom_emoji_id) {
      if (!confirm(`"${s.name}" is enabled but has no premium emoji ID — users will see plain unicode (${s.emoji}) only. Save anyway?`)) return;
    }
    try { await api.services.update(s.id, s); toast.success("Saved"); load(); } catch (e: any) { toast.error(e.message); }
  };
  const del = async (id: number) => { if (!confirm("Delete service?")) return; try { await api.services.remove(id); toast.success("Deleted"); load(); } catch (e: any) { toast.error(e.message); } };
  const patch = (id: number, k: keyof Service, v: any) => setList(list.map((x) => x.id === id ? { ...x, [k]: v } : x));

  return (
    <>
      <PageHeader title="Services" subtitle="WhatsApp, Facebook, Instagram, Telegram…" />

      <div className="glass-card mb-6 p-5">
        <div className="grid gap-3 sm:grid-cols-[100px_1fr_120px_180px_80px_auto_auto]">
          <Input placeholder="code" value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} />
          <Input placeholder="name" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <Input placeholder="🟢 button icon" title="Unicode emoji shown on the inline button" value={draft.emoji} onChange={(e) => setDraft({ ...draft, emoji: e.target.value })} />
          <EmojiIdField value={draft.custom_emoji_id} onChange={(v) => setDraft({ ...draft, custom_emoji_id: v })} className="h-9 w-full font-mono text-xs" placeholder="premium emoji ID (msg text)" />
          <Input type="number" placeholder="sort" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: +e.target.value })} />
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Switch checked={draft.enabled} onCheckedChange={(v) => setDraft({ ...draft, enabled: v })} /> enabled
          </label>
          <Button onClick={create} className="bg-gradient-primary text-primary-foreground"><Plus className="mr-1 h-4 w-4" /> Add</Button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          🔘 <b>Button Icon</b>: a plain unicode emoji (🟢 🔵 🟣 ✈️ 🎵 …) shown on the inline service button. Telegram does <em>not</em> render premium emojis inside buttons.<br />
          💎 <b>Premium emoji ID</b>: forward the emoji from <a className="underline" href="https://t.me/addemoji/ApplicationEmoji" target="_blank" rel="noreferrer">ApplicationEmoji</a> to <code>@RawDataBot</code>, copy <code>custom_emoji_id</code>, paste here. Used in message text via <code>&lt;tg-emoji&gt;</code>.
        </p>
      </div>

      <div className="glass-card overflow-hidden p-0">
        <table className="data-table">
          <thead><tr><th>ID</th><th>Preview</th><th>Code</th><th>Name</th><th title="Unicode emoji on inline button">Button Icon</th><th title="Premium emoji rendered in message text">Premium ID</th><th>Sort</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {list.map((s) => (
              <tr key={s.id}>
                <td className="text-muted-foreground">#{s.id}</td>
                <td><ServiceBadge service={s} size="md" /></td>
                <td><Input value={s.code} onChange={(e) => patch(s.id, "code", e.target.value)} className="h-8 w-24" /></td>
                <td><Input value={s.name} onChange={(e) => patch(s.id, "name", e.target.value)} className="h-8 w-44" /></td>
                <td><Input value={s.emoji} onChange={(e) => patch(s.id, "emoji", e.target.value)} className="h-8 w-16" /></td>
                <td>
                  <EmojiIdField
                    value={s.custom_emoji_id ?? ""}
                    onChange={(v) => patch(s.id, "custom_emoji_id", v)}
                    showMissingWarning={s.enabled}
                  />
                </td>
                <td><Input type="number" value={s.sort_order} onChange={(e) => patch(s.id, "sort_order", +e.target.value)} className="h-8 w-20" /></td>
                <td><Switch checked={s.enabled} onCheckedChange={(v) => patch(s.id, "enabled", v)} /></td>
                <td className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="secondary" onClick={() => save(s)}><Save className="h-3.5 w-3.5" /></Button>
                    <Button size="sm" variant="destructive" onClick={() => del(s.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && (<tr><td colSpan={9} className="py-10 text-center text-muted-foreground">No services yet.</td></tr>)}
          </tbody>
        </table>
      </div>
    </>
  );
}

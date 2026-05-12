import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Save } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export default function Ranges() {
  const [countries, setCountries] = useState<any[]>([]);
  const [ranges, setRanges] = useState<any[]>([]);
  const [form, setForm] = useState({ country_id: 0, name: "", prefix: "", sort_order: 0, enabled: true });

  const load = () => api.ranges.list().then(setRanges).catch((e) => toast.error(e.message));
  useEffect(() => {
    api.countries.list().then(setCountries);
    load();
  }, []);

  const grouped = useMemo(() => {
    const g: Record<number, any[]> = {};
    for (const r of ranges) (g[r.country_id] ||= []).push(r);
    return g;
  }, [ranges]);

  const add = async () => {
    if (!form.country_id || !form.name.trim()) return toast.error("Pick a country and enter a name");
    try {
      await api.ranges.create(form);
      toast.success(`Range "${form.name}" added`);
      setForm({ ...form, name: "", prefix: "" });
      load();
    } catch (e: any) { toast.error(e.message); }
  };

  const save = async (r: any) => {
    try { await api.ranges.update(r.id, r); toast.success(`Saved "${r.name}"`); load(); }
    catch (e: any) { toast.error(e.message); }
  };

  const remove = async (r: any) => {
    if (!confirm(`Delete range "${r.name}"? Numbers in this range will lose the link (kept).`)) return;
    try { await api.ranges.remove(r.id); toast.success("Deleted"); load(); }
    catch (e: any) { toast.error(e.message); }
  };

  return (
    <>
      <PageHeader title="Country Ranges" subtitle="Sub-buckets per country (e.g. Peru 1, Peru 2). Bot shows them after the user picks a country." />

      <div className="mb-6 glass-card p-5">
        <h3 className="mb-3 font-display text-base font-semibold">Add range</h3>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_140px_120px_auto]">
          <Select value={String(form.country_id || "")} onValueChange={(v) => setForm({ ...form, country_id: +v })}>
            <SelectTrigger><SelectValue placeholder="Country" /></SelectTrigger>
            <SelectContent>{countries.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.flag} {c.name}</SelectItem>)}</SelectContent>
          </Select>
          <Input placeholder="Name (e.g. Peru 1)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Input placeholder="Prefix (e.g. 5198)" value={form.prefix} onChange={(e) => setForm({ ...form, prefix: e.target.value })} />
          <Input type="number" placeholder="Sort" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: +e.target.value || 0 })} />
          <Button onClick={add} className="bg-gradient-primary text-primary-foreground"><Plus className="mr-1 h-4 w-4" /> Add</Button>
        </div>
      </div>

      <div className="space-y-4">
        {countries.map((c) => {
          const list = grouped[c.id] || [];
          if (list.length === 0) return null;
          return (
            <div key={c.id} className="glass-card p-5">
              <div className="mb-3 flex items-center gap-2 font-display text-base font-semibold">
                <span className="text-xl">{c.flag}</span> {c.name} <span className="text-xs text-muted-foreground">({list.length})</span>
              </div>
              <div className="space-y-2">
                {list.map((r) => (
                  <div key={r.id} className="grid gap-2 rounded-lg border border-border/40 bg-card/40 p-3 sm:grid-cols-[1fr_140px_100px_auto_auto_auto]">
                    <Input value={r.name} onChange={(e) => setRanges(ranges.map((x) => x.id === r.id ? { ...x, name: e.target.value } : x))} />
                    <Input placeholder="prefix" value={r.prefix || ""} onChange={(e) => setRanges(ranges.map((x) => x.id === r.id ? { ...x, prefix: e.target.value } : x))} />
                    <Input type="number" value={r.sort_order || 0} onChange={(e) => setRanges(ranges.map((x) => x.id === r.id ? { ...x, sort_order: +e.target.value || 0 } : x))} />
                    <div className="flex items-center gap-2">
                      <Switch checked={!!r.enabled} onCheckedChange={(v) => setRanges(ranges.map((x) => x.id === r.id ? { ...x, enabled: v } : x))} />
                      <span className="text-xs text-muted-foreground">{r.enabled ? "On" : "Off"}</span>
                    </div>
                    <Button size="sm" onClick={() => save(r)} className="bg-gradient-primary text-primary-foreground"><Save className="mr-1 h-3.5 w-3.5" /> Save</Button>
                    <Button size="sm" variant="destructive" onClick={() => remove(r)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
        {ranges.length === 0 && <div className="text-muted-foreground">No ranges yet — add one above.</div>}
      </div>
    </>
  );
}

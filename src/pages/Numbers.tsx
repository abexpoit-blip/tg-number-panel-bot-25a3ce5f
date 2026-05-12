import { useEffect, useMemo, useState } from "react";
import { Plus, RotateCcw, Send, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ServiceBadge from "@/components/ServiceBadge";
import { toast } from "sonner";

const statusPill: Record<string, string> = {
  available: "pill-green",
  reserved: "pill-yellow",
  used: "pill-neutral",
  disabled: "pill-red",
};

export default function Numbers() {
  const [list, setList] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 100;
  const [services, setServices] = useState<any[]>([]);
  const [countries, setCountries] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [filter, setFilter] = useState<{ service_id?: number; country_id?: number; status?: string; prefix?: string }>({});
  const [single, setSingle] = useState({ msisdn: "", service_id: 0, country_id: 0, provider_id: 0, status: "available" });
  const [bulk, setBulk] = useState({ msisdns: "", service_id: 0, country_id: 0, provider_id: 0 });

  const load = () => api.numbers.list({ ...filter, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
    .then((r: any) => { setList(r.items || []); setTotal(r.total || 0); })
    .catch((e) => toast.error(e.message));
  useEffect(() => {
    api.services.list().then(setServices);
    api.countries.list().then(setCountries);
    api.providers.list().then(setProviders).catch(() => setProviders([]));
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [JSON.stringify(filter), page]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setPage(0); }, [JSON.stringify(filter)]);

  const addOne = async () => {
    if (!single.msisdn || !single.service_id || !single.country_id) return toast.error("Fill all fields");
    try { await api.numbers.create({ ...single, provider_id: single.provider_id || null }); setSingle({ ...single, msisdn: "" }); load(); toast.success("Number added"); }
    catch (e: any) { toast.error(e.message); }
  };
  const addBulk = async () => {
    if (!bulk.service_id || !bulk.country_id) return toast.error("Pick service + country");
    const arr = bulk.msisdns.split(/[\s,;]+/).filter(Boolean);
    if (!arr.length) return toast.error("Paste numbers");
    try {
      const r = await api.numbers.bulk({ msisdns: arr, service_id: bulk.service_id, country_id: bulk.country_id, provider_id: bulk.provider_id || null });
      toast.success(`Inserted ${r.inserted} of ${r.submitted}`);
      setBulk({ ...bulk, msisdns: "" }); load();
    } catch (e: any) { toast.error(e.message); }
  };

  const deleteRange = async () => {
    if (!filter.service_id && !filter.country_id && !filter.status && !filter.prefix) {
      return toast.error("Pick at least one filter (service/country/status/prefix) before deleting a range.");
    }
    const desc = [
      filter.service_id && `service=${services.find(s => s.id === filter.service_id)?.name}`,
      filter.country_id && `country=${countries.find(c => c.id === filter.country_id)?.name}`,
      filter.status && `status=${filter.status}`,
      filter.prefix && `prefix=${filter.prefix}`,
    ].filter(Boolean).join(", ");
    if (!confirm(`Delete ALL numbers matching: ${desc}?\nThis cannot be undone.`)) return;
    try {
      const r = await api.numbers.bulkDelete(filter);
      toast.success(`Deleted ${r.deleted} numbers`);
      setPage(0); load();
    } catch (e: any) { toast.error(e.message); }
  };

  const counts = useMemo(() => {
    const c = { available: 0, reserved: 0, used: 0, disabled: 0 } as Record<string, number>;
    list.forEach((n) => { c[n.status] = (c[n.status] || 0) + 1; });
    return c;
  }, [list]);

  return (
    <>
      <PageHeader title="Numbers" subtitle="Manually managed pool. Bot picks an available number when a user requests." />

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <div className="glass-card p-5">
          <h3 className="mb-3 font-display text-base font-semibold">Add single number</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            <Input placeholder="393406647354" value={single.msisdn} onChange={(e) => setSingle({ ...single, msisdn: e.target.value })} />
            <Select value={String(single.service_id)} onValueChange={(v) => setSingle({ ...single, service_id: +v })}>
              <SelectTrigger><SelectValue placeholder="Service" /></SelectTrigger>
              <SelectContent>{services.map((s) => <SelectItem key={s.id} value={String(s.id)}><ServiceBadge service={s} /></SelectItem>)}</SelectContent>
            </Select>
            <Select value={String(single.country_id)} onValueChange={(v) => setSingle({ ...single, country_id: +v })}>
              <SelectTrigger><SelectValue placeholder="Country" /></SelectTrigger>
              <SelectContent>{countries.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.flag} {c.name}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={String(single.provider_id)} onValueChange={(v) => setSingle({ ...single, provider_id: +v })}>
              <SelectTrigger><SelectValue placeholder="Provider (optional)" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="0">— No provider —</SelectItem>
                {providers.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name} ({p.currency})</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={addOne} className="mt-3 bg-gradient-primary text-primary-foreground"><Plus className="mr-1 h-4 w-4" /> Add</Button>
        </div>

        <div className="glass-card p-5">
          <h3 className="mb-3 font-display text-base font-semibold">Bulk add (one per line)</h3>
          <div className="grid grid-cols-3 gap-3">
            <Select value={String(bulk.service_id)} onValueChange={(v) => setBulk({ ...bulk, service_id: +v })}>
              <SelectTrigger><SelectValue placeholder="Service" /></SelectTrigger>
              <SelectContent>{services.map((s) => <SelectItem key={s.id} value={String(s.id)}><ServiceBadge service={s} /></SelectItem>)}</SelectContent>
            </Select>
            <Select value={String(bulk.country_id)} onValueChange={(v) => setBulk({ ...bulk, country_id: +v })}>
              <SelectTrigger><SelectValue placeholder="Country" /></SelectTrigger>
              <SelectContent>{countries.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.flag} {c.name}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={String(bulk.provider_id)} onValueChange={(v) => setBulk({ ...bulk, provider_id: +v })}>
              <SelectTrigger><SelectValue placeholder="Provider" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="0">— No provider —</SelectItem>
                {providers.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name} ({p.currency})</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Textarea rows={4} className="mt-3 font-mono text-xs" placeholder={"393406647354\n393925068153\n…"} value={bulk.msisdns} onChange={(e) => setBulk({ ...bulk, msisdns: e.target.value })} />
          <Button onClick={addBulk} className="mt-3 bg-gradient-primary text-primary-foreground"><Upload className="mr-1 h-4 w-4" /> Bulk insert</Button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <Select value={filter.service_id ? String(filter.service_id) : "all"} onValueChange={(v) => setFilter({ ...filter, service_id: v === "all" ? undefined : +v })}>
            <SelectTrigger className="w-44"><SelectValue placeholder="All services" /></SelectTrigger>
            <SelectContent><SelectItem value="all">All services</SelectItem>{services.map((s) => <SelectItem key={s.id} value={String(s.id)}><ServiceBadge service={s} /></SelectItem>)}</SelectContent>
          </Select>
          <Select value={filter.country_id ? String(filter.country_id) : "all"} onValueChange={(v) => setFilter({ ...filter, country_id: v === "all" ? undefined : +v })}>
            <SelectTrigger className="w-44"><SelectValue placeholder="All countries" /></SelectTrigger>
            <SelectContent><SelectItem value="all">All countries</SelectItem>{countries.map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.flag} {c.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={filter.status ?? "all"} onValueChange={(v) => setFilter({ ...filter, status: v === "all" ? undefined : v })}>
            <SelectTrigger className="w-40"><SelectValue placeholder="All status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All status</SelectItem>
              <SelectItem value="available">Available</SelectItem>
              <SelectItem value="reserved">Reserved</SelectItem>
              <SelectItem value="used">Used</SelectItem>
              <SelectItem value="disabled">Disabled</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder="Prefix e.g. 21628"
            className="w-44"
            value={filter.prefix ?? ""}
            onChange={(e) => setFilter({ ...filter, prefix: e.target.value || undefined })}
          />
          <Button variant="destructive" onClick={deleteRange} title="Delete every number matching the current filters">
            <Trash2 className="mr-1 h-4 w-4" /> Delete range ({total})
          </Button>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="pill-green">{counts.available || 0} available</span>
          <span className="pill-yellow">{counts.reserved || 0} reserved</span>
          <span className="pill-neutral">{counts.used || 0} used</span>
          <span className="pill-red">{counts.disabled || 0} disabled</span>
        </div>
      </div>

      <div className="glass-card overflow-hidden p-0">
        <table className="data-table">
          <thead><tr><th>ID</th><th>MSISDN</th><th>Service</th><th>Country</th><th>Status</th><th>Last OTP</th><th></th></tr></thead>
          <tbody>
            {list.map((n) => (
              <tr key={n.id}>
                <td className="text-muted-foreground">#{n.id}</td>
                <td><span className="code-pill">+{n.msisdn}</span></td>
                <td><ServiceBadge service={{ name: n.service_name, code: n.service_keyword }} /></td>
                <td><span className="mr-1 text-lg">{n.country_flag}</span>{n.country_name}</td>
                <td><span className={statusPill[n.status] || "pill-neutral"}>{n.status}</span></td>
                <td className="text-muted-foreground">{n.last_otp_at ? new Date(n.last_otp_at).toLocaleString() : "—"}</td>
                <td className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="default" className="bg-gradient-primary text-primary-foreground" onClick={async () => {
                      const code = prompt(`Send OTP to assigned user for +${n.msisdn}?\nEnter the OTP code:`);
                      if (!code) return;
                      try {
                        const r = await api.sms.inject({ number_id: n.id, code: code.trim(), notify: true });
                        toast.success(r.delivered ? "OTP saved & delivered to user" : "OTP saved (no Telegram delivery)");
                        load();
                      } catch (e: any) { toast.error(e.message); }
                    }}>
                      <Send className="mr-1 h-3.5 w-3.5" /> Send OTP
                    </Button>
                    <Button size="sm" variant="secondary" onClick={async () => { await api.numbers.update(n.id, { ...n, status: "available" }); load(); }}>
                      <RotateCcw className="mr-1 h-3.5 w-3.5" /> Reset
                    </Button>
                    <Button size="sm" variant="destructive" onClick={async () => { if (confirm("Delete?")) { await api.numbers.remove(n.id); load(); } }}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && (<tr><td colSpan={7} className="py-10 text-center text-muted-foreground">No numbers found.</td></tr>)}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
        <span>Showing {list.length === 0 ? 0 : page * PAGE_SIZE + 1}–{page * PAGE_SIZE + list.length} of {total}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>Prev</Button>
          <Button size="sm" variant="secondary" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      </div>
    </>
  );
}

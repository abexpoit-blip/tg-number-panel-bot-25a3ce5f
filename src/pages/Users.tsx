import { useEffect, useState } from "react";
import { Search, DollarSign, Ban, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

export default function Users() {
  const [list, setList] = useState<any[]>([]);
  const [q, setQ] = useState("");

  const load = () => api.users.list(q || undefined).then(setList).catch((e) => toast.error(e.message));
  useEffect(() => { load(); }, []);

  const adjust = async (id: number) => {
    const v = prompt("Adjust balance by (positive or negative):", "0");
    if (!v) return;
    try { await api.users.adjust(id, parseFloat(v)); toast.success("Balance updated"); load(); }
    catch (e: any) { toast.error(e.message); }
  };

  return (
    <>
      <PageHeader title="Users" subtitle="Telegram users of your bot" />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <form onSubmit={(e) => { e.preventDefault(); load(); }} className="flex gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name / username / id" className="w-72 pl-9" />
          </div>
          <Button type="submit" className="bg-gradient-primary text-primary-foreground">Search</Button>
        </form>
        <span className="text-xs text-muted-foreground">{list.length} shown</span>
      </div>

      <div className="glass-card overflow-hidden p-0">
        <table className="data-table">
          <thead><tr><th>TG ID</th><th>Name</th><th>Username</th><th>Balance</th><th>Earned</th><th>OTPs</th><th>Joined</th><th></th></tr></thead>
          <tbody>
            {list.map((u) => (
              <tr key={u.id}>
                <td><span className="code-pill">{u.id}</span></td>
                <td>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{u.first_name || "—"}</span>
                    {u.is_banned && <span className="pill-red">banned</span>}
                  </div>
                </td>
                <td className="text-muted-foreground">{u.username ? "@" + u.username : "—"}</td>
                <td><span className="font-mono text-success">৳{Number(u.balance).toFixed(2)} <span className="text-xs text-muted-foreground">BDT</span></span></td>
                <td><span className="font-mono">৳{Number(u.total_earned || 0).toFixed(2)}</span></td>
                <td>{u.otp_count}</td>
                <td className="text-muted-foreground">{new Date(u.created_at).toLocaleDateString()}</td>
                <td className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="secondary" onClick={() => adjust(u.id)}><DollarSign className="mr-1 h-3.5 w-3.5" /> Adjust</Button>
                    {u.is_banned ? (
                      <Button size="sm" className="bg-success/20 text-success hover:bg-success/30" onClick={async () => { await api.users.unban(u.id); load(); }}>
                        <ShieldCheck className="mr-1 h-3.5 w-3.5" /> Unban
                      </Button>
                    ) : (
                      <Button size="sm" variant="destructive" onClick={async () => { await api.users.ban(u.id); load(); }}>
                        <Ban className="mr-1 h-3.5 w-3.5" /> Ban
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {list.length === 0 && (<tr><td colSpan={8} className="py-10 text-center text-muted-foreground">No users found.</td></tr>)}
          </tbody>
        </table>
      </div>
    </>
  );
}

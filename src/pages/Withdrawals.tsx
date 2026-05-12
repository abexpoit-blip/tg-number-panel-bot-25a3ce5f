import { useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { api } from "@/lib/api";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

const statusPill: Record<string, string> = { paid: "pill-green", rejected: "pill-red", pending: "pill-yellow" };

export default function Withdrawals() {
  const [list, setList] = useState<any[]>([]);
  const [status, setStatus] = useState("pending");

  const load = () => api.withdrawals.list(status || undefined).then(setList).catch((e) => toast.error(e.message));
  useEffect(() => { load(); }, [status]);

  return (
    <>
      <PageHeader title="Withdrawals" subtitle="Approve or reject user payout requests" />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="paid">Paid</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">{list.length} shown</span>
      </div>

      <div className="glass-card overflow-hidden p-0">
        <table className="data-table">
          <thead><tr><th>ID</th><th>User</th><th>Amount</th><th>Method</th><th>Address</th><th>Status</th><th>Requested</th><th></th></tr></thead>
          <tbody>
            {list.map((w) => (
              <tr key={w.id}>
                <td className="text-muted-foreground">#{w.id}</td>
                <td>
                  <div className="font-medium">{w.first_name} {w.username && <span className="text-muted-foreground">@{w.username}</span>}</div>
                  <div className="mt-1"><span className="code-pill">{w.user_id}</span></div>
                </td>
                <td><span className="font-mono text-base font-semibold text-success">৳{Number(w.amount).toFixed(2)} <span className="text-xs text-muted-foreground">BDT</span></span></td>
                <td><span className="pill-neutral uppercase">{w.method}</span></td>
                <td><span className="code-pill max-w-[220px] truncate">{w.address}</span></td>
                <td><span className={statusPill[w.status] || "pill-neutral"}>{w.status}</span></td>
                <td className="text-muted-foreground">{new Date(w.created_at).toLocaleString()}</td>
                <td className="text-right">
                  {w.status === "pending" && (
                    <div className="flex justify-end gap-2">
                      <Button size="sm" className="bg-success/20 text-success hover:bg-success/30" onClick={async () => { const n = prompt("Note (txid):", ""); await api.withdrawals.pay(w.id, n || undefined); load(); }}>
                        <Check className="mr-1 h-3.5 w-3.5" /> Mark paid
                      </Button>
                      <Button size="sm" variant="destructive" onClick={async () => { const n = prompt("Reason:", ""); await api.withdrawals.reject(w.id, n || undefined); load(); }}>
                        <X className="mr-1 h-3.5 w-3.5" /> Reject
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {list.length === 0 && (<tr><td colSpan={8} className="py-10 text-center text-muted-foreground">No withdrawals.</td></tr>)}
          </tbody>
        </table>
      </div>
    </>
  );
}

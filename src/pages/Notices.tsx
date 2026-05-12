import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Send, Megaphone, Users, Radio, MessageSquare } from "lucide-react";

type Target = "dm" | "channel" | "both";

export default function Notices() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [target, setTarget] = useState<Target>("both");

  const list = useQuery({
    queryKey: ["notices"],
    queryFn: () => api.notices.list(),
    refetchInterval: 15_000,
  });

  const send = useMutation({
    mutationFn: () => api.notices.send({ text: text.trim(), target }),
    onSuccess: (r) => {
      toast.success(`Sent ${r.sent}/${r.total} • Failed ${r.failed}`);
      setText("");
      qc.invalidateQueries({ queryKey: ["notices"] });
    },
    onError: (e: Error) => toast.error(e.message || "Failed to send notice"),
  });

  const targets: { id: Target; label: string; icon: typeof Users }[] = [
    { id: "dm", label: "Bot Users (DM)", icon: Users },
    { id: "channel", label: "Feed Channel", icon: Radio },
    { id: "both", label: "Both", icon: Megaphone },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-primary">
          <Megaphone className="h-5 w-5 text-primary-foreground" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Notices</h1>
          <p className="text-sm text-muted-foreground">Broadcast messages to bot users and the OTP feed channel.</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><MessageSquare className="h-4 w-4" /> Compose Notice</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Message (HTML supported: &lt;b&gt;, &lt;i&gt;, &lt;a href&gt;, &lt;code&gt;)
            </label>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              placeholder={"<b>📢 Notice</b>\nNew ranges added! Check the bot now."}
              className="font-mono text-sm"
            />
            <div className="mt-1 text-xs text-muted-foreground">{text.length} / 4000</div>
          </div>

          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-muted-foreground">Send To</label>
            <div className="flex flex-wrap gap-2">
              {targets.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTarget(id)}
                  className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition ${
                    target === id
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <Button
            onClick={() => send.mutate()}
            disabled={send.isPending || !text.trim()}
            className="gap-2"
          >
            <Send className="h-4 w-4" />
            {send.isPending ? "Sending..." : "Send Notice"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <div className="text-sm text-muted-foreground">Loading...</div>
          ) : !list.data?.length ? (
            <div className="text-sm text-muted-foreground">No notices sent yet.</div>
          ) : (
            <div className="space-y-3">
              {list.data.map((n) => (
                <div key={n.id} className="rounded-lg border border-border bg-card/50 p-4">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant="outline">#{n.id}</Badge>
                    <Badge variant="secondary">{n.target}</Badge>
                    <Badge className="bg-emerald-500/15 text-emerald-400">
                      ✓ {n.sent_count}/{n.total_targets}
                    </Badge>
                    {n.failed_count > 0 && (
                      <Badge className="bg-destructive/15 text-destructive">✗ {n.failed_count}</Badge>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {n.created_at ? new Date(n.created_at).toLocaleString() : ""}
                    </span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words text-sm text-foreground/90">
                    {n.text}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

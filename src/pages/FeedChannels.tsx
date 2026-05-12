import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { RefreshCw, Radio, Users as UsersIcon, AlertTriangle, CheckCircle2 } from "lucide-react";

export default function FeedChannels() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api.settings.list() });
  const channels = useQuery({
    queryKey: ["feed-channels"],
    queryFn: () => api.feed.channels(),
    refetchInterval: 30_000,
  });

  const [ids, setIds] = useState("");
  const [botPnl, setBotPnl] = useState("");
  const [support, setSupport] = useState("");

  useEffect(() => {
    if (settings.data) {
      setIds(String(settings.data.public_feed_channel_ids ?? ""));
      setBotPnl(String(settings.data.bot_pnl_url ?? ""));
      setSupport(String(settings.data.support_url ?? ""));
    }
  }, [settings.data]);

  const save = useMutation({
    mutationFn: async () => {
      await Promise.all([
        api.settings.set("public_feed_channel_ids", ids.trim()),
        api.settings.set("bot_pnl_url", botPnl.trim()),
        api.settings.set("support_url", support.trim()),
      ]);
    },
    onSuccess: () => {
      toast.success("Feed settings saved");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["feed-channels"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const list = channels.data?.channels ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight">OTP Feed Channels</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Public channels where the bot mirrors a masked teaser of every received OTP
            (no codes are exposed) so users can see which ranges are active.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => channels.refetch()}
          disabled={channels.isFetching}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${channels.isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Public feed channel IDs (comma-separated)</label>
            <Input
              value={ids}
              onChange={(e) => setIds(e.target.value)}
              placeholder="-1001234567890, -1009876543210"
            />
            <p className="text-xs text-muted-foreground">
              The bot must be added as an admin with “Post messages” permission in each channel.
              Use the negative chat ID format (starts with -100).
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Bot Pnl button URL</label>
              <Input value={botPnl} onChange={(e) => setBotPnl(e.target.value)} placeholder="https://t.me/YourBot" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">All Support button URL</label>
              <Input value={support} onChange={(e) => setSupport(e.target.value)} placeholder="https://t.me/YourSupport" />
            </div>
          </div>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Radio className="h-5 w-5" /> Channel status
            {channels.data && (
              <Badge variant="outline" className="ml-2">
                {channels.data.total_otps} total OTPs forwarded
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {channels.isLoading ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : list.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No feed channels configured yet. Add one above.
            </div>
          ) : (
            <div className="space-y-3">
              {list.map((c) => (
                <div
                  key={c.id}
                  className="flex items-center justify-between gap-4 rounded-lg border bg-card/40 p-4"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 font-medium">
                      {c.ok ? (
                        <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                      ) : (
                        <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
                      )}
                      <span className="truncate">{c.title || c.id}</span>
                      {c.username && (
                        <a
                          href={`https://t.me/${c.username}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-primary hover:underline"
                        >
                          @{c.username}
                        </a>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground font-mono">
                      ID {c.id}
                      {c.type ? ` • ${c.type}` : ""}
                    </div>
                    {c.error && (
                      <div className="mt-1 text-xs text-destructive">{c.error}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {typeof c.members === "number" && (
                      <Badge variant="secondary" className="gap-1">
                        <UsersIcon className="h-3 w-3" />
                        {c.members.toLocaleString()}
                      </Badge>
                    )}
                    <Badge variant={c.ok ? "default" : "destructive"}>
                      {c.ok ? "OK" : "Error"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

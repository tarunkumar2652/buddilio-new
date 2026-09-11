import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Send, RefreshCw } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Badge } from "@/components/Shared";

const PILL = "rounded-full px-4 py-2 text-xs font-bold transition-colors";

/** The week's stories, gathered automatically — you decide when it goes out. */
export const NewsletterDigest = () => {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState("");

  const load = useCallback(() => {
    api.get("/admin/newsletter/digests").then(({ data }) => setD(data)).catch(() => setD(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (path, key) => {
    setBusy(key);
    try { const { data } = await api.post(path); toast[data.ok ? "success" : "message"](data.message); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(""); }
  };

  if (!d) return null;
  const ready = d.items.find((x) => x.status === "ready");

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="digest-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="inline-flex items-center gap-2 text-sm font-black text-slate-900">
            <Mail className="h-4 w-4" />Weekly digest
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Every Sunday Buddilio gathers the week's new stories into one email for your
            {" "}{d.subscribers} subscriber{d.subscribers === 1 ? "" : "s"}. It waits here until you send it.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => act("/admin/newsletter/digests/build", "build")} disabled={!!busy}
            data-testid="digest-build" className={`${PILL} border border-slate-200 disabled:opacity-50`}>
            <RefreshCw className="mr-1.5 inline h-3.5 w-3.5" />
            {busy === "build" ? "Gathering…" : "Gather now"}
          </button>
          {ready && (
            <button onClick={() => act(`/admin/newsletter/digests/${ready.id}/send`, "send")}
              disabled={!!busy} data-testid="digest-send"
              className={`${PILL} bg-brand-magenta text-white disabled:opacity-50`}>
              <Send className="mr-1.5 inline h-3.5 w-3.5" />
              {busy === "send" ? "Sending…" : `Send ${ready.posts.length} story digest`}
            </button>
          )}
        </div>
      </div>

      {d.items.length ? (
        <div className="mt-4 divide-y divide-slate-100">
          {d.items.map((x, i) => (
            <div key={x.id} className="py-3" data-testid={`digest-row-${i}`}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={x.status === "sent" ? "green" : "amber"}>
                  {x.status === "sent" ? `sent to ${x.sent_count}` : "waiting for you"}
                </Badge>
                <span className="text-xs font-semibold text-slate-500">
                  Week of {x.week_of} · {x.posts.length} stor{x.posts.length === 1 ? "y" : "ies"}
                  {x.sent_at ? ` · ${fmtDate(x.sent_at)}` : ""}
                </span>
              </div>
              <p className="mt-1.5 text-sm text-slate-700">
                {x.posts.map((p) => p.title).join(" · ")}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">
          No digest yet — press Gather now once a story has published this week.
        </p>
      )}
    </div>
  );
};

export default NewsletterDigest;

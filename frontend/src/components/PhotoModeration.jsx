import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, EyeOff, Eye, Trash2 } from "lucide-react";
import { api, errMsg, fileUrl, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const TABS = [["reported", "Reported"], ["hidden", "Hidden"], ["all", "All photos"]];

export const PhotoModeration = () => {
  const [status, setStatus] = useState("reported");
  const [data, setData] = useState(null);
  const [notes, setNotes] = useState({});
  const [warn, setWarn] = useState({});

  const load = useCallback(() => {
    setData(null);
    api.get(`/admin/photos?status=${status}`).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [], counts: {} }); });
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const act = async (id, action) => {
    try {
      const { data } = await api.post(`/admin/photos/${id}`, { action, note: notes[id] || "", warn: !!warn[id] });
      toast.success(data.warned ? "Done — the member was warned." : "Done.");
      setNotes((n) => ({ ...n, [id]: "" }));
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div data-testid="photo-moderation-panel">
      <div className="flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)} data-testid={`photomod-filter-${v}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
            {l}{data?.counts?.[v] != null ? ` (${data.counts[v]})` : ""}
          </button>
        ))}
      </div>

      {!data ? <div className="mt-6"><Spinner /></div>
        : data.items.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500" data-testid="photomod-empty">Nothing to moderate right now.</p>
        ) : (
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {data.items.map((p) => (
              <div key={p.id} className="rounded-2xl border border-slate-200 bg-white p-4 flex gap-4"
                data-testid={`photomod-row-${p.id}`}>
                <img src={fileUrl(p.url)} alt="" loading="lazy"
                  className="h-28 w-28 shrink-0 rounded-xl object-cover border border-slate-200" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-bold">{p.event_title || "Event"}</p>
                    {p.hidden ? <Badge tone="red">hidden</Badge> : p.report_count > 0 ? (
                      <Badge tone="amber">{p.report_count} report{p.report_count === 1 ? "" : "s"}</Badge>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500 truncate">
                    {p.user_name} · {p.user_email}{p.warnings ? ` · ${p.warnings} warning(s)` : ""}
                  </p>
                  {p.caption && <p className="mt-1 text-xs text-slate-600 italic line-clamp-2">“{p.caption}”</p>}
                  {p.last_report_reason && (
                    <p className="mt-1 flex items-start gap-1 text-xs text-rose-600">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />{p.last_report_reason}
                    </p>
                  )}
                  <p className="mt-1 text-[11px] text-slate-400">Posted {fmtDate(p.created_at)}</p>

                  <input value={notes[p.id] || ""} onChange={(e) => setNotes((n) => ({ ...n, [p.id]: e.target.value }))}
                    placeholder="Reason (shown to the member if you warn them)" data-testid={`photomod-note-${p.id}`}
                    className="mt-3 w-full rounded-xl border border-slate-200 px-3 py-2 text-xs" />
                  <label className="mt-2 flex items-center gap-2 text-xs font-semibold text-slate-600">
                    <input type="checkbox" checked={!!warn[p.id]} data-testid={`photomod-warn-${p.id}`}
                      onChange={(e) => setWarn((w) => ({ ...w, [p.id]: e.target.checked }))} />
                    Warn the member who posted it
                  </label>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {!p.hidden && (
                      <button onClick={() => act(p.id, "hide")} data-testid={`photomod-hide-${p.id}`}
                        className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-3.5 py-1.5 text-xs font-bold text-white">
                        <EyeOff className="h-3.5 w-3.5" />Hide
                      </button>
                    )}
                    {p.hidden && (
                      <button onClick={() => act(p.id, "restore")} data-testid={`photomod-restore-${p.id}`}
                        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">
                        <Eye className="h-3.5 w-3.5" />Restore
                      </button>
                    )}
                    {p.report_count > 0 && !p.hidden && (
                      <button onClick={() => act(p.id, "dismiss")} data-testid={`photomod-dismiss-${p.id}`}
                        className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">Dismiss reports</button>
                    )}
                    <button onClick={() => act(p.id, "delete")} data-testid={`photomod-delete-${p.id}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold text-rose-600">
                      <Trash2 className="h-3.5 w-3.5" />Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  );
};

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const TABS = [["pending", "Awaiting review"], ["verified", "Verified"], ["rejected", "Rejected"], ["all", "All"]];

export const IdVerifications = () => {
  const [status, setStatus] = useState("pending");
  const [data, setData] = useState(null);
  const [notes, setNotes] = useState({});

  const load = useCallback(() => {
    setData(null);
    api.get(`/admin/id-verifications?status=${status}`).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [], counts: {}, types: [] }); });
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const act = async (id, action) => {
    try {
      await api.post(`/admin/id-verifications/${id}`, { action, note: notes[id] || "" });
      toast.success(action === "approve" ? "Member verified." : "Marked rejected.");
      setNotes((n) => ({ ...n, [id]: "" })); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;
  const label = (k) => (data.types.find((t) => t.key === k) || {}).label || k;

  return (
    <div className="space-y-6" data-testid="id-verifications-panel">
      <div className="flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)} data-testid={`idv-filter-${v}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
            {l}{data.counts?.[v] != null ? ` (${data.counts[v]})` : ""}
          </button>
        ))}
      </div>

      {data.items.length === 0 ? (
        <p className="text-sm text-slate-500" data-testid="idv-empty">Nothing in this list.</p>
      ) : (
        <div className="space-y-4">
          {data.items.map((m) => (
            <div key={m.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`idv-row-${m.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-bold">{m.full_name}</p>
                  <p className="text-xs text-slate-500">{m.email} · {m.city || "—"} · submitted {fmtDate(m.id_verification.submitted_at)}</p>
                  <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
                    <ShieldCheck className="h-4 w-4" />{label(m.id_verification.doc_type)}
                  </p>
                  {m.id_verification.address && (
                    <p className="mt-1 text-sm text-slate-600">{m.id_verification.address}</p>
                  )}
                </div>
                <Badge tone={m.id_verification.status === "verified" ? "green" : m.id_verification.status === "pending" ? "amber" : "red"}>
                  {m.id_verification.status}
                </Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(m.id_verification.documents || []).map((d, i) => (
                  <a key={i} href={d.url} target="_blank" rel="noreferrer" data-testid={`idv-file-${m.id}-${i}`}
                    className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">{d.name}</a>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <input value={notes[m.id] || ""} placeholder="Note (sent to the member)" data-testid={`idv-note-${m.id}`}
                  onChange={(e) => setNotes((n) => ({ ...n, [m.id]: e.target.value }))}
                  className="flex-1 min-w-[200px] rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <button onClick={() => act(m.id, "approve")} data-testid={`idv-approve-${m.id}`}
                  className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Approve</button>
                <button onClick={() => act(m.id, "reject")} data-testid={`idv-reject-${m.id}`}
                  className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">Reject</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

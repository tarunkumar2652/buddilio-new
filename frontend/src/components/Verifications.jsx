import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { BadgeCheck, FileText } from "lucide-react";
import { api, errMsg, fileUrl, fmtDate } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const TABS = [["pending", "Awaiting review"], ["verified", "Verified"], ["rejected", "Rejected"], ["all", "All vendors"]];

export const Verifications = () => {
  const [status, setStatus] = useState("pending");
  const [data, setData] = useState(null);
  const [notes, setNotes] = useState({});

  const load = useCallback(() => {
    setData(null);
    api.get(`/admin/verifications?status=${status}`).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [], counts: {} }); });
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const act = async (id, action) => {
    try {
      await api.post(`/admin/verifications/${id}`, { action, note: notes[id] || "" });
      toast.success(action === "approve" ? "Vendor verified." : action === "reject" ? "Vendor rejected." : "Moved back to the queue.");
      setNotes((n) => ({ ...n, [id]: "" }));
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div data-testid="verifications-panel">
      <div className="flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)} data-testid={`verify-filter-${v}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
            {l}{data?.counts?.[v] != null ? ` (${data.counts[v]})` : ""}
          </button>
        ))}
      </div>

      {!data ? <div className="mt-6"><Spinner /></div>
        : data.items.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500" data-testid="verifications-empty">Nothing in this list right now.</p>
        ) : (
          <div className="mt-6 space-y-4">
            {data.items.map((v) => (
              <div key={v.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`verify-row-${v.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-bold flex items-center gap-2">
                      {v.org_name || v.full_name}
                      {v.verified && <BadgeCheck className="h-4 w-4 text-emerald-600" data-testid={`verify-badge-${v.id}`} />}
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">{v.email} · {v.city || "—"}{v.manager ? ` · managed by ${v.manager}` : ""}</p>
                  </div>
                  <Badge tone={v.verification_status === "verified" ? "green" : v.verification_status === "rejected" ? "red" : "amber"}>
                    {v.verification_status}
                  </Badge>
                </div>

                <div className="mt-4 flex flex-wrap gap-2" data-testid={`verify-docs-${v.id}`}>
                  {v.documents.length === 0 && <p className="text-xs text-slate-400">No documents uploaded.</p>}
                  {v.documents.map((d, i) => (
                    <a key={i} href={fileUrl(d.url)} target="_blank" rel="noreferrer"
                      data-testid={`verify-doc-${v.id}-${i}`}
                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold hover:border-slate-900">
                      <FileText className="h-3.5 w-3.5 text-slate-400" />
                      {d.name || `Document ${i + 1}`}{d.kind ? ` · ${d.kind}` : ""}
                    </a>
                  ))}
                </div>

                {v.verification_note && <p className="mt-3 text-xs text-slate-500">Note: {v.verification_note}</p>}
                {v.verified_at && <p className="mt-1 text-[11px] text-slate-400">Verified {fmtDate(v.verified_at)}</p>}

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <input value={notes[v.id] || ""} onChange={(e) => setNotes((n) => ({ ...n, [v.id]: e.target.value }))}
                    placeholder="Reason / note (sent to the vendor)" data-testid={`verify-note-${v.id}`}
                    className="flex-1 min-w-[200px] rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  {v.verification_status !== "verified" && (
                    <button onClick={() => act(v.id, "approve")} data-testid={`verify-approve-${v.id}`}
                      className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Verify</button>
                  )}
                  {v.verification_status !== "rejected" && (
                    <button onClick={() => act(v.id, "reject")} data-testid={`verify-reject-${v.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">Reject</button>
                  )}
                  {v.verification_status !== "pending" && (
                    <button onClick={() => act(v.id, "reset")} data-testid={`verify-reset-${v.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Back to queue</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
    </div>
  );
};

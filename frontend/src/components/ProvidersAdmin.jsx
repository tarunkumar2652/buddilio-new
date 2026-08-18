import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Compass } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const TABS = [["pending", "Awaiting review"], ["pending_fee", "Fee unpaid"], ["approved", "Listed"],
  ["rejected", "Rejected"], ["all", "All"]];

export const ProvidersAdmin = () => {
  const [status, setStatus] = useState("pending");
  const [data, setData] = useState(null);
  const [notes, setNotes] = useState({});
  const [cfg, setCfg] = useState({ provider_fee: "", travel_markup_percent: "", travel_uplift_percent: "", travel_cut_percent: "" });

  const load = useCallback(() => {
    setData(null);
    api.get(`/admin/providers?status=${status}`).then(({ data }) => {
      setData(data);
      setCfg({ provider_fee: String(data.config.fee), travel_markup_percent: String(data.config.markup_percent),
        travel_uplift_percent: String(data.config.uplift_percent), travel_cut_percent: String(data.config.cut_percent) });
    }).catch((e) => { toast.error(errMsg(e)); setData({ items: [], counts: {}, roles: [], config: {} }); });
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const saveCfg = async () => {
    try {
      await api.put("/admin/settings", Object.fromEntries(Object.entries(cfg).map(([k, v]) => [k, Number(v)])));
      toast.success("Travel pricing updated.");
    } catch (e) { toast.error(errMsg(e)); }
  };

  const act = async (id, action) => {
    try {
      await api.post(`/admin/providers/${id}`, { action, note: notes[id] || "" });
      toast.success("Done."); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;
  const roleLabel = (k) => (data.roles.find((r) => r.key === k) || {}).label || k;

  return (
    <div className="space-y-6" data-testid="providers-admin-panel">
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200 bg-white p-5">
        {[["provider_fee", "Registration fee"], ["travel_markup_percent", "Traveller markup %"],
          ["travel_uplift_percent", "Non-India uplift %"], ["travel_cut_percent", "Buddilio cut %"]].map(([key, label]) => (
          <label key={key} className="text-sm">
            <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">{label}</span>
            <input type="number" step="0.01" value={cfg[key]} data-testid={`travel-${key}`}
              onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })}
              className="mt-1 w-36 rounded-xl border border-slate-200 px-3 py-2 text-sm" />
          </label>
        ))}
        <button onClick={saveCfg} data-testid="travel-config-save"
          className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Save pricing</button>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)} data-testid={`providers-filter-${v}`}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${status === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
            {l}{data.counts?.[v] != null ? ` (${data.counts[v]})` : ""}
          </button>
        ))}
      </div>

      {data.items.length === 0 ? (
        <p className="text-sm text-slate-500" data-testid="providers-empty">Nothing in this list.</p>
      ) : (
        <div className="space-y-4">
          {data.items.map((p) => (
            <div key={p.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`provider-row-${p.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 font-bold"><Compass className="h-4 w-4" />{p.full_name}</p>
                  <p className="text-xs text-slate-500">{p.email} · {p.city || "—"} · {p.roles.map(roleLabel).join(", ")}</p>
                  <p className="mt-1 text-sm">
                    {money(p.day_rate)}/day → traveller sees {money(p.day_price)} · fee paid {money(p.fee_paid || 0)}
                    · {p.experience_years}y experience
                  </p>
                  {p.headline && <p className="mt-1 text-sm text-slate-600">{p.headline}</p>}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(p.documents || []).map((d, i) => (
                      <a key={i} href={d.url} target="_blank" rel="noreferrer" data-testid={`provider-doc-${p.id}-${i}`}
                        className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">{d.name}</a>
                    ))}
                  </div>
                </div>
                <Badge tone={p.status === "approved" ? "green" : p.status === "rejected" ? "red" : "amber"}>{p.status}</Badge>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <input value={notes[p.id] || ""} placeholder="Note to the provider" data-testid={`provider-note-${p.id}`}
                  onChange={(e) => setNotes((n) => ({ ...n, [p.id]: e.target.value }))}
                  className="flex-1 min-w-[200px] rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <button onClick={() => act(p.id, "approve")} data-testid={`provider-approve-${p.id}`}
                  className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Approve</button>
                <button onClick={() => act(p.id, "reject")} data-testid={`provider-reject-${p.id}`}
                  className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">Reject</button>
                {p.status === "approved" && (
                  <button onClick={() => act(p.id, "suspend")} data-testid={`provider-suspend-${p.id}`}
                    className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Suspend</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

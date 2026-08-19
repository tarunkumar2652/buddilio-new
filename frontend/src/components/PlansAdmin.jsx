import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, X } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";

const cls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const CURRENCIES = ["USD", "EUR", "GBP", "AED", "SGD", "JPY", "AUD", "THB"];

const BLANK = {
  name: "", price: 0, duration_days: 30, description: "", benefits: [], discount_percent: 0,
  price_overrides: {}, messages_per_week: 0, hangouts_access: false, premium_filters: false,
  priority_access: false, concierge_support: false, active: true,
};

const TOGGLES = [
  ["hangouts_access", "Paid hangouts"],
  ["premium_filters", "Premium discovery filters"],
  ["priority_access", "Priority event access"],
  ["concierge_support", "Dedicated concierge"],
];

const L = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

export const PlansAdmin = () => {
  const [items, setItems] = useState(null);
  const [edit, setEdit] = useState(null);

  const load = useCallback(() => {
    api.get("/admin/plans").then(({ data }) => setItems(data.items)).catch((e) => { toast.error(errMsg(e)); setItems([]); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async (id) => {
    try { await api.delete(`/admin/plans/${id}`); toast.success("Plan deleted."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!items) return <Spinner />;

  return (
    <div className="space-y-5" data-testid="plans-admin">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Membership plans</h2>
          <p className="mt-1 text-sm text-slate-500">
            Price, message allowance and unlocked features here drive the website and are enforced when members use the app.
          </p>
        </div>
        <button onClick={() => setEdit({ ...BLANK })} data-testid="plan-new"
          className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">
          <Plus className="h-3.5 w-3.5" />New plan
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {items.map((p) => (
          <div key={p.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`plan-row-${p.id}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-display text-lg font-bold">{p.name}</p>
                <p className="text-xs text-slate-500">{p.duration_days} days · {p.discount_percent || 0}% off passes</p>
              </div>
              <Badge tone={p.active ? "green" : "slate"}>{p.active ? "live" : "hidden"}</Badge>
            </div>
            <p className="mt-3 text-2xl font-display font-bold" data-testid={`plan-price-${p.id}`}>{money(p.price)}</p>
            <p className="mt-1 text-xs text-slate-500">
              {p.messages_per_week ? `${p.messages_per_week} messages a week` : "Unlimited messages"}
              {Object.keys(p.price_overrides || {}).length > 0
                && ` · overrides: ${Object.keys(p.price_overrides).join(", ")}`}
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {TOGGLES.filter(([k]) => p[k]).map(([k, l]) => (
                <span key={k} className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold">{l}</span>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setEdit({ ...BLANK, ...p })} data-testid={`plan-edit-${p.id}`}
                className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Edit</button>
              <button onClick={() => remove(p.id)} data-testid={`plan-delete-${p.id}`}
                className="inline-flex items-center gap-1 rounded-full border border-red-200 px-4 py-2 text-xs font-bold text-red-600">
                <Trash2 className="h-3.5 w-3.5" />Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {edit && <PlanForm plan={edit} onClose={() => setEdit(null)} onSaved={load} />}
    </div>
  );
};

const PlanForm = ({ plan, onClose, onSaved }) => {
  const [f, setF] = useState(plan);
  const [busy, setBusy] = useState(false);
  const editing = !!plan.id;

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = {
        ...f, price: Number(f.price) || 0, duration_days: Number(f.duration_days) || 30,
        discount_percent: Number(f.discount_percent) || 0,
        messages_per_week: Number(f.messages_per_week) || 0,
        benefits: (f.benefits || []).map((b) => b.trim()).filter(Boolean),
        price_overrides: Object.fromEntries(Object.entries(f.price_overrides || {})
          .filter(([, v]) => v !== "" && v !== null).map(([k, v]) => [k, Number(v) || 0])),
      };
      if (editing) await api.put(`/admin/plans/${plan.id}`, body);
      else await api.post("/admin/plans", body);
      toast.success("Plan saved — the website updates instantly.");
      onSaved(); onClose();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  const setOverride = (code, value) => setF((p) => {
    const next = { ...(p.price_overrides || {}) };
    if (value === "") delete next[code]; else next[code] = value;
    return { ...p, price_overrides: next };
  });

  return (
    <div className="fixed inset-0 z-[80] grid place-items-start overflow-y-auto bg-slate-900/60 p-4 sm:p-8" data-testid="plan-modal">
      <form onSubmit={save} className="mx-auto w-full max-w-2xl space-y-4 rounded-2xl bg-white p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">{editing ? `Edit ${plan.name}` : "New plan"}</h3>
          <button type="button" onClick={onClose} data-testid="plan-modal-close" className="rounded-full border border-slate-200 p-2">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <L label="Plan name"><input required value={f.name} data-testid="plan-name"
            onChange={(e) => setF({ ...f, name: e.target.value })} className={cls} /></L>
          <L label="Price (INR base)" hint="Members in other currencies see this converted, unless you set an override below.">
            <input type="number" min={0} step="any" value={f.price} data-testid="plan-price"
              onChange={(e) => setF({ ...f, price: e.target.value })} className={cls} />
          </L>
          <L label="Duration (days)"><input type="number" min={1} value={f.duration_days} data-testid="plan-duration"
            onChange={(e) => setF({ ...f, duration_days: e.target.value })} className={cls} /></L>
          <L label="Discount on passes (%)"><input type="number" min={0} max={100} step="any" value={f.discount_percent}
            data-testid="plan-discount" onChange={(e) => setF({ ...f, discount_percent: e.target.value })} className={cls} /></L>
          <L label="Messages per week" hint="0 means unlimited. Enforced when a member sends a chat message.">
            <input type="number" min={0} value={f.messages_per_week} data-testid="plan-messages"
              onChange={(e) => setF({ ...f, messages_per_week: e.target.value })} className={cls} />
          </L>
          <L label="Short description"><input value={f.description} data-testid="plan-description"
            onChange={(e) => setF({ ...f, description: e.target.value })} className={cls} /></L>
        </div>

        <div>
          <p className="text-xs font-bold text-slate-600">What this plan unlocks</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {TOGGLES.map(([k, l]) => (
              <label key={k} className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold">
                <input type="checkbox" checked={!!f[k]} data-testid={`plan-${k}`}
                  onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{l}
              </label>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs font-bold text-slate-600">Extra benefit lines shown on the website</p>
          <div className="mt-2 space-y-2" data-testid="plan-benefits">
            {(f.benefits || []).map((b, i) => (
              <div key={i} className="flex gap-2">
                <input value={b} data-testid={`plan-benefit-${i}`} className={`${cls} mt-0`}
                  onChange={(e) => setF({ ...f, benefits: f.benefits.map((x, n) => (n === i ? e.target.value : x)) })} />
                <button type="button" data-testid={`plan-benefit-remove-${i}`}
                  onClick={() => setF({ ...f, benefits: f.benefits.filter((_, n) => n !== i) })}
                  className="rounded-xl border border-slate-200 px-3 text-xs font-bold">Remove</button>
              </div>
            ))}
            <button type="button" data-testid="plan-benefit-add"
              onClick={() => setF({ ...f, benefits: [...(f.benefits || []), ""] })}
              className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Add benefit line</button>
          </div>
        </div>

        <div>
          <p className="text-xs font-bold text-slate-600">Exact price in other currencies (optional)</p>
          <p className="mt-1 text-[11px] text-slate-400">
            Leave blank to convert from the INR price automatically. An override always wins over the base price.
          </p>
          <div className="mt-2 grid gap-2 sm:grid-cols-4">
            {CURRENCIES.map((c) => (
              <label key={c} className="block">
                <span className="text-[11px] font-bold text-slate-500">{c}</span>
                <input type="number" min={0} step="any" data-testid={`plan-override-${c}`}
                  value={f.price_overrides?.[c] ?? ""} onChange={(e) => setOverride(c, e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
              </label>
            ))}
          </div>
          {Object.keys(f.price_overrides || {}).length > 0 && (
            <button type="button" data-testid="plan-clear-overrides" onClick={() => setF({ ...f, price_overrides: {} })}
              className="mt-3 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">
              Clear all overrides
            </button>
          )}
        </div>

        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={!!f.active} data-testid="plan-active"
            onChange={(e) => setF({ ...f, active: e.target.checked })} />Show this plan on the website
        </label>

        <button disabled={busy} data-testid="plan-save"
          className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : editing ? "Save plan" : "Create plan"}
        </button>
      </form>
    </div>
  );
};

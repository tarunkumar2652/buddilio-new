import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Globe, Plus, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Spinner } from "@/components/Shared";

const cls = "rounded-xl border border-slate-200 px-3 py-2 text-sm";
const blank = { code: "", name: "", currency: "INR", tax_percent: 0, tax_label: "Tax", emergency: "", cities: [], active: true };

export const Places = () => {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState("");
  const [draft, setDraft] = useState(blank);
  const [cityDraft, setCityDraft] = useState({});

  const load = useCallback(() => {
    api.get("/admin/countries").then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [], currencies: [] }); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (c) => {
    try {
      await api.put(`/admin/countries/${c.code}`, c);
      toast.success(`${c.name} saved.`); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/countries", { ...draft, tax_percent: Number(draft.tax_percent) });
      toast.success("Country added."); setDraft(blank); load();
    } catch (er) { toast.error(errMsg(er)); }
  };

  const remove = async (c) => {
    if (!window.confirm(`Remove ${c.name}? Its cities disappear from every dropdown.`)) return;
    try { await api.delete(`/admin/countries/${c.code}`); toast.success("Removed."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const addCity = (c) => {
    const name = (cityDraft[c.code] || "").trim();
    if (!name) return;
    save({ ...c, cities: [...c.cities, name] });
    setCityDraft((d) => ({ ...d, [c.code]: "" }));
  };

  if (!data) return <Spinner />;

  return (
    <div className="space-y-8" data-testid="places-panel">
      <form onSubmit={create} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="country-create-form">
        <p className="flex items-center gap-2 font-bold"><Globe className="h-4 w-4" />Add a country</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <input required placeholder="Code (IN)" value={draft.code} data-testid="country-code"
            onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })} className={cls} />
          <input required placeholder="Name" value={draft.name} data-testid="country-name"
            onChange={(e) => setDraft({ ...draft, name: e.target.value })} className={cls} />
          <select value={draft.currency} data-testid="country-currency"
            onChange={(e) => setDraft({ ...draft, currency: e.target.value })} className={cls}>
            {data.currencies.map((c) => <option key={c}>{c}</option>)}
          </select>
          <input type="number" step="0.01" placeholder="Tax %" value={draft.tax_percent} data-testid="country-tax"
            onChange={(e) => setDraft({ ...draft, tax_percent: e.target.value })} className={cls} />
          <input placeholder="Tax label" value={draft.tax_label} data-testid="country-tax-label"
            onChange={(e) => setDraft({ ...draft, tax_label: e.target.value })} className={cls} />
          <input placeholder="Emergency no." value={draft.emergency} data-testid="country-emergency"
            onChange={(e) => setDraft({ ...draft, emergency: e.target.value })} className={cls} />
        </div>
        <button data-testid="country-create-submit"
          className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">
          <Plus className="h-3.5 w-3.5" />Add country
        </button>
      </form>

      <div className="space-y-3" data-testid="country-list">
        {data.items.map((c) => (
          <div key={c.code} className="rounded-2xl border border-slate-200 bg-white" data-testid={`country-row-${c.code}`}>
            <button onClick={() => setOpen(open === c.code ? "" : c.code)} data-testid={`country-toggle-${c.code}`}
              className="flex w-full flex-wrap items-center justify-between gap-3 px-5 py-4 text-left">
              <span className="font-bold">{c.name} <span className="text-xs font-normal text-slate-400">{c.code}</span></span>
              <span className="text-xs text-slate-500">
                {c.cities.length} cities · {c.currency} · {c.tax_percent}% {c.tax_label}
                {c.active ? "" : " · hidden"}
              </span>
            </button>
            {open === c.code && (
              <div className="border-t border-slate-100 px-5 py-4" data-testid={`country-panel-${c.code}`}>
                <div className="flex flex-wrap gap-2">
                  {c.cities.map((city) => (
                    <span key={city} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold"
                      data-testid={`city-chip-${city}`}>
                      {city}
                      <button onClick={() => save({ ...c, cities: c.cities.filter((x) => x !== city) })}
                        data-testid={`city-remove-${city}`} className="text-slate-400 hover:text-rose-600">×</button>
                    </span>
                  ))}
                  {c.cities.length === 0 && <span className="text-xs text-slate-500">No cities yet.</span>}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <input placeholder="Add a city" value={cityDraft[c.code] || ""} data-testid={`city-input-${c.code}`}
                    onChange={(e) => setCityDraft((d) => ({ ...d, [c.code]: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCity(c); } }}
                    className={`${cls} min-w-[200px]`} />
                  <button onClick={() => addCity(c)} data-testid={`city-add-${c.code}`}
                    className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Add city</button>
                  <label className="flex items-center gap-2 text-xs font-semibold text-slate-600">
                    <input type="checkbox" checked={c.active} data-testid={`country-active-${c.code}`}
                      onChange={(e) => save({ ...c, active: e.target.checked })} />
                    Visible to members
                  </label>
                  <button onClick={() => remove(c)} data-testid={`country-delete-${c.code}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">
                    <Trash2 className="h-3.5 w-3.5" />Remove country
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

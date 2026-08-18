import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CreditCard, Wallet as WalletIcon, Trash2 } from "lucide-react";
import { api, errMsg, fmtDate, money } from "@/lib/api";
import { Spinner, SEO } from "@/components/Shared";

const cls = "w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm";
const QUICK = [500, 1000, 2500, 5000];

export default function Wallet() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [amount, setAmount] = useState(1000);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState({ name: "", number: "", exp_month: "", exp_year: "", autopay: true });
  const [reload, setReload] = useState({ enabled: false, threshold: 500, amount: 1000 });

  const load = useCallback(() => {
    api.get("/wallet").then(({ data }) => {
      setData(data);
      if (data.auto_reload) setReload(data.auto_reload);
    }).catch((e) => { toast.error(errMsg(e)); setData(false); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveReload = async () => {
    try {
      await api.put("/wallet/auto-reload", {
        enabled: reload.enabled, threshold: Number(reload.threshold), amount: Number(reload.amount),
      });
      toast.success("Auto reload saved.");
    } catch (er) { toast.error(errMsg(er)); }
  };

  const topUp = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/wallet/topup", { amount: Number(amount) });
      nav(`/checkout?kind=wallet&id=${data.topup_id}`);
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  const saveCard = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.put("/wallet/card", {
        ...card, exp_month: Number(card.exp_month), exp_year: Number(card.exp_year),
      });
      toast.success("Card saved — accepted hangouts will charge it automatically.");
      setCard({ name: "", number: "", exp_month: "", exp_year: "", autopay: true });
      setData((d) => ({ ...d, card: data.card }));
    } catch (er) { toast.error(errMsg(er)); }
  };

  const removeCard = async () => {
    try { await api.delete("/wallet/card"); toast.success("Card removed."); setData((d) => ({ ...d, card: null })); }
    catch (er) { toast.error(errMsg(er)); }
  };

  if (data === null) return <Spinner label="Loading your wallet" />;
  if (data === false) return null;

  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10 pb-28" data-testid="wallet-page">
      <SEO title="Wallet" description="Top up your Buddilio wallet." />
      <p className="overline">Money</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Your wallet</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl bg-slate-900 p-6 text-white">
          <p className="flex items-center gap-2 text-xs uppercase tracking-widest text-white/60">
            <WalletIcon className="h-4 w-4" />Balance
          </p>
          <p className="mt-3 text-4xl font-bold" data-testid="wallet-balance">{money(data.balance)}</p>
          <p className="mt-2 text-xs text-white/60">Spent automatically the moment a companion accepts.</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <p className="text-xs uppercase tracking-widest text-slate-400">Free requests left this month</p>
          <p className="mt-3 text-4xl font-bold" data-testid="free-requests-left">{data.free_requests_left}</p>
          <p className="mt-2 text-xs text-slate-500">Members skip the request fee on these.</p>
        </div>
      </div>

      <form onSubmit={topUp} className="mt-8 rounded-2xl border border-slate-200 bg-white p-6" data-testid="topup-form">
        <p className="font-bold">Add money</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {QUICK.map((v) => (
            <button key={v} type="button" onClick={() => setAmount(v)} data-testid={`topup-quick-${v}`}
              className={`rounded-full border px-4 py-2 text-xs font-bold ${Number(amount) === v ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>
              {money(v)}
            </button>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[180px] text-sm">
            <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">Amount</span>
            <input type="number" min={data.min_topup} max={data.max_topup} value={amount} data-testid="topup-amount"
              onChange={(e) => setAmount(e.target.value)} className={`${cls} mt-1`} />
          </label>
          <button disabled={busy} data-testid="topup-submit"
            className="rounded-full brand-gradient px-7 py-3 text-sm font-bold text-white disabled:opacity-50">
            {busy ? "Starting…" : `Add ${money(Number(amount) || 0)}`}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">Minimum {money(data.min_topup)}. Wallet money never expires.</p>
      </form>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6" data-testid="card-section">
        <p className="flex items-center gap-2 font-bold"><CreditCard className="h-4 w-4" />Saved card</p>
        {data.card ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-4" data-testid="saved-card">
            <div>
              <p className="font-bold">{data.card.brand} •••• {data.card.last4}</p>
              <p className="text-xs text-slate-500">{data.card.name} · expires {data.card.expiry} ·
                {data.card.autopay ? " auto-charge on" : " auto-charge off"}</p>
            </div>
            <button onClick={removeCard} data-testid="remove-card"
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">
              <Trash2 className="h-3.5 w-3.5" />Remove
            </button>
          </div>
        ) : (
          <form onSubmit={saveCard} className="mt-4 grid gap-3 sm:grid-cols-2" data-testid="card-form">
            <input required placeholder="Name on card" value={card.name} data-testid="card-name"
              onChange={(e) => setCard({ ...card, name: e.target.value })} className={cls} />
            <input required placeholder="Card number" value={card.number} data-testid="card-number"
              onChange={(e) => setCard({ ...card, number: e.target.value })} className={cls} />
            <input required type="number" min={1} max={12} placeholder="Exp month" value={card.exp_month}
              data-testid="card-exp-month" onChange={(e) => setCard({ ...card, exp_month: e.target.value })} className={cls} />
            <input required type="number" min={2026} placeholder="Exp year" value={card.exp_year}
              data-testid="card-exp-year" onChange={(e) => setCard({ ...card, exp_year: e.target.value })} className={cls} />
            <label className="flex items-center gap-2 text-xs text-slate-600 sm:col-span-2">
              <input type="checkbox" checked={card.autopay} data-testid="card-autopay"
                onChange={(e) => setCard({ ...card, autopay: e.target.checked })} />
              Charge this card automatically when a companion accepts and my wallet is short.
            </label>
            <button data-testid="card-save"
              className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white sm:col-span-2 sm:w-fit">
              Save card
            </button>
          </form>
        )}
        <p className="mt-3 text-[11px] text-slate-400">We store only the brand, last four digits and expiry — never the full number.</p>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6" data-testid="auto-reload-section">
        <p className="font-bold">Auto reload</p>
        <p className="mt-1 text-sm text-slate-500">Top the wallet back up from your saved card whenever it runs low.</p>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={reload.enabled} data-testid="auto-reload-enabled"
              onChange={(e) => setReload({ ...reload, enabled: e.target.checked })} />
            Enabled
          </label>
          <label className="text-sm">
            <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">When balance drops below</span>
            <input type="number" min={0} value={reload.threshold} data-testid="auto-reload-threshold"
              onChange={(e) => setReload({ ...reload, threshold: e.target.value })} className={`${cls} mt-1 w-40`} />
          </label>
          <label className="text-sm">
            <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">Add this much</span>
            <input type="number" min={500} value={reload.amount} data-testid="auto-reload-amount"
              onChange={(e) => setReload({ ...reload, amount: e.target.value })} className={`${cls} mt-1 w-40`} />
          </label>
          <button onClick={saveReload} data-testid="auto-reload-save"
            className="rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">Save</button>
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <p className="font-bold">Recent activity</p>
        {data.entries.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500" data-testid="wallet-empty">Nothing here yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100" data-testid="wallet-ledger">
            {data.entries.map((e, i) => (
              <li key={i} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-semibold">{e.reason || e.type}</p>
                  <p className="text-xs text-slate-400">{fmtDate(e.created_at)}</p>
                </div>
                <p className={`text-sm font-bold ${e.amount < 0 ? "text-rose-600" : "text-emerald-600"}`}>
                  {e.amount < 0 ? "−" : "+"}{money(Math.abs(e.amount))}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

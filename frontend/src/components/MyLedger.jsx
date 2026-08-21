import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Download, FileText } from "lucide-react";
import { api, errMsg, fmtDate, money } from "@/lib/api";
import { Spinner, Empty, Badge, statusTone } from "@/components/Shared";

export const downloadInvoicePdf = async (id, label) => {
  try {
    const { data } = await api.get(`/orders/${id}/invoice.pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${label || "buddilio-invoice"}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success("PDF downloaded.");
  } catch (e) { toast.error(errMsg(e)); }
};

const Card = ({ label, value, testid }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-4">
    <p className="text-[11px] uppercase tracking-widest text-slate-400">{label}</p>
    <p className="mt-1.5 text-xl font-display font-bold" data-testid={testid}>{value}</p>
  </div>
);

export const MyLedger = ({ compact = false }) => {
  const [d, setD] = useState(null);
  const [kind, setKind] = useState("");

  const load = useCallback(() => {
    api.get("/me/ledger", { params: { kind } }).then(({ data }) => setD(data))
      .catch((e) => { toast.error(errMsg(e)); setD({ payments: [], credits: [], earnings: [], totals: {}, kinds: {} }); });
  }, [kind]);
  useEffect(() => { load(); }, [load]);

  if (!d) return <Spinner label="Loading your ledger" />;
  const t = d.totals || {};
  const payments = compact ? (d.payments || []).slice(0, 5) : (d.payments || []);

  return (
    <div className="space-y-6" data-testid="my-ledger">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card label={`Total paid (in ${d.currency || "USD"})`} value={money(t.paid || 0)} testid="my-ledger-paid" />
        <Card label="Buddilio credit" value={money(t.credit_balance || 0)} testid="my-ledger-credit" />
        <Card label="You've earned" value={money(t.earned || 0)} testid="my-ledger-earned" />
        <Card label="Earnings pending" value={money(t.earned_pending || 0)} testid="my-ledger-earned-pending" />
      </div>

      {!compact && (
        <div className="flex flex-wrap items-center gap-2">
          <select value={kind} data-testid="my-ledger-kind" onChange={(e) => setKind(e.target.value)}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
            <option value="">All payment types</option>
            {Object.entries(d.kinds || {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
      )}

      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Date</th><th className="px-4 py-3">Document</th>
              <th className="px-4 py-3">What for</th><th className="px-4 py-3 text-right">Amount</th>
              <th className="px-4 py-3">Status</th><th className="px-4 py-3 text-right">Invoice</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100" data-testid="my-ledger-payments">
            {payments.map((p) => (
              <tr key={p.id} data-testid={`my-ledger-row-${p.id}`}>
                <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{fmtDate(p.date)}</td>
                <td className="px-4 py-3">
                  <p className="font-mono text-xs">{p.receipt || p.reference}</p>
                  <p className="text-[11px] text-slate-400">{p.template}</p>
                </td>
                <td className="px-4 py-3">
                  <p className="font-semibold">{p.description || p.kind_label}</p>
                  <p className="text-xs text-slate-500">{p.kind_label}</p>
                </td>
                <td className="px-4 py-3 text-right font-semibold whitespace-nowrap">{money(p.amount, p.currency)}</td>
                <td className="px-4 py-3"><Badge tone={statusTone(p.status)}>{p.status}</Badge></td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-3 whitespace-nowrap">
                    <Link to={`/invoice/${p.id}`} data-testid={`my-ledger-view-${p.id}`}
                      className="inline-flex items-center gap-1 text-xs font-bold text-slate-700 hover:underline">
                      <FileText className="h-3.5 w-3.5" />View
                    </Link>
                    <button onClick={() => downloadInvoicePdf(p.id, p.receipt || p.reference)}
                      data-testid={`my-ledger-pdf-${p.id}`}
                      className="inline-flex items-center gap-1 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-bold text-white">
                      <Download className="h-3.5 w-3.5" />{p.receipt ? "Receipt PDF" : "Invoice PDF"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!payments.length && <div className="p-8"><Empty testid="my-ledger-empty" title="No payments yet"
          sub="Every membership, ticket, hangout, wallet top-up and travel booking you pay for shows up here with its invoice." /></div>}
      </div>

      {!compact && (d.credits || []).length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="my-ledger-credits">
          <p className="font-bold">Buddilio credit</p>
          <div className="mt-3 divide-y divide-slate-100 text-sm">
            {d.credits.map((c, i) => (
              <div key={i} className="flex items-center justify-between gap-4 py-2.5" data-testid={`my-ledger-credit-${i}`}>
                <span className="text-slate-500">{fmtDate(c.date)} · {c.reason || c.type}</span>
                <span className={`font-semibold ${c.amount < 0 ? "text-rose-600" : "text-emerald-600"}`}>
                  {c.amount < 0 ? "−" : "+"}{money(Math.abs(c.amount))}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!compact && (d.earnings || []).length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="my-ledger-earnings">
          <p className="font-bold">Money we owe you</p>
          <div className="mt-3 divide-y divide-slate-100 text-sm">
            {d.earnings.map((e) => (
              <div key={e.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5" data-testid={`my-ledger-earning-${e.id}`}>
                <div>
                  <p className="font-semibold">{e.description || e.kind}</p>
                  <p className="text-xs text-slate-500">{fmtDate(e.date)} · {e.reference} · fee {money(e.fee, e.currency)}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold">{money(e.net, e.currency)}</p>
                  <Badge tone={statusTone(e.status)}>{e.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {compact && (
        <Link to="/ledger" data-testid="my-ledger-see-all"
          className="inline-flex items-center gap-1.5 text-sm font-bold border-b-2 border-slate-900 pb-0.5">
          See all payments &amp; invoices
        </Link>
      )}
    </div>
  );
};

export default function LedgerPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 pb-28" data-testid="my-ledger-page">
      <p className="overline">Your money</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Payments &amp; ledger</h1>
      <p className="mt-2 text-sm text-slate-500 max-w-xl">
        Every payment you've made, credit you hold and payout we owe you — with a downloadable invoice or receipt
        against each line.
      </p>
      <div className="mt-8"><MyLedger /></div>
    </div>
  );
}

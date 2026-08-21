import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileText } from "lucide-react";
import { api, errMsg, fmtDate, money } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";
import { downloadInvoicePdf } from "@/components/MyLedger";

const cls = "rounded-xl border border-slate-200 px-3 py-2 text-sm";

export const Ledger = () => {
  const [data, setData] = useState(null);
  const [f, setF] = useState({ frm: "", to: "", kind: "", direction: "all", q: "", status: "", page: 1 });

  const load = useCallback(() => {
    api.get("/admin/ledger", { params: f }).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [], totals: {}, kinds: {} }); });
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const exportCsv = async () => {
    try {
      const { data: blob } = await api.get("/admin/ledger/export", { params: f, responseType: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "buddilio-ledger.csv";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Exported — opens in Excel.");
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;
  const t = data.totals || {};

  return (
    <div className="space-y-6" data-testid="ledger-panel">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[["Collected", t.collected, "collected"], ["Our commission", t.commission, "commission"],
          ["Tax collected", t.tax, "tax"], ["Payouts pending", t.payouts_pending, "pending"],
          ["Payouts paid", t.payouts_paid, "paid"]].map(([label, value, key]) => (
          <div key={key} className="rounded-2xl border border-slate-200 bg-white p-4">
            <p className="text-[11px] uppercase tracking-widest text-slate-400">{label}</p>
            <p className="mt-1.5 text-xl font-bold" data-testid={`ledger-total-${key}`}>{money(value || 0, data?.currency)}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <input type="date" value={f.frm} data-testid="ledger-from" onChange={(e) => setF({ ...f, frm: e.target.value, page: 1 })} className={cls} />
        <input type="date" value={f.to} data-testid="ledger-to" onChange={(e) => setF({ ...f, to: e.target.value, page: 1 })} className={cls} />
        <select value={f.direction} data-testid="ledger-direction" onChange={(e) => setF({ ...f, direction: e.target.value, page: 1 })} className={cls}>
          <option value="all">Money in &amp; out</option>
          <option value="in">Money in</option>
          <option value="out">Payouts out</option>
        </select>
        <select value={f.kind} data-testid="ledger-kind" onChange={(e) => setF({ ...f, kind: e.target.value, page: 1 })} className={cls}>
          <option value="">All types</option>
          {Object.entries(data.kinds || {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <input value={f.q} placeholder="Client, email or ref" data-testid="ledger-search"
          onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} className={`${cls} w-48`} />
        <button onClick={exportCsv} data-testid="ledger-export"
          className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">
          <Download className="h-3.5 w-3.5" />Export to Excel
        </button>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Date</th><th className="px-4 py-3">Reference</th>
              <th className="px-4 py-3">Type</th><th className="px-4 py-3">Client</th>
              <th className="px-4 py-3 text-right">Gross</th><th className="px-4 py-3 text-right">Commission</th>
              <th className="px-4 py-3 text-right">Payout</th><th className="px-4 py-3">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100" data-testid="ledger-rows">
            {data.items.map((r) => (
              <tr key={`${r.direction}-${r.id}`} data-testid={`ledger-row-${r.id}`}>
                <td className="px-4 py-3 text-xs text-slate-500">{fmtDate(r.date)}</td>
                <td className="px-4 py-3 font-mono text-xs">{r.reference}</td>
                <td className="px-4 py-3">{r.kind_label}
                  <span className={`ml-1.5 text-[10px] font-bold ${r.direction === "in" ? "text-emerald-600" : "text-rose-600"}`}>
                    {r.direction === "in" ? "IN" : "OUT"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <p className="font-semibold">{r.client}</p>
                  <p className="text-xs text-slate-500">{r.email || r.description}</p>
                </td>
                <td className="px-4 py-3 text-right font-semibold">{money(r.gross, r.currency)}</td>
                <td className="px-4 py-3 text-right">{money(r.commission, r.currency)}</td>
                <td className="px-4 py-3 text-right">{money(r.payout, r.currency)}</td>
                <td className="px-4 py-3"><Badge tone={r.status === "paid" ? "green" : r.status === "pending" ? "amber" : "slate"}>{r.status}</Badge></td>
                <td className="px-4 py-3">
                  {r.direction === "in" && (
                    <div className="flex items-center gap-3 whitespace-nowrap">
                      <a href={`/invoice/${r.id}`} target="_blank" rel="noreferrer" data-testid={`ledger-invoice-${r.id}`}
                        className="inline-flex items-center gap-1 text-xs font-bold text-slate-700 hover:underline">
                        <FileText className="h-3.5 w-3.5" />Invoice
                      </a>
                      <button onClick={() => downloadInvoicePdf(r.id, r.reference)} data-testid={`ledger-invoice-pdf-${r.id}`}
                        className="inline-flex items-center gap-1 text-xs font-bold text-pink-700 hover:underline">
                        <Download className="h-3.5 w-3.5" />PDF
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span data-testid="ledger-count">{data.total} entries</span>
        <span className="flex gap-2">
          <button disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="ledger-prev"
            className="rounded-full border border-slate-200 px-4 py-2 font-bold disabled:opacity-40">Prev</button>
          <button disabled={f.page * 50 >= data.total} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="ledger-next"
            className="rounded-full border border-slate-200 px-4 py-2 font-bold disabled:opacity-40">Next</button>
        </span>
      </div>
      <p className="text-[11px] text-slate-400">Every entry is generated from a real order or payout — nothing is typed in by hand.</p>
    </div>
  );
};

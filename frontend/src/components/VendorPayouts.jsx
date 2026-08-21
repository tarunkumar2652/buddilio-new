import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Badge, Empty, Spinner } from "@/components/Shared";

const money = (v, c) => `${c || "USD"} ${Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
const lastMonth = () => {
  const d = new Date();
  d.setDate(0);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export const VendorPayouts = () => {
  const [view, setView] = useState("settlements");
  const [data, setData] = useState(null);
  const [batches, setBatches] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [scores, setScores] = useState([]);
  const [period, setPeriod] = useState(lastMonth());
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      api.get("/admin/vendor-settlements"),
      api.get("/admin/vendor-payout-runs"),
      api.get("/admin/vendor-commission-invoices"),
      api.get("/admin/vendor-scorecards"),
    ]).then(([s, b, i, sc]) => {
      setData(s.data); setBatches(b.data.items); setInvoices(i.data.items); setScores(sc.data.items);
    }).catch((e) => { toast.error(errMsg(e)); setData({ items: [], totals: {} }); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const runBatches = async () => {
    setBusy(true);
    try {
      const { data: r } = await api.post("/admin/vendor-payout-runs", { due_only: true });
      if (!r.created.length && !r.skipped.length) toast.info("Nothing is due right now.");
      else toast.success(`${r.created.length} batch(es) created${r.skipped.length ? `, ${r.skipped.length} vendor(s) skipped (on hold)` : ""}.`);
      r.skipped.forEach((s) => toast.warning(`${s.vendor}: ${s.reason}`));
      setView("batches"); load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const markPaid = async (b) => {
    const utr = window.prompt(`Bank UTR / transfer reference for ${b.batch_no} (${money(b.net, b.currency)})`);
    if (!utr) return;
    try { await api.post(`/admin/vendor-payout-runs/${b.id}/paid`, { utr }); toast.success("Batch settled."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const paySingle = async (s) => {
    const utr = window.prompt(`Bank UTR for ${s.order_no} (${money(s.net, s.currency)})`);
    if (!utr) return;
    try { await api.post(`/admin/vendor-settlements/${s.id}/paid`, { utr }); toast.success("Settlement marked paid."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const generateInvoices = async () => {
    setBusy(true);
    try {
      const { data: r } = await api.post(`/admin/vendor-commission-invoices/generate?period=${period}`);
      toast.success(r.created.length ? `${r.created.length} invoice(s) generated for ${r.period}.` : `Nothing to invoice for ${r.period}.`);
      setView("invoices"); load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const download = async (id, name) => {
    try {
      const res = await api.get(`/vendor-commission-invoices/${id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${name}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const exportCsv = async (b) => {
    try {
      const res = await api.get(`/admin/vendor-payout-runs/${b.id}/export`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${b.batch_no}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;
  const t = data.totals || {};
  const tabs = [["settlements", "Settlements"], ["batches", "Payout runs"],
                ["invoices", "Commission invoices"], ["scores", "Scorecards"]];

  return (
    <div className="space-y-5" data-testid="vendor-payouts-panel">
      <div className="grid gap-3 sm:grid-cols-4">
        {[["Due", t.due], ["In a batch", t.batched], ["Paid", t.paid], ["Commission earned", t.commission]].map(([l, v]) => (
          <div key={l} className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="overline">{l}</p>
            <p className="mt-1.5 font-display text-xl font-bold">{money(v, t.currency)}</p>
          </div>
        ))}
      </div>
      {data.held > 0 && (
        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold" data-testid="payouts-held-note">
          {data.held} vendor(s) are on payout hold and are skipped by payout runs.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {tabs.map(([v, l]) => (
          <button key={v} onClick={() => setView(v)} data-testid={`payouts-tab-${v}`}
            className={`rounded-full px-4 py-2 text-xs font-bold ${view === v ? "bg-slate-900 text-white" : "border border-slate-200"}`}>{l}</button>
        ))}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button onClick={runBatches} disabled={busy} data-testid="payouts-run-batches"
            className="rounded-full bg-brand-magenta px-5 py-2 text-xs font-bold text-white disabled:opacity-60">
            Run payout batch
          </button>
          <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="payouts-period"
            className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold" />
          <button onClick={generateInvoices} disabled={busy} data-testid="payouts-generate-invoices"
            className="rounded-full border border-slate-200 px-5 py-2 text-xs font-bold disabled:opacity-60">
            Generate commission invoices
          </button>
        </div>
      </div>

      {view === "settlements" && (
        <Table head={["Vendor", "Order", "Gross", "Net due", "Status", ""]} testid="settlements-table"
          rows={data.items.map((s) => [
            s.vendor?.legal_name || "—", s.order_no, money(s.gross, s.currency), money(s.net, s.currency),
            <Badge tone={s.status === "paid" ? "green" : s.status === "batched" ? "blue" : "amber"}>{s.status}</Badge>,
            s.status !== "paid" && (
              <button onClick={() => paySingle(s)} data-testid={`settlement-pay-${s.id}`}
                className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Mark paid</button>
            ),
          ])} />
      )}

      {view === "batches" && (
        <Table head={["Batch", "Vendor", "Bookings", "Net", "UTR", "Status", ""]} testid="batches-table"
          rows={batches.map((b) => [
            b.batch_no, b.vendor_name, b.count, money(b.net, b.currency), b.utr || "—",
            <Badge tone={b.status === "paid" ? "green" : "amber"}>{b.status}</Badge>,
            <div className="flex gap-1.5">
              <button onClick={() => exportCsv(b)} data-testid={`batch-export-${b.id}`}
                className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Export</button>
              {b.status !== "paid" && (
                <button onClick={() => markPaid(b)} data-testid={`batch-paid-${b.id}`}
                  className="rounded-full bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-white">Enter UTR</button>
              )}
            </div>,
          ])} />
      )}

      {view === "invoices" && (
        <Table head={["Invoice", "Vendor", "Period", "Commission", "Platform fee", "Total", ""]} testid="commission-invoices-table"
          rows={invoices.map((i) => [
            i.invoice_no, i.vendor_name, i.period, money(i.commission, i.currency),
            money(i.platform_fee, i.currency), money(i.total, i.currency),
            <button onClick={() => download(i.id, i.invoice_no)} data-testid={`commission-pdf-${i.id}`}
              className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">PDF</button>,
          ])} />
      )}

      {view === "scores" && (
        <Table head={["Vendor", "Score", "Events", "Cancel rate", "Rating", "Complaints", "Flag"]} testid="scorecards-table"
          rows={scores.map((s) => [
            s.legal_name, <span className="font-display text-lg font-bold">{s.score}</span>, s.events,
            `${s.cancel_rate}%`, s.rating || "—", s.complaints,
            <Badge tone={s.flag === "green" ? "green" : s.flag === "amber" ? "amber" : "red"}>{s.flag}</Badge>,
          ])} />
      )}
    </div>
  );
};

const Table = ({ head, rows, testid }) => (
  rows.length === 0
    ? <Empty title="Nothing here yet" sub="Records appear as vendors take bookings." />
    : (
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white" data-testid={testid}>
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-[11px] font-bold uppercase tracking-wider text-slate-400">
            <tr>{head.map((h, i) => <th key={i} className="px-4 py-3">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j} className="px-4 py-3">{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    )
);

export default VendorPayouts;

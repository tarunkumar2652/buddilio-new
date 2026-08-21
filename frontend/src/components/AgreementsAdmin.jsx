import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, X } from "lucide-react";
import { api, errMsg, fmtDate, fileUrl, money } from "@/lib/api";
import { Spinner, Badge } from "@/components/Shared";
import { downloadAgreementPdf } from "@/pages/VendorAgreement";

const cls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const tone = (s) => ({ active: "green", approved: "green", pending_vendor_acceptance: "amber",
  amendment_pending: "amber", submitted: "amber", under_review: "amber", documents_required: "amber",
  suspended: "red", terminated: "red", rejected: "red", superseded: "slate" }[s] || "slate");

const F = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

const SCHEDULE_BLANK = {
  service_name: "", currency: "USD", vendor_net_rate: 20, pricing_floor: 20,
  commission_type: "percentage", commission_value: 20, commission_fixed: 0,
  platform_fee_percent: 10, platform_fee_fixed: 0, tax_percent: 18,
  dynamic_pricing_enabled: false, promotion_discount: 0, discount_funding: "buddilio",
  settlement_cycle: "T+7", cancellation_policy: "Free cancellation until 24 hours before the service",
  refund_responsibility: "vendor", payment_processing: "Borne by Buddilio", rate_policy: "none",
  effective_from: "", change_reason: "",
};

export const AgreementsAdmin = () => {
  const [meta, setMeta] = useState(null);
  const [vendors, setVendors] = useState(null);
  const [ags, setAgs] = useState([]);
  const [view, setView] = useState("vendors");
  const [sched, setSched] = useState(null);      // {vendor, agreement?} → schedule modal
  const [detail, setDetail] = useState(null);
  const [docs, setDocs] = useState(null);        // vendor → documents modal
  const [expiring, setExpiring] = useState([]);

  const load = useCallback(async () => {
    try {
      const [m, v, a] = await Promise.all([
        api.get("/vendor-agreements/meta"), api.get("/admin/vendor-profiles"), api.get("/admin/vendor-agreements"),
      ]);
      setMeta(m.data); setVendors(v.data.items); setAgs(a.data.items);
      api.get("/admin/vendor-documents/expiring?days=30")
        .then(({ data }) => setExpiring(data.items)).catch(() => setExpiring([]));
    } catch (e) { toast.error(errMsg(e)); setVendors([]); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setStatus = async (id, status, reason = "") => {
    try { await api.patch(`/admin/vendor-profiles/${id}/status`, { status, reason }); toast.success(`Vendor ${status}.`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!vendors || !meta) return <Spinner />;

  return (
    <div className="space-y-5" data-testid="agreements-admin">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Vendors &amp; agreements</h2>
          <p className="mt-1 text-sm text-slate-500">
            Approve vendors, set versioned commercial terms and track electronic acceptance.
          </p>
        </div>
        <div className="flex gap-2">
          {[["vendors", "Vendors"], ["agreements", "Agreements"]].map(([k, l]) => (
            <button key={k} onClick={() => setView(k)} data-testid={`agr-view-${k}`}
              className={`rounded-full border px-4 py-2 text-xs font-bold ${view === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white"}`}>{l}</button>
          ))}
        </div>
      </div>

      {expiring.length > 0 && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5" data-testid="expiring-docs">
          <p className="font-bold">{expiring.length} mandatory document{expiring.length === 1 ? "" : "s"} expiring within 30 days</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">
            {expiring.map((d) => (
              <li key={d.id} data-testid={`expiring-doc-${d.id}`}>
                <b>{d.vendor?.legal_name || "Vendor"}</b> · {d.doc_type.replace(/_/g, " ")} · expires {String(d.expires_on).slice(0, 10)}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-slate-500">
            Vendors are emailed 30, 7 and 1 day before. On expiry their listings pause automatically.
          </p>
        </div>
      )}

      {view === "vendors" && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3">Vendor</th><th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Status</th><th className="px-4 py-3">Docs</th>
                <th className="px-4 py-3">Agreement</th><th className="px-4 py-3">Commercials</th>
                <th className="px-4 py-3 text-right">Actions</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {vendors.map((v) => (
                <tr key={v.id} data-testid={`vendor-row-${v.id}`}>
                  <td className="px-4 py-3">
                    <p className="font-semibold">{v.legal_name}</p>
                    <p className="text-xs text-slate-500">{v.trade_name} · {v.email}</p>
                  </td>
                  <td className="px-4 py-3 text-xs">{meta.vendor_kinds[v.vendor_kind]}</td>
                  <td className="px-4 py-3"><Badge tone={tone(v.status)}>{v.status?.replace(/_/g, " ")}</Badge></td>
                  <td className="px-4 py-3"><Badge tone={v.documents_complete ? "green" : "amber"}>
                    {v.documents_complete ? "complete" : "pending"}</Badge>
                    {v.payout_hold && <p className="mt-1 text-[11px] font-bold text-red-600"
                      data-testid={`vendor-payout-hold-${v.id}`}>payouts held</p>}</td>
                  <td className="px-4 py-3 text-xs">
                    {v.agreement ? <>{v.agreement.agreement_number}<br /><Badge tone={tone(v.agreement.status)}>{v.agreement.status.replace(/_/g, " ")}</Badge></> : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {v.schedule ? `${money(v.schedule.vendor_net_rate || 0)} · ${v.schedule.commission_value}${v.schedule.commission_type === "percentage" ? "%" : ""} · fee ${v.schedule.platform_fee_percent}%` : "not set"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      {v.status !== "approved" && (
                        <button onClick={() => setStatus(v.id, "approved")} data-testid={`vendor-approve-${v.id}`}
                          className="rounded-full border border-emerald-200 px-3 py-1.5 text-[11px] font-bold text-emerald-700">Approve</button>
                      )}
                      <button onClick={() => setDocs(v)} data-testid={`vendor-docs-review-${v.id}`}
                        className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Review docs</button>
                      {v.payout_hold && (
                        <button onClick={async () => {
                          try {
                            await api.post(`/admin/vendor-profiles/${v.id}/bank-verify`,
                              { status: "approved", note: "New bank proof verified" });
                            toast.success("Bank details verified — payouts released."); load();
                          } catch (e) { toast.error(errMsg(e)); }
                        }} data-testid={`vendor-bank-verify-${v.id}`}
                          className="rounded-full border border-amber-300 px-3 py-1.5 text-[11px] font-bold text-amber-700">
                          Verify bank
                        </button>
                      )}
                      <button onClick={() => setStatus(v.id, "documents_required", "Please upload the missing documents.")}
                        data-testid={`vendor-docs-${v.id}`} className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">Ask docs</button>
                      <button onClick={() => setSched({ vendor: v, form: { ...SCHEDULE_BLANK } })}
                        data-testid={`vendor-schedule-${v.id}`} className="rounded-full bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-white">
                        {v.schedule ? "Amend terms" : "Set terms"}
                      </button>
                      <button onClick={() => setStatus(v.id, "suspended", "Compliance review")} data-testid={`vendor-suspend-${v.id}`}
                        className="rounded-full border border-red-200 px-3 py-1.5 text-[11px] font-bold text-red-600">Suspend</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!vendors.length && <p className="p-8 text-sm text-slate-500">No vendor profiles yet.</p>}
        </div>
      )}

      {view === "agreements" && (
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3">Agreement</th><th className="px-4 py-3">Vendor</th>
                <th className="px-4 py-3">Version</th><th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Commission</th><th className="px-4 py-3">Net / floor</th>
                <th className="px-4 py-3">Accepted</th><th className="px-4 py-3 text-right">Actions</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {ags.map((a) => (
                <tr key={a.id} data-testid={`agreement-row-${a.id}`}>
                  <td className="px-4 py-3 font-mono text-xs">{a.agreement_number}</td>
                  <td className="px-4 py-3">{a.vendor?.legal_name}<br />
                    <span className="text-xs text-slate-500">{a.vendor?.service_category}</span></td>
                  <td className="px-4 py-3">v{a.version}</td>
                  <td className="px-4 py-3"><Badge tone={tone(a.status)}>{a.status.replace(/_/g, " ")}</Badge></td>
                  <td className="px-4 py-3 text-xs">{a.commission_label}</td>
                  <td className="px-4 py-3 text-xs">{money(a.schedule?.vendor_net_rate || 0)} / {money(a.schedule?.pricing_floor || 0)}</td>
                  <td className="px-4 py-3 text-xs">{a.accepted_at ? `${fmtDate(a.accepted_at)}\n${a.accepted_by}` : "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-end gap-1.5">
                      <button onClick={() => setDetail(a.id)} data-testid={`agreement-view-${a.id}`}
                        className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">View</button>
                      <button onClick={() => downloadAgreementPdf(a.id, `${a.agreement_number}-v${a.version}`)}
                        data-testid={`agreement-pdf-${a.id}`}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">
                        <Download className="h-3 w-3" />PDF</button>
                      {!["superseded", "terminated"].includes(a.status) && (
                        <>
                          <button onClick={() => setSched({ vendor: a.vendor, agreementId: a.id, form: { ...SCHEDULE_BLANK, ...(a.schedule || {}), change_reason: "" } })}
                            data-testid={`agreement-amend-${a.id}`}
                            className="rounded-full bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-white">Amend</button>
                          <button onClick={async () => {
                            try { await api.post(`/admin/vendor-agreements/${a.id}/terminate`, { reason: "buddilio_decision", note: "" }); toast.success("Terminated."); load(); }
                            catch (e) { toast.error(errMsg(e)); }
                          }} data-testid={`agreement-terminate-${a.id}`}
                            className="rounded-full border border-red-200 px-3 py-1.5 text-[11px] font-bold text-red-600">Terminate</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!ags.length && <p className="p-8 text-sm text-slate-500">No agreements generated yet.</p>}
        </div>
      )}

      {sched && <ScheduleModal ctx={sched} meta={meta} onClose={() => setSched(null)} onSaved={load} />}
      {docs && <DocsModal vendor={docs} meta={meta} onClose={() => setDocs(null)} onSaved={load} />}
      {detail && <AgreementDetail id={detail} onClose={() => setDetail(null)} />}
    </div>
  );
};

const ScheduleModal = ({ ctx, meta, onClose, onSaved }) => {
  const [f, setF] = useState(ctx.form);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const amending = !!ctx.agreementId;

  const num = (k, v) => setF({ ...f, [k]: v === "" ? "" : Number(v) });
  const floorTooHigh = Number(f.pricing_floor) > Number(f.vendor_net_rate);

  const runPreview = useCallback(async () => {
    try {
      const { data } = await api.post("/admin/pricing/preview", {
        schedule: { ...f, vendor_net_rate: Number(f.vendor_net_rate) || 0, pricing_floor: Number(f.pricing_floor) || 0 },
        quantity: 1, dynamic_adjustment: Number(f.dynamic_preview || 0), discount: Number(f.promotion_discount) || 0,
      });
      setPreview(data.preview);
    } catch (e) { toast.error(errMsg(e)); }
  }, [f]);
  useEffect(() => { runPreview(); }, [runPreview]);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...f };
      if (amending) await api.post(`/admin/vendor-agreements/${ctx.agreementId}/amend`, body);
      else await api.post(`/admin/vendor-profiles/${ctx.vendor.id}/commercial-schedule`, body);
      toast.success(amending ? "New schedule version created — vendor asked to accept." : "Commercial terms set and agreement generated.");
      onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[80] overflow-y-auto bg-slate-900/60 p-4 sm:p-8" data-testid="schedule-modal">
      <div className="mx-auto w-full max-w-3xl space-y-5 rounded-2xl bg-white p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold">{amending ? "Amend commercial terms" : "Commercial schedule"}</h3>
            <p className="text-xs text-slate-500">{ctx.vendor?.legal_name}</p>
          </div>
          <button onClick={onClose} data-testid="schedule-close" className="rounded-full border border-slate-200 p-2"><X className="h-4 w-4" /></button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <F label="Service name (optional)"><input value={f.service_name} data-testid="sched-service"
            onChange={(e) => setF({ ...f, service_name: e.target.value })} className={cls} /></F>
          <F label="Currency"><input value={f.currency} data-testid="sched-currency"
            onChange={(e) => setF({ ...f, currency: e.target.value.toUpperCase() })} className={cls} /></F>
          <F label="Vendor net rate"><input type="number" min={0} step="any" value={f.vendor_net_rate}
            data-testid="sched-net-rate" onChange={(e) => num("vendor_net_rate", e.target.value)} className={cls} /></F>
          <F label="Pricing floor" hint="Vendor settlement never falls below this."><input type="number" min={0} step="any"
            value={f.pricing_floor} data-testid="sched-floor" onChange={(e) => num("pricing_floor", e.target.value)} className={cls} /></F>
          <F label="Commission type">
            <select value={f.commission_type} data-testid="sched-commission-type"
              onChange={(e) => setF({ ...f, commission_type: e.target.value })} className={cls}>
              {meta.commission_types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </F>
          <F label={f.commission_type === "fixed" ? "Commission amount" : "Commission %"}>
            <input type="number" min={0} step="any" value={f.commission_value} data-testid="sched-commission"
              onChange={(e) => num("commission_value", e.target.value)} className={cls} /></F>
          {f.commission_type === "hybrid" && (
            <F label="Plus fixed amount"><input type="number" min={0} step="any" value={f.commission_fixed}
              data-testid="sched-commission-fixed" onChange={(e) => num("commission_fixed", e.target.value)} className={cls} /></F>
          )}
          <F label="Customer platform fee %"><input type="number" min={0} step="any" value={f.platform_fee_percent}
            data-testid="sched-platform-fee" onChange={(e) => num("platform_fee_percent", e.target.value)} className={cls} /></F>
          <F label="Platform fee fixed add-on"><input type="number" min={0} step="any" value={f.platform_fee_fixed}
            data-testid="sched-platform-fee-fixed" onChange={(e) => num("platform_fee_fixed", e.target.value)} className={cls} /></F>
          <F label="Tax %"><input type="number" min={0} step="any" value={f.tax_percent} data-testid="sched-tax"
            onChange={(e) => num("tax_percent", e.target.value)} className={cls} /></F>
          <F label="Promotional discount"><input type="number" min={0} step="any" value={f.promotion_discount}
            data-testid="sched-discount" onChange={(e) => num("promotion_discount", e.target.value)} className={cls} /></F>
          <F label="Discount funded by">
            <select value={f.discount_funding} data-testid="sched-discount-funding"
              onChange={(e) => setF({ ...f, discount_funding: e.target.value })} className={cls}>
              {Object.entries(meta.discount_funding).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </F>
          <F label="Settlement cycle">
            <select value={f.settlement_cycle} data-testid="sched-settlement"
              onChange={(e) => setF({ ...f, settlement_cycle: e.target.value })} className={cls}>
              {meta.settlement_cycles.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </F>
          <F label="Refund responsibility">
            <select value={f.refund_responsibility} data-testid="sched-refund"
              onChange={(e) => setF({ ...f, refund_responsibility: e.target.value })} className={cls}>
              {Object.entries(meta.refund_responsibility).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </F>
          <F label="Rate policy" hint="Buddilio does not impose an unconditional price-parity rule.">
            <select value={f.rate_policy} data-testid="sched-rate-policy"
              onChange={(e) => setF({ ...f, rate_policy: e.target.value })} className={cls}>
              {Object.entries(meta.rate_policies).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </F>
          <F label="Effective from"><input type="datetime-local" value={(f.effective_from || "").slice(0, 16)}
            data-testid="sched-effective" onChange={(e) => setF({ ...f, effective_from: e.target.value })} className={cls} /></F>
          <F label="Dynamic pricing">
            <label className="mt-2 flex items-center gap-2 text-sm font-semibold">
              <input type="checkbox" checked={!!f.dynamic_pricing_enabled} data-testid="sched-dynamic"
                onChange={(e) => setF({ ...f, dynamic_pricing_enabled: e.target.checked })} />Enabled
            </label>
          </F>
          {f.dynamic_pricing_enabled && (
            <F label="Test a dynamic adjustment"><input type="number" step="any" value={f.dynamic_preview || 0}
              data-testid="sched-dynamic-preview" onChange={(e) => num("dynamic_preview", e.target.value)} className={cls} /></F>
          )}
        </div>
        <F label="Cancellation policy"><textarea rows={2} value={f.cancellation_policy} data-testid="sched-cancellation"
          onChange={(e) => setF({ ...f, cancellation_policy: e.target.value })} className={cls} /></F>
        {amending && (
          <F label="Reason for this amendment"><input value={f.change_reason} data-testid="sched-reason"
            onChange={(e) => setF({ ...f, change_reason: e.target.value })} className={cls} /></F>
        )}

        {preview && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5" data-testid="sched-preview">
            <p className="font-bold">Price preview</p>
            <div className="mt-3 grid gap-1.5 text-sm sm:grid-cols-2">
              <p>Vendor net rate: <b>{money(preview.vendor_net_rate || 0)}</b></p>
              <p>Commission: <b>{money(preview.commission || 0)}</b></p>
              <p>Platform fee: <b>{money(preview.platform_fee || 0)}</b></p>
              <p>Dynamic adjustment: <b>{money(preview.dynamic_adjustment || 0)}</b></p>
              <p>Customer discount: <b>{money(preview.discount || 0)}</b></p>
              <p>Tax: <b>{money(preview.tax || 0)}</b></p>
              <p className="text-base">Estimated customer price: <b data-testid="preview-customer-price">{money(preview.customer_price || 0)}</b></p>
              <p className="text-base">Vendor settlement: <b data-testid="preview-settlement">{money(preview.vendor_settlement || 0)}</b></p>
            </div>
          </div>
        )}

        {floorTooHigh && (
          <p className="rounded-xl bg-red-50 px-4 py-3 text-sm font-bold text-red-700" data-testid="sched-floor-warning">
            The pricing floor can't be higher than the vendor net rate.
          </p>
        )}

        <button disabled={busy || floorTooHigh} onClick={save} data-testid="schedule-save"
          className="rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : amending ? "Create new version & notify vendor" : "Publish terms & generate agreement"}
        </button>
      </div>
    </div>
  );
};

const DocsModal = ({ vendor, meta, onClose, onSaved }) => {
  const [d, setD] = useState(null);
  const load = useCallback(() => {
    api.get(`/admin/vendor-profiles/${vendor.id}/documents`).then(({ data }) => setD(data))
      .catch((e) => toast.error(errMsg(e)));
  }, [vendor.id]);
  useEffect(() => { load(); }, [load]);

  const review = async (id, status) => {
    let note = "";
    if (status === "rejected") {
      note = window.prompt("Why is this document being rejected? (the vendor sees this)",
        "Not acceptable — please upload a clearer document.") || "";
      if (!note.trim()) return;
    }
    try {
      await api.patch(`/admin/vendor-documents/${id}`, { status, note });
      toast.success(`Document ${status}.`); load(); onSaved();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="fixed inset-0 z-[80] overflow-y-auto bg-slate-900/60 p-4 sm:p-8" data-testid="vendor-docs-modal">
      <div className="mx-auto w-full max-w-2xl space-y-5 rounded-2xl bg-white p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold">Documents</h3>
            <p className="text-xs text-slate-500">{vendor.legal_name}</p>
          </div>
          <button onClick={onClose} data-testid="vendor-docs-close" className="rounded-full border border-slate-200 p-2"><X className="h-4 w-4" /></button>
        </div>
        {!d ? <Spinner /> : (
          <>
            <p className="text-sm text-slate-500">
              PAN and address proof plus one bank proof (cancelled cheque or bank statement) must be approved
              before a vendor can be activated or paid.
            </p>
            <div className="divide-y divide-slate-100">
              {meta.doc_types.map((t) => {
                const row = (d.items || []).find((x) => x.doc_type === t.key);
                return (
                  <div key={t.key} className="flex flex-wrap items-center gap-3 py-3" data-testid={`admin-doc-${t.key}`}>
                    <div className="min-w-[180px] flex-1">
                      <p className="text-sm font-semibold">{t.label}{t.required && <span className="ml-1 text-brand-magenta">*</span>}</p>
                      <p className="text-xs text-slate-500">
                        {row ? `${fmtDate(row.uploaded_at)}${row.expires_on ? ` · expires ${String(row.expires_on).slice(0, 10)}` : ""}` : "not uploaded"}
                        {row?.note ? ` · ${row.note}` : ""}
                      </p>
                    </div>
                    <Badge tone={row ? tone(row.status) : "slate"}>{row ? row.status : "missing"}</Badge>
                    {row && (
                      <div className="flex gap-1.5">
                        <a href={fileUrl(row.path)} target="_blank" rel="noreferrer" data-testid={`admin-doc-view-${t.key}`}
                          className="rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">View</a>
                        {row.status !== "approved" && (
                          <button onClick={() => review(row.id, "approved")} data-testid={`admin-doc-approve-${t.key}`}
                            className="rounded-full bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-white">Approve</button>
                        )}
                        {row.status !== "rejected" && (
                          <button onClick={() => review(row.id, "rejected")} data-testid={`admin-doc-reject-${t.key}`}
                            className="rounded-full border border-red-200 px-3 py-1.5 text-[11px] font-bold text-red-600">Reject</button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="text-sm font-bold" data-testid="vendor-docs-complete">
              Mandatory set: {d.complete ? "complete" : "incomplete"}
            </p>
          </>
        )}
      </div>
    </div>
  );
};

const AgreementDetail = ({ id, onClose }) => {
  const [d, setD] = useState(null);
  const [audit, setAudit] = useState([]);

  useEffect(() => {
    api.get(`/admin/vendor-agreements/${id}`).then(({ data }) => setD(data)).catch((e) => toast.error(errMsg(e)));
    api.get(`/admin/vendor-agreements/${id}/audit`).then(({ data }) => setAudit(data.items)).catch(() => setAudit([]));
  }, [id]);

  return (
    <div className="fixed inset-0 z-[80] overflow-y-auto bg-slate-900/60 p-4 sm:p-8" data-testid="agreement-detail">
      <div className="mx-auto w-full max-w-3xl space-y-5 rounded-2xl bg-white p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">{d?.agreement?.agreement_number} · v{d?.agreement?.version}</h3>
          <button onClick={onClose} data-testid="agreement-detail-close" className="rounded-full border border-slate-200 p-2"><X className="h-4 w-4" /></button>
        </div>
        {!d ? <Spinner /> : (
          <>
            <table className="w-full text-sm" data-testid="detail-commercial-rows">
              <tbody className="divide-y divide-slate-100">
                {d.commercial_rows.map(([k, v]) => (
                  <tr key={k}><td className="py-2 pr-4 text-slate-500">{k}</td><td className="py-2 font-semibold">{v}</td></tr>
                ))}
              </tbody>
            </table>
            {d.banking_rows?.length > 0 && (
              <div className="rounded-2xl border border-slate-200 p-4" data-testid="detail-banking">
                <p className="font-bold">Banking details for payment transfer</p>
                <table className="mt-2 w-full text-sm"><tbody className="divide-y divide-slate-100">
                  {d.banking_rows.map(([k, val]) => (
                    <tr key={k}><td className="py-1.5 pr-4 text-slate-500">{k}</td><td className="py-1.5 font-semibold">{val}</td></tr>
                  ))}
                </tbody></table>
              </div>
            )}
            {d.acceptance && (
              <div className="rounded-2xl border border-slate-200 p-4 text-sm" data-testid="detail-acceptance">
                <p className="font-bold">Acceptance record</p>
                <p className="mt-1 text-slate-600">{d.acceptance.accepted_by} · {fmtDate(d.acceptance.accepted_at)} · {d.acceptance.acceptance_method}</p>
                <p className="text-xs text-slate-500">IP {d.acceptance.ip_address} · {d.acceptance.otp_reference}</p>
                <p className="break-all text-xs text-slate-500">{d.acceptance.document_hash}</p>
              </div>
            )}
            <div>
              <p className="font-bold">Schedule versions</p>
              <div className="mt-2 divide-y divide-slate-100 text-sm" data-testid="detail-schedules">
                {d.schedules.map((s) => (
                  <div key={s.id} className="py-2">
                    v{s.version} · {s.status} · net {money(s.vendor_net_rate || 0)} · commission {s.commission_value}
                    {s.commission_type === "percentage" ? "%" : ""} · fee {s.platform_fee_percent}% · {s.settlement_cycle}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="font-bold">Audit trail</p>
              <div className="mt-2 max-h-56 divide-y divide-slate-100 overflow-y-auto text-xs" data-testid="detail-audit">
                {audit.map((a) => (
                  <div key={a.id} className="py-2">
                    <b>{a.action}</b> · {a.actor_name || a.actor_email || a.actor_id} · {fmtDate(a.created_at)}
                  </div>
                ))}
                {!audit.length && <p className="py-2 text-slate-500">No audit rows yet.</p>}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

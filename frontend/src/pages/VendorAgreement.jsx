import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileText, ShieldCheck } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";
import { Spinner, Badge, SEO } from "@/components/Shared";
import { ImageUpload } from "@/components/ImageUpload";

const cls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const tone = (s) => ({ active: "green", approved: "green", pending_vendor_acceptance: "amber",
  amendment_pending: "amber", submitted: "amber", under_review: "amber", documents_required: "amber",
  suspended: "red", terminated: "red", rejected: "red" }[s] || "slate");

const F = ({ label, hint, children }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

export const downloadAgreementPdf = async (id, label) => {
  try {
    const { data } = await api.get(`/vendor-agreements/${id}/pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url; a.download = `${label || "buddilio-vendor-agreement"}.pdf`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast.success("Agreement downloaded.");
  } catch (e) { toast.error(errMsg(e)); }
};

const BLANK = {
  legal_name: "", trade_name: "", vendor_kind: "organiser", contact_person: "", email: "", phone: "",
  registered_address: "", operating_address: "", pan: "", gstin: "", registration_details: "",
  bank_account_name: "", bank_account_number: "", bank_ifsc: "", service_category: "",
  service_description: "", city: "", country: "India", website: "", licenses: "",
};

export default function VendorAgreement() {
  const [meta, setMeta] = useState(null);
  const [data, setData] = useState(null);
  const [ag, setAg] = useState(null);
  const [terms, setTerms] = useState(null);
  const [history, setHistory] = useState(null);
  const [settle, setSettle] = useState(null);
  const [tab, setTab] = useState("profile");

  const load = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([api.get("/vendor-agreements/meta"), api.get("/vendor/profile")]);
      setMeta(m.data); setData(p.data);
      if (p.data.vendor) {
        const [a, t, h, s] = await Promise.all([
          api.get("/vendor/agreement").catch(() => ({ data: null })),
          api.get("/vendor/commercial-terms").catch(() => ({ data: null })),
          api.get("/vendor/agreement/history").catch(() => ({ data: null })),
          api.get("/vendor/settlements").catch(() => ({ data: null })),
        ]);
        setAg(a.data); setTerms(t.data); setHistory(h.data); setSettle(s.data);
      }
    } catch (e) { toast.error(errMsg(e)); setData({ vendor: null, documents: [] }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!data || !meta) return <Spinner label="Loading your vendor portal" />;
  const v = data.vendor;
  const agreement = ag?.agreement;
  const awaiting = agreement && ["pending_vendor_acceptance", "amendment_pending"].includes(agreement.status);

  const TABS = [["profile", "Business profile"], ["documents", "Documents"], ["agreement", "My agreement"],
    ["terms", "Commercial terms"], ["settlements", "Settlements"], ["history", "History"]];

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 pb-28" data-testid="vendor-agreement-page">
      <SEO title="Vendor agreement" />
      <p className="overline">Vendor portal</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">My Buddilio agreement</h1>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        <span data-testid="vendor-status"><Badge tone={tone(v?.status)}>{(v?.status || "not started").replace(/_/g, " ")}</Badge></span>
        {agreement && <span data-testid="agreement-status"><Badge tone={tone(agreement.status)}>{agreement.status.replace(/_/g, " ")}</Badge></span>}
        {agreement && <span className="font-mono text-xs text-slate-500" data-testid="agreement-number">
          {agreement.agreement_number} · v{agreement.version}</span>}
      </div>

      {awaiting && (
        <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5" data-testid="vendor-accept-banner">
          <p className="font-bold">
            {agreement.status === "amendment_pending"
              ? "Your Buddilio Commercial Terms have been updated. Please review and accept the revised terms."
              : "Your agreement is ready for acceptance."}
          </p>
          <button onClick={() => setTab("agreement")} data-testid="vendor-goto-accept"
            className="mt-3 rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">Review &amp; accept agreement</button>
        </div>
      )}

      <div className="mt-8 flex gap-2 overflow-x-auto no-scrollbar pb-1">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`vendor-tab-${k}`}
            className={`whitespace-nowrap rounded-full border px-4 py-2 text-xs font-bold ${
              tab === k ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white"}`}>{l}</button>
        ))}
      </div>

      <div className="mt-7">
        {tab === "profile" && <Profile vendor={v} meta={meta} onSaved={load} />}
        {tab === "documents" && <Documents docs={data.documents} meta={meta} vendor={v} onSaved={load} />}
        {tab === "agreement" && <AgreementView data={ag} onAccepted={load} />}
        {tab === "terms" && <Terms terms={terms} />}
        {tab === "settlements" && <Settlements data={settle} />}
        {tab === "history" && <History data={history} />}
      </div>
    </div>
  );
}

const Profile = ({ vendor, meta, onSaved }) => {
  const [f, setF] = useState({ ...BLANK, ...(vendor || {}) });
  const [busy, setBusy] = useState(false);
  const locked = ["approved", "suspended", "terminated"].includes(vendor?.status);

  const save = async (submit) => {
    setBusy(true);
    try {
      await api.post("/vendor/profile", f);
      if (submit) await api.post("/vendor/profile/submit");
      toast.success(submit ? "Sent to Buddilio for review." : "Saved.");
      onSaved();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5" data-testid="vendor-profile-form">
      <div className="grid gap-3 sm:grid-cols-2">
        <F label="Full legal name"><input value={f.legal_name} disabled={locked} data-testid="vendor-legal-name"
          onChange={(e) => setF({ ...f, legal_name: e.target.value })} className={cls} /></F>
        <F label="Business / trading name"><input value={f.trade_name} data-testid="vendor-trade-name"
          onChange={(e) => setF({ ...f, trade_name: e.target.value })} className={cls} /></F>
        <F label="Vendor type">
          <select value={f.vendor_kind} data-testid="vendor-kind" onChange={(e) => setF({ ...f, vendor_kind: e.target.value })} className={cls}>
            {Object.entries(meta.vendor_kinds).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </F>
        <F label="Contact person"><input value={f.contact_person} data-testid="vendor-contact"
          onChange={(e) => setF({ ...f, contact_person: e.target.value })} className={cls} /></F>
        <F label="Email"><input type="email" value={f.email} data-testid="vendor-email"
          onChange={(e) => setF({ ...f, email: e.target.value })} className={cls} /></F>
        <F label="Mobile"><input value={f.phone} data-testid="vendor-phone"
          onChange={(e) => setF({ ...f, phone: e.target.value })} className={cls} /></F>
        <F label="PAN"><input value={f.pan} disabled={locked} data-testid="vendor-pan"
          onChange={(e) => setF({ ...f, pan: e.target.value.toUpperCase() })} className={cls} /></F>
        <F label="GSTIN" hint="Leave blank if you're not registered."><input value={f.gstin} disabled={locked}
          data-testid="vendor-gstin" onChange={(e) => setF({ ...f, gstin: e.target.value.toUpperCase() })} className={cls} /></F>
        <F label="Service category"><input value={f.service_category} data-testid="vendor-category"
          onChange={(e) => setF({ ...f, service_category: e.target.value })} className={cls} /></F>
        <F label="City"><input value={f.city} data-testid="vendor-city"
          onChange={(e) => setF({ ...f, city: e.target.value })} className={cls} /></F>
        <F label="Business registration details"><input value={f.registration_details} data-testid="vendor-registration"
          onChange={(e) => setF({ ...f, registration_details: e.target.value })} className={cls} /></F>
        <F label="Website / social"><input value={f.website} data-testid="vendor-website"
          onChange={(e) => setF({ ...f, website: e.target.value })} className={cls} /></F>
        <F label="Bank account name"><input value={f.bank_account_name} data-testid="vendor-bank-name"
          onChange={(e) => setF({ ...f, bank_account_name: e.target.value })} className={cls} /></F>
        <F label="Bank account number"><input value={f.bank_account_number} data-testid="vendor-bank-account"
          onChange={(e) => setF({ ...f, bank_account_number: e.target.value })} className={cls} /></F>
        <F label="IFSC"><input value={f.bank_ifsc} data-testid="vendor-ifsc"
          onChange={(e) => setF({ ...f, bank_ifsc: e.target.value.toUpperCase() })} className={cls} /></F>
        <F label="Licences / permits held"><input value={f.licenses} data-testid="vendor-licenses"
          onChange={(e) => setF({ ...f, licenses: e.target.value })} className={cls} /></F>
      </div>
      <F label="Registered address"><textarea rows={2} value={f.registered_address} data-testid="vendor-reg-address"
        onChange={(e) => setF({ ...f, registered_address: e.target.value })} className={cls} /></F>
      <F label="Operating address"><textarea rows={2} value={f.operating_address} data-testid="vendor-op-address"
        onChange={(e) => setF({ ...f, operating_address: e.target.value })} className={cls} /></F>
      <F label="Service description"><textarea rows={3} value={f.service_description} data-testid="vendor-service-description"
        onChange={(e) => setF({ ...f, service_description: e.target.value })} className={cls} /></F>

      <div className="flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => save(false)} data-testid="vendor-profile-save"
          className="rounded-full border border-slate-200 px-5 py-2.5 text-xs font-bold">Save draft</button>
        <button disabled={busy} onClick={() => save(true)} data-testid="vendor-profile-submit"
          className="rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">Submit for review</button>
      </div>
    </div>
  );
};

const Documents = ({ docs, meta, vendor, onSaved }) => {
  const [type, setType] = useState("pan");
  const byType = Object.fromEntries((docs || []).map((d) => [d.doc_type, d]));

  const upload = async (path) => {
    try { await api.post("/vendor/documents", { doc_type: type, path }); toast.success("Uploaded for review."); onSaved(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="space-y-5" data-testid="vendor-documents">
      <p className="text-sm text-slate-500">
        PAN, bank proof and address proof are mandatory. Buddilio can't activate a vendor while a mandatory
        document is missing or expired.
      </p>
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <F label="Document type">
            <select value={type} data-testid="vendor-doc-type" onChange={(e) => setType(e.target.value)} className={cls}>
              {meta.doc_types.map((d) => <option key={d.key} value={d.key}>{d.label}{d.required ? " (required)" : ""}</option>)}
            </select>
          </F>
          <div className="flex items-end">
            <ImageUpload value="" onChange={upload} label="Upload document" testid="vendor-doc-upload" />
          </div>
        </div>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="px-4 py-3">Document</th><th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Uploaded</th><th className="px-4 py-3">Note</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {meta.doc_types.map((d) => {
              const row = byType[d.key];
              return (
                <tr key={d.key} data-testid={`vendor-doc-row-${d.key}`}>
                  <td className="px-4 py-3 font-semibold">{d.label}{d.required && <span className="ml-1 text-brand-magenta">*</span>}</td>
                  <td className="px-4 py-3"><Badge tone={row ? tone(row.status) : "slate"}>{row ? row.status : "not uploaded"}</Badge></td>
                  <td className="px-4 py-3 text-xs text-slate-500">{row ? fmtDate(row.uploaded_at) : "—"}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{row?.note || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {vendor?.status === "documents_required" && (
        <p className="text-sm font-bold text-amber-700" data-testid="vendor-docs-required">
          Buddilio has asked for more documents: {vendor.status_reason || "see the notes above"}.
        </p>
      )}
    </div>
  );
};

const CHECKS = [
  ["read_agreement", "I have read and understood the Buddilio Vendor Agreement."],
  ["authorised", "I confirm that I am authorized to accept this Agreement on behalf of the Vendor."],
  ["accept_commercials", "I agree to the Commercial Schedule, including the Vendor Net Rate, Pricing Floor, Buddilio Commission, settlement terms and applicable pricing rules."],
  ["consent_electronic", "I consent to electronic acceptance of this Agreement and understand that my acceptance will be recorded electronically."],
];

const AgreementView = ({ data, onAccepted }) => {
  const [ticks, setTicks] = useState({});
  const [stage, setStage] = useState("review");
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  if (!data?.agreement) return (
    <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500" data-testid="vendor-no-agreement">
      No agreement yet. Once Buddilio approves your profile and sets your commercial terms, your agreement
      appears here for acceptance.
    </div>
  );
  const { agreement, schedule, acceptance, commercial_rows: rows, sections, vendor } = data;
  const awaiting = ["pending_vendor_acceptance", "amendment_pending"].includes(agreement.status);
  const allTicked = CHECKS.every(([k]) => ticks[k]);

  const sendOtp = async () => {
    setBusy(true);
    try {
      const { data: r } = await api.post("/vendor/agreement/otp", { channel: "email" });
      setSentTo(r.sent_to); setStage("otp"); toast.success(`Code sent to ${r.sent_to}.`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const accept = async () => {
    setBusy(true);
    try {
      const { data: r } = await api.post("/vendor/agreement/accept", {
        otp, accepted_by: name, read_agreement: true, authorised: true,
        accept_commercials: true, consent_electronic: true,
      });
      setDone(r); setStage("done"); toast.success("Agreement accepted."); onAccepted();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (stage === "done" && done) return (
    <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-7" data-testid="vendor-accept-success">
      <ShieldCheck className="h-8 w-8 text-emerald-600" />
      <h2 className="mt-3 text-2xl font-bold">Agreement successfully accepted</h2>
      <div className="mt-3 space-y-1 text-sm">
        <p>Agreement ID: <b>{done.agreement_number}</b></p>
        <p>Version: <b>{done.version}</b></p>
        <p>Accepted on: <b>{fmtDate(done.accepted_at)}</b></p>
        <p>Accepted by: <b>{done.accepted_by}</b></p>
        <p>Method: <b>{done.method}</b></p>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <button onClick={() => downloadAgreementPdf(agreement.id, `${done.agreement_number}-v${done.version}`)}
          data-testid="vendor-download-executed" className="rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white">
          Download PDF
        </button>
        <a href="/vendor/agreement" className="rounded-full border border-slate-200 px-5 py-2.5 text-xs font-bold">Go to vendor dashboard</a>
      </div>
    </div>
  );

  return (
    <div className="space-y-6" data-testid="vendor-agreement-view">
      <div className="rounded-2xl border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="overline">Buddilio vendor agreement</p>
            <h2 className="mt-1.5 text-xl font-bold">{agreement.agreement_number} · v{agreement.version}</h2>
            <p className="mt-1 text-sm text-slate-500">
              Effective {String(agreement.effective_date || "").slice(0, 10)} · status {agreement.status.replace(/_/g, " ")}
            </p>
          </div>
          <button onClick={() => downloadAgreementPdf(agreement.id, `${agreement.agreement_number}-v${agreement.version}`)}
            data-testid="vendor-agreement-pdf"
            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">
            <Download className="h-3.5 w-3.5" />Download PDF
          </button>
        </div>

        <h3 className="mt-7 text-base font-bold">Vendor information</h3>
        <div className="mt-2 grid gap-1.5 text-sm text-slate-600 sm:grid-cols-2">
          <p>{vendor?.legal_name} {vendor?.trade_name && `(${vendor.trade_name})`}</p>
          <p>PAN {vendor?.pan || "—"} · GSTIN {vendor?.gstin || "not registered"}</p>
          <p>{vendor?.contact_person} · {vendor?.email}</p>
          <p>{vendor?.registered_address}</p>
        </div>

        <h3 className="mt-7 text-base font-bold">Commercial terms</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm" data-testid="vendor-commercial-table">
            <tbody className="divide-y divide-slate-100">
              {rows.map(([k, val]) => (
                <tr key={k}><td className="py-2.5 pr-4 text-slate-500">{k}</td><td className="py-2.5 font-semibold">{val}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="max-h-[520px] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6" data-testid="vendor-agreement-text">
        {sections.map(([title, paras], i) => (
          <section key={title} className="mb-6">
            <h3 className="text-base font-bold">{i + 1}. {title}</h3>
            {paras.map((p, n) => <p key={n} className="mt-2 text-sm leading-relaxed text-slate-600">{p}</p>)}
          </section>
        ))}
      </div>

      {acceptance && !awaiting && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="vendor-acceptance-record">
          <h3 className="text-base font-bold">Electronic acceptance record</h3>
          <div className="mt-2 grid gap-1.5 text-sm text-slate-600 sm:grid-cols-2">
            <p>Accepted by {acceptance.accepted_by}</p>
            <p>{fmtDate(acceptance.accepted_at)} ({acceptance.time_zone})</p>
            <p>Method {acceptance.acceptance_method} · {acceptance.otp_reference}</p>
            <p className="break-all">Hash {acceptance.document_hash}</p>
          </div>
        </div>
      )}

      {awaiting && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="vendor-acceptance-box">
          <h3 className="text-base font-bold">Acceptance</h3>
          {stage === "review" && (
            <>
              <div className="mt-4 space-y-3">
                {CHECKS.map(([k, label]) => (
                  <label key={k} className="flex gap-3 text-sm">
                    <input type="checkbox" className="mt-1" checked={!!ticks[k]} data-testid={`vendor-check-${k}`}
                      onChange={(e) => setTicks({ ...ticks, [k]: e.target.checked })} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <button disabled={!allTicked || busy} onClick={sendOtp} data-testid="vendor-send-otp"
                className="mt-5 rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white disabled:opacity-50">
                Review &amp; accept agreement — send code
              </button>
              {!allTicked && <p className="mt-2 text-xs text-slate-400">Tick all four confirmations to continue.</p>}
            </>
          )}
          {stage === "otp" && (
            <div className="mt-4 space-y-3 max-w-sm">
              <p className="text-sm text-slate-500">We emailed a 6-digit code to <b>{sentTo}</b>. It expires in 10 minutes.</p>
              <F label="Your full name (authorised signatory)"><input value={name} data-testid="vendor-accept-name"
                onChange={(e) => setName(e.target.value)} className={cls} /></F>
              <F label="Verification code"><input value={otp} inputMode="numeric" data-testid="vendor-otp"
                onChange={(e) => setOtp(e.target.value)} className={cls} /></F>
              <div className="flex gap-2">
                <button disabled={busy || !otp || !name.trim()} onClick={accept} data-testid="vendor-confirm-accept"
                  className="rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white disabled:opacity-50">
                  Confirm acceptance
                </button>
                <button onClick={sendOtp} data-testid="vendor-resend-otp"
                  className="rounded-full border border-slate-200 px-5 py-3 text-xs font-bold">Resend code</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const Terms = ({ terms }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="vendor-terms-panel">
    {terms?.schedule ? (
      <table className="w-full text-sm">
        <tbody className="divide-y divide-slate-100">
          {terms.rows.map(([k, v]) => (
            <tr key={k}><td className="py-2.5 pr-4 text-slate-500">{k}</td><td className="py-2.5 font-semibold">{v}</td></tr>
          ))}
        </tbody>
      </table>
    ) : <p className="text-sm text-slate-500">No active commercial schedule yet.</p>}
  </div>
);

const Settlements = ({ data }) => (
  <div className="space-y-4" data-testid="vendor-settlements">
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="overline">Settled</p><p className="mt-1 text-xl font-bold">₹{(data?.totals?.paid || 0).toLocaleString()}</p>
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <p className="overline">Pending</p><p className="mt-1 text-xl font-bold">₹{(data?.totals?.pending || 0).toLocaleString()}</p>
      </div>
    </div>
    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr><th className="px-4 py-3">Booking</th><th className="px-4 py-3 text-right">Customer paid</th>
            <th className="px-4 py-3 text-right">Commission</th><th className="px-4 py-3 text-right">Fees</th>
            <th className="px-4 py-3 text-right">Net to you</th><th className="px-4 py-3">Due</th>
            <th className="px-4 py-3">Status</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {(data?.items || []).map((r) => (
            <tr key={r.id} data-testid={`vendor-settlement-${r.id}`}>
              <td className="px-4 py-3 font-mono text-xs">{r.order_no}</td>
              <td className="px-4 py-3 text-right">₹{r.gross?.toLocaleString()}</td>
              <td className="px-4 py-3 text-right">₹{r.commission?.toLocaleString()}</td>
              <td className="px-4 py-3 text-right">₹{r.platform_fee?.toLocaleString()}</td>
              <td className="px-4 py-3 text-right font-semibold">₹{r.net?.toLocaleString()}</td>
              <td className="px-4 py-3 text-xs text-slate-500">{fmtDate(r.due_on)}</td>
              <td className="px-4 py-3"><Badge tone={r.status === "paid" ? "green" : "amber"}>{r.status}</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!(data?.items || []).length && <p className="p-8 text-sm text-slate-500">No settlements yet.</p>}
    </div>
  </div>
);

const History = ({ data }) => (
  <div className="space-y-5" data-testid="vendor-history">
    <Section title="Agreements" rows={(data?.agreements || []).map((a) => ({
      id: a.id, main: `${a.agreement_number} · v${a.version}`, sub: `${a.status.replace(/_/g, " ")} · effective ${String(a.effective_date).slice(0, 10)}`,
      action: <button onClick={() => downloadAgreementPdf(a.id, `${a.agreement_number}-v${a.version}`)}
        data-testid={`vendor-history-pdf-${a.id}`} className="inline-flex items-center gap-1 text-xs font-bold text-brand-magenta">
        <FileText className="h-3.5 w-3.5" />PDF</button>,
    }))} />
    <Section title="Commercial schedules" rows={(data?.schedules || []).map((s) => ({
      id: s.id, main: `Version ${s.version} · ${s.status}`,
      sub: `Net ₹${s.vendor_net_rate} · commission ${s.commission_value}${s.commission_type === "percentage" ? "%" : ""} · platform fee ${s.platform_fee_percent}% · ${s.settlement_cycle} · from ${String(s.effective_from).slice(0, 10)}`,
    }))} />
    <Section title="Acceptances" rows={(data?.acceptances || []).map((a) => ({
      id: a.id, main: `${a.accepted_by} · v${a.version}`,
      sub: `${fmtDate(a.accepted_at)} · ${a.acceptance_method} · ${a.otp_reference}`,
    }))} />
  </div>
);

const Section = ({ title, rows }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-5">
    <p className="font-bold">{title}</p>
    <div className="mt-3 divide-y divide-slate-100">
      {rows.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div><p className="text-sm font-semibold">{r.main}</p><p className="text-xs text-slate-500">{r.sub}</p></div>
          {r.action}
        </div>
      ))}
      {!rows.length && <p className="py-3 text-sm text-slate-500">Nothing yet.</p>}
    </div>
  </div>
);

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Spinner } from "@/components/Shared";

const PILL = "rounded-full px-4 py-2.5 text-xs font-bold";
const fm = (c, v) => `${c === "INR" ? "₹" : `${c || ""} `}${Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

/** Member cancellation sheet — shows the deduction breakdown before anything is cancelled. */
export const CancelBookingDialog = ({ order, onClose, onDone }) => {
  const [q, setQ] = useState(null);
  const [err, setErr] = useState("");
  const [prefer, setPrefer] = useState("refund");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const loadQuote = useCallback(() => {
    setErr("");
    api.get(`/me/orders/${order.id}/cancellation-quote`).then(({ data }) => setQ(data))
      .catch((e) => setErr(errMsg(e) || "We couldn't work out your refund just now."));
  }, [order.id]);
  useEffect(() => { loadQuote(); }, [loadQuote]);

  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/me/orders/${order.id}/cancel`, { reason, prefer });
      toast.success("Cancelled. Buddilio will settle the refundable amount shortly.");
      onDone();
      onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-end sm:items-center justify-center bg-slate-900/50 p-0 sm:p-6"
      data-testid="cancel-dialog" onClick={onClose}>
      <div className="w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}>
        <p className="text-xs font-bold uppercase tracking-widest text-brand-magenta">Cancel booking</p>
        <h3 className="mt-1 text-lg font-black text-slate-900">{order.item_name}</h3>
        {err ? (
          <div data-testid="cancel-error">
            <p className="mt-3 rounded-2xl bg-red-50 p-4 text-sm text-red-700">{err}</p>
            <p className="mt-2 text-xs text-slate-500">
              Nothing has been cancelled. Try again, or write to support and we'll sort it out.
            </p>
            <div className="mt-5 flex gap-2">
              <button onClick={loadQuote} data-testid="cancel-retry" className={`${PILL} flex-1 bg-slate-900 text-white`}>Try again</button>
              <button onClick={onClose} data-testid="cancel-dismiss" className={`${PILL} border border-slate-200`}>Close</button>
            </div>
          </div>
        ) : !q ? <div className="py-8"><Spinner /></div> : (
          <>
            <p className="mt-2 text-sm text-slate-500">{q.reason}</p>
            <dl className="mt-4 space-y-2 rounded-2xl bg-slate-50 p-4 text-sm" data-testid="cancel-breakdown">
              {[["Paid", fm(q.currency, q.paid)],
                ["Deduction", `${q.deduction_percent}%`],
                ["Refundable", fm(q.currency, q.refundable)]].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3">
                    <dt className="text-slate-500">{k}</dt><dd className="font-bold text-slate-900">{v}</dd>
                  </div>
                ))}
            </dl>
            {q.credit_option > 0 && (
              <div className="mt-3 flex gap-2">
                {[["refund", "Refund to card"], ["credit", `Credit ${fm(q.currency, q.credit_option)} (+10%)`]].map(([v, label]) => (
                  <button key={v} onClick={() => setPrefer(v)} data-testid={`cancel-prefer-${v}`}
                    className={`${PILL} flex-1 border ${prefer === v ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>
                    {label}
                  </button>
                ))}
              </div>
            )}
            <input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="cancel-reason"
              placeholder="Anything we should know? (optional)"
              className="mt-3 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
            <p className="mt-3 text-xs text-slate-500">Your pass stops working straight away. Membership fees are non-refundable.</p>
            <div className="mt-5 flex gap-2">
              <button onClick={submit} disabled={busy || !q.cancellable} data-testid="cancel-confirm"
                className={`${PILL} flex-1 bg-slate-900 text-white disabled:opacity-60`}>
                {busy ? "Cancelling…" : "Cancel booking"}
              </button>
              <button onClick={onClose} data-testid="cancel-dismiss" className={`${PILL} border border-slate-200`}>Keep it</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default CancelBookingDialog;

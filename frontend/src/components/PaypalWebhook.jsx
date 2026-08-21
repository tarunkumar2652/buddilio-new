import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Spinner } from "@/components/Shared";

/** Admin → Payments: creates the PayPal webhook so renewals/cancellations sync by themselves. */
export const PaypalWebhook = () => {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.get("/admin/paypal/webhook").then(({ data }) => setS(data)).catch(() => setS(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const setup = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/paypal/webhook/setup", {});
      toast.success(data.message);
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!s) return <div className="mb-5"><Spinner /></div>;
  const live = s.matches && s.webhook_id;
  return (
    <div className="mb-5 rounded-2xl border border-slate-200 bg-white p-5" data-testid="paypal-webhook-card">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-[240px] flex-1">
          <p className="overline">PayPal webhook · {s.env}</p>
          <p className="mt-1 flex items-center gap-2 text-sm font-bold text-slate-900" data-testid="paypal-webhook-state">
            {live ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertTriangle className="h-4 w-4 text-amber-500" />}
            {live ? "Connected — renewals and cancellations update on their own"
              : s.webhook_id ? "Webhook id saved, but PayPal has no matching subscription for this URL"
                : "Not connected — PayPal events are ignored until you connect it"}
          </p>
          <p className="mt-2 break-all text-xs text-slate-500">
            Notification URL: <span className="font-mono" data-testid="paypal-webhook-url">{s.url}</span>
          </p>
          {s.webhook_id && (
            <p className="mt-1 break-all text-xs text-slate-500">
              Webhook ID: <span className="font-mono" data-testid="paypal-webhook-id">{s.webhook_id}</span>
              {s.from_env ? " (from environment)" : ""}
            </p>
          )}
          {s.error && <p className="mt-2 text-xs font-semibold text-red-600" data-testid="paypal-webhook-error">{s.error}</p>}
          <p className="mt-2 text-xs text-slate-400">
            Subscribes to {s.events.length} events including subscription activated / cancelled / expired,
            payment completed and refunded.
          </p>
        </div>
        <button onClick={setup} disabled={busy} data-testid="paypal-webhook-setup"
          className="rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white disabled:opacity-60">
          {busy ? "Connecting…" : live ? "Re-sync events" : "Connect webhook"}
        </button>
      </div>
      {!s.error && !s.registered?.length && (
        <p className="mt-3 text-xs text-slate-400" data-testid="paypal-webhook-none">
          PayPal reports 0 webhooks on this account.
        </p>
      )}
      {!!s.registered?.length && (
        <details className="mt-4 text-xs text-slate-500" data-testid="paypal-webhook-registered">
          <summary className="cursor-pointer font-bold">Webhooks registered on this PayPal account ({s.registered.length})</summary>
          <ul className="mt-2 space-y-1">
            {s.registered.map((h) => (
              <li key={h.id} className="break-all font-mono">{h.id} · {h.url} · {h.events.length} events</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
};

export default PaypalWebhook;

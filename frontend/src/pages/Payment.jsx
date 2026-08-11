import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Spinner, SEO } from "@/components/Shared";
import { CheckCircle2, XCircle } from "lucide-react";

export function PaymentSuccess() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const sessionId = params.get("session_id");
  const [state, setState] = useState("checking");

  useEffect(() => {
    if (!sessionId) { setState("failed"); return; }
    let tries = 0;
    const tick = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") return setState("paid");
        if (["failed", "expired"].includes(data.payment_status)) return setState("failed");
      } catch (e) { /* keep polling */ }
      if (++tries > 15) return setState("slow");
      setTimeout(tick, 2000);
    };
    tick();
  }, [sessionId]);

  return (
    <div className="mx-auto max-w-lg px-4 py-24 text-center" data-testid="payment-success-page">
      <SEO title="Payment status" />
      {state === "checking" && <Spinner label="Confirming your payment with the bank" />}
      {state === "paid" && (
        <div data-testid="payment-paid">
          <CheckCircle2 className="h-14 w-14 mx-auto text-emerald-600" />
          <h1 className="mt-6 text-3xl font-bold">Payment confirmed</h1>
          <p className="mt-3 text-slate-600">We've emailed your receipt. Everything you bought is in your account.</p>
          <div className="mt-8 flex gap-3 justify-center">
            <Link to="/orders" className="rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">My orders</Link>
            <Link to="/dashboard" className="rounded-full border border-slate-200 px-6 py-3 text-sm font-bold">Dashboard</Link>
          </div>
        </div>
      )}
      {state === "slow" && (
        <div data-testid="payment-slow">
          <h1 className="text-2xl font-bold">Still confirming</h1>
          <p className="mt-3 text-slate-600">Your bank is taking a little longer. We'll email you the moment it clears — no need to pay again.</p>
          <Link to="/orders" className="mt-8 inline-block rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">Check my orders</Link>
        </div>
      )}
      {state === "failed" && (
        <div data-testid="payment-failed">
          <XCircle className="h-14 w-14 mx-auto text-red-500" />
          <h1 className="mt-6 text-3xl font-bold">Payment not completed</h1>
          <p className="mt-3 text-slate-600">No amount was captured. You can try again with another method.</p>
          <button onClick={() => nav("/passes")} className="mt-8 rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">Try again</button>
        </div>
      )}
    </div>
  );
}

export function PaymentCancel() {
  return (
    <div className="mx-auto max-w-lg px-4 py-24 text-center" data-testid="payment-cancel-page">
      <SEO title="Payment cancelled" />
      <XCircle className="h-14 w-14 mx-auto text-slate-400" />
      <h1 className="mt-6 text-3xl font-bold">Payment cancelled</h1>
      <p className="mt-3 text-slate-600">Your order is still pending — nothing was charged.</p>
      <Link to="/orders" className="mt-8 inline-block rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">View my orders</Link>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { Spinner, SEO } from "@/components/Shared";
import { CheckCircle2, XCircle } from "lucide-react";

export function PayPalReturn() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const orderId = params.get("order");
  const ppOrder = params.get("token");
  const [state, setState] = useState("capturing");
  const fired = useRef(false);

  useEffect(() => {
    if (!orderId) { setState("failed"); return; }
    if (fired.current) return;
    fired.current = true;
    api.post("/payments/paypal/capture", { order_id: orderId, paypal_order_id: ppOrder })
      .then(() => setState("paid"))
      .catch((e) => { toast.error(errMsg(e)); setState("failed"); });
  }, [orderId, ppOrder]);

  return (
    <div className="mx-auto max-w-lg px-4 py-24 text-center" data-testid="paypal-return-page">
      <SEO title="PayPal payment" />
      {state === "capturing" && <Spinner label="Confirming your PayPal payment" />}
      {state === "paid" && (
        <div data-testid="paypal-paid">
          <CheckCircle2 className="h-14 w-14 mx-auto text-emerald-600" />
          <h1 className="mt-6 text-3xl font-bold">Payment confirmed</h1>
          <p className="mt-3 text-slate-600">PayPal captured your payment and your order is complete. The receipt is in your email and your ledger.</p>
          <div className="mt-8 flex gap-3 justify-center">
            <Link to="/orders" className="rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold" data-testid="paypal-orders-link">My orders</Link>
            <Link to="/dashboard" className="rounded-full border border-slate-200 px-6 py-3 text-sm font-bold">Dashboard</Link>
          </div>
        </div>
      )}
      {state === "failed" && (
        <div data-testid="paypal-failed">
          <XCircle className="h-14 w-14 mx-auto text-red-500" />
          <h1 className="mt-6 text-3xl font-bold">Payment not completed</h1>
          <p className="mt-3 text-slate-600">Nothing was charged. Start again from the item you were buying and a fresh order will be created.</p>
          <div className="mt-8 flex gap-3 justify-center">
            <button onClick={() => nav("/passes")} className="rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">Browse passes</button>
            <Link to="/orders" className="rounded-full border border-slate-200 px-6 py-3 text-sm font-bold">My orders</Link>
          </div>
        </div>
      )}
    </div>
  );
}

export function PayPalSubscriptionReturn() {
  const [params] = useSearchParams();
  const subId = params.get("subscription_id");
  const [state, setState] = useState("checking");

  useEffect(() => {
    if (!subId) { setState("failed"); return; }
    let tries = 0;
    const tick = async () => {
      try {
        const { data } = await api.post("/payments/paypal/subscription/activate", { subscription_id: subId });
        if (data.membership) return setState("active");
      } catch (e) { /* keep polling — PayPal can lag a second */ }
      if (++tries > 8) return setState("slow");
      setTimeout(tick, 2000);
    };
    tick();
  }, [subId]);

  return (
    <div className="mx-auto max-w-lg px-4 py-24 text-center" data-testid="paypal-subscription-page">
      <SEO title="Membership" />
      {state === "checking" && <Spinner label="Activating your membership" />}
      {state === "active" && (
        <div data-testid="paypal-subscription-active">
          <CheckCircle2 className="h-14 w-14 mx-auto text-emerald-600" />
          <h1 className="mt-6 text-3xl font-bold">Membership active</h1>
          <p className="mt-3 text-slate-600">PayPal will renew it automatically each cycle, and you can cancel any time from your membership page.</p>
          <Link to="/membership" className="mt-8 inline-block rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold" data-testid="paypal-membership-link">View my membership</Link>
        </div>
      )}
      {state === "slow" && (
        <div data-testid="paypal-subscription-slow">
          <h1 className="text-2xl font-bold">Almost there</h1>
          <p className="mt-3 text-slate-600">PayPal is still confirming the first payment. Your membership switches on automatically — no need to pay again.</p>
          <Link to="/membership" className="mt-8 inline-block rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">Membership page</Link>
        </div>
      )}
      {state === "failed" && (
        <div data-testid="paypal-subscription-failed">
          <XCircle className="h-14 w-14 mx-auto text-red-500" />
          <h1 className="mt-6 text-3xl font-bold">Subscription not completed</h1>
          <p className="mt-3 text-slate-600">Nothing was charged. You can start again from the membership page.</p>
          <Link to="/membership" className="mt-8 inline-block rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold">Back to plans</Link>
        </div>
      )}
    </div>
  );
}

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

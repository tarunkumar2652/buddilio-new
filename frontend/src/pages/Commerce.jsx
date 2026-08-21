import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { Spinner, Empty, Badge, SEO } from "@/components/Shared";
import { Check, ShieldCheck, CreditCard, Smartphone, Building2, Globe } from "lucide-react";

/** Everything the plan unlocks, built from the live plan record so admin edits show up immediately. */
export const planFeatures = (p) => {
  const derived = [
    p.messages_per_week ? `${p.messages_per_week} messages a week` : "Unlimited messaging",
    p.premium_filters && "Premium discovery filters",
    p.hangouts_access && "Paid hangouts with companions",
    p.priority_access && "Priority event access",
    p.concierge_support && "Dedicated concierge support",
    p.discount_percent > 0 && `${p.discount_percent}% off every pass`,
  ].filter(Boolean);
  const key = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const seen = new Set(derived.map(key));
  // Hand-written extras survive unless they repeat a line the switches already produced.
  const extras = (p.benefits || []).filter((b) => {
    const k = key(b);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return [...derived, ...extras];
};

export function Membership() {
  const { user } = useAuth();
  const { fmt, code, list } = useCurrency();
  const nav = useNavigate();
  const [plans, setPlans] = useState(null);
  const [mine, setMine] = useState(null);
  const [cfg, setCfg] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/plans").then(({ data }) => setPlans(data.items)).catch(() => setPlans([]));
    api.get("/payments/config").then(({ data }) => setCfg(data)).catch(() => {});
    if (user) api.get("/me/membership").then(({ data }) => setMine(data.membership)).catch(() => {});
  }, [user]);

  const cancel = async () => {
    if (!window.confirm("Turn off auto-renewal? Your benefits stay active until the end of the paid period.")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/me/membership/cancel");
      toast.success(data.message);
      const { data: m } = await api.get("/me/membership");
      setMine(m.membership);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!plans) return <Spinner />;

  const symbol = list.find((c) => c.code === code)?.symbol || "";
  const priceFor = (p) => {
    const ov = p.price_overrides?.[code];
    return ov ? `${symbol}${Number(ov).toLocaleString()}` : fmt(p.price);
  };

  const pick = async (p, mode = "card") => {
    if (!user) return nav("/login");
    if (p.price === 0) return toast.success("You're already on Basic — it's free for every member.");
    if (mode === "subscribe" && cfg.subscriptions_via === "paypal") {
      setBusy(true);
      try {
        const { data } = await api.post("/payments/paypal/subscription",
          { plan_id: p.id, origin_url: window.location.origin });
        if (!data.approve_url) throw new Error("PayPal did not return a checkout link.");
        window.location.href = data.approve_url;
        return;
      } catch (e) { toast.error(errMsg(e) || e.message); setBusy(false); return; }
    }
    nav(`/checkout?kind=membership&id=${p.id}`);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="membership-page">
      <SEO title="Membership plans" description="Buddilio membership: discounts on passes, premium discovery filters and priority access." />
      <p className="overline">Membership</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Choose how you go out</h1>

      {mine && (
        <div className="mt-6 rounded-2xl bg-slate-900 text-white p-6 flex flex-wrap items-center justify-between gap-4" data-testid="current-membership">
          <div>
            <p className="overline text-slate-400">Your active plan</p>
            <p className="text-xl font-display font-bold mt-1">{mine.plan_name}</p>
          </div>
          <p className="text-sm text-slate-400">Renews / expires {new Date(mine.ends_at).toLocaleDateString(undefined)}</p>
          {mine.paypal_subscription_id && mine.auto_renews !== false && (
            <button onClick={cancel} disabled={busy} data-testid="cancel-membership-btn"
              className="rounded-full border border-white/30 px-5 py-2.5 text-xs font-bold disabled:opacity-60">
              Cancel auto-renewal
            </button>
          )}
          {mine.auto_renews === false && (
            <p className="text-xs font-bold text-amber-300" data-testid="membership-cancelled-note">
              Auto-renewal is off — benefits run until {new Date(mine.ends_at).toLocaleDateString(undefined)}
            </p>
          )}
        </div>
      )}

      <div className="mt-10 grid md:grid-cols-3 gap-6">
        {plans.map((p, i) => (
          <div key={p.id} data-testid={`plan-card-${p.id}`}
            className={`rounded-3xl p-8 border hover-lift ${i === 2 ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
            {i === 2 && <span className="overline text-slate-400">Best value</span>}
            <p className="font-display font-semibold text-2xl mt-1">{p.name}</p>
            <p className={`text-sm mt-2 ${i === 2 ? "text-slate-400" : "text-slate-500"}`}>{p.description}</p>
            <p className="mt-6 text-4xl font-display font-bold">{p.price === 0 ? "Free" : priceFor(p)}</p>
            <p className={`text-xs mt-1 ${i === 2 ? "text-slate-400" : "text-slate-500"}`}>for {p.duration_days} days{p.discount_percent > 0 && ` · ${p.discount_percent}% off all passes`}</p>
            {p.price_overrides?.[code] && (
              <p className={`text-[11px] mt-1 ${i === 2 ? "text-slate-400" : "text-slate-400"}`} data-testid={`plan-exact-${p.id}`}>
                Exact {code} price set by Buddilio
              </p>
            )}
            <ul className="mt-6 space-y-2.5 text-sm" data-testid={`plan-features-${p.id}`}>
              {planFeatures(p).map((b) => <li key={b} className="flex gap-2"><Check className="h-4 w-4 shrink-0 mt-0.5" />{b}</li>)}
            </ul>
            <button onClick={() => pick(p, "card")} disabled={busy} data-testid={`plan-cta-${p.id}`}
              className={`mt-8 w-full rounded-full py-3.5 text-sm font-bold disabled:opacity-60 ${i === 2 ? "bg-white text-slate-900" : "bg-slate-900 text-white"}`}>
              {p.price === 0 ? "Included free" : `Pay by card — ${p.duration_days} days`}
            </button>
            {p.price > 0 && cfg.subscriptions_via === "paypal" && (
              <>
                <button onClick={() => pick(p, "subscribe")} disabled={busy} data-testid={`plan-subscribe-${p.id}`}
                  className={`mt-3 w-full rounded-full border-2 py-3.5 text-sm font-bold disabled:opacity-60 ${i === 2 ? "border-white/40 text-white" : "border-[#003087] bg-[#ffc439] text-[#003087]"}`}>
                  {busy ? "Opening PayPal…" : "Subscribe with PayPal (auto-renews)"}
                </button>
                <p className={`mt-2 text-[11px] ${i === 2 ? "text-slate-300" : "text-slate-500"}`} data-testid={`plan-paypal-note-${p.id}`}>
                  Card payment needs no PayPal account and covers {p.duration_days} days.
                  Subscribing renews automatically in {cfg.paypal_currency || "USD"} and needs a PayPal
                  account — cancel any time.
                </p>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function useCurrencySymbol(code) {
  const { list } = useCurrency();
  return list.find((c) => c.code === code)?.symbol || "";
}


export function Passes() {
  const { user } = useAuth();
  const { fmt } = useCurrency();
  const nav = useNavigate();
  const [items, setItems] = useState(null);
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [meta, setMeta] = useState({ cities: [], countries: [] });

  useEffect(() => { api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, []);
  useEffect(() => { api.get("/products", { params: { city, country } }).then(({ data }) => setItems(data.items)).catch(() => setItems([])); }, [city, country]);

  const cityOptions = country ? (meta.countries || []).find((c) => c.name === country)?.cities || [] : meta.cities || [];

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="passes-page">
      <SEO title="Passes & products" description="Party passes, night passes, dining experiences and gift cards from Buddilio." />
      <p className="overline">Passes</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Buddilio passes</h1>
      <p className="mt-3 text-slate-600 max-w-2xl">One purchase, multiple nights out. Members get an extra discount at checkout.</p>

      <div className="mt-6 flex flex-wrap gap-3">
        <select data-testid="passes-country" value={country} onChange={(e) => { setCountry(e.target.value); setCity(""); }}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
          <option value="">All countries</option>{(meta.countries || []).map((c) => <option key={c.code} value={c.name}>{c.name}</option>)}
        </select>
        <select data-testid="passes-city" value={city} onChange={(e) => setCity(e.target.value)}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm">
          <option value="">{country ? `All cities in ${country}` : "All cities"}</option>{cityOptions.map((c) => <option key={c}>{c}</option>)}
        </select>
      </div>

      {!items ? <Spinner /> : items.length ? (
        <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {items.map((p) => {
            const final = p.price * (1 - p.discount_percent / 100);
            return (
              <div key={p.id} data-testid={`product-card-${p.id}`} className="rounded-2xl border border-slate-200 bg-white overflow-hidden hover-lift">
                <img src={fileUrl(p.image)} alt={p.name} loading="lazy" className="aspect-[16/10] w-full object-cover" />
                <div className="p-6">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-display font-semibold text-lg">{p.name}</h3>
                    {p.discount_percent > 0 && <Badge tone="green">{p.discount_percent}% off</Badge>}
                  </div>
                  <p className="mt-2 text-sm text-slate-500 leading-relaxed">{p.description}</p>
                  <div className="mt-4 flex items-baseline gap-2">
                    <p className="text-2xl font-display font-bold">{fmt(final)}</p>
                    {p.discount_percent > 0 && <p className="text-sm text-slate-400 line-through">{fmt(p.price)}</p>}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">Valid {p.validity_days} days · {p.city} · +{p.tax_percent}% tax</p>
                  <button onClick={() => user ? nav(`/checkout?kind=product&id=${p.id}`) : nav("/login")}
                    data-testid={`buy-product-${p.id}`} className="mt-5 w-full rounded-full bg-slate-900 text-white py-3 text-sm font-bold">
                    Buy pass
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : <div className="mt-8"><Empty title="No passes here yet" sub="Try All countries — many passes work worldwide." /></div>}
    </div>
  );
}

export function Checkout() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { code, list, fmt } = useCurrency();
  const kind = params.get("kind");
  const itemId = params.get("id");
  const [order, setOrder] = useState(null);
  const [coupon, setCoupon] = useState("");
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState("upi");
  const [cfg, setCfg] = useState({ razorpay_live: false, stripe_enabled: false });
  const [currency, setCurrency] = useState(code);
  const [useCredit, setUseCredit] = useState(true);
  const [balance, setBalance] = useState(0);

  useEffect(() => { api.get("/payments/config").then(({ data }) => setCfg(data)).catch(() => {}); }, []);

  const symbol = list.find((c) => c.code === currency)?.symbol || "";
  const amt = (n) => `${symbol}${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: currency === "INR" ? 0 : 2, maximumFractionDigits: currency === "INR" ? 0 : 2 })}`;

  const create = async (cur = currency, code2 = coupon, credit = useCredit) => {
    setBusy(true);
    try {
      const { data } = await api.post("/checkout", { kind, item_id: itemId, quantity: 1, coupon_code: code2, currency: cur, use_credit: credit });
      setOrder(data.order);
      setCurrency(data.order.currency);
      setBalance(data.credit_balance || 0);
      if (code2) toast.success("Coupon applied");
    } catch (e) { toast.error(errMsg(e)); if (!order) nav(-1); } finally { setBusy(false); }
  };

  useEffect(() => { if (kind && itemId) create(code, ""); /* eslint-disable-next-line */ }, [kind, itemId]);

  const done = () => nav(kind === "membership" ? "/membership" : kind === "event" ? `/events/${itemId}`
    : kind === "wallet" ? "/wallet"
    : kind === "companion" ? "/hangouts/bookings" : "/orders");

  const loadRazorpayScript = () => new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });

  const payRazorpay = async () => {
    setBusy(true);
    try {
      const ok = await loadRazorpayScript();
      if (!ok) throw new Error("Could not load the payment window. Check your connection.");
      const { data } = await api.post("/payments/razorpay/order", { order_id: order.id });
      const rz = new window.Razorpay({
        key: data.key_id, amount: data.amount, currency: data.currency,
        order_id: data.razorpay_order_id, name: "Buddilio", description: order.item_name,
        prefill: { name: user?.full_name, email: user?.email, contact: user?.mobile || "" },
        theme: { color: "#0F172A" },
        handler: async (res) => {
          try {
            await api.post("/payments/razorpay/verify", {
              order_id: order.id, razorpay_order_id: res.razorpay_order_id,
              razorpay_payment_id: res.razorpay_payment_id, razorpay_signature: res.razorpay_signature });
            toast.success("Payment successful");
            done();
          } catch (e) { toast.error(errMsg(e)); }
        },
        modal: { ondismiss: () => toast.error("Payment cancelled. Your order is still pending.") },
      });
      rz.on("payment.failed", (r) => toast.error(r?.error?.description || "Payment failed. Please try another method."));
      rz.open();
    } catch (e) { toast.error(errMsg(e) || e.message); } finally { setBusy(false); }
  };

  const payStripe = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/payments/stripe/session", { order_id: order.id, origin_url: window.location.origin });
      window.location.href = data.checkout_url;
    } catch (e) { toast.error(errMsg(e)); setBusy(false); }
  };

  const payPayPal = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/payments/paypal/order", { order_id: order.id, origin_url: window.location.origin });
      if (!data.approve_url) throw new Error("PayPal did not return a checkout link.");
      window.location.href = data.approve_url;
    } catch (e) { toast.error(errMsg(e) || e.message); setBusy(false); }
  };

  const paySim = async (simulate) => {
    setBusy(true);
    try {
      await api.post("/payments/verify", { order_id: order.id, simulate });
      toast.success("Payment successful");
      done();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  if (!order) return <Spinner label="Preparing your order" />;

  const isINR = currency === "INR";
  const canRazorpay = isINR && cfg.razorpay_live;
  const canStripe = !isINR && cfg.stripe_enabled;
  const canPaypal = cfg.paypal_enabled;

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 pb-28" data-testid="checkout-page">
      <SEO title="Checkout" />
      <h1 className="text-3xl font-bold">Checkout</h1>
      <p className="mt-2 text-sm text-slate-500">Order #{order.order_no}</p>

      <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-semibold">{order.item_name}</p>
          <span className="flex items-center gap-2 text-xs font-bold text-slate-600" data-testid="checkout-currency">
            <Globe className="h-4 w-4" />Billed in {order.currency}
          </span>
        </div>
        <div className="mt-5 space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-slate-500">Subtotal</span><span>{amt(order.charge_subtotal)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Discount</span><span className="text-emerald-600">− {amt(order.charge_discount)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">{order.tax_label || "Tax"}{order.tax_percent ? ` (${order.tax_percent}%)` : ""}</span><span>{amt(order.charge_tax)}</span></div>
          {order.credit_applied > 0 && (
            <div className="flex justify-between" data-testid="credit-line">
              <span className="text-slate-500">Buddilio credit</span>
              <span className="text-emerald-600">− {amt(order.charge_credit || order.credit_applied)}</span>
            </div>
          )}
          <div className="flex justify-between border-t border-slate-200 pt-3 font-bold text-base"><span>Total payable</span><span data-testid="order-total">{amt(order.charge_total)}</span></div>
          {order.currency !== code && (
            <p className="text-xs text-slate-400" data-testid="checkout-fx-hint">
              Charged in {order.currency} · about {fmt(order.total)} in {code}
            </p>
          )}
        </div>

        {(order.credit_applied > 0 || balance > 0) && (
          <label className="mt-5 flex items-start gap-3 rounded-xl bg-slate-50 p-4 text-sm" data-testid="use-credit-toggle">
            <input type="checkbox" checked={useCredit} data-testid="use-credit-checkbox"
              onChange={(e) => { setUseCredit(e.target.checked); create(currency, coupon, e.target.checked); }}
              className="mt-0.5 h-4 w-4" />
            <span>
              <span className="font-semibold">Use my Buddilio credit</span>
              <span className="block text-xs text-slate-500 mt-0.5">
                {order.credit_applied > 0
                  ? `${amt(order.charge_credit || order.credit_applied)} applied · ${amt(balance)} left in your wallet`
                  : `${fmt(balance)} available from referrals`}
              </span>
            </span>
          </label>
        )}

        <div className="mt-6 flex gap-2">
          <input data-testid="coupon-input" value={coupon} onChange={(e) => setCoupon(e.target.value.toUpperCase())} placeholder="Coupon code"
            className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm" />
          <button onClick={() => create(currency, coupon)} disabled={busy} data-testid="apply-coupon"
            className="rounded-xl border border-slate-900 px-5 py-2.5 text-sm font-bold">Apply</button>
        </div>
        <p className="text-xs text-slate-400 mt-2">Try BUDDY20 or FIRSTNIGHT</p>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <p className="overline">Before you pay</p>
        <p className="mt-2 text-sm text-slate-600" data-testid="checkout-notice">
          By completing this purchase, you confirm that you have reviewed the applicable price, service or
          event details and cancellation/refund terms.
        </p>
        {order.kind === "membership" && (
          <p className="mt-2 text-sm text-slate-600" data-testid="checkout-notice-membership">
            Please review the membership price, duration, benefits, renewal terms and cancellation/refund
            policy before completing your purchase.
          </p>
        )}
        {order.kind === "event" && (
          <p className="mt-2 text-sm text-slate-600" data-testid="checkout-notice-event">
            Please review the event date, venue, inclusions, exclusions, price and cancellation policy before
            completing your booking.
          </p>
        )}
        {["travel", "companion", "product"].includes(order.kind) && (
          <p className="mt-2 text-sm text-slate-600" data-testid="checkout-notice-vendor">
            This service is provided by the listed Vendor. Please review the Vendor's service details and
            applicable cancellation terms before completing your booking.
          </p>
        )}
        <p className="mt-3 text-xs text-slate-400">
          <a href="/p/refund" target="_blank" rel="noreferrer" className="underline" data-testid="checkout-refund-link">
            Cancellation &amp; Refund Policy</a>{" · "}
          <a href="/p/terms" target="_blank" rel="noreferrer" className="underline" data-testid="checkout-terms-link">
            Terms &amp; Conditions</a>
        </p>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6">
        <p className="overline">Payment method</p>
        {isINR ? (
          <div className="mt-4 grid sm:grid-cols-3 gap-3">
            {[["upi", "UPI", Smartphone], ["card", "Card", CreditCard], ["netbanking", "Net banking", Building2]].map(([v, l, Icon]) => (
              <button key={v} onClick={() => setMethod(v)} data-testid={`pay-method-${v}`}
                className={`rounded-xl border p-4 text-left ${method === v ? "border-slate-900 bg-slate-50" : "border-slate-200"}`}>
                <Icon className="h-5 w-5" /><p className="mt-2 text-sm font-semibold">{l}</p>
              </button>
            ))}
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-slate-900 bg-slate-50 p-4 flex items-center gap-3">
            <CreditCard className="h-5 w-5" />
            <div><p className="text-sm font-semibold">International card</p>
              <p className="text-xs text-slate-500">Visa, Mastercard, Amex and local wallets via Stripe</p></div>
          </div>
        )}
        <p className="mt-4 text-xs text-slate-500 flex items-start gap-2">
          <ShieldCheck className="h-4 w-4 shrink-0 mt-0.5" />
          {canStripe ? "Secured by Stripe. You'll be taken to a hosted payment page; we confirm the payment on our server before releasing your order."
            : canRazorpay ? "Secured by Razorpay. UPI, cards, net banking and wallets, all verified server-side."
            : canPaypal ? "Pay by debit or credit card through PayPal — no PayPal account needed. Every payment is verified on our server before your order is released."
            : "No payment method is available right now. Please contact support so we can complete this booking for you."}
        </p>
        {canStripe ? (
          <button onClick={payStripe} disabled={busy} data-testid="pay-stripe-btn"
            className="mt-6 w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold disabled:opacity-60">
            {busy ? "Opening secure checkout…" : `Pay ${amt(order.charge_total)} with card`}
          </button>
        ) : canRazorpay ? (
          <button onClick={payRazorpay} disabled={busy} data-testid="pay-razorpay-btn"
            className="mt-6 w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold disabled:opacity-60">
            {busy ? "Opening secure checkout…" : `Pay ${amt(order.charge_total)} with Razorpay`}
          </button>
        ) : cfg.simulation_enabled ? (
          <div className="mt-6 grid sm:grid-cols-2 gap-3">
            <button onClick={() => paySim("success")} disabled={busy} data-testid="pay-success-btn"
              className="rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold disabled:opacity-60">
              {busy ? "Processing…" : `Pay ${amt(order.charge_total)} (test mode)`}
            </button>
            <button onClick={() => paySim("failure")} disabled={busy} data-testid="pay-failure-btn"
              className="rounded-full border border-slate-200 py-3.5 text-sm font-bold text-slate-500">Simulate failed payment</button>
          </div>
        ) : null}
        {canPaypal && (
          <button onClick={payPayPal} disabled={busy} data-testid="pay-paypal-btn"
            className="mt-6 w-full rounded-full border-2 border-[#003087] bg-[#ffc439] py-3.5 text-sm font-bold text-[#003087] transition-transform hover:scale-[1.01] disabled:opacity-60">
            {busy ? "Opening PayPal…" : `Pay ${amt(order.charge_total)} by card or PayPal`}
          </button>
        )}
      </div>
      <Link to="/orders" className="mt-6 inline-block text-sm font-bold border-b-2 border-slate-900 pb-0.5">View my orders</Link>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Clock, Lock, MapPin, ShieldCheck, Search, Sparkles } from "lucide-react";
import { api, errMsg, fileUrl, fmtDate, money } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Spinner, Empty, Badge, SEO } from "@/components/Shared";

const cls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const L = ({ label, children }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>{children}</label>
);

const Locked = ({ message }) => (
  <div className="mx-auto max-w-2xl px-4 py-24 text-center" data-testid="hangouts-locked">
    <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-slate-900 text-white"><Lock className="h-6 w-6" /></span>
    <h1 className="mt-6 text-3xl font-bold">Hangouts are for premium members</h1>
    <p className="mt-3 text-slate-600">{message || "Upgrade to browse companions and book time with someone whose company you'll enjoy."}</p>
    <Link to="/membership" data-testid="hangouts-upgrade-cta"
      className="mt-8 inline-block rounded-full brand-gradient px-7 py-3.5 text-sm font-bold text-white">See membership plans</Link>
  </div>
);

const Terms = ({ text }) => (
  <p className="mt-4 flex gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900" data-testid="hangout-terms">
    <ShieldCheck className="h-4 w-4 shrink-0" />{text}
  </p>
);

export function Hangouts() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ q: "", city: "", max_rate: -1, sort: "rate" });
  const [data, setData] = useState(null);
  const [locked, setLocked] = useState("");

  const load = useCallback(() => {
    api.get("/companions", { params: { ...f, limit: 24 } })
      .then(({ data }) => setData(data))
      .catch((e) => { if (e.response?.status === 403) setLocked(errMsg(e)); else setData({ items: [] }); });
  }, [f]);
  useEffect(() => { if (!user) nav("/login"); else { const t = setTimeout(load, 250); return () => clearTimeout(t); } }, [load, user, nav]);

  if (locked) return <Locked message={locked} />;
  if (!data) return <Spinner label="Loading companions" />;

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="hangouts-page">
      <SEO title="Hangouts" description="Book time with a verified companion." />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline">Premium · Hangouts</p>
          <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Book someone's time</h1>
          <p className="mt-3 max-w-2xl text-slate-600">Verified members who are happy to be your plus-one for
            dinner, an event or a walk around town. You pay a small non-refundable request fee, they accept with
            their price, and the balance comes out of your wallet or card.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/hangouts/bookings" data-testid="my-bookings-link"
            className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">My bookings</Link>
          <Link to="/hangouts/host" data-testid="become-host-link"
            className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white">Offer hangouts</Link>
        </div>
      </div>
      <Terms text={data.terms} />

      <div className="mt-6 flex flex-wrap gap-3">
        <label className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input data-testid="hangouts-search" value={f.q} placeholder="Search by name or headline…"
            onChange={(e) => setF({ ...f, q: e.target.value })}
            className="w-full rounded-full border border-slate-200 pl-10 pr-4 py-2.5 text-sm" />
        </label>
        <input data-testid="hangouts-city" value={f.city} placeholder="City"
          onChange={(e) => setF({ ...f, city: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm w-40" />
        <select data-testid="hangouts-sort" value={f.sort}
          onChange={(e) => setF({ ...f, sort: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm">
          <option value="rating">Top rated</option>
          <option value="experience">Most experienced</option>
          <option value="rate">Price: low to high</option>
          <option value="rate_desc">Price: high to low</option>
        </select>
      </div>

      {data.items.length === 0 ? (
        <div className="mt-10"><Empty title="No companions yet" sub="Check back soon — new hosts are approved every day." /></div>
      ) : (
        <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {data.items.map((c) => (
            <Link key={c.id} to={`/hangouts/${c.id}`} data-testid="companion-card" data-companion={c.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 hover-lift">
              <div className="flex gap-4">
                {c.photo ? <img src={fileUrl(c.photo)} alt={c.name} className="h-16 w-16 rounded-2xl object-cover" />
                  : <span className="grid h-16 w-16 place-items-center rounded-2xl bg-slate-900 text-white font-display text-xl">{c.name[0]}</span>}
                <div className="min-w-0">
                  <p className="font-bold truncate">{c.name}{c.age ? `, ${c.age}` : ""}</p>
                  <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500"><MapPin className="h-3 w-3" />{c.city || "Global"}</p>
                  <p className="mt-2 text-xs font-semibold text-slate-500" data-testid={`rate-hidden-${c.id}`}>Rate shared once they accept</p>
                </div>
              </div>
              {c.headline && <p className="mt-3 line-clamp-2 text-sm text-slate-600">{c.headline}</p>}
              <p className="mt-3 flex items-center gap-3 text-[11px] font-semibold text-slate-400">
                <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{c.min_hours}–{c.max_hours}h</span>
                {c.rating_count > 0 && <span data-testid={`companion-rating-${c.id}`}>★ {c.rating} ({c.rating_count})</span>}
                {c.packages?.length > 0 && <span>{c.packages.length} package{c.packages.length === 1 ? "" : "s"}</span>}
                {c.hangouts > 0 && <span>{c.hangouts} hangouts</span>}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function CompanionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [c, setC] = useState(null);
  const [locked, setLocked] = useState("");
  const [f, setF] = useState({ hours: 0, package_index: -1, offer_amount: 0, starts_at: "", place: "", note: "", accept_terms: false });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/companions/${id}`).then(({ data }) => { setC(data); setF((p) => ({ ...p, hours: data.min_hours })); })
      .catch((e) => { if (e.response?.status === 403) setLocked(errMsg(e)); else setC(false); });
  }, [id]);

  const fee = c ? (c.free_requests_left > 0 ? 0 : c.request_fee || 0) : 0;
  const freeLeft = c ? c.free_requests_left || 0 : 0;

  const book = async (e) => {
    e.preventDefault();
    if (!f.accept_terms) return toast.error("Please accept the hangout terms.");
    setBusy(true);
    try {
      const { data } = await api.post(`/companions/${id}/bookings`, {
        ...f, hours: Number(f.hours) || 0, offer_amount: Number(f.offer_amount) || 0,
        starts_at: new Date(f.starts_at).toISOString(),
      });
      if (data.fee_waived) {
        toast.success("Request sent — no fee, one of your free requests was used.");
        return nav("/hangouts/bookings");
      }
      nav(`/checkout?kind=companion&id=${data.booking.id}`);
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  if (locked) return <Locked message={locked} />;
  if (c === null) return <Spinner />;
  if (c === false) return <div className="py-24"><Empty title="Companion unavailable" sub="This profile is no longer listed." /></div>;

  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10 pb-28" data-testid="companion-detail">
      <SEO title={`Hangout with ${c.name}`} />
      <div className="flex flex-wrap items-start gap-5">
        {c.photo ? <img src={fileUrl(c.photo)} alt={c.name} className="h-24 w-24 rounded-2xl object-cover" />
          : <span className="grid h-24 w-24 place-items-center rounded-2xl bg-slate-900 text-white font-display text-3xl">{c.name[0]}</span>}
        <div className="min-w-0 flex-1">
          <h1 className="text-3xl font-bold">{c.name}{c.age ? `, ${c.age}` : ""}</h1>
          <p className="mt-1 text-sm text-slate-500">{c.city || "Global"} · {c.hangouts} hangouts{c.rating_count ? ` · ★ ${c.rating} (${c.rating_count})` : ""}{c.languages?.length ? ` · ${c.languages.join(", ")}` : ""}</p>
          <p className="mt-3 text-base font-semibold text-slate-500" data-testid="companion-rate">
            Rate stays private until they accept your request
          </p>
        </div>
      </div>
      {c.headline && <p className="mt-5 text-lg font-semibold">{c.headline}</p>}
      {c.about && <p className="mt-3 whitespace-pre-line text-slate-600 leading-relaxed">{c.about}</p>}
      <Terms text={c.terms} />

      <form onSubmit={book} className="mt-8 space-y-4 rounded-2xl border border-slate-200 bg-white p-6" data-testid="booking-form">
        <p className="font-bold">Request a hangout</p>
        {c.packages?.length > 0 && (
          <L label="Package (optional)">
            <select value={f.package_index} data-testid="booking-package"
              onChange={(e) => setF({ ...f, package_index: Number(e.target.value) })} className={cls}>
              <option value={-1}>Pay by the hour</option>
              {c.packages.map((p, i) => <option key={i} value={i}>{p.label} · {p.hours}h</option>)}
            </select>
          </L>
        )}
        {f.package_index < 0 && (
          <L label={`Hours (${c.min_hours}–${c.max_hours})`}>
            <input type="number" min={c.min_hours} max={c.max_hours} value={f.hours} data-testid="booking-hours"
              onChange={(e) => setF({ ...f, hours: e.target.value })} className={cls} />
          </L>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <L label="When"><input required type="datetime-local" value={f.starts_at} data-testid="booking-when"
            onChange={(e) => setF({ ...f, starts_at: e.target.value })} className={cls} /></L>
          <L label="Where (public venue)"><input value={f.place} data-testid="booking-place"
            onChange={(e) => setF({ ...f, place: e.target.value })} className={cls} /></L>
        </div>
        <L label="Your offer (optional — offer more to stand out)">
          <input type="number" min={0} value={f.offer_amount} data-testid="booking-offer"
            onChange={(e) => setF({ ...f, offer_amount: e.target.value })} className={cls} />
        </L>
        <L label="Note for your companion"><textarea rows={3} value={f.note} data-testid="booking-note"
          onChange={(e) => setF({ ...f, note: e.target.value })} className={cls} /></L>
        <label className="flex items-start gap-2 text-xs text-slate-600">
          <input type="checkbox" checked={f.accept_terms} data-testid="booking-terms"
            onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} className="mt-0.5" />
          I understand this is for company only, that the {money(fee)} request fee is non-refundable, and that
          the full rate is shown and payable only after my companion accepts.
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-lg font-bold" data-testid="booking-total">
            {fee > 0 ? `Request fee now: ${money(fee)}`
              : `Free request (${freeLeft} left this month)`}
          </p>
          <button disabled={busy} data-testid="booking-submit"
            className="inline-flex items-center gap-2 rounded-full brand-gradient px-7 py-3 text-sm font-bold text-white disabled:opacity-50">
            <Sparkles className="h-4 w-4" />{busy ? "Sending…" : fee > 0 ? `Pay ${money(fee)} & send request` : "Send request"}
          </button>
        </div>
      </form>
    </div>
  );
}

const STATUS_TONE = {
  pending_request_fee: "amber", pending_payment: "amber", awaiting_acceptance: "amber",
  payment_due: "amber", counter_offered: "amber",
  confirmed: "green", completed: "green", declined: "red", cancelled: "red", no_show: "red",
};

export function MyBookings() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const load = useCallback(() => {
    api.get("/me/bookings").then(({ data }) => setData(data)).catch(() => setData({ items: [] }));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (b, path, body) => {
    try { const { data } = await api.post(`/bookings/${b.id}/${path}`, body || {}); 
      toast.success(data.paid_from === "wallet" ? "Confirmed — paid from their Buddilio wallet."
        : data.paid_from === "card" ? "Confirmed — their saved card was charged."
        : data.rating ? "Thanks — your rating is private."
        : data.credit_issued ? `Done — ${money(data.credit_issued)} credit added.` : "Done.");
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;

  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 py-10 pb-28" data-testid="my-bookings-page">
      <SEO title="My hangouts" />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline">Hangouts</p>
          <h1 className="mt-2 text-3xl font-bold">My bookings</h1>
        </div>
        <p className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white" data-testid="credit-balance">
          Credit: {money(data.credit_balance || 0)}
        </p>
        <Link to="/wallet" data-testid="wallet-link"
          className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">
          Wallet · {data.free_requests_left || 0} free requests
        </Link>
      </div>

      {data.items.length === 0 ? (
        <div className="mt-10"><Empty title="No hangouts yet" sub="Browse companions and book someone's time." /></div>
      ) : (
        <div className="mt-8 space-y-4">
          {data.items.map((b) => (
            <div key={b.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`booking-${b.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-bold">{b.role === "member" ? `With ${b.with_name}` : `${b.with_name} booked you`}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {b.hours}h{b.package ? ` · ${b.package}` : ""} · {fmtDate(b.starts_at)}{b.place ? ` · ${b.place}` : ""}
                  </p>
                  {b.note && <p className="mt-2 text-sm italic text-slate-600">“{b.note}”</p>}
                  {b.counter_note && <p className="mt-2 text-sm text-amber-700">Counter-offer note: {b.counter_note}</p>}
                </div>
                <div className="text-right">
                  <Badge tone={STATUS_TONE[b.status] || "slate"}>{b.status.replace(/_/g, " ")}</Badge>
                  <p className="mt-2 text-sm font-bold">{b.rate_hidden ? `Fee paid ${money(b.request_fee)}` : money(b.paid_total || b.amount)}</p>
                  {b.rate_hidden && <p className="text-[11px] text-slate-500" data-testid={`rate-pending-${b.id}`}>Rate shown after they accept</p>}
                  {b.role === "companion" && b.companion_net > 0 && (
                    <p className="text-[11px] text-slate-500" data-testid={`booking-net-${b.id}`}>You get {money(b.companion_net)}</p>
                  )}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {b.role === "member" && (b.status === "pending_request_fee" || b.status === "pending_payment") && (
                  <button onClick={() => nav(`/checkout?kind=companion&id=${b.id}`)} data-testid={`pay-${b.id}`}
                    className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">
                    Pay {money(b.due_amount)} now
                  </button>
                )}
                {b.role === "member" && (b.status === "payment_due" || b.status === "counter_offered") && (
                  <>
                    <button onClick={() => nav(`/checkout?kind=companion&id=${b.id}`)} data-testid={`pay-counter-${b.id}`}
                      className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">
                      Pay {money(b.due_amount)}
                    </button>
                    <button onClick={() => act(b, "reject-counter")} data-testid={`reject-counter-${b.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Turn down</button>
                  </>
                )}
                {b.role === "companion" && b.status === "awaiting_acceptance" && (
                  <>
                    <button onClick={() => act(b, "accept")} data-testid={`accept-${b.id}`}
                      className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Accept at my rate</button>
                    <button data-testid={`counter-${b.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold"
                      onClick={() => {
                        const amount = window.prompt("Your price for this hangout");
                        if (!amount) return;
                        act(b, "counter", { amount: Number(amount), note: window.prompt("Add a note (optional)") || "" });
                      }}>Name a price</button>
                    <button onClick={() => act(b, "decline")} data-testid={`decline-${b.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">Decline</button>
                  </>
                )}
                {b.status === "completed" && b.role === "member" && !b.rated && (
                  <button data-testid={`rate-${b.id}`} className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white"
                    onClick={() => {
                      const stars = window.prompt("Rate this hangout 1–5 (private — only the average is shown)");
                      if (!stars) return;
                      act(b, "rate", { stars: Number(stars), note: window.prompt("Anything our team should know? (private)") || "" });
                    }}>Rate this hangout</button>
                )}
                {b.status === "confirmed" && (
                  <>
                    <button onClick={() => act(b, "complete")} data-testid={`complete-${b.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Mark as done</button>
                    {b.role === "member" && (
                      <button data-testid={`no-show-${b.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600"
                        onClick={() => act(b, "no-show", { note: window.prompt("What happened?") || "" })}>Report a no-show</button>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function HostHangouts() {
  const [data, setData] = useState(null);
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get("/me/companion").then(({ data }) => {
      setData(data);
      const p = data.profile;
      setF({
        hourly_rate: p.hourly_rate || "", min_hours: p.min_hours || 1, max_hours: p.max_hours || 4,
        headline: p.headline || "", about: p.about || "", city: p.city || "",
        languages: p.languages || [], packages: p.packages || [], enabled: p.enabled !== false,
        accept_terms: p.status !== "none",
      });
    }).catch(() => setData(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/me/companion", {
        ...f, hourly_rate: Number(f.hourly_rate), min_hours: Number(f.min_hours), max_hours: Number(f.max_hours),
        packages: f.packages.map((p) => ({ ...p, hours: Number(p.hours), price: Number(p.price) })),
      });
      toast.success("Saved. Our team reviews new profiles before they go live.");
      load();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  if (data === null || !f) return <Spinner />;
  if (data === false) return <div className="py-24"><Empty title="Not available" sub="Please sign in again." /></div>;
  const p = data.profile;

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 pb-28" data-testid="host-hangouts-page">
      <SEO title="Offer hangouts" />
      <p className="overline">Earn on Buddilio</p>
      <h1 className="mt-2 text-3xl font-bold">Offer hangouts</h1>
      <p className="mt-3 text-slate-600">Set your hourly rate and premium members can book your time. Buddilio
        keeps {data.cut_percent}% of each booking — the remaining {100 - data.cut_percent}% is yours and lands in
        your payouts.</p>
      <Terms text={data.terms} />

      {p.status !== "none" && (
        <p className="mt-4 flex items-center gap-2 text-sm font-bold" data-testid="host-status">
          Status: <Badge tone={p.status === "approved" ? "green" : p.status === "pending" ? "amber" : "red"}>{p.status}</Badge>
          {p.rejected_reason && <span className="text-xs font-normal text-rose-600">{p.rejected_reason}</span>}
        </p>
      )}
      {!data.can_apply && (
        <p className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600" data-testid="host-needs-verify">
          Get your profile verified first — then you can list yourself here.
        </p>
      )}

      <form onSubmit={save} className="mt-6 space-y-4 rounded-2xl border border-slate-200 bg-white p-6" data-testid="host-form">
        <div className="grid gap-3 sm:grid-cols-3">
          <L label="Hourly rate"><input required type="number" min={1} value={f.hourly_rate} data-testid="host-rate"
            onChange={(e) => setF({ ...f, hourly_rate: e.target.value })} className={cls} /></L>
          <L label="Minimum hours"><input type="number" min={1} max={6} value={f.min_hours} data-testid="host-min"
            onChange={(e) => setF({ ...f, min_hours: e.target.value })} className={cls} /></L>
          <L label="Maximum hours"><input type="number" min={1} max={6} value={f.max_hours} data-testid="host-max"
            onChange={(e) => setF({ ...f, max_hours: e.target.value })} className={cls} /></L>
        </div>
        <L label="Headline"><input value={f.headline} data-testid="host-headline"
          onChange={(e) => setF({ ...f, headline: e.target.value })} className={cls} /></L>
        <L label="About you"><textarea rows={5} value={f.about} data-testid="host-about"
          onChange={(e) => setF({ ...f, about: e.target.value })} className={cls} /></L>
        <div className="grid gap-3 sm:grid-cols-2">
          <L label="City"><input value={f.city} data-testid="host-city"
            onChange={(e) => setF({ ...f, city: e.target.value })} className={cls} /></L>
          <L label="Languages (comma separated)"><input value={(f.languages || []).join(", ")} data-testid="host-languages"
            onChange={(e) => setF({ ...f, languages: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} className={cls} /></L>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600">Fixed packages (optional)</span>
            <button type="button" data-testid="host-add-package"
              onClick={() => setF({ ...f, packages: [...f.packages, { label: "", hours: 2, price: "" }] })}
              className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">Add package</button>
          </div>
          <div className="mt-3 space-y-2">
            {f.packages.map((pk, i) => (
              <div key={i} className="grid grid-cols-[1fr_80px_100px_auto] gap-2" data-testid={`host-package-${i}`}>
                <input placeholder="Dinner evening" value={pk.label} data-testid={`host-package-label-${i}`}
                  onChange={(e) => setF({ ...f, packages: f.packages.map((x, n) => n === i ? { ...x, label: e.target.value } : x) })}
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <input type="number" min={1} max={6} value={pk.hours} data-testid={`host-package-hours-${i}`}
                  onChange={(e) => setF({ ...f, packages: f.packages.map((x, n) => n === i ? { ...x, hours: e.target.value } : x) })}
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <input type="number" min={1} placeholder="Price" value={pk.price} data-testid={`host-package-price-${i}`}
                  onChange={(e) => setF({ ...f, packages: f.packages.map((x, n) => n === i ? { ...x, price: e.target.value } : x) })}
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <button type="button" data-testid={`host-package-remove-${i}`}
                  onClick={() => setF({ ...f, packages: f.packages.filter((_, n) => n !== i) })}
                  className="rounded-xl border border-slate-200 px-3 text-xs font-bold text-rose-600">Remove</button>
              </div>
            ))}
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={f.enabled} data-testid="host-enabled"
            onChange={(e) => setF({ ...f, enabled: e.target.checked })} />Accepting bookings
        </label>
        <label className="flex items-start gap-2 text-xs text-slate-600">
          <input type="checkbox" checked={f.accept_terms} data-testid="host-terms" className="mt-0.5"
            onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} />
          I agree hangouts are for company and conversation only, in public venues, and that Buddilio keeps
          {" "}{data.cut_percent}% of each booking.
        </label>
        <button disabled={busy || !data.can_apply} data-testid="host-save"
          className="rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : p.status === "none" ? "Submit for review" : "Save profile"}
        </button>
      </form>

      <Link to="/hangouts/bookings" data-testid="host-bookings-link"
        className="mt-6 inline-block rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">
        See requests & bookings
      </Link>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { MapPin, CalendarDays, Users, Sparkles, BadgeCheck, Compass } from "lucide-react";
import { api, errMsg, fmtDate, money } from "@/lib/api";
import { Spinner, Empty, Badge, SEO } from "@/components/Shared";
import { RichHtml } from "@/components/RichText";

const cls = "w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm";
const TABS = [["trips", "Trips"], ["providers", "Guides & crew"], ["requests", "My requests"], ["bookings", "Bookings"]];

const L = ({ label, children }) => (
  <label className="block"><span className="text-xs font-bold text-slate-600">{label}</span>
    <div className="mt-1.5">{children}</div></label>
);

export default function Travel() {
  const [tab, setTab] = useState("trips");
  const [meta, setMeta] = useState(null);

  useEffect(() => { api.get("/travel/meta").then(({ data }) => setMeta(data)).catch(() => setMeta(false)); }, []);
  if (!meta) return <Spinner label="Loading travel" />;

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10 pb-28" data-testid="travel-page">
      <SEO title="Solo travel" description="Find a group, a guide or a cook for your next trip." />
      <p className="overline">Solo travel</p>
      <h1 className="mt-2 text-3xl sm:text-4xl lg:text-5xl font-bold">Never travel alone unless you want to</h1>
      <p className="mt-3 max-w-2xl text-base text-slate-600">
        Post where you're headed and let other solo travellers join for free — or book a verified guide,
        cook or porter for the days you need one.
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)} data-testid={`travel-tab-${v}`}
            className={`rounded-full px-5 py-2.5 text-sm font-bold border transition-colors ${tab === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
            {l}
          </button>
        ))}
        <Link to="/travel/provider" data-testid="become-provider-link"
          className="rounded-full brand-gradient px-5 py-2.5 text-sm font-bold text-white">
          Offer your services
        </Link>
      </div>

      <p className="mt-4 text-xs text-slate-500" data-testid="travel-terms">{meta.terms}</p>

      <div className="mt-8">
        {tab === "trips" && <Trips meta={meta} />}
        {tab === "providers" && <Providers meta={meta} />}
        {tab === "requests" && <Requests meta={meta} />}
        {tab === "bookings" && <Bookings />}
      </div>
    </div>
  );
}

const Trips = ({ meta }) => {
  const [data, setData] = useState(null);
  const [f, setF] = useState({ destination: "", activity: "" });
  const [form, setForm] = useState(null);
  const [reqs, setReqs] = useState(null);

  const load = useCallback(() => {
    api.get("/travel/trips", { params: f }).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [] }); });
  }, [f]);
  useEffect(() => { load(); }, [load]);

  const join = async (t) => {
    try {
      await api.post(`/travel/trips/${t.id}/join`, { note: window.prompt("Say hi to the host (optional)") || "" });
      toast.success("Request sent — the host will get back to you."); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const openRequests = async (t) => {
    try { const { data } = await api.get(`/travel/trips/${t.id}/requests`); setReqs({ trip: t, items: data.items }); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const decide = async (t, id, action) => {
    try {
      await api.post(`/travel/trips/${t.id}/requests/${id}`, { action, note: "" });
      toast.success(action === "approve" ? "They're in." : "Declined.");
      openRequests(t); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <input value={f.destination} placeholder="Destination" data-testid="trip-filter-destination"
          onChange={(e) => setF({ ...f, destination: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm w-44" />
        <select value={f.activity} data-testid="trip-filter-activity"
          onChange={(e) => setF({ ...f, activity: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm">
          <option value="">Any activity</option>
          {meta.activities.map((a) => <option key={a}>{a}</option>)}
        </select>
        <button onClick={() => setForm(form ? null : { activity: "Trekking", group_size: 4, gender_pref: "any" })}
          data-testid="post-trip-btn" className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white">
          {form ? "Close" : "Post a trip"}
        </button>
      </div>

      {form && <TripForm meta={meta} onDone={() => { setForm(null); load(); }} />}

      {data.items.length === 0 ? <Empty title="No open trips yet" subtitle="Post the first one — it's free." /> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="trip-list">
          {data.items.map((t) => (
            <div key={t.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`trip-card-${t.id}`}>
              <div className="flex items-start justify-between gap-2">
                <p className="font-bold">{t.title}</p>
                <Badge tone={t.status === "open" ? "green" : "slate"}>{t.status}</Badge>
              </div>
              <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-600">
                <MapPin className="h-3.5 w-3.5" />{t.destination}{t.country ? `, ${t.country}` : ""}
              </p>
              <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-600">
                <CalendarDays className="h-3.5 w-3.5" />{fmtDate(t.starts_at)}
              </p>
              <p className="mt-1 flex items-center gap-1.5 text-sm text-slate-600">
                <Users className="h-3.5 w-3.5" />{t.joined}/{t.group_size - 1} joined · {t.activity}
                {t.budget ? ` · ~${money(t.budget)}` : ""}
              </p>
              {t.notes && <RichHtml html={t.notes} className="mt-2 text-sm text-slate-500" />}
              <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-500">
                Hosted by {t.host_name}
                {t.host_verified && <BadgeCheck className="h-3.5 w-3.5 text-emerald-600" />}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {t.is_host ? (
                  <>
                    <button onClick={() => openRequests(t)} data-testid={`trip-requests-${t.id}`}
                      className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Who asked to join</button>
                    <button onClick={async () => { await api.delete(`/travel/trips/${t.id}`); toast.success("Closed."); load(); }}
                      data-testid={`trip-close-${t.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Close</button>
                  </>
                ) : t.requested ? (
                  <span className="text-xs font-bold text-slate-500" data-testid={`trip-requested-${t.id}`}>Request sent</span>
                ) : (
                  <button onClick={() => join(t)} data-testid={`trip-join-${t.id}`}
                    className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Ask to join · free</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {reqs && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="trip-request-list">
          <p className="font-bold">Requests for {reqs.trip.title}</p>
          {reqs.items.length === 0 ? <p className="mt-2 text-sm text-slate-500">Nobody yet.</p> : (
            <ul className="mt-3 divide-y divide-slate-100">
              {reqs.items.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3" data-testid={`trip-request-${r.id}`}>
                  <div>
                    <p className="text-sm font-semibold">{r.name} {r.verified && <BadgeCheck className="inline h-3.5 w-3.5 text-emerald-600" />}</p>
                    <p className="text-xs text-slate-500">{r.city} · {r.note || "No message"} · {r.status}</p>
                  </div>
                  {r.status === "requested" && (
                    <div className="flex gap-2">
                      <button onClick={() => decide(reqs.trip, r.id, "approve")} data-testid={`trip-approve-${r.id}`}
                        className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Accept</button>
                      <button onClick={() => decide(reqs.trip, r.id, "reject")} data-testid={`trip-decline-${r.id}`}
                        className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Decline</button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

const TripForm = ({ meta, onDone }) => {
  const [f, setF] = useState({ title: "", destination: "", starts_at: "", ends_at: "", activity: "Trekking",
    group_size: 4, budget: 0, gender_pref: "any", notes: "" });
  const [busy, setBusy] = useState(false);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/travel/trips", { ...f, group_size: Number(f.group_size), budget: Number(f.budget),
        starts_at: new Date(f.starts_at).toISOString(),
        ends_at: f.ends_at ? new Date(f.ends_at).toISOString() : "" });
      toast.success("Trip posted."); onDone();
    } catch (er) { toast.error(errMsg(er)); } finally { setBusy(false); }
  };

  return (
    <form onSubmit={save} className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 sm:grid-cols-2"
      data-testid="trip-form">
      <L label="Trip title"><input required value={f.title} data-testid="trip-title"
        onChange={(e) => setF({ ...f, title: e.target.value })} className={cls} /></L>
      <L label="Destination"><input required value={f.destination} data-testid="trip-destination"
        onChange={(e) => setF({ ...f, destination: e.target.value })} className={cls} /></L>
      <L label="Starts"><input required type="datetime-local" value={f.starts_at} data-testid="trip-starts"
        onChange={(e) => setF({ ...f, starts_at: e.target.value })} className={cls} /></L>
      <L label="Ends (optional)"><input type="datetime-local" value={f.ends_at} data-testid="trip-ends"
        onChange={(e) => setF({ ...f, ends_at: e.target.value })} className={cls} /></L>
      <L label="Activity"><select value={f.activity} data-testid="trip-activity"
        onChange={(e) => setF({ ...f, activity: e.target.value })} className={cls}>
        {meta.activities.map((a) => <option key={a}>{a}</option>)}</select></L>
      <L label="Group size"><input type="number" min={2} max={30} value={f.group_size} data-testid="trip-group-size"
        onChange={(e) => setF({ ...f, group_size: e.target.value })} className={cls} /></L>
      <L label="Rough budget per person"><input type="number" min={0} value={f.budget} data-testid="trip-budget"
        onChange={(e) => setF({ ...f, budget: e.target.value })} className={cls} /></L>
      <L label="Who can join"><select value={f.gender_pref} data-testid="trip-gender"
        onChange={(e) => setF({ ...f, gender_pref: e.target.value })} className={cls}>
        <option value="any">Anyone</option><option value="women">Women only</option><option value="men">Men only</option>
      </select></L>
      <div className="sm:col-span-2">
        <L label="Plan / notes"><textarea rows={3} value={f.notes} data-testid="trip-notes"
          onChange={(e) => setF({ ...f, notes: e.target.value })} className={cls} /></L>
      </div>
      <button disabled={busy} data-testid="trip-submit"
        className="rounded-full brand-gradient px-6 py-3 text-sm font-bold text-white disabled:opacity-50 sm:col-span-2 sm:w-fit">
        <Sparkles className="mr-1.5 inline h-4 w-4" />{busy ? "Posting…" : "Post trip · free"}
      </button>
    </form>
  );
};

const Providers = ({ meta }) => {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [f, setF] = useState({ role: "", destination: "", sort: "rating" });

  useEffect(() => {
    api.get("/travel/providers", { params: f }).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [] }); });
  }, [f]);

  const book = async (p) => {
    const days = window.prompt(`How many days? (${money(p.day_price)} per day)`, "1");
    if (!days) return;
    const when = window.prompt("Start date (YYYY-MM-DD)");
    if (!when) return;
    try {
      const { data } = await api.post(`/travel/providers/${p.id}/bookings`, {
        days: Number(days), starts_at: new Date(`${when}T09:00`).toISOString(), people: 1 });
      nav(`/checkout?kind=travel&id=${data.booking_id}`);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <select value={f.role} data-testid="provider-filter-role" onChange={(e) => setF({ ...f, role: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm">
          <option value="">Any service</option>
          {meta.roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
        <input value={f.destination} placeholder="Destination" data-testid="provider-filter-destination"
          onChange={(e) => setF({ ...f, destination: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm w-44" />
        <select value={f.sort} data-testid="provider-sort" onChange={(e) => setF({ ...f, sort: e.target.value })}
          className="rounded-full border border-slate-200 px-4 py-2.5 text-sm">
          <option value="rating">Top rated</option>
          <option value="experience">Most experienced</option>
          <option value="price">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
        </select>
      </div>

      {data.items.length === 0 ? <Empty title="No one listed here yet" subtitle="Try another service or destination." /> : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="provider-list">
          {data.items.map((p) => (
            <div key={p.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`provider-card-${p.id}`}>
              <div className="flex items-center gap-3">
                {p.photo ? <img src={p.photo} alt={p.name} className="h-12 w-12 rounded-full object-cover" />
                  : <div className="grid h-12 w-12 place-items-center rounded-full bg-slate-100"><Compass className="h-5 w-5 text-slate-400" /></div>}
                <div>
                  <p className="font-bold">{p.name} {p.verified && <BadgeCheck className="inline h-3.5 w-3.5 text-emerald-600" />}</p>
                  <p className="text-xs text-slate-500">{p.roles.map((r) => (meta.roles.find((x) => x.key === r) || {}).label).join(", ")}</p>
                </div>
              </div>
              {p.headline && <p className="mt-3 text-sm text-slate-600">{p.headline}</p>}
              <p className="mt-2 text-xs text-slate-500">
                {p.destinations.slice(0, 3).join(" · ") || "Flexible"} · {p.experience_years}y experience
                {p.rating_count ? ` · ★ ${p.rating} (${p.rating_count})` : ""}
              </p>
              <p className="mt-3 text-lg font-bold" data-testid={`provider-price-${p.id}`}>{money(p.day_price)}<span className="text-xs font-normal text-slate-500"> / day</span></p>
              <button onClick={() => book(p)} data-testid={`provider-book-${p.id}`}
                className="mt-3 w-full rounded-full bg-slate-900 px-4 py-2.5 text-xs font-bold text-white">Book &amp; pay</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const Requests = ({ meta }) => {
  const nav = useNavigate();
  const [mine, setMine] = useState(null);
  const [open, setOpen] = useState(null);
  const [f, setF] = useState({ destination: "", roles: [], starts_at: "", days: 1, people: 1, budget: 0, notes: "" });

  const load = useCallback(() => {
    api.get("/travel/requests", { params: { mine: true } }).then(({ data }) => setMine(data.items)).catch(() => setMine([]));
    api.get("/travel/requests").then(({ data }) => setOpen(data.items)).catch(() => setOpen(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const post = async (e) => {
    e.preventDefault();
    try {
      await api.post("/travel/requests", { ...f, days: Number(f.days), people: Number(f.people),
        budget: Number(f.budget), starts_at: new Date(f.starts_at).toISOString() });
      toast.success("Request posted — providers can quote now.");
      setF({ ...f, notes: "" }); load();
    } catch (er) { toast.error(errMsg(er)); }
  };

  const quote = async (r) => {
    const amount = window.prompt("Your price for the whole job");
    if (!amount) return;
    try {
      const { data } = await api.post(`/travel/requests/${r.id}/quotes`, { amount: Number(amount), note: "" });
      toast.success(`Quote sent — the traveller sees ${money(data.amount)}.`); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const accept = async (q) => {
    try {
      const { data } = await api.post(`/travel/quotes/${q.id}/accept`);
      nav(`/checkout?kind=travel&id=${data.booking_id}`);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (mine === null) return <Spinner />;

  return (
    <div className="space-y-8">
      <form onSubmit={post} className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-6 sm:grid-cols-2"
        data-testid="service-request-form">
        <p className="font-bold sm:col-span-2">Need a guide, cook or porter?</p>
        <L label="Destination"><input required value={f.destination} data-testid="sr-destination"
          onChange={(e) => setF({ ...f, destination: e.target.value })} className={cls} /></L>
        <L label="Start date"><input required type="datetime-local" value={f.starts_at} data-testid="sr-starts"
          onChange={(e) => setF({ ...f, starts_at: e.target.value })} className={cls} /></L>
        <L label="Days"><input type="number" min={1} max={30} value={f.days} data-testid="sr-days"
          onChange={(e) => setF({ ...f, days: e.target.value })} className={cls} /></L>
        <L label="People"><input type="number" min={1} max={30} value={f.people} data-testid="sr-people"
          onChange={(e) => setF({ ...f, people: e.target.value })} className={cls} /></L>
        <div className="sm:col-span-2">
          <p className="text-xs font-bold text-slate-600">Services needed</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {meta.roles.map((r) => (
              <button key={r.key} type="button" data-testid={`sr-role-${r.key}`}
                onClick={() => setF({ ...f, roles: f.roles.includes(r.key) ? f.roles.filter((x) => x !== r.key) : [...f.roles, r.key] })}
                className={`rounded-full border px-4 py-2 text-xs font-bold ${f.roles.includes(r.key) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <button data-testid="sr-submit" className="rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white sm:col-span-2 sm:w-fit">
          Post request
        </button>
      </form>

      <div>
        <h2 className="mb-3 text-sm font-bold uppercase tracking-widest text-slate-500">Your requests</h2>
        {mine.length === 0 ? <Empty title="Nothing posted yet" /> : (
          <div className="space-y-3" data-testid="my-requests">
            {mine.map((r) => (
              <div key={r.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`request-${r.id}`}>
                <p className="font-bold">{r.destination} · {r.days} day(s)</p>
                <p className="text-xs text-slate-500">{fmtDate(r.starts_at)} · {r.roles.join(", ")} · {r.status} · {r.quote_count} quote(s)</p>
                {r.quotes?.map((q) => (
                  <div key={q.id} className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3"
                    data-testid={`quote-${q.id}`}>
                    <p className="text-sm"><b>{q.provider_name}</b> · {money(q.amount)} {q.note && `· ${q.note}`}</p>
                    {q.status === "open" && (
                      <button onClick={() => accept(q)} data-testid={`accept-quote-${q.id}`}
                        className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Accept &amp; pay</button>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {open && (
        <div>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-widest text-slate-500">Open requests you can quote on</h2>
          <div className="space-y-3" data-testid="open-requests">
            {open.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-5"
                data-testid={`open-request-${r.id}`}>
                <div>
                  <p className="font-bold">{r.destination} · {r.days} day(s)</p>
                  <p className="text-xs text-slate-500">{fmtDate(r.starts_at)} · {r.roles.join(", ")} · {r.traveller_name}</p>
                </div>
                {r.my_quote ? <span className="text-xs font-bold text-slate-500">You quoted {money(r.my_quote)}</span> : (
                  <button onClick={() => quote(r)} data-testid={`send-quote-${r.id}`}
                    className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Send a quote</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const Bookings = () => {
  const [items, setItems] = useState(null);
  const nav = useNavigate();
  useEffect(() => { api.get("/travel/bookings").then(({ data }) => setItems(data.items)).catch(() => setItems([])); }, []);
  if (!items) return <Spinner />;
  if (items.length === 0) return <Empty title="No travel bookings yet" />;
  return (
    <div className="space-y-3" data-testid="travel-bookings">
      {items.map((b) => (
        <div key={b.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-5"
          data-testid={`travel-booking-${b.id}`}>
          <div>
            <p className="font-bold">{b.item_name}</p>
            <p className="text-xs text-slate-500">
              {fmtDate(b.starts_at)} · {b.days} day(s) · with {b.with_name} · {b.status}
              {b.role === "provider" ? ` · you earn ${money(b.provider_net)}` : ` · ${money(b.amount)}`}
            </p>
          </div>
          {b.role === "traveller" && b.status === "pending_payment" && (
            <button onClick={() => nav(`/checkout?kind=travel&id=${b.id}`)} data-testid={`pay-travel-${b.id}`}
              className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Pay {money(b.due_amount)}</button>
          )}
        </div>
      ))}
    </div>
  );
};

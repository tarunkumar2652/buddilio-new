import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg, fmtDate, fmtTime, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { EventCard, Stars } from "@/components/Cards";
import { ReviewSection } from "@/components/ReviewSection";
import { Spinner, Empty, Badge, SEO } from "@/components/Shared";
import { CalendarDays, MapPin, Users, Share2, Heart, Flag, ShieldAlert } from "lucide-react";
export function Events() {
  const [meta, setMeta] = useState({ cities: [], categories: [] });
  const [f, setF] = useState({ q: "", city: "", category: "", max_price: -1, when: "", sort: "date" });
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);

  useEffect(() => { api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, []);

  const load = useCallback(() => {
    api.get("/events", { params: { ...f, page, limit: 12 } })
      .then(({ data }) => setData(data)).catch(() => setData({ items: [], total: 0 }));
  }, [f, page]);

  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="events-page">
      <SEO title="Events & experiences" description="Discover parties, dining, nightlife, concerts and lifestyle experiences across India." />
      <p className="overline">Experiences</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">What's happening</h1>

      <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-4 grid gap-3 md:grid-cols-5">
        <input data-testid="events-search" placeholder="Search events…" value={f.q}
          onChange={(e) => { setPage(1); setF({ ...f, q: e.target.value }); }}
          className="md:col-span-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
        <select data-testid="events-city" value={f.city} onChange={(e) => { setPage(1); setF({ ...f, city: e.target.value }); }}
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value="">All cities</option>{meta.cities.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select data-testid="events-category" value={f.category} onChange={(e) => { setPage(1); setF({ ...f, category: e.target.value }); }}
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value="">All categories</option>{meta.categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select data-testid="events-price" value={f.max_price} onChange={(e) => { setPage(1); setF({ ...f, max_price: Number(e.target.value) }); }}
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value={-1}>Any price</option><option value={0}>Free only</option>
          <option value={1000}>Under ₹1,000</option><option value={2500}>Under ₹2,500</option><option value={5000}>Under ₹5,000</option>
        </select>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {[["", "All"], ["upcoming", "Upcoming"], ["past", "Past & rated"]].map(([v, l]) => (
          <button key={l} data-testid={`events-when-${l.toLowerCase().split(" ")[0]}`} onClick={() => { setPage(1); setF({ ...f, when: v }); }}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${f.when === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{l}</button>
        ))}
        {[["date", "By date"], ["popular", "Most popular"], ["rating", "Top rated"]].map(([v, l]) => (
          <button key={l} data-testid={`events-sort-${v}`} onClick={() => { setPage(1); setF({ ...f, sort: v }); }}
            className={`rounded-full px-4 py-2 text-xs font-bold border ${f.sort === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{l}</button>
        ))}
      </div>

      {!data ? <Spinner /> : data.items.length ? (
        <>
          <p className="mt-8 text-sm text-slate-500">{data.total} experiences found</p>
          <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {data.items.map((ev) => <EventCard key={ev.id} ev={ev} />)}
          </div>
          {data.total > 12 && (
            <div className="mt-10 flex justify-center gap-3">
              <button disabled={page === 1} data-testid="events-prev" onClick={() => setPage(page - 1)}
                className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold disabled:opacity-40">Previous</button>
              <span className="px-4 py-2.5 text-sm">Page {page} of {Math.ceil(data.total / 12)}</span>
              <button disabled={page >= Math.ceil(data.total / 12)} data-testid="events-next" onClick={() => setPage(page + 1)}
                className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold disabled:opacity-40">Next</button>
            </div>
          )}
        </>
      ) : <div className="mt-8"><Empty title="No events match those filters" sub="Try widening your city or price range." /></div>}
    </div>
  );
}

export function EventDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { fmt } = useCurrency();
  const [ev, setEv] = useState(null);
  const [busy, setBusy] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    api.get(`/events/${id}`).then(({ data }) => setEv(data)).catch((e) => { toast.error(errMsg(e)); setEv(false); });
  }, [id]);
  useEffect(() => { load(); }, [load]);

  if (ev === null) return <Spinner label="Loading event" />;
  if (ev === false) return <div className="py-24"><Empty title="Event unavailable" sub="It may have been removed or is awaiting approval." /></div>;

  const join = async () => {
    if (!user) return nav("/login");
    setBusy(true);
    try {
      if (ev.price > 0) return nav(`/checkout?kind=event&id=${ev.id}`);
      const { data } = await api.post(`/events/${ev.id}/join`);
      toast.success(data.status === "confirmed" ? "You're going! See you there." : "Request sent — the organiser will confirm shortly.");
      load();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const cancel = async () => {
    try { await api.post(`/events/${ev.id}/cancel`); toast.success("Participation cancelled."); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const save = async () => {
    if (!user) return nav("/login");
    try { const { data } = await api.post(`/events/${ev.id}/save`); toast.success(data.saved ? "Saved to your list" : "Removed from saved"); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const openGroupChat = async () => {
    try {
      const { data } = await api.get(`/events/${ev.id}/chat`);
      nav(`/messages?c=${data.conversation_id}`);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const finished = (ev.ends_at || ev.starts_at) < new Date().toISOString();

  const share = async () => {    const url = window.location.href;
    try {
      if (navigator.share) await navigator.share({ title: ev.title, url });
      else { await navigator.clipboard.writeText(url); toast.success("Link copied to clipboard"); }
    } catch { /* dismissed */ }
  };

  const report = async () => {
    if (!reason.trim()) return toast.error("Tell us what's wrong.");
    try {
      await api.post("/reports", { target_type: "event", target_id: ev.id, reason, details: "" });
      toast.success("Report submitted. Thanks for keeping Buddilio safe.");
      setReporting(false); setReason("");
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div data-testid="event-detail-page">
      <SEO title={ev.title} description={ev.description?.slice(0, 155)} />
      <div className="relative h-[45vh] min-h-[300px] bg-slate-900">
        <img src={fileUrl(ev.cover_image)} alt={ev.title} className="absolute inset-0 h-full w-full object-cover opacity-70" />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-900 via-slate-900/40 to-transparent" />
        <div className="relative h-full mx-auto max-w-7xl px-4 sm:px-6 flex flex-col justify-end pb-10 text-white">
          <div className="flex gap-2 items-center">
            <Badge tone="dark">{ev.category}</Badge>
            {ev.featured && <span className="rounded-full bg-white text-slate-900 px-2.5 py-1 text-xs font-bold">Featured</span>}
            {ev.rating > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/95 text-slate-900 px-2.5 py-1 text-xs font-bold" data-testid="detail-rating">
                <Stars value={ev.rating} size="h-3 w-3" />{ev.rating} ({ev.rating_count})
              </span>
            )}
          </div>
          <h1 className="mt-4 text-3xl sm:text-4xl lg:text-5xl font-bold max-w-3xl">{ev.title}</h1>
          <p className="mt-3 text-slate-300 text-sm">Hosted by {ev.partner_name}</p>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28 grid lg:grid-cols-3 gap-10">
        <div className="lg:col-span-2 space-y-10">
          <div className="grid sm:grid-cols-3 gap-4">
            {[[CalendarDays, "When", `${fmtDate(ev.starts_at)} · ${fmtTime(ev.starts_at)}`],
              [MapPin, "Where", `${ev.venue}, ${ev.city}`],
              [Users, "Spots", `${ev.seats_left} of ${ev.capacity} left`]].map(([Icon, l, v]) => (
              <div key={l} className="rounded-xl border border-slate-200 bg-white p-5">
                <Icon className="h-4 w-4 text-slate-400" />
                <p className="overline mt-3">{l}</p>
                <p className="text-sm font-semibold mt-1">{v}</p>
              </div>
            ))}
          </div>

          <div>
            <h2 className="text-2xl font-bold">About this experience</h2>
            <p className="mt-4 text-slate-600 leading-relaxed whitespace-pre-line">{ev.description}</p>
          </div>

          {ev.gallery?.length > 0 && (
            <div>
              <h2 className="text-2xl font-bold">Gallery</h2>
              <div className="mt-4 grid grid-cols-2 gap-4">
                {ev.gallery.map((g, i) => <img key={i} src={fileUrl(g)} alt="" loading="lazy" className="rounded-2xl aspect-[4/3] object-cover w-full" />)}
              </div>
            </div>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-6">
              <p className="overline">Rules</p><p className="mt-2 text-sm text-slate-600">{ev.rules}</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-6">
              <p className="overline">Cancellation policy</p><p className="mt-2 text-sm text-slate-600">{ev.cancellation_policy}</p>
            </div>
          </div>

          {user && ev.participants?.length > 0 && (
            <div>
              <h2 className="text-2xl font-bold">Who's going</h2>
              <div className="mt-4 flex flex-wrap gap-4">
                {ev.participants.map((p) => (
                  <Link key={p.id} to={`/u/${p.id}`} data-testid={`participant-${p.id}`} className="flex items-center gap-3 rounded-full border border-slate-200 bg-white pl-1 pr-4 py-1">
                    {p.photo ? <img src={fileUrl(p.photo)} alt="" className="h-9 w-9 rounded-full object-cover" />
                      : <span className="h-9 w-9 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{p.full_name[0]}</span>}
                    <span className="text-sm font-semibold">{p.full_name.split(" ")[0]}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <ReviewSection eventId={ev.id} canReview={!!user && ev.my_status === "confirmed" && finished} />

          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 flex gap-3">
            <ShieldAlert className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-sm">Stay safe</p>
              <p className="text-sm text-amber-800 mt-1">Meet in the public venue listed. Never transfer money to another member. Report anything that feels off.</p>
            </div>
          </div>
        </div>

        <aside className="lg:sticky lg:top-24 h-fit">
          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <p className="text-3xl font-display font-bold">{ev.price > 0 ? fmt(ev.price) : "Free"}</p>
            <p className="text-xs text-slate-500 mt-1">
              {ev.approval_mode === "instant" ? "Instant confirmation" : "Requires organiser approval"} · {ev.participant_count} going
            </p>
            {ev.my_status ? (
              <div className="mt-5 space-y-3">
                <div className="rounded-xl bg-emerald-50 text-emerald-700 px-4 py-3 text-sm font-semibold text-center" data-testid="my-participation">
                  Your spot is {ev.my_status}
                </div>
                <button onClick={openGroupChat} data-testid="event-group-chat-btn"
                  className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-slate-900 text-white py-3 text-sm font-bold">
                  <Users className="h-4 w-4" />Open group chat
                </button>
                {!finished && (
                  <button onClick={cancel} data-testid="cancel-participation"
                    className="w-full rounded-full border border-slate-200 py-3 text-sm font-bold">Cancel participation</button>
                )}
              </div>
            ) : finished ? (
              <div className="mt-5 rounded-xl bg-slate-100 px-4 py-3 text-sm font-semibold text-center text-slate-600" data-testid="event-finished">
                This experience has finished
              </div>
            ) : (
              <button onClick={join} disabled={busy || ev.seats_left === 0} data-testid="join-event-btn"
                className="mt-5 w-full rounded-full bg-slate-900 text-white py-3.5 text-sm font-bold disabled:opacity-50 hover:bg-slate-800">
                {ev.seats_left === 0 ? "Sold out" : ev.price > 0 ? "Buy pass & join" : "Join this event"}
              </button>
            )}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button onClick={save} data-testid="save-event-btn" className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 py-2.5 text-xs font-bold"><Heart className="h-4 w-4" />Save</button>
              <button onClick={share} data-testid="share-event-btn" className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 py-2.5 text-xs font-bold"><Share2 className="h-4 w-4" />Share</button>
            </div>
            {user && (
              <button onClick={() => setReporting(!reporting)} data-testid="report-event-btn"
                className="mt-4 w-full inline-flex items-center justify-center gap-2 text-xs font-bold text-slate-500 hover:text-red-600"><Flag className="h-3.5 w-3.5" />Report this event</button>
            )}
            {reporting && (
              <div className="mt-3 space-y-2" data-testid="report-event-form">
                <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What's the issue?"
                  className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                <button onClick={report} data-testid="submit-event-report" className="w-full rounded-full bg-red-600 text-white py-2.5 text-xs font-bold">Submit report</button>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, money } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { EventCard, PersonCard } from "@/components/Cards";
import { Spinner, Empty, Badge, SEO } from "@/components/Shared";
import { Compass, Ticket, MessageCircle, Bell, Heart, CalendarDays, Star } from "lucide-react";

export default function Dashboard() {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [reviewable, setReviewable] = useState([]);

  useEffect(() => {
    api.get("/me/dashboard").then(({ data }) => setD(data)).catch(() => setD({}));
    api.get("/me/reviewable").then(({ data }) => setReviewable(data.items)).catch(() => {});
  }, []);

  if (!d) return <Spinner label="Loading your dashboard" />;

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28 md:pb-16" data-testid="dashboard-page">
      <SEO title="Dashboard" />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="overline">Welcome back</p>
          <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Hey {user?.full_name?.split(" ")[0]} 👋</h1>
        </div>
        <div className="flex gap-2">
          {d.membership ? <Badge tone="dark">{d.membership.plan_name} member</Badge> : (
            <Link to="/membership" data-testid="dash-upgrade" className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Go Premium</Link>
          )}
        </div>
      </div>

      {d.profile_completion < 100 && (
        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6" data-testid="profile-completion">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="font-semibold">Your profile is {d.profile_completion}% complete</p>
              <p className="text-sm text-slate-500 mt-1">Complete profiles get 3x more connection requests.</p>
            </div>
            <Link to="/profile" className="text-sm font-bold whitespace-nowrap border-b-2 border-slate-900 pb-0.5" data-testid="dash-complete-profile">Finish it</Link>
          </div>
          <div className="mt-4 h-2 rounded-full bg-slate-100 overflow-hidden">
            <div className="h-full bg-slate-900 transition-all" style={{ width: `${d.profile_completion}%` }} />
          </div>
        </div>
      )}

      <div className="mt-8 grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[["Messages", d.unread_messages, MessageCircle, "/messages"], ["Notifications", d.unread_notifications, Bell, "/notifications"],
          ["Orders", d.orders, Ticket, "/orders"], ["Saved events", d.saved_count, Heart, "/saved"]].map(([l, v, Icon, to]) => (
          <Link key={l} to={to} data-testid={`dash-tile-${l.toLowerCase().split(" ")[0]}`}
            className="rounded-2xl border border-slate-200 bg-white p-5 hover-lift">
            <Icon className="h-5 w-5 text-slate-400" />
            <p className="mt-3 text-2xl font-display font-bold">{v || 0}</p>
            <p className="text-xs text-slate-500 mt-0.5">{l}</p>
          </Link>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap gap-3">
        <Link to="/discover" data-testid="quick-discover" className="inline-flex items-center gap-2 rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold"><Compass className="h-4 w-4" />Discover companions</Link>
        <Link to="/events" data-testid="quick-events" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold"><CalendarDays className="h-4 w-4" />Browse events</Link>
        <Link to="/passes" data-testid="quick-passes" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold"><Ticket className="h-4 w-4" />Buy a pass</Link>
      </div>

      <section className="mt-14">
        <h2 className="text-2xl font-bold">Your upcoming events</h2>        <div className="mt-5">
          {d.upcoming_events?.length ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">{d.upcoming_events.map((e) => <EventCard key={e.id} ev={e} />)}</div>
          ) : (
            <Empty testid="no-upcoming" title="Nothing booked yet" sub="Join a free event or grab a pass — most members start with a brunch or a comedy night."
              action={<Link to="/events" className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Find an event</Link>} />
          )}
        </div>
      </section>

      {reviewable.length > 0 && (
        <section className="mt-14" data-testid="reviewable-section">
          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <div className="flex items-center gap-2">
              <Star className="h-5 w-5" />
              <h2 className="text-xl font-bold">Rate your recent experiences</h2>
            </div>
            <p className="text-sm text-slate-500 mt-1">Your review helps other members pick the right night out.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {reviewable.map((e) => (
                <Link key={e.id} to={`/events/${e.id}`} data-testid={`review-prompt-${e.id}`}
                  className="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold hover:border-slate-900">
                  Review {e.title}
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="mt-14">
        <h2 className="text-2xl font-bold">Recommended companions</h2>
        <div className="mt-5 grid grid-cols-2 lg:grid-cols-4 gap-5">
          {d.recommended_people?.map((p) => <PersonCard key={p.id} p={p} />)}
        </div>
      </section>

      <section className="mt-14">
        <h2 className="text-2xl font-bold">Picked for you</h2>
        <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {d.recommended_events?.map((e) => <EventCard key={e.id} ev={e} />)}
        </div>
      </section>

      {d.membership && (
        <div className="mt-14 rounded-2xl bg-slate-900 text-white p-8" data-testid="membership-status">
          <p className="overline text-slate-400">Membership</p>
          <p className="mt-2 text-2xl font-display font-bold">{d.membership.plan_name}</p>
          <p className="text-sm text-slate-400 mt-1">Active until {new Date(d.membership.ends_at).toLocaleDateString("en-IN")}</p>
        </div>
      )}
    </div>
  );
}

export function SavedEvents() {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get("/me/saved-events").then(({ data }) => setItems(data.items)).catch(() => setItems([])); }, []);
  if (!items) return <Spinner />;
  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="saved-page">
      <SEO title="Saved events" />
      <h1 className="text-3xl font-bold">Saved events</h1>
      <div className="mt-8">
        {items.length ? <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">{items.map((e) => <EventCard key={e.id} ev={e} />)}</div>
          : <Empty title="No saved events" sub="Tap the save icon on any event to keep it here." />}
      </div>
    </div>
  );
}

export function Orders() {
  const [items, setItems] = useState(null);
  useEffect(() => { api.get("/me/orders").then(({ data }) => setItems(data.items)).catch(() => setItems([])); }, []);
  if (!items) return <Spinner />;
  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 pb-28" data-testid="orders-page">
      <SEO title="My orders" />
      <h1 className="text-3xl font-bold">My orders</h1>
      <div className="mt-8 space-y-4">
        {items.length ? items.map((o) => (
          <div key={o.id} className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-wrap items-center justify-between gap-4" data-testid={`order-row-${o.id}`}>
            <div>
              <p className="font-semibold">{o.item_name}</p>
              <p className="text-xs text-slate-500 mt-1">#{o.order_no} · {new Date(o.created_at).toLocaleDateString("en-IN")} · {o.kind}</p>
              {o.coupon && <p className="text-xs text-emerald-600 mt-1">Coupon {o.coupon} applied</p>}
            </div>
            <div className="text-right">
              <p className="font-display font-bold">
                {o.currency && o.currency !== "INR"
                  ? `${o.currency} ${Number(o.charge_total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                  : money(o.total)}
              </p>
              <div className="mt-1 flex gap-1.5 justify-end">
                <Badge tone={o.payment_status === "paid" ? "green" : o.payment_status === "failed" ? "red" : "amber"}>{o.payment_status}</Badge>
                {o.refund_status !== "none" && <Badge tone="red">{o.refund_status}</Badge>}
              </div>
            </div>
          </div>
        )) : <Empty title="No orders yet" sub="Passes and memberships you buy will show up here."
          action={<Link to="/passes" className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Browse passes</Link>} />}
      </div>
    </div>
  );
}

export function Notifications() {
  const [d, setD] = useState(null);
  const load = () => api.get("/notifications").then(({ data }) => setD(data)).catch(() => setD({ items: [] }));
  useEffect(() => { load(); }, []);
  if (!d) return <Spinner />;
  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 pb-28" data-testid="notifications-page">
      <SEO title="Notifications" />
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Notifications</h1>
        <button data-testid="mark-all-read" onClick={async () => { await api.post("/notifications/read-all"); load(); }}
          className="text-sm font-bold border-b-2 border-slate-900 pb-0.5">Mark all read</button>
      </div>
      <div className="mt-8 space-y-3">
        {d.items.length ? d.items.map((n) => (
          <Link key={n.id} to={n.link || "#"} data-testid={`notification-${n.id}`}
            className={`block rounded-xl border p-4 ${n.read ? "border-slate-200 bg-white" : "border-slate-900/10 bg-slate-900/[0.03]"}`}>
            <div className="flex justify-between gap-4">
              <p className="font-semibold text-sm">{n.title}</p>
              {!n.read && <span className="h-2 w-2 rounded-full bg-slate-900 mt-1.5 shrink-0" />}
            </div>
            <p className="text-sm text-slate-500 mt-1">{n.body}</p>
            <p className="text-[11px] text-slate-400 mt-2">{new Date(n.created_at).toLocaleString("en-IN")}</p>
          </Link>
        )) : <Empty title="All caught up" sub="We'll ping you about bookings, messages and new events." />}
      </div>
    </div>
  );
}

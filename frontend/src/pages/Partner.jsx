import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg, money, fmtDate, fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ImageUpload } from "@/components/ImageUpload";
import { RichText } from "@/components/RichText";
import { GalleryUpload } from "@/components/GalleryUpload";
import { CopyHelper } from "@/components/CopyHelper";
import { Stars } from "@/components/Cards";
import { DoorTakings } from "@/components/DoorTakings";
import { Spinner, Empty, Badge, Stat, statusTone, SEO } from "@/components/Shared";
import { Plus, Send } from "lucide-react";

const blank = {
  title: "", description: "", category: "Parties", city: "Delhi NCR", country: "India", venue: "",
  starts_at: "", ends_at: "", cover_image: "", gallery: [], price: 0, price_currency: "USD", capacity: 50,
  rules: "Government ID required at entry. 21+ only.",
  cancellation_policy: "Full refund up to 48 hours before start.",
  approval_mode: "instant", featured: false,
};

export default function PartnerDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useState("dashboard");
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [meta, setMeta] = useState({ cities: [], categories: [] });
  const [f, setF] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [participants, setParticipants] = useState(null);
  const [payouts, setPayouts] = useState(null);
  const [reviews, setReviews] = useState(null);
  const [replyFor, setReplyFor] = useState(null);
  const [replyText, setReplyText] = useState("");

  const load = useCallback(() => {
    api.get("/partner/stats").then(({ data }) => setStats(data)).catch(() => setStats({}));
    api.get("/partner/events").then(({ data }) => setEvents(data.items)).catch(() => {});
    api.get("/partner/payouts").then(({ data }) => setPayouts(data)).catch(() => {});
    api.get("/partner/reviews").then(({ data }) => setReviews(data)).catch(() => setReviews({ items: [] }));
  }, []);
  useEffect(() => { load(); api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, [load]);

  const save = async (submit) => {
    if (!f.title || !f.starts_at) return toast.error("Add at least a title and a start date/time.");
    try {
      const payload = { ...f, price: Number(f.price), capacity: Number(f.capacity) };
      if (editing) { await api.put(`/partner/events/${editing}`, payload); if (submit) await api.post(`/partner/events/${editing}/submit`); }
      else { await api.post("/partner/events", payload, { params: { submit } }); }
      toast.success(submit ? "Event submitted for admin review" : "Event saved as draft");
      setF(blank); setEditing(null); setTab("events"); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const submitExisting = async (id) => {
    try { await api.post(`/partner/events/${id}/submit`); toast.success("Sent for admin review"); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const viewParticipants = async (ev) => {
    try {
      const { data } = await api.get(`/partner/events/${ev.id}/participants`);
      setParticipants({ ev, items: data.items }); setTab("participants");
    } catch (e) { toast.error(errMsg(e)); }
  };

  const postReply = async (id) => {
    if (!replyText.trim()) return toast.error("Write a reply first.");
    try {
      await api.post(`/reviews/${id}/reply`, { body: replyText });
      toast.success("Reply posted publicly on the event page");
      setReplyFor(null); setReplyText(""); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!stats) return <Spinner />;

  const TABS = [["dashboard", "Dashboard"], ["events", "My events"], ["create", "Create event"], ["participants", "Participants"], ["reviews", "Reviews"], ["payouts", "Revenue & payouts"]];

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="partner-dashboard">
      <SEO title="Partner dashboard" />
      <p className="overline">Partner portal</p>
      <h1 className="mt-2 text-3xl font-bold">{user?.org_name || user?.full_name}</h1>

      <div className="mt-6 flex gap-2 overflow-x-auto no-scrollbar">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => { setTab(v); if (v === "create") { setF(blank); setEditing(null); } }} data-testid={`partner-tab-${v}`}
            className={`whitespace-nowrap rounded-full px-4 py-2 text-sm font-bold border ${tab === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>{l}</button>
        ))}
      </div>

      {tab === "dashboard" && (
        <div className="mt-8 grid grid-cols-2 lg:grid-cols-3 gap-4" data-testid="partner-stats">
          <Stat label="Total events" value={stats.events} testid="stat-events" />
          <Stat label="Published" value={stats.published} testid="stat-published" />
          <Stat label="Pending review" value={stats.pending} testid="stat-pending" />
          <Stat label="Participants" value={stats.participants} testid="stat-participants" />
          <Stat label="Revenue" value={money(stats.revenue)} testid="stat-revenue" />
          <Stat label="Payout due" value={money(stats.payout_due)} sub={`after ${15}% platform fee`} testid="stat-payout" />
          <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid="partner-rating">
            <p className="overline">Member rating</p>
            <div className="mt-2 flex items-center gap-2">
              <Stars value={stats.rating || 0} />
              <span className="text-2xl font-display font-semibold">{stats.rating || "—"}</span>
            </div>
            <p className="text-xs text-slate-500 mt-1">{stats.rating_count || 0} reviews across your events</p>
          </div>
        </div>
      )}

      {tab === "events" && (
        <div className="mt-8 space-y-4">
          {events.length ? events.map((ev) => (
            <div key={ev.id} className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-wrap gap-4 items-center" data-testid={`partner-event-${ev.id}`}>
              {ev.cover_image && <img src={fileUrl(ev.cover_image)} alt="" className="h-16 w-24 rounded-xl object-cover" />}
              <div className="flex-1 min-w-[200px]">
                <p className="font-semibold">{ev.title}</p>
                <p className="text-xs text-slate-500 mt-1">{ev.city} · {fmtDate(ev.starts_at)} · {ev.participant_count} going · {ev.price > 0 ? money(ev.price) : "Free"}</p>
              </div>
              <Badge tone={statusTone(ev.status)}>{ev.status}</Badge>
              <div className="flex gap-2">
                <button onClick={() => { setF({ ...blank, ...ev, price: ev.price_input ?? ev.price,
                  price_currency: ev.price_currency || "USD",
                  starts_at: ev.starts_at?.slice(0, 16), ends_at: ev.ends_at?.slice(0, 16) }); setEditing(ev.id); setTab("create"); }}
                  data-testid={`edit-event-${ev.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Edit</button>
                <button onClick={() => viewParticipants(ev)} data-testid={`participants-event-${ev.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Participants</button>
                {(ev.status === "draft" || ev.status === "rejected") && (
                  <button onClick={() => submitExisting(ev.id)} data-testid={`submit-event-${ev.id}`} className="rounded-full bg-slate-900 text-white px-4 py-2 text-xs font-bold inline-flex items-center gap-1"><Send className="h-3 w-3" />Submit</button>
                )}
                {ev.status === "published" && <Link to={`/events/${ev.id}`} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">View</Link>}
                {ev.status === "published" && <Link to={`/door?event=${ev.id}`} data-testid={`door-event-${ev.id}`} className="rounded-full bg-brand-magenta text-white px-4 py-2 text-xs font-bold">Door check-in</Link>}
              </div>
            </div>
          )) : <Empty title="No events yet" sub="Create your first experience — admin approves it before it goes live."
            action={<button onClick={() => setTab("create")} className="rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Create event</button>} />}
        </div>
      )}

      {tab === "create" && (
        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 space-y-4 max-w-3xl" data-testid="partner-event-form">
          <h2 className="text-xl font-bold">{editing ? "Edit event" : "Create event"}</h2>
          <CopyHelper form={f} onApply={(patch) => setF({ ...f, ...patch })} />
          {[["title", "Event title"], ["venue", "Venue"]].map(([k, l]) => (
            <label key={k} className="block"><span className="text-xs font-bold text-slate-600">{l}</span>
              <input data-testid={`event-${k}`} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
          ))}
          <ImageUpload value={f.cover_image} onChange={(url) => setF({ ...f, cover_image: url })} label="Cover image" testid="event-cover-upload" aspect="wide" />
          <GalleryUpload value={f.gallery} onChange={(gallery) => setF({ ...f, gallery })} testid="event-gallery-upload" />
          <label className="block"><span className="text-xs font-bold text-slate-600">Description</span>
            <textarea data-testid="event-description-json" hidden value={f.description} readOnly />
            <RichText value={f.description} rows={5} testid="event-description"
              onChange={(html) => setF({ ...f, description: html })} />
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
          <div className="grid sm:grid-cols-2 gap-4">
            <label className="block"><span className="text-xs font-bold text-slate-600">Category</span>
              <select data-testid="event-category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">{meta.categories.map((c) => <option key={c}>{c}</option>)}</select></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Country</span>
              <select data-testid="event-country" value={f.country}
                onChange={(e) => {
                  const c = (meta.countries || []).find((x) => x.name === e.target.value);
                  setF({ ...f, country: e.target.value, city: c?.primary_city || c?.cities?.[0] || f.city,
                    price_currency: c?.currency || f.price_currency });
                }}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
                {(meta.countries || []).map((c) => <option key={c.code} value={c.name}>{c.name}</option>)}
              </select></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">City</span>
              <select data-testid="event-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
                {(((meta.countries || []).find((c) => c.name === f.country)?.cities) || meta.cities || []).map((c) => <option key={c}>{c}</option>)}
              </select></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Starts at</span>
              <input type="datetime-local" data-testid="event-starts" value={f.starts_at} onChange={(e) => setF({ ...f, starts_at: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Ends at</span>
              <input type="datetime-local" data-testid="event-ends" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Ticket price (0 = free)</span>
              <input type="number" data-testid="event-price" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Price currency</span>
              <select data-testid="event-price-currency" value={f.price_currency} onChange={(e) => setF({ ...f, price_currency: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
                {(meta.currencies || []).map((c) => <option key={c.code} value={c.code}>{`${c.code} — ${c.label}`}</option>)}
              </select>
              <span className="mt-1.5 block text-[11px] text-slate-500">
                Locals pay exactly this in {f.price_currency}. Other currencies convert automatically.
              </span></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Capacity</span>
              <input type="number" data-testid="event-capacity" value={f.capacity} onChange={(e) => setF({ ...f, capacity: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
            <label className="block"><span className="text-xs font-bold text-slate-600">Approval mode</span>
              <select data-testid="event-approval" value={f.approval_mode} onChange={(e) => setF({ ...f, approval_mode: e.target.value })}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
                <option value="instant">Instant confirmation</option>
                <option value="organizer">Organiser approval</option>
                <option value="admin">Admin approval</option>
              </select></label>
          </div>
          <label className="block"><span className="text-xs font-bold text-slate-600">Rules / terms</span>
            <RichText value={f.rules} rows={3} testid="event-rules"
              onChange={(html) => setF({ ...f, rules: html })} /></label>
          <label className="block"><span className="text-xs font-bold text-slate-600">Cancellation policy</span>
            <RichText value={f.cancellation_policy} rows={3} testid="event-cancellation"
              onChange={(html) => setF({ ...f, cancellation_policy: html })} /></label>
          <div className="flex gap-3 pt-2">
            <button onClick={() => save(false)} data-testid="save-draft-btn" className="rounded-full border border-slate-200 px-6 py-3 text-sm font-bold">Save draft</button>
            <button onClick={() => save(true)} data-testid="submit-review-btn" className="rounded-full bg-slate-900 text-white px-6 py-3 text-sm font-bold inline-flex items-center gap-2"><Plus className="h-4 w-4" />Submit for review</button>
          </div>
        </div>
      )}

      {tab === "participants" && (
        <div className="mt-8">
          {participants ? (
            <>
              <h2 className="text-xl font-bold">{participants.ev.title}</h2>
              <div className="mt-4 rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100" data-testid="participants-list">
                {participants.items.length ? participants.items.map((p) => (
                  <div key={p.id} className="p-4 flex items-center gap-4">
                    {p.photo ? <img src={fileUrl(p.photo)} alt="" className="h-10 w-10 rounded-full object-cover" /> : <span className="h-10 w-10 rounded-full bg-slate-200" />}
                    <div className="flex-1"><p className="font-semibold text-sm">{p.full_name}</p><p className="text-xs text-slate-500">{p.city}</p></div>
                    <Badge tone={statusTone(p.participation_status)}>{p.participation_status}</Badge>
                  </div>
                )) : <p className="p-6 text-sm text-slate-500">No participants yet.</p>}
              </div>
            </>
          ) : <Empty title="Pick an event" sub="Open My events and choose Participants." />}
        </div>
      )}

      {tab === "reviews" && (
        <div className="mt-8" data-testid="partner-reviews">
          <div className="grid sm:grid-cols-3 gap-4">
            <Stat label="Member rating" value={reviews?.average || "—"} testid="prev-average" />
            <Stat label="Reviews" value={reviews?.count || 0} testid="prev-count" />
            <Stat label="Awaiting your reply" value={reviews?.unanswered || 0} sub="A reply shows publicly under the review" testid="prev-unanswered" />
          </div>
          <div className="mt-6 space-y-4">
            {reviews?.items?.length ? reviews.items.map((r) => (
              <div key={r.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`partner-review-${r.id}`}>
                <div className="flex flex-wrap items-center gap-3">
                  {r.user_photo ? <img src={fileUrl(r.user_photo)} alt="" className="h-9 w-9 rounded-full object-cover" />
                    : <span className="h-9 w-9 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{r.user_name?.[0]}</span>}
                  <div className="min-w-[140px]">
                    <p className="text-sm font-semibold">{r.user_name}</p>
                    <p className="text-[11px] text-slate-400">{r.event_title} · {fmtDate(r.created_at)}</p>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    {r.status === "hidden" && <Badge tone="red">hidden by admin</Badge>}
                    <Stars value={r.rating} />
                  </div>
                </div>
                {r.comment && <p className="mt-3 text-sm text-slate-600 leading-relaxed">{r.comment}</p>}
                {r.reply ? (
                  <div className="mt-4 rounded-xl border-l-2 border-slate-900 bg-slate-50 px-4 py-3" data-testid={`partner-reply-${r.id}`}>
                    <p className="overline">Your reply · {fmtDate(r.reply.at)}</p>
                    <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{r.reply.body}</p>
                    <button onClick={() => { setReplyFor(r.id); setReplyText(r.reply.body); }} data-testid={`edit-reply-${r.id}`}
                      className="mt-2 text-[11px] font-bold text-slate-500 hover:text-slate-900">Edit reply</button>
                  </div>
                ) : replyFor !== r.id && (
                  <button onClick={() => { setReplyFor(r.id); setReplyText(""); }} data-testid={`reply-btn-${r.id}`}
                    className="mt-3 rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Reply publicly</button>
                )}
                {replyFor === r.id && (
                  <div className="mt-3">
                    <textarea rows={3} value={replyText} onChange={(e) => setReplyText(e.target.value)} data-testid={`reply-input-${r.id}`}
                      placeholder="Thank the member, or explain what you'll change next time…"
                      className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
                    <div className="mt-2 flex gap-2">
                      <button onClick={() => postReply(r.id)} data-testid={`reply-submit-${r.id}`}
                        className="rounded-full bg-slate-900 text-white px-5 py-2 text-xs font-bold">Post reply</button>
                      <button onClick={() => { setReplyFor(null); setReplyText(""); }}
                        className="rounded-full border border-slate-200 px-5 py-2 text-xs font-bold">Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            )) : <Empty title="No reviews yet" sub="Attendees can review an experience once it has finished." />}
          </div>
        </div>
      )}

      {tab === "payouts" && (
        <div className="mt-8" data-testid="partner-payouts">
          <div className="grid sm:grid-cols-3 gap-4">
            <Stat label="Gross revenue" value={money(stats.revenue)} testid="rev-gross" />
            <Stat label="Pending payout" value={money(payouts?.pending_total || 0)} sub="Settled 48h after each event" testid="rev-payout" />
            <Stat label="Settled to date" value={money(payouts?.paid_total || 0)} testid="rev-paid" />
          </div>
          <div className="mt-6 rounded-xl border border-slate-200 bg-white overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left"><tr>
                {["Event", "Orders", "Gross", "Platform fee", "Net payable", "Status", "Reference"].map((h) => (
                  <th key={h} className="px-4 py-3 text-xs uppercase tracking-wider text-slate-500 font-semibold">{h}</th>))}
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {(payouts?.items || []).map((p) => (
                  <tr key={p.id} data-testid={`payout-row-${p.id}`}>
                    <td className="px-4 py-3"><p className="font-semibold">{p.event_title}</p><p className="text-xs text-slate-500">{fmtDate(p.created_at)}</p></td>
                    <td className="px-4 py-3">{p.orders}</td>
                    <td className="px-4 py-3">{money(p.gross)}</td>
                    <td className="px-4 py-3 text-slate-500">− {money(p.fee)} ({p.fee_percent}%)</td>
                    <td className="px-4 py-3 font-semibold">{money(p.net)}</td>
                    <td className="px-4 py-3"><Badge tone={p.status === "paid" ? "green" : "amber"}>{p.status}</Badge></td>
                    <td className="px-4 py-3 text-xs text-slate-500">{p.reference || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!payouts?.items?.length && <p className="p-6 text-sm text-slate-500">No payouts yet. A ledger entry is created automatically 48 hours after each event finishes.</p>}
          </div>
          <DoorTakings />
        </div>
      )}
    </div>
  );
}

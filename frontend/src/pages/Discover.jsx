import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PersonCard } from "@/components/Cards";
import { Spinner, Empty, Badge, SEO } from "@/components/Shared";
import { MessageCircle, UserPlus, Ban, Flag, CalendarDays, Ticket } from "lucide-react";

export function Discover() {
  const [meta, setMeta] = useState({ cities: [], categories: [], interests: [] });
  const [f, setF] = useState({ city: "", interest: "", category: "", min_age: 21, max_age: 60, q: "" });
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);

  useEffect(() => { api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, []);

  const load = useCallback(() => {
    api.get("/discover", { params: { ...f, page, limit: 12 } })
      .then(({ data }) => setData(data)).catch(() => setData({ items: [], total: 0 }));
  }, [f, page]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="discover-page">
      <SEO title="Discover companions" />
      <p className="overline">Social discovery</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">Find your people</h1>
      <p className="mt-3 text-slate-600 max-w-2xl">Members near you who like the same things. Connect, chat, then pick an experience together.</p>

      <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-4 grid gap-3 md:grid-cols-5">
        <input data-testid="discover-search" placeholder="Search by name…" value={f.q}
          onChange={(e) => { setPage(1); setF({ ...f, q: e.target.value }); }}
          className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
        <select data-testid="discover-city" value={f.city} onChange={(e) => { setPage(1); setF({ ...f, city: e.target.value }); }}
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value="">All cities</option>{meta.cities.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select data-testid="discover-interest" value={f.interest} onChange={(e) => { setPage(1); setF({ ...f, interest: e.target.value }); }}
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value="">Any interest</option>{meta.interests.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select data-testid="discover-category" value={f.category} onChange={(e) => { setPage(1); setF({ ...f, category: e.target.value }); }}
          className="rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          <option value="">Any event type</option>{meta.categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <div className="flex items-center gap-2">
          <input type="number" min={21} max={99} value={f.min_age} data-testid="discover-min-age"
            onChange={(e) => { setPage(1); setF({ ...f, min_age: Number(e.target.value) }); }}
            className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
          <span className="text-slate-400 text-sm">–</span>
          <input type="number" min={21} max={99} value={f.max_age} data-testid="discover-max-age"
            onChange={(e) => { setPage(1); setF({ ...f, max_age: Number(e.target.value) }); }}
            className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
        </div>
      </div>

      {!data ? <Spinner /> : data.items.length ? (
        <>
          <p className="mt-8 text-sm text-slate-500">{data.total} members match</p>
          <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-5">
            {data.items.map((p) => <PersonCard key={p.id} p={p} />)}
          </div>
          {data.total > 12 && (
            <div className="mt-10 flex justify-center gap-3">
              <button disabled={page === 1} onClick={() => setPage(page - 1)} data-testid="discover-prev"
                className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold disabled:opacity-40">Previous</button>
              <span className="px-4 py-2.5 text-sm">Page {page}</span>
              <button disabled={page >= Math.ceil(data.total / 12)} onClick={() => setPage(page + 1)} data-testid="discover-next"
                className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-bold disabled:opacity-40">Next</button>
            </div>
          )}
        </>
      ) : <div className="mt-8"><Empty title="No members match" sub="Try a wider age range or another city." /></div>}
    </div>
  );
}

export function PublicProfile() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const [p, setP] = useState(null);
  const [events, setEvents] = useState([]);
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    api.get(`/users/${id}`).then(({ data }) => setP(data)).catch((e) => { toast.error(errMsg(e)); setP(false); });
  }, [id]);
  useEffect(() => { load(); api.get("/events", { params: { limit: 20 } }).then(({ data }) => setEvents(data.items)).catch(() => {}); }, [load]);

  if (p === null) return <Spinner />;
  if (p === false) return <div className="py-24"><Empty title="Profile unavailable" sub="This member may be private or no longer active." /></div>;

  const message = async () => {
    try { const { data } = await api.post("/conversations", { user_id: id }); nav(`/messages?c=${data.id}`); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const connect = async () => {
    try { await api.post(`/users/${id}/connect`); toast.success(`Connection sent to ${p.full_name.split(" ")[0]}`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const block = async () => {
    try { await api.post(`/users/${id}/block`); toast.success("Member blocked. They can no longer reach you."); nav("/discover"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const report = async () => {
    if (!reason.trim()) return toast.error("Please describe the issue.");
    try {
      await api.post("/reports", { target_type: "user", target_id: id, reason, details: "" });
      toast.success("Report submitted to our safety team."); setReporting(false); setReason("");
    } catch (e) { toast.error(errMsg(e)); }
  };
  const invite = async (ev) => {
    try {
      const { data } = await api.post("/conversations", { user_id: id });
      await api.post(`/conversations/${data.id}/messages`, { body: `Hey! Want to join me at "${ev.title}" on ${new Date(ev.starts_at).toLocaleDateString("en-IN")}? ${window.location.origin}/events/${ev.id}` });
      toast.success("Invitation sent in chat");
      nav(`/messages?c=${data.id}`);
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 pb-28" data-testid="public-profile-page">
      <SEO title={p.full_name} description={p.bio} />
      <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden">
        <div className="h-32 bg-slate-900" />
        <div className="px-6 sm:px-10 pb-8">
          <div className="-mt-14 flex items-end gap-5 flex-wrap">
            {p.photo ? <img src={p.photo} alt={p.full_name} className="h-28 w-28 rounded-2xl object-cover border-4 border-white" />
              : <div className="h-28 w-28 rounded-2xl bg-slate-200 border-4 border-white grid place-items-center text-3xl font-display">{p.full_name[0]}</div>}
            <div className="pb-2">
              <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
                {p.full_name}{p.membership && <Badge tone="dark">Premium</Badge>}
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                {p.age ? `${p.age} · ` : ""}{p.city} · Joined {new Date(p.created_at).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}
              </p>
            </div>
          </div>

          <p className="mt-6 text-slate-600 leading-relaxed">{p.bio || "This member hasn't added a bio yet."}</p>

          <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div className="rounded-xl border border-slate-200 p-4"><p className="overline">Events attended</p><p className="text-xl font-display font-bold mt-1">{p.events_attended}</p></div>
            <div className="rounded-xl border border-slate-200 p-4"><p className="overline">Interests</p><p className="text-xl font-display font-bold mt-1">{p.interests?.length || 0}</p></div>
            <div className="rounded-xl border border-slate-200 p-4"><p className="overline">Verified</p><p className="text-xl font-display font-bold mt-1">{p.verified ? "Yes" : "Pending"}</p></div>
          </div>

          {p.interests?.length > 0 && (
            <div className="mt-6">
              <p className="overline">Interests</p>
              <div className="mt-3 flex flex-wrap gap-2">{p.interests.map((i) => <Badge key={i}>{i}</Badge>)}</div>
            </div>
          )}
          {p.event_categories?.length > 0 && (
            <div className="mt-6">
              <p className="overline">Event interests</p>
              <div className="mt-3 flex flex-wrap gap-2">{p.event_categories.map((i) => <Badge key={i}>{i}</Badge>)}</div>
            </div>
          )}

          {user && user.id !== id && (
            <>
              <div className="mt-8 flex flex-wrap gap-3">
                <button onClick={message} data-testid="profile-message-btn" className="inline-flex items-center gap-2 rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold"><MessageCircle className="h-4 w-4" />Message</button>
                <button onClick={connect} data-testid="profile-connect-btn" className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold"><UserPlus className="h-4 w-4" />{p.is_connected ? "Connected" : "Connect"}</button>
                <button onClick={block} data-testid="profile-block-btn" className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold text-slate-600"><Ban className="h-4 w-4" />Block</button>
                <button onClick={() => setReporting(!reporting)} data-testid="profile-report-btn" className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold text-slate-600"><Flag className="h-4 w-4" />Report</button>
              </div>
              {reporting && (
                <div className="mt-4 rounded-2xl border border-slate-200 p-4 space-y-3 max-w-md" data-testid="report-user-form">
                  <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Tell our safety team what happened"
                    className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  <button onClick={report} data-testid="submit-user-report" className="rounded-full bg-red-600 text-white px-5 py-2.5 text-xs font-bold">Submit report</button>
                </div>
              )}

              <div className="mt-8">
                <p className="overline">Invite to an event</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {events.slice(0, 5).map((ev) => (
                    <button key={ev.id} onClick={() => invite(ev)} data-testid={`invite-event-${ev.id}`}
                      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold hover:border-slate-900">
                      <CalendarDays className="h-3.5 w-3.5" />{ev.title}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
          {!user && (
            <div className="mt-8 rounded-2xl bg-slate-50 border border-slate-200 p-6">
              <p className="font-semibold">Join Buddilio to connect</p>
              <p className="text-sm text-slate-500 mt-1">Messaging and connections are for verified members only.</p>
              <Link to="/register" data-testid="profile-join-cta" className="mt-4 inline-block rounded-full bg-slate-900 text-white px-5 py-2.5 text-sm font-bold">Join free</Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function MyProfile() {
  const { user, refresh } = useAuth();
  const [meta, setMeta] = useState({ cities: [], categories: [], interests: [] });
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get("/meta").then(({ data }) => setMeta(data)).catch(() => {}); }, []);
  useEffect(() => {
    if (user) setF({
      full_name: user.full_name || "", bio: user.bio || "", city: user.city || "", photo: user.photo || "",
      interests: user.interests || [], event_categories: user.event_categories || [], lifestyle: user.lifestyle || [],
      privacy: user.privacy || { profile_visibility: "public", who_can_message: "everyone" },
      notification_prefs: user.notification_prefs || { email: true, in_app: true, sms: false },
    });
  }, [user]);

  if (!f) return <Spinner />;

  const toggle = (key, val) => setF((p) => ({ ...p, [key]: p[key].includes(val) ? p[key].filter((x) => x !== val) : [...p[key], val] }));

  const photo = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 3_000_000) return toast.error("Please pick an image under 3MB.");
    const r = new FileReader();
    r.onload = () => setF((p) => ({ ...p, photo: r.result }));
    r.readAsDataURL(file);
  };

  const save = async () => {
    setBusy(true);
    try { await api.put("/users/me", f); await refresh(); toast.success("Profile updated"); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-10 pb-28" data-testid="my-profile-page">
      <SEO title="My profile" />
      <h1 className="text-3xl font-bold">My profile</h1>
      <p className="mt-2 text-sm text-slate-500">Your mobile, email and date of birth are never shown publicly.</p>

      <div className="mt-8 space-y-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 space-y-4">
          <div className="flex items-center gap-4">
            {f.photo ? <img src={f.photo} alt="" className="h-20 w-20 rounded-2xl object-cover" />
              : <div className="h-20 w-20 rounded-2xl bg-slate-100 grid place-items-center text-2xl font-display">{f.full_name?.[0]}</div>}
            <input type="file" accept="image/*" onChange={photo} data-testid="profile-photo-input"
              className="text-sm file:mr-3 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2 file:text-white file:text-xs file:font-bold" />
          </div>
          <label className="block"><span className="text-xs font-bold text-slate-600">Full name</span>
            <input data-testid="profile-name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
          <label className="block"><span className="text-xs font-bold text-slate-600">Bio</span>
            <textarea data-testid="profile-bio" rows={3} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm" /></label>
          <label className="block"><span className="text-xs font-bold text-slate-600">City</span>
            <select data-testid="profile-city" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
              {meta.cities.map((c) => <option key={c}>{c}</option>)}
            </select></label>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <p className="overline">Interests</p>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="profile-interests">
            {meta.interests.map((i) => (
              <button key={i} onClick={() => toggle("interests", i)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold border ${f.interests.includes(i) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>{i}</button>
            ))}
          </div>
          <p className="overline mt-6">Event interests</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {meta.categories.map((i) => (
              <button key={i} onClick={() => toggle("event_categories", i)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold border ${f.event_categories.includes(i) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200"}`}>{i}</button>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 space-y-4" data-testid="privacy-settings">
          <p className="overline">Privacy</p>
          <label className="block"><span className="text-xs font-bold text-slate-600">Who can see my profile</span>
            <select data-testid="privacy-visibility" value={f.privacy.profile_visibility}
              onChange={(e) => setF({ ...f, privacy: { ...f.privacy, profile_visibility: e.target.value } })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
              <option value="public">Everyone on Buddilio</option>
              <option value="private">Only my connections</option>
            </select></label>
          <label className="block"><span className="text-xs font-bold text-slate-600">Who can message me</span>
            <select data-testid="privacy-messaging" value={f.privacy.who_can_message}
              onChange={(e) => setF({ ...f, privacy: { ...f.privacy, who_can_message: e.target.value } })}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm">
              <option value="everyone">Any verified member</option>
              <option value="connections">Only my connections</option>
            </select></label>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="notification-prefs">
          <p className="overline">Notification preferences</p>
          <div className="mt-3 space-y-3">
            {[["in_app", "In-app notifications"], ["email", "Email notifications"], ["sms", "SMS / WhatsApp alerts"]].map(([k, l]) => (
              <label key={k} className="flex items-center gap-3 text-sm">
                <input type="checkbox" data-testid={`notif-${k}`} checked={!!f.notification_prefs[k]}
                  onChange={(e) => setF({ ...f, notification_prefs: { ...f.notification_prefs, [k]: e.target.checked } })} className="h-4 w-4" />
                {l}
              </label>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <button onClick={save} disabled={busy} data-testid="save-profile-btn"
            className="rounded-full bg-slate-900 text-white px-7 py-3 text-sm font-bold disabled:opacity-60">{busy ? "Saving…" : "Save changes"}</button>
          <Link to={`/u/${user.id}`} data-testid="view-public-profile" className="rounded-full border border-slate-200 bg-white px-7 py-3 text-sm font-bold">View public profile</Link>
          <Link to="/orders" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-7 py-3 text-sm font-bold"><Ticket className="h-4 w-4" />My orders</Link>
        </div>
      </div>
    </div>
  );
}

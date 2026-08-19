import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { BadgeCheck, MapPin, Search, Star, Users, Heart } from "lucide-react";
import { api, errMsg, fileUrl, fmtDate } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { EventCard } from "@/components/Cards";
import { Spinner, Empty, SEO } from "@/components/Shared";
import { RichHtml, plainText } from "@/components/RichText";

const Avatar = ({ src, name, size = "h-16 w-16" }) => (src ? (
  <img src={fileUrl(src)} alt={name} className={`${size} rounded-2xl object-cover border border-slate-200`} />
) : (
  <span className={`${size} rounded-2xl bg-slate-900 text-white grid place-items-center font-display text-xl`}>
    {name?.[0] || "B"}
  </span>
));

export function Hosts() {
  const [f, setF] = useState({ q: "", verified_only: true });
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    api.get("/hosts", { params: { ...f, limit: 24 } })
      .then(({ data }) => setData(data)).catch(() => setData({ items: [], total: 0 }));
  }, [f]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28" data-testid="hosts-page">
      <SEO title="Organisers on Buddilio"
        description="Browse the verified organisers behind Buddilio nights — their events, ratings and photo walls." />
      <p className="overline">Organisers</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold">The people behind the nights</h1>
      <p className="mt-3 max-w-2xl text-slate-600">Follow the organisers whose taste matches yours and hear about
        their next experience before it fills up.</p>

      <div className="mt-8 flex flex-wrap gap-3">
        <label className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input data-testid="hosts-search" placeholder="Search organisers…" value={f.q}
            onChange={(e) => setF({ ...f, q: e.target.value })}
            className="w-full rounded-full border border-slate-200 bg-white pl-10 pr-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
        </label>
        <button data-testid="hosts-verified-only" onClick={() => setF({ ...f, verified_only: !f.verified_only })}
          className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2.5 text-xs font-bold border transition-colors ${f.verified_only ? "bg-emerald-600 text-white border-emerald-600" : "bg-white border-slate-200 text-emerald-700"}`}>
          <BadgeCheck className="h-4 w-4" />Verified only
        </button>
      </div>

      {!data ? <div className="mt-10"><Spinner /></div> : data.items.length === 0 ? (
        <div className="mt-10"><Empty title="No organisers match that" sub="Try a different name or turn off the verified filter." /></div>
      ) : (
        <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {data.items.map((h) => (
            <Link key={h.id} to={`/host/${h.id}`} data-testid={`host-card-${h.id}`}
              className="group rounded-2xl border border-slate-200 bg-white p-5 hover-lift flex gap-4">
              <Avatar src={h.photo} name={h.name} />
              <div className="min-w-0">
                <p className="font-bold flex items-center gap-1.5 truncate">
                  {h.name}
                  {h.verified && <BadgeCheck className="h-4 w-4 shrink-0 text-emerald-600" data-testid={`host-verified-${h.id}`} />}
                </p>
                <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500"><MapPin className="h-3 w-3" />{h.city || "Global"}</p>
                <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1"><Star className="h-3 w-3" />{h.rating || "—"}</span>
                  <span>{h.events} events</span>
                  <span className="inline-flex items-center gap-1"><Users className="h-3 w-3" />{h.followers} following</span>
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function HostProfile() {
  const { id } = useParams();
  const { user } = useAuth();
  const [h, setH] = useState(null);

  const load = useCallback(() => {
    api.get(`/hosts/${id}`).then(({ data }) => setH(data)).catch(() => setH(false));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const follow = async () => {
    if (!user) return toast.error("Log in to follow this organiser.");
    try {
      const { data } = await api.post(`/hosts/${id}/follow`);
      setH((p) => ({ ...p, is_following: data.following, followers: data.followers }));
      toast.success(data.following ? "You'll hear about their next night first." : "Unfollowed.");
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (h === null) return <Spinner label="Loading organiser" />;
  if (h === false) return <div className="py-24"><Empty title="Organiser not found" sub="This profile may have been removed." /></div>;

  return (
    <div data-testid="host-profile-page">
      <SEO title={`${h.name} on Buddilio`} description={plainText(h.bio) || `Events hosted by ${h.name}.`} />
      <div className="bg-brand-ink text-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 py-12 flex flex-wrap items-center gap-6">
          <Avatar src={h.photo} name={h.name} size="h-24 w-24" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-3xl sm:text-4xl font-bold">{h.name}</h1>
              {h.verified && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-300 px-2.5 py-1 text-xs font-bold"
                  data-testid="host-verified-badge">
                  <BadgeCheck className="h-4 w-4" />Verified organiser
                </span>
              )}
            </div>
            <p className="mt-2 text-sm text-white/70">
              {h.city || "Global"} · {h.events} events · {h.rating ? `${h.rating}★ (${h.rating_count})` : "no ratings yet"} ·{" "}
              <span data-testid="host-followers">{h.followers} following</span>
            </p>
          </div>
          <button onClick={follow} data-testid="host-follow-btn"
            className={`inline-flex items-center gap-2 rounded-full px-6 py-3 text-sm font-bold transition-transform hover:-translate-y-0.5 ${h.is_following ? "bg-white/10 text-white border border-white/20" : "brand-gradient text-white"}`}>
            <Heart className={`h-4 w-4 ${h.is_following ? "fill-current" : ""}`} />
            {h.is_following ? "Following" : "Follow"}
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 pb-28 space-y-12">
        {h.bio && <RichHtml html={h.bio} className="max-w-3xl text-slate-600 leading-relaxed" testid="host-bio" />}

        <div>
          <h2 className="text-2xl font-bold">Coming up</h2>
          {h.upcoming.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500" data-testid="host-upcoming-empty">
              Nothing on the calendar right now — follow them to hear first.
            </p>
          ) : (
            <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="host-upcoming">
              {h.upcoming.map((ev) => <EventCard key={ev.id} ev={ev} />)}
            </div>
          )}
        </div>

        {h.photos.length > 0 && (
          <div>
            <h2 className="text-2xl font-bold">From their photo walls</h2>
            <div className="mt-4 grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3" data-testid="host-photos">
              {h.photos.map((p, i) => (
                <Link key={i} to={`/events/${p.event_id}`} data-testid={`host-photo-${i}`}>
                  <img src={fileUrl(p.url)} alt={p.caption || ""} loading="lazy"
                    className="rounded-xl aspect-square object-cover w-full transition-transform hover:scale-[1.03]" />
                </Link>
              ))}
            </div>
          </div>
        )}

        {h.reviews.length > 0 && (
          <div>
            <h2 className="text-2xl font-bold">What members said</h2>
            <div className="mt-4 grid sm:grid-cols-3 gap-4" data-testid="host-reviews">
              {h.reviews.map((r, i) => (
                <blockquote key={i} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`host-review-${i}`}>
                  <p className="flex items-center gap-1 text-sm font-bold">{r.rating}<Star className="h-3.5 w-3.5 fill-slate-900" /></p>
                  <p className="mt-2 text-sm text-slate-600 italic leading-relaxed">“{r.comment}”</p>
                </blockquote>
              ))}
            </div>
          </div>
        )}

        {h.past.length > 0 && (
          <div>
            <h2 className="text-2xl font-bold">Already happened</h2>
            <ul className="mt-4 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white" data-testid="host-past">
              {h.past.map((ev) => (
                <li key={ev.id}>
                  <Link to={`/events/${ev.id}`} data-testid={`host-past-${ev.id}`}
                    className="flex flex-wrap items-center gap-x-3 px-5 py-3.5 text-sm hover:bg-slate-50">
                    <span className="font-semibold">{ev.title}</span>
                    <span className="text-slate-500">{ev.city}</span>
                    <span className="ml-auto text-xs text-slate-400">{fmtDate(ev.starts_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

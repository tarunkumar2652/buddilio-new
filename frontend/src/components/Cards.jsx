import { Link } from "react-router-dom";
import { CalendarDays, MapPin, Users, Star } from "lucide-react";
import { fmtDate, fileUrl } from "@/lib/api";
import { useCurrency } from "@/context/CurrencyContext";
import { Badge } from "@/components/Shared";

export const EventCard = ({ ev, className = "" }) => {
  const { fmt } = useCurrency();
  return (
    <Link to={`/events/${ev.id}`} data-testid={`event-card-${ev.id}`}
      className={`group block rounded-2xl overflow-hidden bg-white border border-slate-200 hover-lift ${className}`}>
      <div className="relative aspect-[4/3] overflow-hidden bg-slate-100">
        <img src={fileUrl(ev.cover_image)} alt={ev.title} loading="lazy"
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
        <div className="absolute top-3 left-3 flex gap-2">
          <span className="rounded-full bg-white/95 px-2.5 py-1 text-[11px] font-bold">{ev.category}</span>
          {ev.featured && <span className="rounded-full bg-slate-900 text-white px-2.5 py-1 text-[11px] font-bold">Featured</span>}
        </div>
        {ev.rating > 0 && (
          <span className="absolute top-3 right-3 inline-flex items-center gap-1 rounded-full bg-white/95 px-2.5 py-1 text-[11px] font-bold" data-testid={`event-rating-${ev.id}`}>
            <Star className="h-3 w-3 fill-slate-900" />{ev.rating}
          </span>
        )}
        <p className="absolute bottom-3 left-3 text-white font-semibold text-sm">
          {ev.price > 0 ? fmt(ev.price) : "Free entry"}
        </p>
      </div>
      <div className="p-5">
        <h3 className="font-display font-semibold text-lg leading-snug line-clamp-2">{ev.title}</h3>
        <div className="mt-3 space-y-1.5 text-sm text-slate-500">
          <p className="flex items-center gap-2"><CalendarDays className="h-4 w-4" />{fmtDate(ev.starts_at)}</p>
          <p className="flex items-center gap-2"><MapPin className="h-4 w-4" />{ev.venue || ev.city}</p>
          <p className="flex items-center gap-2"><Users className="h-4 w-4" />{ev.participant_count || 0} going · {ev.capacity} spots</p>
        </div>
      </div>
    </Link>
  );
};

export const PersonCard = ({ p }) => (
  <Link to={`/u/${p.id}`} data-testid={`discover-card-${p.id}`}
    className="group block rounded-2xl overflow-hidden border border-slate-200 bg-white hover-lift">
    <div className="relative aspect-[4/5] bg-slate-100 overflow-hidden">
      {p.photo ? (
        <img src={fileUrl(p.photo)} alt={p.full_name} loading="lazy"
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
      ) : (
        <div className="h-full w-full grid place-items-center text-4xl font-display text-slate-300">{p.full_name?.[0]}</div>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
      {p.membership && <span className="absolute top-3 right-3 rounded-full bg-white/95 px-2.5 py-1 text-[10px] font-bold">PREMIUM</span>}
      <div className="absolute bottom-0 p-4 text-white">
        <p className="font-display font-semibold text-lg leading-tight">{p.full_name}{p.age ? `, ${p.age}` : ""}</p>
        <p className="text-xs opacity-85">{p.city}</p>
      </div>
    </div>
    <div className="p-4">
      <p className="text-sm text-slate-600 line-clamp-2 min-h-[40px]">{p.bio || "Buddilio member"}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(p.interests || []).slice(0, 3).map((i) => <Badge key={i}>{i}</Badge>)}
      </div>
    </div>
  </Link>
);

export const Stars = ({ value = 0, size = "h-4 w-4", onPick }) => (
  <div className="flex gap-0.5">
    {[1, 2, 3, 4, 5].map((n) => (
      onPick ? (
        <button key={n} type="button" onClick={() => onPick(n)} data-testid={`star-${n}`}>
          <Star className={`${size} ${n <= value ? "fill-slate-900 text-slate-900" : "text-slate-300"}`} />
        </button>
      ) : (
        <Star key={n} className={`${size} ${n <= Math.round(value) ? "fill-slate-900 text-slate-900" : "text-slate-300"}`} />
      )
    ))}
  </div>
);

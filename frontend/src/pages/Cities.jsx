import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg, fileUrl, citySlug } from "@/lib/api";
import { EventCard } from "@/components/Cards";
import { Stars } from "@/components/Cards";
import { Spinner, Empty, SEO } from "@/components/Shared";
import { MapPin, Users, CalendarDays, Building2, ArrowRight, Mail, Globe2, Sparkles } from "lucide-react";

const jsonLd = (data) => {
  const el = document.getElementById("city-jsonld") || Object.assign(document.createElement("script"), {
    id: "city-jsonld", type: "application/ld+json",
  });
  el.textContent = JSON.stringify(data);
  if (!el.parentNode) document.head.appendChild(el);
};

const cityFaqs = (d) => [
  [`Is Buddilio live in ${d.name}?`, d.events_total > 0
    ? `Yes. There ${d.events_total === 1 ? "is" : "are"} ${d.events_total} Buddilio experience${d.events_total === 1 ? "" : "s"} in ${d.name} and ${d.members} verified member${d.members === 1 ? "" : "s"} nearby. Browse what's on and book a spot in minutes.`
    : `Not yet — ${d.name} is on our opening list. Add your email to the waitlist on this page and we'll email you the day it opens.`],
  [`How much do Buddilio experiences cost in ${d.name}?`,
    `Organisers price every ${d.name} experience in ${d.currency}, so you pay the local amount with no conversion surprises. ${d.tax_label} of ${d.tax_percent}% is shown at checkout before you pay, and membership discounts apply automatically.`],
  [`Where do Buddilio members go out in ${d.name}?`, d.guide?.areas?.length
    ? `Mostly ${d.guide.areas.map((a) => a[0]).join(", ")}. ${d.guide.when}`
    : `Across the city — every listing shows the venue and neighbourhood before you book.`],
  ["Can I come on my own?",
    `Yes, and most members do. Every ${d.name} booking opens a group chat with the other attendees and the organiser, so you know who you're meeting before you arrive.`],
  ["Is Buddilio a dating app?",
    "No. Buddilio is a social discovery platform for finding people to attend events with — parties, dinners, concerts, sport and travel. Members are 21+ and verified, and profiles are not swipeable."],
];

export const CityIndex = () => {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/cities").then(({ data }) => setD(data)).catch(() => setD({ items: [] })); }, []);
  if (!d) return <Spinner label="Loading cities" />;

  const byCountry = d.items.reduce((acc, c) => {
    (acc[c.country] = acc[c.country] || []).push(c);
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-12 pb-28" data-testid="cities-page">
      <SEO title="Buddilio cities — where we're live"
        description={`Buddilio runs in ${d.cities} cities across ${d.countries} countries. Find curated parties, dinners and nights out near you and people to go with.`} />
      <p className="overline">Global footprint</p>
      <h1 className="mt-2 text-4xl sm:text-5xl font-bold tracking-tight">Find your city</h1>
      <p className="mt-4 text-slate-600 max-w-2xl leading-relaxed">
        Buddilio is live in <b>{d.live_cities}</b> of {d.cities} cities across {d.countries} countries. Pick yours
        to see what's on this month — or add your name to the list and we'll open it next.
      </p>

      <div className="mt-12 space-y-12">
        {Object.entries(byCountry).map(([country, cities]) => (
          <section key={country} data-testid={`cities-country-${citySlug(country)}`}>
            <h2 className="text-lg md:text-lg font-bold flex items-center gap-2">
              <Globe2 className="h-4 w-4 text-brand-magenta" />{country}
            </h2>
            <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {cities.map((c) => (
                <Link key={c.slug} to={`/city/${c.slug}`} data-testid={`city-link-${c.slug}`}
                  className="group rounded-2xl border border-slate-200 bg-white p-5 transition-all hover:border-brand-magenta/40 hover:-translate-y-0.5">
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-display font-bold text-lg">{c.name}</p>
                    <ArrowRight className="h-4 w-4 text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-brand-magenta" />
                  </div>
                  <p className="mt-2 text-xs font-semibold text-slate-500">
                    {c.live ? `${c.events} experience${c.events === 1 ? "" : "s"} live` : "Opening soon"}
                    {c.members > 0 && ` · ${c.members} member${c.members === 1 ? "" : "s"}`}
                  </p>
                  <p className="mt-1 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-400">
                    Prices in {c.currency}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
};

const Waitlist = ({ slug, city, waiting }) => {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(0);
  const submit = async (e) => {
    e.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return toast.error("Enter a valid email address.");
    try {
      const { data } = await api.post(`/cities/${slug}/waitlist`, { email });
      toast.success(data.message);
      setDone(data.waiting); setEmail("");
    } catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <form onSubmit={submit} noValidate className="rounded-3xl border border-slate-200 bg-white p-7" data-testid="city-waitlist">
      <p className="overline">Not live yet</p>
      <h2 className="mt-2 text-lg md:text-lg font-bold">Be first when Buddilio opens in {city}</h2>
      <p className="mt-2 text-sm text-slate-500 leading-relaxed">
        We open cities where members ask for them. {(done || waiting) > 0 && `${done || waiting} people are already waiting here.`}
      </p>
      <div className="mt-5 flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Mail className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}            data-testid="city-waitlist-input" placeholder="you@email.com"
            className="w-full rounded-full border border-slate-200 pl-10 pr-4 py-3 text-sm outline-none focus:ring-2 focus:ring-brand-magenta/60" />
        </div>
        <button type="submit" data-testid="city-waitlist-submit"
          className="brand-gradient text-white rounded-full px-6 py-3 text-sm font-bold transition-transform hover:scale-[1.02] active:scale-[.98]">
          Notify me
        </button>
      </div>
    </form>
  );
};

export const CityPage = () => {
  const { slug } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setD(null); setErr("");
    api.get(`/cities/${slug}`).then(({ data }) => setD(data)).catch((e) => setErr(errMsg(e)));
  }, [slug]);

  useEffect(() => {
    if (!d) return;
    jsonLd([{
      "@context": "https://schema.org", "@type": "CollectionPage",
      name: `Things to do in ${d.name} with Buddilio`,
      about: { "@type": "City", name: d.name, addressCountry: d.country_code },
      url: `${window.location.origin}/city/${d.slug}`,
      hasPart: (d.upcoming || []).map((e) => ({
        "@type": "Event", name: e.title, startDate: e.starts_at,
        location: { "@type": "Place", name: e.venue || d.name, address: `${d.name}, ${d.country}` },
      })),
    }, {
      "@context": "https://schema.org", "@type": "FAQPage",
      mainEntity: cityFaqs(d).map(([q, a]) => ({
        "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a },
      })),
    }]);
    return () => document.getElementById("city-jsonld")?.remove();
  }, [d]);

  if (err) return (
    <div className="mx-auto max-w-2xl px-4 py-20">
      <Empty testid="city-not-found" title="We're not in that city yet" sub={err}
        action={<Link to="/cities" className="rounded-full brand-gradient text-white px-5 py-2.5 text-sm font-bold">Browse all cities</Link>} />
    </div>
  );
  if (!d) return <Spinner label="Loading city" />;

  const stats = [
    [CalendarDays, `${d.events_total}`, "experiences hosted"],
    [Users, `${d.members}`, "members nearby"],
    [Building2, `${d.organisers}`, "local organisers"],
    [Sparkles, d.currency, "priced locally"],
  ];

  return (
    <div data-testid="city-page" data-city={d.slug}>
      <SEO title={`Things to do in ${d.name} — events & people to go with`}
        description={`Buddilio in ${d.name}: ${d.events_total} curated parties, dinners and nights out with ${d.members} verified members nearby. Book in ${d.currency} and never go alone.`} />

      <section className="relative overflow-hidden bg-brand-ink text-white">
        {d.hero && <img src={fileUrl(d.hero)} alt="" className="absolute inset-0 h-full w-full object-cover opacity-35" />}
        <div className="aurora opacity-70" />
        <div className="relative mx-auto max-w-6xl px-4 sm:px-6 py-20 sm:py-28">
          <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-xs font-bold text-white/85">
            <MapPin className="h-3.5 w-3.5" />{d.name} · {d.country}
          </p>
          <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight max-w-3xl">
            Nights out in <span className="text-gradient">{d.name}</span>, with people you'll actually like.
          </h1>
          <p className="mt-5 max-w-2xl text-base text-white/75 leading-relaxed">
            Curated parties, dinners, concerts and lifestyle experiences across {d.name} — every listing priced in{" "}
            {d.currency}, every member verified, and a group chat waiting once you book.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <Link to={`/events?city=${encodeURIComponent(d.name)}`} data-testid="city-browse-events"
              className="brand-gradient rounded-full px-7 py-3.5 text-sm font-bold transition-transform hover:scale-[1.03]">
              See what's on in {d.name}
            </Link>
            <Link to="/register" data-testid="city-join-btn"
              className="rounded-full border border-white/30 px-7 py-3.5 text-sm font-bold transition-colors hover:bg-white/10">
              Join Buddilio
            </Link>
          </div>
          {d.faces?.length > 0 && (
            <div className="mt-10 flex items-center gap-3" data-testid="city-faces">
              <div className="flex -space-x-3">
                {d.faces.slice(0, 6).map((f) => (
                  <img key={f.id} src={fileUrl(f.photo)} alt={f.name}
                    className="h-10 w-10 rounded-full object-cover ring-2 ring-brand-ink" />
                ))}
              </div>
              <p className="text-xs font-semibold text-white/65">
                {d.faces.map((f) => f.name.split(" ")[0]).slice(0, 3).join(", ")}
                {d.members > 3 ? ` and ${d.members - 3} more` : ""} {d.members === 1 ? "is" : "are"} out in {d.name}
              </p>
            </div>
          )}
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-14 pb-28 space-y-16">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="city-stats">
          {stats.map(([Icon, value, label]) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-white p-5">
              <Icon className="h-4 w-4 text-brand-magenta" />
              <p className="mt-3 font-display text-2xl font-bold">{value}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          ))}
        </div>

        {d.categories?.length > 0 && (
          <section>
            <h2 className="text-lg md:text-lg font-bold">What people book in {d.name}</h2>
            <div className="mt-4 flex flex-wrap gap-2" data-testid="city-categories">
              {d.categories.map((c) => (
                <Link key={c} to={`/events?city=${encodeURIComponent(d.name)}&category=${encodeURIComponent(c)}`}
                  data-testid={`city-category-${citySlug(c)}`}
                  className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold transition-colors hover:border-brand-magenta/50 hover:text-brand-magenta">
                  {c}
                </Link>
              ))}
            </div>
          </section>
        )}

        {d.guide?.intro && (
          <section data-testid="city-guide">
            <p className="overline">City guide</p>
            <h2 className="mt-1.5 text-2xl font-bold">Where to go out in {d.name}</h2>
            <p className="mt-4 max-w-3xl text-slate-600 leading-relaxed" data-testid="city-guide-intro">{d.guide.intro}</p>
            <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {d.guide.areas.map(([area, blurb], i) => (
                <div key={area} data-testid={`city-area-${i + 1}`}
                  className="rounded-2xl border border-slate-200 bg-white p-5">
                  <span className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand-magenta">
                    Area {String(i + 1).padStart(2, "0")}
                  </span>
                  <p className="mt-2.5 font-display font-bold">{area}</p>
                  <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">{blurb}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 grid sm:grid-cols-3 gap-4">
              {[["When to go out", d.guide.when], ["Getting around", d.guide.around], ["Local tip", d.guide.tip]].map(([label, text]) => (
                <div key={label} className="rounded-2xl bg-brand-ink/[0.03] border border-slate-200 p-5">
                  <p className="overline">{label}</p>
                  <p className="mt-2 text-sm text-slate-600 leading-relaxed">{text}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <div className="flex items-end justify-between gap-4">
            <h2 className="text-2xl font-bold">Coming up in {d.name}</h2>
            <Link to={`/events?city=${encodeURIComponent(d.name)}`} className="text-sm font-bold text-brand-magenta">All events →</Link>
          </div>
          <div className="mt-6">
            {d.upcoming?.length ? (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="city-events">
                {d.upcoming.map((ev) => <EventCard key={ev.id} ev={ev} />)}
              </div>
            ) : (
              <Empty testid="city-no-events" title={`No dates open in ${d.name} right now`}
                sub="New experiences drop every week — members get first pick." />
            )}
          </div>
        </section>

        {d.quotes?.length > 0 && (
          <section className="grid md:grid-cols-2 gap-5" data-testid="city-quotes">
            {d.quotes.map((q, i) => (
              <div key={i} className="rounded-2xl border border-slate-200 bg-white p-6">
                <Stars value={q.rating} />
                <p className="mt-3 text-sm text-slate-600 italic leading-relaxed">“{q.comment}”</p>
                <p className="mt-4 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">{q.user_name} · {d.name}</p>
              </div>
            ))}
          </section>
        )}

        <section className="rounded-3xl bg-white border border-slate-200 p-7">
          <h2 className="text-lg md:text-lg font-bold">Good to know in {d.name}</h2>
          <div className="mt-5 grid sm:grid-cols-3 gap-5 text-sm">
            <div><p className="overline">You pay in</p><p className="mt-1.5 font-semibold">{d.currency}</p></div>
            <div><p className="overline">{d.tax_label}</p><p className="mt-1.5 font-semibold">{d.tax_percent}% on bookings</p></div>
            <div><p className="overline">Emergency number</p><p className="mt-1.5 font-semibold">{d.emergency}</p></div>
          </div>
        </section>

        {d.events_total === 0 && <Waitlist slug={d.slug} city={d.name} waiting={d.waiting} />}

        <section data-testid="city-faq">
          <p className="overline">Good questions</p>
          <h2 className="mt-1.5 text-2xl font-bold">Buddilio in {d.name}, answered</h2>
          <div className="mt-6 rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100">
            {cityFaqs(d).map(([q, a], i) => (
              <details key={q} className="group px-5 py-4" data-testid={`city-faq-${i + 1}`}>
                <summary className="flex cursor-pointer items-center justify-between gap-4 text-sm font-bold marker:content-['']">
                  {q}
                  <span className="text-brand-magenta transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 text-sm text-slate-600 leading-relaxed">{a}</p>
              </details>
            ))}
          </div>
        </section>

        {d.nearby?.length > 0 && (
          <section>
            <h2 className="text-lg md:text-lg font-bold">Nearby cities</h2>
            <div className="mt-4 flex flex-wrap gap-2" data-testid="city-nearby">
              {d.nearby.map((n) => (
                <Link key={n.slug} to={`/city/${n.slug}`} data-testid={`city-nearby-${n.slug}`}
                  className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold transition-colors hover:border-brand-magenta/50">
                  {n.name}
                </Link>
              ))}
              <Link to="/cities" data-testid="city-all-link"
                className="rounded-full bg-slate-900 text-white px-4 py-2 text-sm font-bold">All cities</Link>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

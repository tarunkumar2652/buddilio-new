import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useCurrency } from "@/context/CurrencyContext";
import { EventCard } from "@/components/Cards";
import { SEO } from "@/components/Shared";
import { ShieldCheck, Sparkles, UserCheck, Ticket, ArrowRight, Star, Check, MessageCircle } from "lucide-react";

const HERO = "https://images.pexels.com/photos/8921578/pexels-photo-8921578.jpeg?auto=compress&w=1600";
const IMG_NIGHT = "https://images.unsplash.com/photo-1762237874410-17ddf6c782a1?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200";
const IMG_CAFE = "https://images.pexels.com/photos/36729801/pexels-photo-36729801.jpeg?auto=compress&w=1200";
const IMG_CITY = "https://images.unsplash.com/photo-1684285746670-3d2eeed72192?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200";

const FAQS = [
  ["Is Buddilio a dating app?", "No. Buddilio is built for finding companions for experiences — dinners, gigs, treks, parties. Romance is not the product."],
  ["Do I need a paid membership?", "No. Browsing, free events and basic messaging are open to every verified member. Premium unlocks discounts and priority access."],
  ["How do you keep members safe?", "Email and mobile verification, active moderation, one-tap block and report, and a safety team that reviews every report."],
  ["Can I attend an event alone?", "Most members do. Hosts make introductions at the door so nobody stands around awkwardly."],
  ["Which cities are live?", "Buddilio runs in 27 cities across 12 countries — Delhi NCR, Mumbai, Bengaluru, Hyderabad, Pune and Goa in India, plus Dubai, Abu Dhabi, Singapore, London, Manchester, New York, Los Angeles, Miami, Austin, Toronto, Vancouver, Sydney, Melbourne, Berlin, Barcelona, Madrid, Paris, Bangkok and Tokyo. Not live where you are? Join anyway — we open cities where members ask for them."],
];

const TESTIMONIALS = [
  ["Moved to Dubai for work and knew nobody. Three Buddilio dinners later I have a proper weekend crew.", "Ritika S.", "Dubai"],
  ["I had concert tickets and no one to go with. Found two members going to the same gig in ten minutes.", "Aman T.", "London"],
  ["The vetting makes the difference. It never feels like a random internet meetup.", "Sofia M.", "Barcelona"],
];

export default function Home() {
  const { fmt } = useCurrency();
  const [featured, setFeatured] = useState([]);
  const [popular, setPopular] = useState([]);
  const [plans, setPlans] = useState([]);
  const [faqOpen, setFaqOpen] = useState(0);

  useEffect(() => {
    api.get("/events", { params: { featured: true, limit: 4 } }).then(({ data }) => setFeatured(data.items)).catch(() => {});
    api.get("/events", { params: { sort: "popular", limit: 6 } }).then(({ data }) => setPopular(data.items)).catch(() => {});
    api.get("/plans").then(({ data }) => setPlans(data.items)).catch(() => {});
  }, []);

  return (
    <div data-testid="home-page">
      <SEO title="Find your people for every experience" />

      {/* HERO */}
      <section className="relative overflow-hidden bg-slate-900 text-white grain">
        <img src={HERO} alt="" className="absolute inset-0 h-full w-full object-cover opacity-45" />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900 via-slate-900/85 to-slate-900/25" />
        <div className="aurora" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 py-24 sm:py-32 lg:py-40">
          <div className="max-w-2xl fade-up">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.18em] text-white/85" data-testid="hero-tagline">
              <img src="/brand/mark.png" alt="" className="h-4 w-4 object-contain" />Your Vibe, Your Buddy
            </span>
            <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-bold leading-[1.05]">
              Great nights out shouldn't <span className="text-gradient">depend on who's free.</span>
            </h1>
            <p className="mt-6 text-base md:text-lg text-white/75 leading-relaxed max-w-xl">
              Buddilio is a curated social club for adults, live in 27 cities worldwide. Discover parties, dinners,
              concerts and getaways — then find verified companions who actually want to go.
            </p>
            <p className="mt-5 text-xs font-bold uppercase tracking-[0.2em] text-white/45">Delhi NCR · Dubai · London · New York · Singapore</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link to="/events" data-testid="hero-explore-cta"
                className="brand-gradient rounded-full px-7 py-3.5 text-sm font-bold text-white shadow-glow-lg transition-transform hover:scale-[1.03] active:scale-[.98]">
                Explore Events
              </Link>
              <Link to="/discover" data-testid="hero-companions-cta"
                className="rounded-full border border-white/30 px-6 py-3.5 text-sm font-bold hover:bg-white/10 transition-colors">
                Find Companions
              </Link>
              <Link to="/register" data-testid="hero-join-cta"
                className="rounded-full bg-white/10 border border-white/20 px-6 py-3.5 text-sm font-bold hover:bg-white/20 transition-colors">
                Join Buddilio
              </Link>
            </div>
            <div className="mt-12 flex flex-wrap gap-8 text-sm">
              {[["12,400+", "verified members"], ["380+", "curated experiences"], ["27", "cities · 12 countries"]].map(([n, l]) => (
                <div key={l}><p className="text-2xl font-display font-bold">{n}</p><p className="text-white/50 text-xs">{l}</p></div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* FIND YOUR PEOPLE — bento */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 py-20 sm:py-28">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div>
            <p className="overline">Find your people</p>
            <h2 className="mt-4 text-3xl sm:text-4xl font-bold">Companions first. Plans second.</h2>
            <p className="mt-5 text-slate-600 leading-relaxed">
              Tell us your city, your interests and the kind of nights you enjoy. Buddilio surfaces members
              with overlapping taste — not a swipe deck. Connect, chat, then decide what you're doing together.
            </p>
            <ul className="mt-8 space-y-4">
              {[[UserCheck, "Verified adults only", "Every profile is age-checked and moderated. 21+, always."],
                [MessageCircle, "Chat before you commit", "Message inside Buddilio until you're comfortable."],
                [ShieldCheck, "Block & report in one tap", "Our safety team reviews every single report."]].map(([Icon, t, d]) => (
                <li key={t} className="flex gap-4">
                  <span className="h-10 w-10 shrink-0 rounded-xl bg-slate-900 text-white grid place-items-center"><Icon className="h-5 w-5" /></span>
                  <div><p className="font-semibold">{t}</p><p className="text-sm text-slate-500 mt-0.5">{d}</p></div>
                </li>
              ))}
            </ul>
            <Link to="/discover" data-testid="find-people-cta"
              className="mt-9 inline-flex items-center gap-2 text-sm font-bold border-b-2 border-slate-900 pb-1">
              Start discovering <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
          <div className="grid grid-cols-2 gap-4 sm:gap-6">
            <img src={IMG_NIGHT} alt="Members at a Buddilio party" loading="lazy" className="rounded-3xl object-cover aspect-[3/4] col-span-1 row-span-2" />
            <img src={IMG_CAFE} alt="Members at a cafe meetup" loading="lazy" className="rounded-3xl object-cover aspect-square" />
            <img src={IMG_CITY} alt="City nightlife" loading="lazy" className="rounded-3xl object-cover aspect-square" />
          </div>
        </div>
      </section>

      {/* FEATURED */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 pb-20 sm:pb-28">
        <div className="flex items-end justify-between gap-6 mb-8">
          <div>
            <p className="overline">Featured this month</p>
            <h2 className="mt-3 text-3xl sm:text-4xl font-bold">Curated by Buddilio</h2>
          </div>
          <Link to="/events" data-testid="featured-all-link" className="text-sm font-bold whitespace-nowrap hidden sm:inline-flex items-center gap-1">
            All events <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {featured.map((ev) => <EventCard key={ev.id} ev={ev} />)}
        </div>
      </section>

      {/* POPULAR EXPERIENCES */}
      <section className="bg-white border-y border-slate-200 py-20 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <p className="overline">Popular experiences</p>
          <h2 className="mt-3 text-3xl sm:text-4xl font-bold max-w-xl">What members are booking right now</h2>
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {popular.map((ev) => <EventCard key={ev.id} ev={ev} />)}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 py-20 sm:py-28">
        <p className="overline">How Buddilio works</p>
        <h2 className="mt-3 text-3xl sm:text-4xl font-bold">Six steps. No awkwardness.</h2>
        <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {[["Discover", "Browse members and experiences in your city."],
            ["Connect", "Send a connection to people with shared interests."],
            ["Chat", "Talk inside Buddilio — safely, on your terms."],
            ["Choose", "Pick an experience: dinner, gig, trek or party."],
            ["Join", "Book a free spot or buy a pass in seconds."],
            ["Enjoy", "Show up, get introduced, have a great night."]].map(([t, d], i) => (
            <div key={t} className="rounded-2xl border border-slate-200 bg-white p-7 hover-lift">
              <p className="text-3xl font-display font-bold text-slate-200">0{i + 1}</p>
              <p className="mt-4 font-display font-semibold text-xl">{t}</p>
              <p className="mt-2 text-sm text-slate-500 leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* MEMBERSHIP */}
      <section className="bg-slate-900 text-white py-20 sm:py-28" data-testid="home-membership">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <p className="overline text-slate-400">Membership</p>
          <h2 className="mt-3 text-3xl sm:text-4xl font-bold">Go premium, go more often.</h2>
          <div className="mt-12 grid md:grid-cols-3 gap-6">
            {plans.map((p, i) => (
              <div key={p.id} className={`rounded-3xl p-8 ${i === 2 ? "bg-white text-slate-900" : "bg-white/5 border border-white/10"}`}>
                {i === 2 && <span className="overline text-slate-500">Best value</span>}
                <p className="font-display font-semibold text-2xl mt-1">{p.name}</p>
                <p className={`mt-2 text-sm ${i === 2 ? "text-slate-600" : "text-slate-400"}`}>{p.description}</p>
                <p className="mt-6 text-3xl font-display font-bold">{p.price === 0 ? "Free" : fmt(p.price)}
                  <span className="text-sm font-normal opacity-60"> / {p.duration_days} days</span></p>
                <ul className="mt-6 space-y-2.5 text-sm">
                  {p.benefits.map((b) => <li key={b} className="flex gap-2"><Check className="h-4 w-4 shrink-0 mt-0.5" />{b}</li>)}
                </ul>
                <Link to="/membership" data-testid={`home-plan-cta-${p.id}`}
                  className={`mt-8 block text-center rounded-full py-3 text-sm font-bold transition-transform hover:scale-[1.02] ${i === 2 ? "brand-gradient text-white shadow-glow" : "bg-white text-slate-900"}`}>
                  {p.price === 0 ? "Start free" : "Get " + p.name}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* SAFETY */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 py-20 sm:py-28 grid lg:grid-cols-2 gap-14 items-center">
        <div>
          <p className="overline">Safety & trust</p>
          <h2 className="mt-3 text-3xl sm:text-4xl font-bold">Built for people who are careful.</h2>
          <p className="mt-5 text-slate-600 leading-relaxed">
            Meeting new people should feel exciting, never risky. Buddilio verifies members, moderates events
            and gives you full control over who reaches you.
          </p>
          <div className="mt-8 grid sm:grid-cols-2 gap-4">
            {[[ShieldCheck, "Meet in public places"], [UserCheck, "Verified 21+ members"],
              [Sparkles, "Moderated event partners"], [Ticket, "Never pay a member directly"]].map(([Icon, t]) => (
              <div key={t} className="rounded-xl border border-slate-200 bg-white p-5 flex gap-3 items-start">
                <Icon className="h-5 w-5 mt-0.5" /><p className="text-sm font-semibold">{t}</p>
              </div>
            ))}
          </div>
          <Link to="/safety" data-testid="safety-center-cta" className="mt-8 inline-flex items-center gap-2 text-sm font-bold border-b-2 border-slate-900 pb-1">
            Visit the Safety Center <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <div className="rounded-3xl overflow-hidden">
          <img src={IMG_CITY} alt="Safe city nightlife" loading="lazy" className="w-full aspect-[4/3] object-cover" />
        </div>
      </section>

      {/* TESTIMONIALS */}
      <section className="bg-white border-y border-slate-200 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <p className="overline">Members</p>
          <h2 className="mt-3 text-3xl sm:text-4xl font-bold">Why they stayed</h2>
          <div className="mt-10 grid md:grid-cols-3 gap-6">
            {TESTIMONIALS.map(([quote, name, city]) => (
              <div key={name} className="rounded-2xl border border-slate-200 p-7">
                <div className="flex gap-0.5">{[...Array(5)].map((_, i) => <Star key={i} className="h-4 w-4 fill-slate-900 text-slate-900" />)}</div>
                <p className="mt-4 text-slate-700 leading-relaxed">"{quote}"</p>
                <p className="mt-5 text-sm font-semibold">{name} <span className="text-slate-400 font-normal">· {city}</span></p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="mx-auto max-w-3xl px-4 sm:px-6 py-20 sm:py-28" data-testid="home-faq">
        <p className="overline">FAQ</p>
        <h2 className="mt-3 text-3xl sm:text-4xl font-bold">Questions, answered</h2>
        <div className="mt-10 divide-y divide-slate-200 border-y border-slate-200">
          {FAQS.map(([q, a], i) => (
            <div key={q}>
              <button onClick={() => setFaqOpen(faqOpen === i ? -1 : i)} data-testid={`faq-toggle-${i}`}
                className="w-full text-left py-5 flex items-center justify-between gap-4 font-semibold">
                {q}<span className="text-slate-400 text-xl">{faqOpen === i ? "−" : "+"}</span>
              </button>
              {faqOpen === i && <p className="pb-5 text-sm text-slate-600 leading-relaxed" data-testid={`faq-answer-${i}`}>{a}</p>}
            </div>
          ))}
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 pb-24">
        <div className="relative overflow-hidden rounded-3xl bg-slate-900 text-white px-8 py-16 sm:px-16 sm:py-20 grain">
          <div className="relative max-w-xl">
            <h2 className="text-3xl sm:text-4xl font-bold">Your next great night is already on the calendar.</h2>
            <p className="mt-4 text-slate-300">Join free in under two minutes. No swiping, no pressure.</p>
            <Link to="/register" data-testid="final-cta"
              className="mt-8 inline-block rounded-full bg-white text-slate-900 px-7 py-3.5 text-sm font-bold hover:bg-slate-100">
              Join Buddilio
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { api, fileUrl, citySlug } from "@/lib/api";
import { useSite } from "@/lib/site";
import {
  Menu, X, Search, Bell, LayoutGrid, Compass, CalendarDays, MessageCircle, User,
  Facebook, Instagram, Twitter, MapPin, Sparkles,
} from "lucide-react";

const MARK = "/brand/mark.png";

const NAV_PUBLIC = [
  { to: "/events", label: "Events" },
  { to: "/hosts", label: "Organisers" },
  { to: "/passes", label: "Passes" },
  { to: "/membership", label: "Membership" },
  { to: "/safety", label: "Safety" },
];

const NAV_USER = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/discover", label: "Discover" },
  { to: "/events", label: "Events" },
  { to: "/hosts", label: "Organisers" },
  { to: "/hangouts", label: "Hangouts" },
  { to: "/messages", label: "Messages" },
  { to: "/membership", label: "Membership" },
  { to: "/orders", label: "Orders" },
  { to: "/wallet", label: "Wallet" },
];

const navFor = (site, signedIn) => {
  const base = (signedIn ? site?.nav?.member : site?.nav?.public) || (signedIn ? NAV_USER : NAV_PUBLIC);
  const extra = (site?.pages || []).filter((p) => p.header)
    .sort((a, b) => (a.order || 0) - (b.order || 0))
    .map((p) => ({ to: `/p/${p.slug}`, label: p.label }));
  return [...base, ...extra];
};

const footerGroups = (site) => {
  const groups = (site?.footer?.groups || FOOT_LINKS.map(([title, links]) => ({
    title, links: links.map(([label, to]) => ({ label, to })),
  }))).map((g) => ({ ...g, links: [...(g.links || [])] }));
  (site?.pages || []).filter((p) => p.footer_group).forEach((p) => {
    const g = groups.find((x) => x.title === p.footer_group);
    const link = { label: p.label, to: `/p/${p.slug}` };
    if (g) { if (!g.links.some((l) => l.to === link.to)) g.links.push(link); }
    else groups.push({ title: p.footer_group, links: [link] });
  });
  return groups;
};

const CITY_STRIP = ["Delhi NCR", "Mumbai", "Bengaluru", "Goa", "Dubai", "Abu Dhabi", "Singapore", "London",
  "Manchester", "New York", "Los Angeles", "Miami", "Austin", "Toronto", "Vancouver", "Sydney", "Melbourne",
  "Berlin", "Barcelona", "Madrid", "Paris", "Bangkok", "Tokyo"];

export const Logo = ({ tone = "dark", tagline = true, size = "h-9 w-9" }) => (
  <span className="flex items-center gap-2.5">
    <img src={MARK} alt="" className={`${size} object-contain select-none`} draggable="false" />
    <span className="leading-none">
      <span className={`block font-display font-extrabold italic text-[19px] tracking-tight ${tone === "light" ? "text-white" : "text-slate-900"}`}>
        Buddilio
      </span>
      {tagline && (
        <span className={`mt-1 block text-[10px] font-semibold tracking-wide ${tone === "light" ? "text-white/55" : "text-slate-400"}`}>
          Your Vibe, Your Buddy
        </span>
      )}
    </span>
  </span>
);

export const CurrencyPicker = () => {
  const { list, code, set } = useCurrency();
  return (
    <select value={code} onChange={(e) => set(e.target.value)} data-testid="currency-picker"
      className="rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-bold outline-none focus:ring-2 focus:ring-brand-magenta">
      {list.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
    </select>
  );
};

export const Navbar = () => {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [unread, setUnread] = useState(0);
  const site = useSite();

  useEffect(() => { setOpen(false); setRes(null); setQ(""); }, [loc.pathname]);

  useEffect(() => {
    if (!user) return;
    api.get("/notifications").then(({ data }) => setUnread(data.unread)).catch(() => {});
  }, [user, loc.pathname]);

  useEffect(() => {
    if (q.length < 2) { setRes(null); return; }
    const t = setTimeout(() => {
      api.get("/search", { params: { q } }).then(({ data }) => setRes(data)).catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const links = navFor(site, !!user);

  return (
    <>
      <header className="sticky top-0 z-50" data-testid="site-header">
        <div className="brand-rule" />
        <div className="glass border-b border-slate-200">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 h-[70px] flex items-center gap-4">
            <Link to="/" className="shrink-0 transition-transform hover:scale-[1.02]" data-testid="nav-logo">
              <Logo />
            </Link>

            <nav className="hidden lg:flex items-center gap-1 ml-3">
              {links.map((l) => (
                <Link key={l.to} to={l.to} data-testid={`nav-${l.label.toLowerCase()}`} data-active={loc.pathname === l.to}
                  className={`link-underline px-3 py-2 rounded-lg text-sm font-bold transition-colors ${
                    loc.pathname === l.to ? "text-slate-900" : "text-slate-600 hover:text-slate-900"}`}>
                  {l.label}
                </Link>
              ))}
            </nav>

            <div className="hidden md:block relative ml-auto w-64">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input data-testid="global-search-input" value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Search events, people…"
                className="w-full rounded-full border border-slate-200 bg-white pl-9 pr-4 py-2 text-sm outline-none transition-shadow focus:ring-2 focus:ring-brand-magenta/60" />
              {res && (
                <div className="absolute mt-2 w-80 right-0 rounded-2xl border border-slate-200 bg-white soft-shadow p-2 max-h-80 overflow-auto" data-testid="global-search-results">
                  {[["events", "Events", "/events/"], ["users", "People", "/u/"], ["products", "Passes", "/passes"]].map(([k, lbl, base]) => (
                    res[k]?.length ? (
                      <div key={k} className="p-1">
                        <p className="overline px-2 py-1">{lbl}</p>
                        {res[k].map((it) => (
                          <button key={it.id} data-testid={`search-result-${it.id}`}
                            onClick={() => nav(base === "/passes" ? base : base + it.id)}
                            className="w-full text-left px-2 py-2 rounded-lg hover:bg-slate-50 text-sm">
                            {it.title || it.full_name || it.name}
                          </button>
                        ))}
                      </div>
                    ) : null
                  ))}
                  {!res.events?.length && !res.users?.length && !res.products?.length &&
                    <p className="p-3 text-sm text-slate-500">No matches found.</p>}
                </div>
              )}
            </div>

            <div className="ml-auto md:ml-0 flex items-center gap-2">
              <span className="hidden sm:block"><CurrencyPicker /></span>
              {user ? (
                <>
                  <Link to="/ai" data-testid="nav-ai"
                    className="hidden lg:inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 rounded-full border border-brand-pink/40 bg-white px-3.5 py-2 text-xs font-bold text-brand-magenta transition-colors hover:bg-brand-pink/10">
                    <Sparkles className="h-3.5 w-3.5" />Buddy AI
                  </Link>
                  <Link to="/notifications" className="relative p-2 rounded-full hover:bg-slate-100 transition-colors" data-testid="nav-notifications">
                    <Bell className="h-5 w-5" />
                    {unread > 0 && <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-brand-magenta ring-2 ring-white" />}
                  </Link>
                  {user.role === "admin" && <Link to="/admin" className="hidden sm:block text-sm font-bold px-3 py-2 rounded-lg hover:bg-slate-100" data-testid="nav-admin">Admin</Link>}
                  {user.role === "partner" && <Link to="/partner" className="hidden sm:block text-sm font-bold px-3 py-2 rounded-lg hover:bg-slate-100" data-testid="nav-partner">Partner</Link>}
                  <Link to="/profile" data-testid="nav-profile" className="hidden sm:flex items-center gap-2">
                    {user.photo ? <img src={fileUrl(user.photo)} alt="" className="h-9 w-9 rounded-full object-cover ring-2 ring-brand-pink/40" />
                      : <span className="h-9 w-9 rounded-full brand-gradient text-white grid place-items-center text-xs font-bold">{user.full_name?.[0]}</span>}
                  </Link>
                  <button onClick={() => { logout(); nav("/"); }} data-testid="nav-logout"
                    className="hidden sm:block shrink-0 whitespace-nowrap text-sm font-bold text-slate-600 hover:text-slate-900 px-2 py-2">Log out</button>
                </>
              ) : (
                <>
                  <Link to="/login" data-testid="nav-login" className="hidden sm:block text-sm font-bold px-3 py-2 rounded-lg hover:bg-slate-100">Log in</Link>
                  <Link to="/register" data-testid="nav-join"
                    className="brand-gradient text-white text-sm font-bold rounded-full px-4 sm:px-5 py-2.5 shadow-[0_6px_18px_rgba(232,30,124,0.26)] transition-transform hover:scale-[1.03] active:scale-[.98]">
                    Join<span className="hidden sm:inline"> Buddilio</span>
                  </Link>
                </>
              )}
              <button className="lg:hidden p-2 rounded-lg hover:bg-slate-100" onClick={() => setOpen(!open)} data-testid="nav-mobile-toggle">
                {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            </div>
          </div>

          {open && (
            <div className="lg:hidden border-t border-slate-200 bg-white px-4 py-3 space-y-1" data-testid="nav-mobile-menu">
              {links.map((l) => (
                <Link key={l.to} to={l.to} className="block px-3 py-2.5 rounded-lg text-sm font-bold hover:bg-slate-50"
                  data-testid={`mnav-${l.label.toLowerCase()}`}>{l.label}</Link>
              ))}
              {user?.role === "admin" && <Link to="/admin" className="block px-3 py-2.5 rounded-lg text-sm font-bold hover:bg-slate-50" data-testid="mnav-admin">Admin</Link>}
              {user?.role === "partner" && <Link to="/partner" className="block px-3 py-2.5 rounded-lg text-sm font-bold hover:bg-slate-50" data-testid="mnav-partner">Partner</Link>}
              {user ? (
                <>
                  <Link to="/ai" className="block px-3 py-2.5 rounded-lg text-sm font-bold text-brand-magenta hover:bg-slate-50" data-testid="mnav-ai">Buddy AI</Link>
                  <Link to="/referrals" className="block px-3 py-2.5 rounded-lg text-sm font-bold hover:bg-slate-50" data-testid="mnav-referrals">Invite &amp; earn</Link>
                  <Link to="/profile" className="block px-3 py-2.5 rounded-lg text-sm font-bold hover:bg-slate-50" data-testid="mnav-profile">Profile</Link>
                  <button onClick={() => { logout(); nav("/"); }} className="block w-full text-left px-3 py-2.5 rounded-lg text-sm font-bold text-red-600" data-testid="mnav-logout">Log out</button>
                </>
              ) : (
                <>
                  <Link to="/login" className="block px-3 py-2.5 rounded-lg text-sm font-bold hover:bg-slate-50" data-testid="mnav-login">Log in</Link>
                  <Link to="/register" className="block px-3 py-2.5 rounded-full text-sm font-bold brand-gradient text-white text-center" data-testid="mnav-join">Join Buddilio</Link>
                </>
              )}
              <div className="sm:hidden flex items-center justify-between px-3 pt-3 border-t border-slate-100">
                <span className="text-xs font-bold text-slate-500">Currency</span>
                <CurrencyPicker />
              </div>
            </div>
          )}
        </div>
      </header>

      {user && user.role === "user" && (
        <nav className="md:hidden fixed bottom-0 inset-x-0 z-50 glass border-t border-slate-200 grid grid-cols-5" data-testid="bottom-nav">
          {[["/dashboard", LayoutGrid, "Home"], ["/discover", Compass, "Discover"], ["/events", CalendarDays, "Events"],
            ["/messages", MessageCircle, "Chat"], ["/profile", User, "You"]].map(([to, Icon, label]) => (
            <Link key={to} to={to} data-testid={`bnav-${label.toLowerCase()}`}
              className={`flex flex-col items-center gap-1 py-2.5 text-[10px] font-bold transition-colors ${
                loc.pathname === to ? "text-brand-magenta" : "text-slate-400"}`}>
              <Icon className="h-5 w-5" />{label}
            </Link>
          ))}
        </nav>
      )}
    </>
  );
};

const FOOT_LINKS = [
  ["Explore", [["Events", "/events"], ["Cities", "/cities"], ["Passes", "/passes"], ["Membership", "/membership"],
    ["Discover", "/discover"], ["Leaderboard", "/leaderboard"], ["Invite & earn", "/referrals"]]],
  ["Company", [["About", "/p/about"], ["Contact", "/p/contact"], ["FAQ", "/p/faq"],
    ["Partner with us", "/register?role=partner"]]],
  ["Trust & Safety", [["Safety Center", "/safety"], ["Community Guidelines", "/p/guidelines"],
    ["Terms", "/p/terms"], ["Privacy", "/p/privacy"], ["Refund Policy", "/p/refund"]]],
];

const SOCIALS = [
  [Instagram, "instagram", "https://www.instagram.com/buddilio"],
  [Facebook, "facebook", "https://www.facebook.com/Buddilio/"],
  [Twitter, "x", "https://x.com/buddilio_"],
];

export const Footer = () => {
  const site = useSite();
  return (
  <footer className="relative mt-28 overflow-hidden bg-brand-ink text-white grain" data-testid="footer">
    <div className="aurora opacity-80" />
    <div className="relative mx-auto max-w-7xl px-4 sm:px-6 pt-16 pb-8">
      <div className="grid gap-12 lg:grid-cols-[1.5fr_repeat(3,1fr)]">
        <div>
          <Logo tone="light" />
          <p className="mt-6 text-sm text-white/70 leading-relaxed max-w-sm">
            A curated social club for adults. Find the experience, find your people, and never skip a great
            night out because nobody was free.
          </p>
          <p className="mt-5 inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-xs font-bold text-white/80">
            <MapPin className="h-3.5 w-3.5" />Live in 27 cities · 12 countries
          </p>
          <div className="mt-6 flex items-center gap-2.5">
            {SOCIALS.map(([Icon, name, href]) => (
              <a key={name} href={href} target="_blank" rel="noreferrer noopener" aria-label={name}
                data-testid={`footer-social-${name}`}
                className="h-10 w-10 grid place-items-center rounded-full bg-white/10 text-white/80 transition-all hover:bg-white/20 hover:text-white hover:-translate-y-0.5">
                <Icon className="h-4 w-4" />
              </a>
            ))}
          </div>
        </div>

        {footerGroups(site).map((g) => (
          <div key={g.title}>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/45">{g.title}</p>
            <ul className="mt-5 space-y-3">
              {(g.links || []).map(({ label, to }) => (
                <li key={to}>
                  <Link to={to} className="text-sm text-white/70 transition-colors hover:text-brand-pink">{label}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-14 rounded-2xl border border-white/10 bg-white/[0.04] py-4 overflow-hidden" data-testid="footer-cities">
        <div className="flex w-max animate-marquee gap-8 pr-8">
          {[...CITY_STRIP, ...CITY_STRIP].map((c, i) => (
            <Link key={`${c}-${i}`} to={`/city/${citySlug(c)}`} data-testid={i < CITY_STRIP.length ? `footer-city-${citySlug(c)}` : undefined}
              className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-white/45 whitespace-nowrap transition-colors hover:text-brand-pink">
              <Sparkles className="h-3 w-3 text-brand-pink" />{c}
            </Link>
          ))}
        </div>
      </div>

      <div className="mt-8 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-white/10 pt-6">
        <p className="text-xs text-white/45">© {new Date().getFullYear()} Buddilio Experiences · a global social club</p>
        <p className="text-xs text-white/45">Buddilio is a social discovery platform, not a dating service. Members are 21+.</p>
      </div>
    </div>
  </footer>
  );
};

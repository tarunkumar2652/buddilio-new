import { useEffect, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useCurrency } from "@/context/CurrencyContext";
import { api, fileUrl } from "@/lib/api";
import { Menu, X, Search, Bell, LayoutGrid, Compass, CalendarDays, MessageCircle, User } from "lucide-react";

const NAV_PUBLIC = [
  { to: "/events", label: "Events" },
  { to: "/passes", label: "Passes" },
  { to: "/membership", label: "Membership" },
  { to: "/safety", label: "Safety" },
];

const NAV_USER = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/discover", label: "Discover" },
  { to: "/events", label: "Events" },
  { to: "/messages", label: "Messages" },
  { to: "/membership", label: "Membership" },
  { to: "/orders", label: "Orders" },
];

export const CurrencyPicker = () => {
  const { list, code, set } = useCurrency();
  return (
    <select value={code} onChange={(e) => set(e.target.value)} data-testid="currency-picker"
      className="rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-bold outline-none focus:ring-2 focus:ring-slate-900">
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

  const links = user ? NAV_USER : NAV_PUBLIC;

  return (
    <>
      <header className="sticky top-0 z-50 glass border-b border-slate-200">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 h-16 flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2 shrink-0" data-testid="nav-logo">
            <span className="h-8 w-8 rounded-xl bg-slate-900 text-white grid place-items-center font-display font-bold">B</span>
            <span className="font-display font-bold text-lg tracking-tight">Buddilio</span>
          </Link>

          <nav className="hidden lg:flex items-center gap-1 ml-4">
            {links.map((l) => (
              <Link key={l.to} to={l.to} data-testid={`nav-${l.label.toLowerCase()}`}
                className={`px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${
                  loc.pathname === l.to ? "text-slate-900 bg-slate-100" : "text-slate-600 hover:text-slate-900"}`}>
                {l.label}
              </Link>
            ))}
          </nav>

          <div className="hidden md:block relative ml-auto w-64">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input data-testid="global-search-input" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Search events, people…"
              className="w-full rounded-full border border-slate-200 bg-white pl-9 pr-4 py-2 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
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
            <CurrencyPicker />
            {user ? (
              <>
                <Link to="/notifications" className="relative p-2 rounded-full hover:bg-slate-100" data-testid="nav-notifications">
                  <Bell className="h-5 w-5" />
                  {unread > 0 && <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-red-500" />}
                </Link>
                {user.role === "admin" && <Link to="/admin" className="hidden sm:block text-sm font-semibold px-3 py-2 rounded-lg hover:bg-slate-100" data-testid="nav-admin">Admin</Link>}
                {user.role === "partner" && <Link to="/partner" className="hidden sm:block text-sm font-semibold px-3 py-2 rounded-lg hover:bg-slate-100" data-testid="nav-partner">Partner</Link>}
                <Link to="/profile" data-testid="nav-profile" className="hidden sm:flex items-center gap-2">
                  {user.photo ? <img src={fileUrl(user.photo)} alt="" className="h-8 w-8 rounded-full object-cover" />
                    : <span className="h-8 w-8 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{user.full_name?.[0]}</span>}
                </Link>
                <button onClick={() => { logout(); nav("/"); }} data-testid="nav-logout"
                  className="hidden sm:block text-sm font-semibold text-slate-600 hover:text-slate-900 px-2">Log out</button>
              </>
            ) : (
              <>
                <Link to="/login" data-testid="nav-login" className="text-sm font-semibold px-3 py-2 rounded-lg hover:bg-slate-100">Log in</Link>
                <Link to="/register" data-testid="nav-join"
                  className="text-sm font-semibold rounded-full bg-slate-900 text-white px-4 py-2 hover:bg-slate-800 transition-transform hover:scale-[1.02] active:scale-[.98]">
                  Join Buddilio
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
              <Link key={l.to} to={l.to} className="block px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-slate-50"
                data-testid={`mnav-${l.label.toLowerCase()}`}>{l.label}</Link>
            ))}
            {user?.role === "admin" && <Link to="/admin" className="block px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-slate-50" data-testid="mnav-admin">Admin</Link>}
            {user?.role === "partner" && <Link to="/partner" className="block px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-slate-50" data-testid="mnav-partner">Partner</Link>}
            {user ? (
              <>
                <Link to="/profile" className="block px-3 py-2.5 rounded-lg text-sm font-semibold hover:bg-slate-50" data-testid="mnav-profile">Profile</Link>
                <button onClick={() => { logout(); nav("/"); }} className="block w-full text-left px-3 py-2.5 rounded-lg text-sm font-semibold text-red-600" data-testid="mnav-logout">Log out</button>
              </>
            ) : (
              <Link to="/register" className="block px-3 py-2.5 rounded-lg text-sm font-semibold bg-slate-900 text-white text-center" data-testid="mnav-join">Join Buddilio</Link>
            )}
          </div>
        )}
      </header>

      {user && user.role === "user" && (
        <nav className="md:hidden fixed bottom-0 inset-x-0 z-50 glass border-t border-slate-200 grid grid-cols-5" data-testid="bottom-nav">
          {[["/dashboard", LayoutGrid, "Home"], ["/discover", Compass, "Discover"], ["/events", CalendarDays, "Events"],
            ["/messages", MessageCircle, "Chat"], ["/profile", User, "You"]].map(([to, Icon, label]) => (
            <Link key={to} to={to} data-testid={`bnav-${label.toLowerCase()}`}
              className={`flex flex-col items-center gap-1 py-2.5 text-[10px] font-semibold ${loc.pathname === to ? "text-slate-900" : "text-slate-400"}`}>
              <Icon className="h-5 w-5" />{label}
            </Link>
          ))}
        </nav>
      )}
    </>
  );
};

export const Footer = () => (
  <footer className="mt-24 border-t border-slate-200 bg-white" data-testid="footer">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-14 grid gap-10 md:grid-cols-4">
      <div>
        <div className="flex items-center gap-2">
          <span className="h-8 w-8 rounded-xl bg-slate-900 text-white grid place-items-center font-display font-bold">B</span>
          <span className="font-display font-bold text-lg">Buddilio</span>
        </div>
        <p className="text-sm text-slate-500 mt-4 leading-relaxed">
          Curated social discovery for adults. Find great experiences — and the right people to share them with.
        </p>
        <p className="text-xs text-slate-400 mt-4">Buddilio Experiences Pvt. Ltd., Gurugram, India</p>
      </div>
      {[["Explore", [["Events", "/events"], ["Passes", "/passes"], ["Membership", "/membership"], ["Discover", "/discover"]]],
        ["Company", [["About", "/p/about"], ["Contact", "/p/contact"], ["FAQ", "/p/faq"], ["Partner with us", "/register?role=partner"]]],
        ["Trust & Safety", [["Safety Center", "/safety"], ["Community Guidelines", "/p/guidelines"], ["Terms", "/p/terms"], ["Privacy", "/p/privacy"], ["Refund Policy", "/p/refund"]]]].map(([title, items]) => (
        <div key={title}>
          <p className="overline">{title}</p>
          <ul className="mt-4 space-y-2.5">
            {items.map(([l, to]) => (
              <li key={to}><Link to={to} className="text-sm text-slate-600 hover:text-slate-900">{l}</Link></li>
            ))}
          </ul>
        </div>
      ))}
    </div>
    <div className="border-t border-slate-200 py-6 text-center text-xs text-slate-400">
      © {new Date().getFullYear()} Buddilio. Buddilio is a social discovery platform, not a dating service.
    </div>
  </footer>
);

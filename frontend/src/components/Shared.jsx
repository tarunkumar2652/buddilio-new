import { Link } from "react-router-dom";

export const CATEGORIES = ["Parties", "Dining", "Nightlife", "Concerts", "Festivals", "Sports",
  "Travel", "Networking", "Social Gatherings", "Lifestyle Experiences", "Other"];

// Buddy replies in light markdown: [label](/path) links and **bold**.
export const RichText = ({ text }) => {
  const nodes = [];
  const re = /\[([^\]]+)\]\((\/[^)\s]*)\)|\*\*([^*]+)\*\*/g;
  let last = 0, m, k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) {
      nodes.push(
        <Link key={k++} to={m[2]} className="font-semibold text-brand-magenta underline decoration-brand-pink/50 underline-offset-2 hover:decoration-brand-magenta">
          {m[1]}
        </Link>
      );
    } else {
      nodes.push(<strong key={k++} className="font-bold">{m[3]}</strong>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <span className="whitespace-pre-wrap leading-relaxed">{nodes}</span>;
};

export const Spinner = ({ label = "Loading" }) => (
  <div className="flex flex-col items-center justify-center py-20 gap-3" data-testid="loading-state">
    <div className="h-8 w-8 rounded-full border-2 border-slate-200 border-t-slate-900 animate-spin" />
    <p className="text-sm text-slate-500">{label}…</p>
  </div>
);

export const Empty = ({ title, sub, action, testid = "empty-state" }) => (
  <div className="text-center py-16 px-6 rounded-2xl border border-dashed border-slate-300 bg-white" data-testid={testid}>
    <h3 className="text-xl font-semibold">{title}</h3>
    {sub && <p className="text-sm text-slate-500 mt-2 max-w-md mx-auto">{sub}</p>}
    {action && <div className="mt-5 flex justify-center">{action}</div>}
  </div>
);

export const Badge = ({ children, tone = "slate" }) => {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    dark: "bg-slate-900 text-white",
    green: "bg-emerald-50 text-emerald-700",
    amber: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
  };
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>;
};

export const statusTone = (s) =>
  ({ published: "green", paid: "green", confirmed: "green", active: "green",
     submitted: "amber", pending: "amber", draft: "slate", created: "slate",
     rejected: "red", failed: "red", banned: "red", suspended: "red", refunded: "red" }[s] || "slate");

export const Stat = ({ label, value, sub, testid }) => (
  <div className="rounded-xl border border-slate-200 bg-white p-5" data-testid={testid}>
    <p className="overline">{label}</p>
    <p className="text-2xl font-semibold mt-2 font-display">{value}</p>
    {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
  </div>
);

const setMeta = (attr, key, content) => {
  let el = document.querySelector(`meta[${attr}="${key}"]`);
  if (!el) { el = document.createElement("meta"); el.setAttribute(attr, key); document.head.appendChild(el); }
  el.setAttribute("content", content);
};

export const SEO = ({ title, description, image }) => {
  if (typeof document !== "undefined") {
    document.title = title
      ? (title.includes("Buddilio") ? title : `${title} | Buddilio`)
      : "Buddilio — Meet real people. Share real experiences.";
    const desc = description
      || "Online is where it starts. Buddilio is where it happens — real people, real experiences, in 27 cities.";
    setMeta("name", "description", desc);
    setMeta("property", "og:description", desc);
    setMeta("name", "twitter:card", "summary_large_image");
    setMeta("name", "twitter:title", title || "Buddilio");
    setMeta("name", "twitter:description", desc);
    const card = image || `${window.location.origin}/brand/og-cover.jpg`;
    setMeta("property", "og:image", card);
    setMeta("name", "twitter:image", card);
    let og = document.querySelector('meta[property="og:title"]');
    if (!og) { og = document.createElement("meta"); og.setAttribute("property", "og:title"); document.head.appendChild(og); }
    og.content = title || "Buddilio";
    let can = document.querySelector('link[rel="canonical"]');
    if (!can) { can = document.createElement("link"); can.rel = "canonical"; document.head.appendChild(can); }
    can.href = window.location.origin + window.location.pathname;
  }
  return null;
};

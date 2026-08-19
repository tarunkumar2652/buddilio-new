import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fileUrl } from "@/lib/api";
import { Spinner, Empty, SEO } from "@/components/Shared";
import { RichHtml } from "@/components/RichText";
import { ShieldCheck, MapPin, EyeOff, Flag, Ban, PhoneCall } from "lucide-react";

export function CmsPage() {
  const { slug } = useParams();
  const [p, setP] = useState(null);
  useEffect(() => { setP(null); api.get(`/cms/${slug}`).then(({ data }) => setP(data)).catch(() => setP(false)); }, [slug]);
  if (p === null) return <Spinner />;
  if (p === false) return <div className="py-24"><Empty title="Page not found" sub="This page may have been moved." /></div>;
  const blocks = p.blocks || [];
  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-16 pb-28" data-testid={`cms-page-${slug}`}>
      <SEO title={p.seo_title || p.title} description={p.seo_description} />
      <p className="overline">Buddilio</p>
      <h1 className="mt-3 text-3xl sm:text-4xl font-bold">{p.title}</h1>
      {p.last_updated && (
        <p className="mt-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-400" data-testid="cms-last-updated">
          Last updated {new Date(p.last_updated).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}
          {p.policy_version ? ` · version ${p.policy_version}` : ""}
        </p>
      )}
      {p.content && (
        <RichHtml html={p.content} testid="cms-intro"
          className="mt-8 text-slate-600 leading-relaxed" />
      )}
      {blocks.length > 0 && (
        <div className="mt-10 space-y-8" data-testid="cms-blocks">
          {blocks.map((b, i) => <PageBlock key={i} b={b} i={i} />)}
        </div>
      )}
    </div>
  );
}

const PageBlock = ({ b, i }) => {
  const key = `cms-block-${i}`;
  if (b.type === "heading") return <h2 className="text-2xl font-bold" data-testid={key}>{b.heading || b.text}</h2>;
  if (b.type === "image") return b.image
    ? <img src={fileUrl(b.image)} alt={b.heading || ""} loading="lazy" className="w-full rounded-2xl object-cover" data-testid={key} />
    : null;
  if (b.type === "quote") return (
    <blockquote className="rounded-2xl border-l-4 border-slate-900 bg-slate-50 p-6 text-lg italic text-slate-700" data-testid={key}>
      <RichHtml html={b.text} />
      {b.heading && <span className="mt-2 block text-sm not-italic font-bold text-slate-500">— {b.heading}</span>}
    </blockquote>
  );
  if (b.type === "list") return (
    <div data-testid={key}>
      {b.heading && <h2 className="text-2xl font-bold">{b.heading}</h2>}
      <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-600">
        {(b.items || []).filter(Boolean).map((it, n) => <li key={n}>{it}</li>)}
      </ul>
    </div>
  );
  if (b.type === "faq") return (
    <div data-testid={key}>
      {b.heading && <h2 className="text-2xl font-bold">{b.heading}</h2>}
      <div className="mt-3 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
        {(b.items || []).filter(Boolean).map((it, n) => {
          const [q, ...rest] = String(it).split("|");
          return (
            <details key={n} className="px-5 py-4" data-testid={`${key}-faq-${n}`}>
              <summary className="cursor-pointer text-sm font-bold">{q.trim()}</summary>
              <RichHtml html={rest.join("|").trim()} className="mt-2 text-sm text-slate-600" />
            </details>
          );
        })}
      </div>
    </div>
  );
  if (b.type === "cta") return (
    <div className="rounded-2xl bg-brand-ink p-8 text-white" data-testid={key}>
      {b.heading && <h2 className="text-2xl font-bold">{b.heading}</h2>}
      {b.text && <RichHtml html={b.text} className="mt-2 text-white/70" />}
      {b.cta_label && (
        <Link to={b.cta_url || "/events"} data-testid={`${key}-cta`}
          className="mt-5 inline-block rounded-full brand-gradient px-6 py-3 text-sm font-bold">{b.cta_label}</Link>
      )}
    </div>
  );
  return (
    <div data-testid={key}>
      {b.heading && <h2 className="text-2xl font-bold">{b.heading}</h2>}
      <RichHtml html={b.text} className="mt-3 text-slate-600 leading-relaxed" />
    </div>
  );
};

const TIPS = [
  [MapPin, "Always meet in public", "First meetups should be at the listed venue — a bar, cafe, club or event ground. Never a private residence."],
  [EyeOff, "Protect your information", "Keep your address, workplace and financial details private until you genuinely trust someone."],
  [Ban, "Never send money", "No Buddilio member, host or partner will ever ask you to transfer money directly. Report anyone who does."],
  [Flag, "Report anything off", "One tap on any profile, event or chat sends it to our safety team. Every report is reviewed."],
  [ShieldCheck, "Tell a friend your plan", "Share the event link and your expected return time with someone you trust."],
  [PhoneCall, "Emergencies come first", "Call your local emergency number first — 112 in India and the EU, 911 in the US and Canada, 999 in the UK, UAE and Singapore, 000 in Australia. Then let us know."],
];

export function Safety() {
  const [page, setPage] = useState(null);
  useEffect(() => { api.get("/cms/safety").then(({ data }) => setPage(data)).catch(() => {}); }, []);
  return (
    <div data-testid="safety-page">
      <SEO title="Safety Center" description="How Buddilio keeps members safe: verification, moderation, blocking, reporting and meetup guidance." />
      <section className="bg-slate-900 text-white py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <p className="overline text-slate-400">Safety Center</p>
          <h1 className="mt-3 text-3xl sm:text-5xl font-bold max-w-2xl">Meeting new people should never feel risky.</h1>
          <p className="mt-5 text-slate-300 max-w-2xl">
            Buddilio verifies every member, moderates every partner event and gives you full control over who can reach you.
          </p>
        </div>
      </section>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-16 pb-28">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {TIPS.map(([Icon, t, d]) => (
            <div key={t} className="rounded-2xl border border-slate-200 bg-white p-7 hover-lift">
              <span className="h-10 w-10 rounded-xl bg-slate-900 text-white grid place-items-center"><Icon className="h-5 w-5" /></span>
              <p className="mt-5 font-display font-semibold text-lg">{t}</p>
              <p className="mt-2 text-sm text-slate-500 leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
        {page && (
          <div className="mt-14 rounded-2xl border border-slate-200 bg-white p-8">
            <p className="overline">Official policy</p>
            {page.last_updated && (
              <p className="mt-2 text-xs font-bold uppercase tracking-[0.14em] text-slate-400" data-testid="cms-last-updated">
                Last updated {new Date(page.last_updated).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}
                {page.policy_version ? ` · version ${page.policy_version}` : ""}
              </p>
            )}
            <RichHtml html={page.content} className="mt-4 text-sm text-slate-600" testid="safety-policy" />
            {(page.blocks || []).map((b, i) => <div key={i} className="mt-8"><PageBlock b={b} i={i} /></div>)}
          </div>
        )}
      </div>
    </div>
  );
}

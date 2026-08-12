import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Spinner, Empty, SEO } from "@/components/Shared";
import { ShieldCheck, MapPin, EyeOff, Flag, Ban, PhoneCall } from "lucide-react";

export function CmsPage() {
  const { slug } = useParams();
  const [p, setP] = useState(null);
  useEffect(() => { setP(null); api.get(`/cms/${slug}`).then(({ data }) => setP(data)).catch(() => setP(false)); }, [slug]);
  if (p === null) return <Spinner />;
  if (p === false) return <div className="py-24"><Empty title="Page not found" sub="This page may have been moved." /></div>;
  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-16 pb-28" data-testid={`cms-page-${slug}`}>
      <SEO title={p.title} description={p.seo_description} />
      <p className="overline">Buddilio</p>
      <h1 className="mt-3 text-3xl sm:text-4xl font-bold">{p.title}</h1>
      <div className="mt-8 space-y-4 text-slate-600 leading-relaxed">
        {p.content.split("\n").filter(Boolean).map((line, i) => <p key={i}>{line}</p>)}
      </div>
    </div>
  );
}

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
            <div className="mt-4 space-y-3 text-sm text-slate-600">
              {page.content.split("\n").filter(Boolean).map((l, i) => <p key={i}>{l}</p>)}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

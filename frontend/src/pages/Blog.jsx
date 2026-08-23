import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight, Clock, Search, PenLine } from "lucide-react";
import { api } from "@/lib/api";
import { SEO, Spinner } from "@/components/Shared";

const CHIP = "inline-flex items-center px-5 py-2 rounded-full text-[11px] font-bold uppercase tracking-[0.18em] transition-all duration-300";
const day = (v) => v ? new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";

const Meta = ({ p, light }) => (
  <p className={`flex flex-wrap items-center gap-3 text-xs font-medium ${light ? "text-white/70" : "text-slate-500"}`}>
    <span className={`font-bold uppercase tracking-[0.18em] ${light ? "text-white" : "text-brand-magenta"}`}>{p.category}</span>
    <span>{day(p.published_at)}</span>
    <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{p.read_minutes} min read</span>
  </p>
);

export const PostCard = ({ p, index = 0 }) => (
  <motion.article initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: "-80px" }}
    transition={{ duration: 0.5, delay: Math.min(index * 0.06, 0.3), ease: [0.22, 1, 0.36, 1] }}
    className="group flex flex-col" data-testid={`post-card-${p.slug}`}>
    <Link to={`/blog/${p.slug}`} className="flex flex-col gap-5">
      <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-slate-100">
        {p.cover_image
          ? <img src={p.cover_image} alt={p.title} loading="lazy"
              className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-[1.04]" />
          : <div className="h-full w-full bg-gradient-to-br from-slate-900 to-slate-700" />}
      </div>
      <div className="space-y-3">
        <Meta p={p} />
        <h3 className="font-display text-2xl font-bold leading-snug text-slate-900 transition-colors duration-300 group-hover:text-brand-magenta">
          {p.title}
        </h3>
        <p className="line-clamp-2 text-sm text-slate-600">{p.excerpt}</p>
      </div>
    </Link>
  </motion.article>
);

/** Buddilio Journal — the crawlable, editorial face of the platform. */
export default function Blog() {
  const [params, setParams] = useSearchParams();
  const category = params.get("category") || "";
  const tag = params.get("tag") || "";
  const [q, setQ] = useState(params.get("q") || "");
  const [term, setTerm] = useState(params.get("q") || "");
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    api.get("/blog", { params: { category, tag, q: term } })
      .then(({ data }) => setD(data))
      .catch(() => setD({ items: [], featured: null, categories: [], all_categories: [] }));
  }, [category, tag, term]);
  useEffect(() => { load(); }, [load]);

  const setCat = (c) => {
    const next = new URLSearchParams(params);
    c ? next.set("category", c) : next.delete("category");
    next.delete("tag");
    setParams(next);
  };

  const rest = useMemo(() => (d?.items || []).filter((p) => p.slug !== d?.featured?.slug), [d]);
  const hero = d?.featured;

  return (
    <div className="bg-[#FAFAFA]" data-testid="blog-page">
      <SEO title="The Buddilio Journal — going out, done well"
        description="Stories, city guides and safety notes for people who go out: nightlife, dining, travel and the etiquette of meeting new people." />

      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-16 pb-10 lg:pt-24">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-brand-magenta">The Journal</p>
            <h1 className="mt-3 font-display text-4xl font-bold leading-[1.05] tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
              Going out,<br />done well.
            </h1>
            <p className="mt-4 max-w-xl text-base text-slate-600 sm:text-lg">
              City guides, night-out playbooks and honest safety notes from the Buddilio editorial desk.
            </p>
          </div>
          <label className="relative w-full md:w-72">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setTerm(q)} data-testid="blog-search"
              placeholder="Search the journal" aria-label="Search the journal"
              className="w-full rounded-full border border-slate-200 bg-white py-3 pl-11 pr-4 text-sm outline-none transition focus:border-brand-magenta" />
          </label>
        </div>

        <div className="mt-10 flex flex-wrap gap-2" data-testid="blog-categories">
          <button onClick={() => setCat("")} data-testid="blog-cat-all"
            className={`${CHIP} ${!category ? "bg-brand-magenta text-white shadow-md" : "bg-white text-slate-600 shadow-sm hover:text-brand-magenta"}`}>
            All stories
          </button>
          {(d?.all_categories || []).map((c) => {
            const count = (d.categories || []).find((x) => x.name === c)?.count || 0;
            return (
              <button key={c} onClick={() => setCat(c)} data-testid={`blog-cat-${c}`}
                className={`${CHIP} ${category === c ? "bg-brand-magenta text-white shadow-md" : "bg-white text-slate-600 shadow-sm hover:text-brand-magenta"}`}>
                {c}{count ? <span className="ml-2 opacity-60">{count}</span> : null}
              </button>
            );
          })}
        </div>
      </section>

      {!d ? <div className="py-24"><Spinner /></div> : (
        <>
          {hero && (
            <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pb-16" data-testid="blog-hero">
              <Link to={`/blog/${hero.slug}`} className="group grid gap-8 lg:grid-cols-12 lg:gap-14">
                <motion.div initial={{ opacity: 0, scale: 1.04 }} animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.9, ease: "easeOut" }}
                  className="relative col-span-full h-[46vh] overflow-hidden rounded-3xl bg-slate-900 lg:col-span-8 lg:h-[62vh]">
                  {hero.cover_image && (
                    <img src={hero.cover_image} alt={hero.title}
                      className="h-full w-full object-cover transition-transform duration-[1.2s] ease-out group-hover:scale-[1.05]" />
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 via-slate-900/10 to-transparent" />
                  <div className="absolute inset-x-0 bottom-0 p-6 lg:hidden">
                    <Meta p={hero} light />
                    <h2 className="mt-2 font-display text-2xl font-bold text-white">{hero.title}</h2>
                  </div>
                </motion.div>
                <div className="col-span-full hidden flex-col justify-center lg:col-span-4 lg:flex">
                  <span className="text-[11px] font-bold uppercase tracking-[0.22em] text-slate-400">Featured</span>
                  <Meta p={hero} />
                  <h2 className="mt-4 font-display text-3xl font-bold leading-tight text-slate-900 transition-colors group-hover:text-brand-magenta xl:text-4xl">
                    {hero.title}
                  </h2>
                  <p className="mt-4 text-base text-slate-600">{hero.excerpt}</p>
                  <span className="mt-6 inline-flex items-center gap-2 text-sm font-bold text-slate-900">
                    Read the story
                    <ArrowUpRight className="h-4 w-4 transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
                  </span>
                </div>
              </Link>
            </section>
          )}

          <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pb-24">
            {rest.length ? (
              <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-3 lg:gap-x-10 lg:gap-y-16" data-testid="blog-grid">
                {rest.map((p, i) => <PostCard key={p.slug} p={p} index={i} />)}
              </div>
            ) : !hero ? (
              <div className="rounded-3xl border border-dashed border-slate-300 bg-white px-6 py-20 text-center"
                data-testid="blog-empty">
                <PenLine className="mx-auto h-8 w-8 text-slate-300" />
                <p className="mt-4 font-display text-2xl font-bold text-slate-900">Nothing published yet</p>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
                  {category || term
                    ? "No stories match that yet — try another category."
                    : "The first Buddilio story is being written. Check back shortly."}
                </p>
              </div>
            ) : null}
          </section>

          <section className="border-t border-slate-200 bg-slate-900 py-20">
            <div className="mx-auto max-w-3xl px-6 text-center">
              <h2 className="font-display text-3xl font-bold text-white sm:text-4xl">
                Reading about it is fine. Going is better.
              </h2>
              <p className="mt-4 text-base text-white/70">
                Buddilio members find verified people to go out with — events, dining, nightlife and travel, all 21+.
              </p>
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                <Link to="/events" data-testid="blog-cta-events"
                  className="rounded-full bg-brand-magenta px-7 py-3 text-sm font-bold text-white transition hover:bg-[#C81566]">
                  Browse events
                </Link>
                <Link to="/membership" data-testid="blog-cta-membership"
                  className="rounded-full border border-white/25 px-7 py-3 text-sm font-bold text-white transition hover:bg-white/10">
                  See membership
                </Link>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

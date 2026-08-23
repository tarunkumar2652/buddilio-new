import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ArrowLeft, Clock, Link2, Share2 } from "lucide-react";
import { api } from "@/lib/api";
import { SEO, Spinner } from "@/components/Shared";
import { PostCard } from "@/pages/Blog";
import { NewsletterSignup } from "@/components/NewsletterSignup";

const day = (v) => v ? new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" }) : "";

const jsonLd = (data) => {
  const id = "blog-jsonld";
  document.getElementById(id)?.remove();
  const tag = document.createElement("script");
  tag.type = "application/ld+json";
  tag.id = id;
  tag.text = JSON.stringify(data);
  document.head.appendChild(tag);
};

/** Long-form reading experience with a sticky share rail and structured data for crawlers. */
export default function BlogPost() {
  const { slug } = useParams();
  const [d, setD] = useState(null);
  const [missing, setMissing] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    setD(null); setMissing(false);
    api.get(`/blog/${slug}`).then(({ data }) => { setD(data); jsonLd(data.jsonld); })
      .catch(() => setMissing(true));
    window.scrollTo({ top: 0 });
  }, [slug]);

  useEffect(() => {
    const onScroll = () => {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(h > 0 ? Math.min(100, (window.scrollY / h) * 100) : 0);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const share = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try { await navigator.share({ title: d?.post?.title, url }); return; } catch { /* dismissed */ }
    }
    await navigator.clipboard.writeText(url);
    toast.success("Link copied.");
  };

  if (missing) {
    return (
      <div className="mx-auto max-w-xl px-6 py-32 text-center" data-testid="blog-post-missing">
        <h1 className="font-display text-3xl font-bold text-slate-900">We couldn't find that story</h1>
        <p className="mt-3 text-sm text-slate-500">It may have been unpublished or renamed.</p>
        <Link to="/blog" className="mt-6 inline-block rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white">
          Back to the journal
        </Link>
      </div>
    );
  }
  if (!d) return <div className="py-32"><Spinner /></div>;
  const p = d.post;

  return (
    <div className="bg-white" data-testid="blog-post-page">
      <SEO title={p.seo_title || p.title} description={p.seo_description || p.excerpt} />
      <div className="fixed inset-x-0 top-0 z-40 h-0.5 bg-brand-magenta/20">
        <div className="h-full bg-brand-magenta transition-[width] duration-150" style={{ width: `${progress}%` }}
          data-testid="read-progress" />
      </div>

      <header className="mx-auto max-w-3xl px-4 pt-16 text-center sm:px-6 lg:pt-24">
        <Link to="/blog" data-testid="back-to-journal"
          className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.18em] text-slate-400 transition hover:text-brand-magenta">
          <ArrowLeft className="h-3.5 w-3.5" />The Journal
        </Link>
        <p className="mt-6 text-xs font-bold uppercase tracking-[0.22em] text-brand-magenta">{p.category}</p>
        <h1 className="mt-4 font-display text-3xl font-bold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl">
          {p.title}
        </h1>
        <p className="mt-5 text-base text-slate-600 sm:text-lg">{p.excerpt}</p>
        <p className="mt-6 flex flex-wrap items-center justify-center gap-3 text-xs text-slate-500">
          {d.author ? (
            <Link to={`/blog/author/${d.author.slug}`} data-testid="post-author-link"
              className="inline-flex items-center gap-2 transition hover:text-brand-magenta">
              {d.author.photo ? (
                <img src={d.author.photo} alt={d.author.name} className="h-8 w-8 rounded-full object-cover" />
              ) : (
                <span className="grid h-8 w-8 place-items-center rounded-full bg-slate-900 text-[11px] font-black text-white">
                  {d.author.name.slice(0, 1)}
                </span>
              )}
              <span className="font-semibold text-slate-900">{d.author.name}</span>
              {d.author.role && <span className="text-slate-500">{d.author.role}</span>}
            </Link>
          ) : (
            <>
              <span className="font-semibold text-slate-900">{p.author_name || "Buddilio Editorial"}</span>
              {p.author_role && <span>{p.author_role}</span>}
            </>
          )}
          <span>{day(p.published_at)}</span>
          <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{p.read_minutes} min read</span>
        </p>
      </header>

      {p.cover_image && (
        <motion.figure initial={{ opacity: 0, scale: 1.03 }} animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1, ease: "easeOut" }} className="mx-auto mt-12 max-w-6xl px-4 sm:px-6">
          <img src={p.cover_image} alt={p.title} data-testid="post-cover"
            className="max-h-[62vh] w-full rounded-3xl object-cover shadow-lg" />
          {p.cover_credit && <figcaption className="mt-3 text-center text-xs text-slate-400">{p.cover_credit}</figcaption>}
        </motion.figure>
      )}

      <div className="mx-auto mt-14 flex max-w-6xl flex-col gap-10 px-4 sm:px-6 lg:flex-row lg:justify-center lg:gap-14">
        <aside className="hidden lg:sticky lg:top-32 lg:flex lg:h-fit lg:w-14 lg:flex-col lg:items-center lg:gap-4">
          <button onClick={share} data-testid="post-share"
            className="rounded-full border border-slate-200 p-3 text-slate-500 transition hover:border-brand-magenta hover:text-brand-magenta"
            aria-label="Share this story">
            <Share2 className="h-4 w-4" />
          </button>
          <button onClick={() => { navigator.clipboard.writeText(window.location.href); toast.success("Link copied."); }}
            data-testid="post-copy-link"
            className="rounded-full border border-slate-200 p-3 text-slate-500 transition hover:border-brand-magenta hover:text-brand-magenta"
            aria-label="Copy link">
            <Link2 className="h-4 w-4" />
          </button>
        </aside>

        <article data-testid="post-body"
          className="blog-body max-w-prose pb-6 text-base leading-[1.85] text-slate-700 sm:text-lg"
          dangerouslySetInnerHTML={{ __html: p.body }} />
      </div>

      <div className="mx-auto mt-14 max-w-prose px-4 pb-8 sm:px-6">
        <div className="flex flex-wrap gap-2">
          {(p.tags || []).map((t) => (
            <Link key={t} to={`/blog?tag=${encodeURIComponent(t)}`} data-testid={`post-tag-${t}`}
              className="rounded-full bg-slate-100 px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-600 transition hover:bg-brand-magenta hover:text-white">
              {t}
            </Link>
          ))}
        </div>
        <div className="mt-10 rounded-3xl bg-slate-900 p-8 text-center text-white sm:p-12" data-testid="post-cta">
          <h2 className="font-display text-2xl font-bold sm:text-3xl">{p.cta_label || "Find your people for the next one"}</h2>
          <p className="mt-3 text-sm text-white/70">
            Buddilio members go out with verified company — events, dining, nightlife and travel, all 21+.
          </p>
          <Link to={p.cta_url || "/events"} data-testid="post-cta-link"
            className="mt-6 inline-block rounded-full bg-brand-magenta px-7 py-3 text-sm font-bold text-white transition hover:bg-[#C81566]">
            {p.cta_url ? "Take a look" : "Browse events"}
          </Link>
        </div>
        <div className="mt-6 flex justify-center gap-3 lg:hidden">
          <button onClick={share} data-testid="post-share-mobile"
            className="rounded-full border border-slate-200 px-5 py-2.5 text-xs font-bold text-slate-700">
            <Share2 className="mr-1.5 inline h-3.5 w-3.5" />Share this story
          </button>
        </div>
      </div>

      {d.author && (
        <section className="mx-auto mt-20 max-w-3xl px-4 sm:px-6" data-testid="post-author-card">
          <div className="flex flex-col gap-5 rounded-3xl border border-slate-200 bg-slate-50 p-6 sm:flex-row sm:items-center">
            {d.author.photo ? (
              <img src={d.author.photo} alt={d.author.name}
                className="h-16 w-16 shrink-0 rounded-full object-cover ring-4 ring-white" />
            ) : (
              <span className="grid h-16 w-16 shrink-0 place-items-center rounded-full bg-slate-900 text-xl font-black text-white">
                {d.author.name.slice(0, 1)}
              </span>
            )}
            <div className="min-w-0">
              <p className="text-sm font-black text-slate-900">{d.author.name}</p>
              {d.author.role && <p className="text-xs font-bold uppercase tracking-wide text-brand-magenta">{d.author.role}</p>}
              {d.author.bio && <p className="mt-2 text-sm text-slate-600">{d.author.bio}</p>}
              <Link to={`/blog/author/${d.author.slug}`} data-testid="post-author-more"
                className="mt-3 inline-block text-xs font-bold text-slate-900 underline decoration-brand-magenta decoration-2 underline-offset-4">
                All stories by {d.author.name.split(" ")[0]}
              </Link>
            </div>
          </div>
        </section>
      )}

      {!!d.related.length && (        <section className="mx-auto mt-24 max-w-7xl px-4 pb-24 sm:px-6 lg:px-8" data-testid="post-related">
          <h2 className="font-display text-2xl font-bold text-slate-900">Keep reading</h2>
          <div className="mt-8 grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
            {d.related.map((r, i) => <PostCard key={r.slug} p={r} index={i} />)}
          </div>
        </section>
      )}

      <section className="border-t border-slate-200 bg-slate-50 py-16">
        <div className="mx-auto max-w-3xl px-6" data-testid="post-newsletter">
          <NewsletterSignup source={`article:${p.slug}`} />
        </div>
      </section>
    </div>
  );
}

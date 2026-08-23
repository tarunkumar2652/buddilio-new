import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, MapPin, Globe, Instagram, Twitter } from "lucide-react";
import { api } from "@/lib/api";
import { SEO, Spinner } from "@/components/Shared";
import { PostCard } from "@/pages/Blog";
import { NewsletterSignup } from "@/components/NewsletterSignup";

const setJsonLd = (data) => {
  const id = "author-jsonld";
  document.getElementById(id)?.remove();
  if (!data) return;
  const el = document.createElement("script");
  el.id = id;
  el.type = "application/ld+json";
  el.text = JSON.stringify(data);
  document.head.appendChild(el);
};

export default function BlogAuthor() {
  const { slug } = useParams();
  const [d, setD] = useState(null);

  useEffect(() => {
    setD(null);
    api.get(`/blog-authors/${slug}`).then(({ data }) => { setD(data); setJsonLd(data.jsonld); })
      .catch(() => setD(false));
    return () => setJsonLd(null);
  }, [slug]);

  if (d === null) return <div className="py-32"><Spinner /></div>;
  if (d === false) return (
    <div className="grid min-h-[60vh] place-items-center px-6 text-center" data-testid="author-missing">
      <div>
        <h1 className="font-display text-3xl font-bold text-slate-900">We don't have that writer</h1>
        <Link to="/blog" className="mt-6 inline-block rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white">
          Back to the Journal
        </Link>
      </div>
    </div>
  );

  const a = d.author;
  const links = [[a.site_url, Globe, "Website"], [a.x_url, Twitter, "X"], [a.instagram_url, Instagram, "Instagram"]]
    .filter(([u]) => u);

  return (
    <div className="bg-white" data-testid="author-page">
      <SEO title={`${a.name} — Buddilio Journal`}
        description={a.bio || `Stories by ${a.name} in the Buddilio Journal.`} />

      <header className="mx-auto max-w-4xl px-4 pt-16 sm:px-6 lg:pt-24">
        <Link to="/blog" data-testid="author-back"
          className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.18em] text-slate-400 transition hover:text-brand-magenta">
          <ArrowLeft className="h-3.5 w-3.5" />The Journal
        </Link>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }} className="mt-8 flex flex-col gap-6 sm:flex-row sm:items-center">
          {a.photo ? (
            <img src={a.photo} alt={a.name} data-testid="author-photo"
              className="h-24 w-24 shrink-0 rounded-full object-cover ring-4 ring-slate-100" />
          ) : (
            <div className="grid h-24 w-24 shrink-0 place-items-center rounded-full bg-slate-900 text-2xl font-black text-white">
              {a.name.slice(0, 1)}
            </div>
          )}
          <div>
            {a.role && <p className="text-xs font-bold uppercase tracking-[0.22em] text-brand-magenta">{a.role}</p>}
            <h1 className="mt-2 font-display text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl"
              data-testid="author-name">{a.name}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-xs font-semibold text-slate-500">
              {a.city && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{a.city}</span>}
              <span>{d.posts.length} {d.posts.length === 1 ? "story" : "stories"}</span>
              {links.map(([u, Icon, label]) => (
                <a key={label} href={u} target="_blank" rel="noreferrer" data-testid={`author-link-${label.toLowerCase()}`}
                  className="inline-flex items-center gap-1 transition hover:text-brand-magenta">
                  <Icon className="h-3.5 w-3.5" />{label}
                </a>
              ))}
            </div>
          </div>
        </motion.div>
        {a.bio && <p className="mt-8 max-w-2xl text-base leading-relaxed text-slate-600" data-testid="author-bio">{a.bio}</p>}
      </header>

      <section className="mx-auto mt-16 max-w-7xl px-4 pb-20 sm:px-6 lg:px-8">
        <h2 className="font-display text-2xl font-bold text-slate-900">Stories by {a.name.split(" ")[0]}</h2>
        {d.posts.length ? (
          <div className="mt-8 grid gap-10 sm:grid-cols-2 lg:grid-cols-3" data-testid="author-posts">
            {d.posts.map((p, i) => <PostCard key={p.slug} p={p} index={i} />)}
          </div>
        ) : (
          <p className="mt-6 text-sm text-slate-500" data-testid="author-no-posts">
            Nothing published under this byline yet.
          </p>
        )}
      </section>

      <section className="border-t border-slate-200 bg-slate-50 py-16">
        <div className="mx-auto max-w-3xl px-6"><NewsletterSignup source={`author:${a.slug}`} /></div>
      </section>
    </div>
  );
}

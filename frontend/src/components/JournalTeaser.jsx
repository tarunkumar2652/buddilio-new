import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import { PostCard } from "@/pages/Blog";

/** "From the journal" teaser — gives the homepage fresh, crawlable copy. */
export const JournalTeaser = () => {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.get("/blog", { params: { limit: 3 } }).then(({ data }) => setItems(data.items.slice(0, 3)))
      .catch(() => setItems([]));
  }, []);

  if (!items.length) return null;
  return (
    <section className="border-t border-slate-200 bg-slate-50 py-20 sm:py-28" data-testid="journal-teaser">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.22em] text-brand-magenta">From the journal</p>
            <h2 className="mt-3 font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
              Read before you go
            </h2>
          </div>
          <Link to="/blog" data-testid="journal-teaser-all"
            className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-900 hover:text-brand-magenta">
            All stories <ArrowUpRight className="h-4 w-4" />
          </Link>
        </div>
        <div className="mt-12 grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((p, i) => <PostCard key={p.slug} p={p} index={i} />)}
        </div>
      </div>
    </section>
  );
};

export default JournalTeaser;

const SHOTS = [
  ["https://images.unsplash.com/photo-1696627958251-775068a8ddbc?crop=entropy&cs=srgb&fm=jpg&q=80&w=640",
    "Supper club", "London"],
  ["https://images.unsplash.com/photo-1701008583539-a379768a8d10?crop=entropy&cs=srgb&fm=jpg&q=80&w=640",
    "Rooftop hour", "Dubai"],
  ["https://images.unsplash.com/photo-1753154113797-e9bec0c7fcc1?crop=entropy&cs=srgb&fm=jpg&q=80&w=640",
    "Backyard gig", "Austin"],
  ["https://images.unsplash.com/photo-1658827004233-3f41ed1850bf?crop=entropy&cs=srgb&fm=jpg&q=80&w=640",
    "Sunset walk", "Barcelona"],
];

export const ProofStrip = () => (
  <section className="border-b border-slate-200 bg-white" data-testid="proof-strip">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 py-10 sm:py-12">
      <p className="max-w-xl text-sm font-semibold text-slate-500">
        Last week on Buddilio — members who turned a message thread into an actual evening.
      </p>
      <div className="mt-6 flex gap-4 overflow-x-auto pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {SHOTS.map(([src, label, city], i) => (
          <figure key={label} data-testid={`proof-shot-${i}`}
            className="group relative h-40 w-64 shrink-0 overflow-hidden rounded-2xl sm:h-44 sm:w-72">
            <img src={src} alt={`${label} in ${city}`} loading="lazy"
              className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-105" />
            <span className="absolute inset-0 bg-gradient-to-t from-slate-900/80 via-slate-900/10 to-transparent" />
            <figcaption className="absolute bottom-3 left-3.5 text-white">
              <span className="block text-sm font-bold leading-tight">{label}</span>
              <span className="block text-[11px] font-semibold uppercase tracking-[0.16em] text-white/65">{city}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </div>
  </section>
);

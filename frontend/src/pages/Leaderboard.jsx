import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Leaderboard } from "@/components/Leaderboard";
import { SEO } from "@/components/Shared";
import { Gift, Users, Trophy } from "lucide-react";

const HOW = [
  [Users, "Members share their link", "Every member gets an invite code and a link they can send to anyone."],
  [Gift, "Friends join and book", "When a friend pays for their first booking, their inviter earns credit."],
  [Trophy, "The month's best wins", "Whoever brings the most people that month wins a free Buddilio pass."],
];

export default function LeaderboardPage() {
  const { user } = useAuth();
  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 py-12 pb-28" data-testid="leaderboard-page">
      <SEO title="Top inviters this month — Buddilio leaderboard"
        description="See the Buddilio members bringing the most people out this month. Invite friends, earn credit, and the month's top inviter wins a free pass." />
      <p className="overline">Community</p>
      <h1 className="mt-2 text-4xl sm:text-5xl font-bold tracking-tight">The people building Buddilio</h1>
      <p className="mt-4 max-w-2xl text-slate-600 leading-relaxed">
        Buddilio grows by invitation — one member bringing a friend who keeps saying “we should go out more”.
        This is who's doing the most of it right now. Names are shortened; nobody's contact details are ever shown.
      </p>

      <Leaderboard className="mt-10" />

      <section className="mt-14 grid md:grid-cols-3 gap-5">
        {HOW.map(([Icon, title, sub]) => (
          <div key={title} className="rounded-2xl border border-slate-200 bg-white p-6">
            <Icon className="h-5 w-5 text-brand-magenta" />
            <p className="mt-4 font-semibold">{title}</p>
            <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">{sub}</p>
          </div>
        ))}
      </section>

      <div className="mt-10 rounded-3xl bg-brand-ink text-white p-7 sm:p-9 relative overflow-hidden">
        <div className="aurora opacity-70" />
        <div className="relative">
          <h2 className="text-lg md:text-lg font-bold">
            {user ? "Your invite link is waiting" : "Get on next month's board"}
          </h2>
          <p className="mt-2 max-w-xl text-sm text-white/70 leading-relaxed">
            {user
              ? "Grab your code, send it to one friend today, and your credit lands the moment they book."
              : "Join free, verify your profile, then share your invite link. Credit lands automatically on their first booking."}
          </p>
          <Link to={user ? "/referrals" : "/register"} data-testid="leaderboard-cta"
            className="mt-6 inline-flex rounded-full brand-gradient px-7 py-3.5 text-sm font-bold transition-transform hover:scale-[1.03]">
            {user ? "Open invite & earn" : "Join Buddilio"}
          </Link>
        </div>
      </div>
    </div>
  );
}

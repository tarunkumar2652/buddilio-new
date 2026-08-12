import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fileUrl } from "@/lib/api";
import { useCurrency } from "@/context/CurrencyContext";
import { Spinner, Empty } from "@/components/Shared";
import { Trophy, Crown, Medal, Flame, ArrowRight } from "lucide-react";

const RANK_ICON = [Crown, Trophy, Medal];

const BADGE_TONE = {
  Legend: "bg-brand-magenta/10 text-brand-magenta",
  Ambassador: "bg-brand-violet/10 text-brand-violet",
  Connector: "bg-amber-50 text-amber-700",
  Starter: "bg-slate-100 text-slate-600",
};

const monthOptions = () => {
  const out = [];
  const now = new Date();
  for (let i = 0; i < 3; i += 1) {
    const dt = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push([`${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`,
      dt.toLocaleDateString(undefined, { month: "long", year: "numeric" })]);
  }
  return out;
};

export const Leaderboard = ({ className = "mt-14" }) => {
  const { fmt } = useCurrency();
  const months = monthOptions();
  const [month, setMonth] = useState(months[0][0]);
  const [d, setD] = useState(null);

  useEffect(() => {
    setD(null);
    api.get("/referrals/leaderboard", { params: { month } })
      .then(({ data }) => setD(data)).catch(() => setD({ items: [], me: null }));
  }, [month]);

  const badge = d?.me?.badge;

  return (
    <section className={className} data-testid="leaderboard-section">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="overline">Monthly leaderboard</p>
          <h2 className="mt-1.5 text-2xl font-bold flex items-center gap-2">
            <Trophy className="h-5 w-5 text-brand-magenta" />Top inviters
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            The month's number one wins {d?.prize || "a free Buddilio pass"} — awarded automatically on the 1st.
          </p>
        </div>
        <select value={month} onChange={(e) => setMonth(e.target.value)} data-testid="leaderboard-month"
          className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-brand-magenta">
          {months.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      {d?.champion && (
        <div className="mt-5 rounded-2xl bg-brand-ink text-white p-5 flex flex-wrap items-center gap-4 relative overflow-hidden" data-testid="leaderboard-champion">
          <div className="aurora opacity-60" />
          <span className="relative h-11 w-11 rounded-2xl bg-white/10 grid place-items-center">
            <Crown className="h-5 w-5 text-brand-pink" />
          </span>
          {d.champion.photo && <img src={fileUrl(d.champion.photo)} alt="" className="relative h-11 w-11 rounded-full object-cover ring-2 ring-white/20" />}
          <div className="relative flex-1 min-w-[200px]">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-white/50">
              {d.champion.month_label} champion
            </p>
            <p className="mt-1 text-sm font-semibold">
              {d.champion.me ? "You" : d.champion.name} won with {d.champion.invites} invite{d.champion.invites === 1 ? "" : "s"}
              {d.champion.city ? ` · ${d.champion.city}` : ""}
            </p>
          </div>
          <span className="relative rounded-full bg-white/10 px-3.5 py-1.5 text-xs font-bold text-white/85" data-testid="champion-prize">
            Won {d.champion.prize}
          </span>
        </div>
      )}

      {badge && (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 flex flex-wrap items-center gap-4" data-testid="leaderboard-me">
          <span className="h-11 w-11 rounded-2xl brand-gradient text-white grid place-items-center font-display font-bold">
            {d.me.rank > 0 ? `#${d.me.rank}` : "—"}
          </span>
          <div className="flex-1 min-w-[180px]">
            <p className="text-sm font-semibold">
              {d.me.rank > 0 ? `You're #${d.me.rank} this month` : "You're not on the board yet"}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              {d.me.invites} rewarded invite{d.me.invites === 1 ? "" : "s"} this month · {fmt(d.me.credit)} earned
            </p>
          </div>
          {badge.name && (
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold ${BADGE_TONE[badge.name]}`} data-testid="my-badge">
              <Flame className="h-3.5 w-3.5" />{badge.name}
            </span>
          )}
          {badge.next > 0 && (
            <p className="text-xs text-slate-500 w-full sm:w-auto">
              {badge.next - d.me.lifetime} more invite{badge.next - d.me.lifetime === 1 ? "" : "s"} to unlock the next badge
            </p>
          )}
        </div>
      )}

      {d && !d.me && (
        <div className="mt-5 rounded-2xl border border-dashed border-brand-magenta/40 bg-brand-magenta/[0.03] p-5 flex flex-wrap items-center gap-4" data-testid="leaderboard-guest-cta">
          <div className="flex-1 min-w-[220px]">
            <p className="text-sm font-semibold">Your name could be on this board next month</p>
            <p className="text-xs text-slate-500 mt-0.5">
              Members earn credit for every friend who joins and books — the top inviter takes the monthly pass.
            </p>
          </div>
          <Link to="/register" data-testid="leaderboard-join-btn"
            className="inline-flex items-center gap-2 rounded-full brand-gradient text-white px-5 py-2.5 text-sm font-bold transition-transform hover:scale-[1.02]">
            Join Buddilio<ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      <div className="mt-5">
        {!d ? <Spinner label="Ranking inviters" /> : d.items.length ? (
          <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100 overflow-hidden" data-testid="leaderboard-list">
            {d.items.map((r) => {
              const Icon = RANK_ICON[r.rank - 1];
              return (
                <div key={r.rank} data-testid={`leaderboard-row-${r.rank}`}
                  className={`p-4 flex flex-wrap items-center gap-3 ${r.me ? "bg-brand-magenta/[0.04]" : ""}`}>
                  <span className={`h-9 w-9 shrink-0 rounded-xl grid place-items-center font-display text-sm font-bold ${
                    r.rank === 1 ? "brand-gradient text-white" : "bg-slate-100 text-slate-600"}`}>
                    {Icon ? <Icon className="h-4 w-4" /> : r.rank}
                  </span>
                  {r.photo ? <img src={fileUrl(r.photo)} alt="" className="h-9 w-9 rounded-full object-cover" />
                    : <span className="h-9 w-9 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{r.name?.[0]}</span>}
                  <div className="flex-1 min-w-[140px]">
                    <p className="text-sm font-semibold">{r.name}{r.me && <span className="text-brand-magenta"> · you</span>}</p>
                    <p className="text-xs text-slate-400">{r.city || "Buddilio member"}</p>
                  </div>
                  {r.badge && <span className={`hidden sm:inline-flex rounded-full px-2.5 py-1 text-[11px] font-bold ${BADGE_TONE[r.badge]}`}>{r.badge}</span>}
                  <div className="text-right">
                    <p className="font-display font-bold text-sm">{r.invites} invite{r.invites === 1 ? "" : "s"}</p>
                    <p className="text-xs text-emerald-600 font-semibold">{fmt(r.credit)} earned</p>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty testid="leaderboard-empty" title="The board is open"
            sub="No rewarded invites this month yet — bring one friend and you're straight in at number one." />
        )}
      </div>
      {d?.participants > 0 && (
        <p className="mt-3 text-xs text-slate-400">{d.participants} member{d.participants === 1 ? "" : "s"} earned credit this month.</p>
      )}
    </section>
  );
};

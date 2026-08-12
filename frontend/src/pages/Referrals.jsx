import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, fmtDate, fileUrl } from "@/lib/api";
import { useCurrency } from "@/context/CurrencyContext";
import { Spinner, Empty, Badge, Stat, SEO } from "@/components/Shared";
import { Copy, Gift, Share2, Users, Trophy, Crown, Medal, Flame } from "lucide-react";

const STEPS = [
  ["Share your link", "Send it to a friend who keeps saying “we should go out more”."],
  ["They join Buddilio", "Your name shows up on their signup, so it never feels like spam."],
  ["You both win", "The moment they pay for their first booking, your credit lands automatically."],
];

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

const Leaderboard = () => {
  const { fmt } = useCurrency();
  const months = monthOptions();
  const [month, setMonth] = useState(months[0][0]);
  const [d, setD] = useState(null);

  useEffect(() => {
    setD(null);
    api.get("/referrals/leaderboard", { params: { month } })
      .then(({ data }) => setD(data)).catch(() => setD({ items: [], me: {} }));
  }, [month]);

  const badge = d?.me?.badge;

  return (
    <section className="mt-14" data-testid="leaderboard-section">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="overline">Monthly leaderboard</p>
          <h2 className="mt-1.5 text-2xl font-bold flex items-center gap-2">
            <Trophy className="h-5 w-5 text-brand-magenta" />Top inviters
          </h2>
        </div>
        <select value={month} onChange={(e) => setMonth(e.target.value)} data-testid="leaderboard-month"
          className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-brand-magenta">
          {months.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

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

export default function Referrals() {
  const { fmt } = useCurrency();
  const [d, setD] = useState(null);

  useEffect(() => { api.get("/me/referrals").then(({ data }) => setD(data)).catch(() => setD({ invites: [], credits: [] })); }, []);
  if (!d) return <Spinner label="Loading your invites" />;

  const link = d.link || `${window.location.origin}/register?ref=${d.code}`;
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); toast.success("Invite link copied"); }
    catch { toast.error("Couldn't copy — select the link and copy it manually."); }
  };
  const share = () => {
    const text = `Come out with me on Buddilio — curated parties, dinners and nights out with a vetted crowd. Join with my link: ${link}`;
    if (navigator.share) navigator.share({ title: "Join me on Buddilio", text, url: link }).catch(() => {});
    else window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
  };

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-10 pb-28" data-testid="referrals-page">
      <SEO title="Invite & earn" description="Invite friends to Buddilio and earn credit on their first booking." />
      <p className="overline">Invite &amp; earn</p>
      <h1 className="mt-2 text-3xl sm:text-4xl font-bold tracking-tight">Bring your people along</h1>
      <p className="mt-3 text-slate-600 max-w-xl leading-relaxed">
        Every friend who joins with your link earns you <b>{fmt(d.reward)}</b> in Buddilio credit once they pay
        for their first booking. Credit is applied automatically at your next checkout.
      </p>

      <div className="mt-8 rounded-3xl bg-brand-ink text-white p-7 sm:p-9 relative overflow-hidden" data-testid="referral-card">
        <div className="aurora opacity-70" />
        <div className="relative">
        <p className="overline text-slate-400">Your invite code</p>
        <p className="mt-2 font-display text-4xl font-bold tracking-tight" data-testid="referral-code">{d.code}</p>
        <div className="mt-6 flex flex-col sm:flex-row gap-3">
          <div className="flex-1 rounded-xl bg-white/10 px-4 py-3 text-sm text-slate-200 truncate" data-testid="referral-link">{link}</div>
          <button onClick={copy} data-testid="copy-referral-btn"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-white text-slate-900 px-5 py-3 text-sm font-bold transition-transform hover:scale-[1.02] active:scale-[.98]">
            <Copy className="h-4 w-4" />Copy link
          </button>
          <button onClick={share} data-testid="share-referral-btn"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-white/30 px-5 py-3 text-sm font-bold transition-colors hover:bg-white/10">
            <Share2 className="h-4 w-4" />Share
          </button>
        </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Credit available" value={fmt(d.balance)} sub="Used automatically at checkout" testid="referral-balance" />
        <Stat label="Friends joined" value={d.joined || 0} testid="referral-joined" />
        <Stat label="Rewards earned" value={d.rewarded || 0} testid="referral-rewarded" />
        <Stat label="Per friend" value={fmt(d.reward)} sub="On their first paid booking" testid="referral-reward" />
      </div>

      <div className="mt-10 grid md:grid-cols-3 gap-5">
        {STEPS.map(([t, s], i) => (
          <div key={t} className="rounded-2xl border border-slate-200 bg-white p-6">
            <span className="h-8 w-8 rounded-xl bg-slate-900 text-white grid place-items-center font-display font-bold text-sm">{i + 1}</span>
            <p className="mt-4 font-semibold">{t}</p>
            <p className="mt-1.5 text-sm text-slate-500 leading-relaxed">{s}</p>
          </div>
        ))}
      </div>

      <Leaderboard />

      <section className="mt-12">
        <h2 className="text-2xl font-bold flex items-center gap-2"><Users className="h-5 w-5" />Your invites</h2>
        <div className="mt-5">
          {d.invites?.length ? (
            <div className="rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100" data-testid="referral-invites">
              {d.invites.map((i, k) => (
                <div key={k} className="p-4 flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-[160px]">
                    <p className="text-sm font-semibold">{i.name || "New member"}</p>
                    <p className="text-xs text-slate-400">Joined {fmtDate(i.created_at)}</p>
                  </div>
                  <Badge tone={i.status === "rewarded" ? "green" : "amber"}>
                    {i.status === "rewarded" ? `${fmt(d.reward)} earned` : "Awaiting first booking"}
                  </Badge>
                </div>
              ))}
            </div>
          ) : <Empty testid="no-invites" title="No invites yet" sub="Share your link with one friend today — most members bring two." />}
        </div>
      </section>

      {d.credits?.length > 0 && (
        <section className="mt-12">
          <h2 className="text-2xl font-bold flex items-center gap-2"><Gift className="h-5 w-5" />Credit history</h2>
          <div className="mt-5 rounded-2xl border border-slate-200 bg-white divide-y divide-slate-100" data-testid="credit-history">
            {d.credits.map((c) => (
              <div key={c.id} className="p-4 flex flex-wrap items-center gap-3">
                <div className="flex-1 min-w-[180px]">
                  <p className="text-sm font-semibold">{c.reason}</p>
                  <p className="text-xs text-slate-400">{fmtDate(c.created_at)}</p>
                </div>
                <p className={`font-display font-bold text-sm ${c.amount > 0 ? "text-emerald-600" : "text-slate-500"}`}>
                  {c.amount > 0 ? "+" : "−"}{fmt(Math.abs(c.amount))}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

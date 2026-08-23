import { useState } from "react";
import { toast } from "sonner";
import { Mail, Check, Loader2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";

/** Journal sign-up — one field, one click, unsubscribe in every email. */
export const NewsletterSignup = ({ tone = "light", source = "journal" }) => {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const dark = tone === "dark";

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/newsletter/subscribe", { email: email.trim(), source });
      toast.success(data.message);
      setDone(true);
      setEmail("");
    } catch (e2) {
      toast.error(e2?.response?.status === 422
        ? "That doesn't look like a valid email address."
        : errMsg(e2));
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="newsletter-signup" className="w-full">
      <p className={`flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.22em] ${dark ? "text-white/50" : "text-slate-400"}`}>
        <Mail className="h-3.5 w-3.5" />The Journal, by email
      </p>
      <p className={`mt-2 font-display text-2xl font-bold ${dark ? "text-white" : "text-slate-900"}`}>
        Every new story, straight to you.
      </p>
      <p className={`mt-2 text-sm ${dark ? "text-white/60" : "text-slate-500"}`}>
        City guides, night-out playbooks and safety notes. No spam, unsubscribe in one click.
      </p>
      {done ? (
        <p className={`mt-5 inline-flex items-center gap-2 text-sm font-bold ${dark ? "text-white" : "text-slate-900"}`}
          data-testid="newsletter-done">
          <Check className="h-4 w-4 text-emerald-500" />You're on the list.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-5 flex flex-col gap-2 sm:flex-row">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="you@email.com" data-testid="newsletter-email"
            className={`flex-1 rounded-full border px-5 py-3 text-sm outline-none transition ${dark
              ? "border-white/15 bg-white/10 text-white placeholder:text-white/40 focus:border-white/40"
              : "border-slate-200 bg-white text-slate-900 focus:border-brand-magenta"}`} />
          <button disabled={busy} data-testid="newsletter-submit"
            className="rounded-full bg-brand-magenta px-6 py-3 text-sm font-bold text-white transition hover:bg-[#C81566] disabled:opacity-60">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Subscribe"}
          </button>
        </form>
      )}
    </div>
  );
};

export default NewsletterSignup;

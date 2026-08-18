import { useState } from "react";
import { toast } from "sonner";
import { Sparkles, Loader2, Wand2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";

const EXAMPLE = "rooftop supper club, 6 courses, small plates, live saxophone from 9pm, 24 seats, dress smart casual";

export const CopyHelper = ({ form, onApply }) => {
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(null);

  const run = async () => {
    if (notes.trim().length < 15) return toast.error("Give Buddy a few more details to work with.");
    setBusy(true);
    try {
      const { data } = await api.post("/partner/ai-draft", {
        notes, category: form.category, city: form.city, venue: form.venue,
        starts_at: form.starts_at, price: form.price, price_currency: form.price_currency,
        capacity: form.capacity,
      });
      setDraft(data);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="rounded-2xl border border-brand-pink/30 bg-brand-pink/[0.05] p-5" data-testid="copy-helper">
      <p className="flex items-center gap-2 text-sm font-bold">
        <Sparkles className="h-4 w-4 text-brand-magenta" />Let Buddy draft your listing
      </p>
      <p className="mt-1 text-xs text-slate-500">
        A few bullets is enough — Buddy writes the title, description and rules. You can edit everything after.
      </p>
      <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="copy-helper-notes"
        placeholder={EXAMPLE} maxLength={1500}
        className="mt-3 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-brand-magenta" />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" onClick={run} disabled={busy} data-testid="copy-helper-run"
          className="inline-flex items-center gap-2 rounded-full brand-gradient px-5 py-2.5 text-sm font-bold text-white disabled:opacity-60">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
          {busy ? "Writing…" : "Draft it"}
        </button>
        {draft && (
          <button type="button" data-testid="copy-helper-apply"
            onClick={() => {
              onApply({ title: draft.title, description: draft.description, rules: draft.rules });
              toast.success("Draft applied — tweak anything you like.");
            }}
            className="rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white">
            Use this draft
          </button>
        )}
        {draft?.daily_cap && (
          <span className="text-[11px] text-slate-400">{draft.daily_cap - draft.used_today} drafts left today</span>
        )}
      </div>

      {draft && (
        <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-white p-4" data-testid="copy-helper-draft">
          <p className="text-base font-bold" data-testid="copy-helper-title">{draft.title}</p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600" data-testid="copy-helper-description">
            {draft.description}
          </p>
          {!!draft.highlights?.length && (
            <div className="flex flex-wrap gap-2" data-testid="copy-helper-highlights">
              {draft.highlights.map((h) => (
                <span key={h} className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-bold">{h}</span>
              ))}
            </div>
          )}
          <p className="whitespace-pre-wrap text-xs text-slate-500" data-testid="copy-helper-rules">{draft.rules}</p>
        </div>
      )}
    </div>
  );
};

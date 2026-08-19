import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg, fmtDate } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/** Asks a signed-in member to accept a materially updated policy, and records the acceptance. */
export const PolicyConsent = () => {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [ticked, setTicked] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.get("/policies/pending").then(({ data }) => setItems(data.items || [])).catch(() => setItems([]));
  }, [user]);

  if (!user || !items.length) return null;

  const accept = async () => {
    setBusy(true);
    try {
      await api.post("/policies/accept", { slugs: items.map((i) => i.slug) });
      toast.success("Thank you — noted.");
      setItems([]);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[95] grid place-items-center bg-slate-900/70 p-4" data-testid="policy-consent">
      <div className="w-full max-w-lg rounded-2xl bg-white p-7">
        <p className="overline">Policy update</p>
        <h2 className="mt-2 text-2xl font-bold">We've updated our policies</h2>
        <p className="mt-2 text-sm text-slate-500">
          Please review and accept the updated documents to carry on using Buddilio.
        </p>
        <ul className="mt-5 space-y-2.5">
          {items.map((i) => (
            <li key={i.slug} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-3">
              <span className="text-sm font-semibold">{i.title}</span>
              <Link to={`/p/${i.slug}`} target="_blank" data-testid={`policy-read-${i.slug}`}
                className="text-xs font-bold text-brand-magenta underline">
                Read (updated {fmtDate(i.last_updated)})
              </Link>
            </li>
          ))}
        </ul>
        <label className="mt-5 flex items-start gap-3 text-sm">
          <input type="checkbox" checked={ticked} data-testid="policy-consent-check" className="mt-1"
            onChange={(e) => setTicked(e.target.checked)} />
          <span className="text-slate-600">
            I have read and accept the updated documents listed above. I understand my acceptance is recorded
            electronically.
          </span>
        </label>
        <button disabled={!ticked || busy} onClick={accept} data-testid="policy-consent-accept"
          className="mt-5 w-full rounded-full bg-slate-900 py-3 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Saving…" : "Accept and continue"}
        </button>
      </div>
    </div>
  );
};

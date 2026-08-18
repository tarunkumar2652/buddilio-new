import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Sparkles, Loader2, Download, Share2 } from "lucide-react";
import { api, errMsg, fileUrl } from "@/lib/api";

export const RecapCard = ({ eventId }) => {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/events/${eventId}/recap`).then(({ data }) => setData(data)).catch(() => setData(null));
  }, [eventId]);

  const make = async () => {
    setBusy(true);
    try {
      const { data: res } = await api.post(`/events/${eventId}/recap`);
      setData((p) => ({ ...p, card_url: res.card_url }));
      toast.success("Your recap card is ready.");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const share = async () => {
    const url = data?.share_url || window.location.href;
    try {
      if (navigator.share) await navigator.share({ title: data?.title, url });
      else { await navigator.clipboard.writeText(url); toast.success("Event link copied — paste it with the card."); }
    } catch { /* dismissed */ }
  };

  if (!data || data.photo_count === 0) return null;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6" data-testid="recap-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="overline">Recap card</p>
          <h3 className="mt-1 text-lg font-bold">Show the night, pull the next crowd</h3>
          <p className="mt-1 text-sm text-slate-500">
            We stitch the wall's newest {Math.min(data.photo_count, 4)} photo{data.photo_count === 1 ? "" : "s"} into
            one card you can post anywhere.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={make} disabled={busy || !data.can_make} data-testid="recap-generate-btn"
            className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-bold text-white transition-transform hover:-translate-y-0.5 disabled:opacity-50">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {data.card_url ? "Rebuild card" : "Create card"}
          </button>
          <button onClick={share} data-testid="recap-share-btn"
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">
            <Share2 className="h-4 w-4" />Share link
          </button>
        </div>
      </div>

      {!data.can_make && !data.card_url && (
        <p className="mt-3 text-xs font-semibold text-slate-400" data-testid="recap-locked">
          Log in to build a card from this wall.
        </p>
      )}

      {data.card_url && (
        <div className="mt-5 flex flex-wrap items-start gap-4">
          <img src={fileUrl(data.card_url)} alt="Event recap card" data-testid="recap-image"
            className="w-52 rounded-2xl border border-slate-200 shadow-sm" />
          <a href={fileUrl(data.card_url)} download target="_blank" rel="noreferrer" data-testid="recap-download"
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">
            <Download className="h-4 w-4" />Download image
          </a>
        </div>
      )}
    </div>
  );
};

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Flag, EyeOff, CornerDownRight } from "lucide-react";
import { api, errMsg, fileUrl } from "@/lib/api";
import { Stars } from "@/components/Cards";
import { Badge } from "@/components/Shared";

const REASONS = ["Offensive or abusive language", "Fake or spam review", "Personal information shared", "Not about this experience"];

const ReportBox = ({ reviewId, onDone }) => {
  const [reason, setReason] = useState(REASONS[0]);
  const send = async () => {
    try {
      const { data } = await api.post(`/reviews/${reviewId}/report`, { reason });
      toast.success(data.message);
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="mt-3 rounded-xl bg-slate-50 p-3 flex flex-wrap gap-2 items-center" data-testid={`report-box-${reviewId}`}>
      <select value={reason} onChange={(e) => setReason(e.target.value)} data-testid={`report-reason-${reviewId}`}
        className="flex-1 min-w-[180px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs">
        {REASONS.map((r) => <option key={r}>{r}</option>)}
      </select>
      <button onClick={send} data-testid={`report-submit-${reviewId}`}
        className="rounded-full bg-slate-900 text-white px-4 py-2 text-xs font-bold">Send report</button>
      <button onClick={onDone} className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Cancel</button>
    </div>
  );
};

export const ReviewSection = ({ eventId, canReview }) => {
  const [data, setData] = useState(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [reporting, setReporting] = useState(null);

  const load = useCallback(() => {
    api.get(`/events/${eventId}/reviews`).then(({ data }) => setData(data)).catch(() => setData({ items: [], average: 0, count: 0 }));
  }, [eventId]);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!rating) return toast.error("Pick a star rating first.");
    try {
      await api.post(`/events/${eventId}/reviews`, { rating, comment });
      toast.success("Thanks for reviewing this experience");
      setRating(0); setComment(""); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return null;

  return (
    <div data-testid="reviews-section">
      <div className="flex items-end justify-between gap-4">
        <h2 className="text-2xl font-bold">Reviews</h2>
        {data.count > 0 && (
          <div className="flex items-center gap-2" data-testid="reviews-average">
            <Stars value={data.average} />
            <span className="text-sm font-semibold">{data.average} · {data.count} review{data.count > 1 ? "s" : ""}</span>
          </div>
        )}
      </div>

      {canReview && (
        <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-6" data-testid="review-form">
          <p className="font-semibold text-sm">How was it?</p>
          <div className="mt-3"><Stars value={rating} size="h-7 w-7" onPick={setRating} /></div>
          <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} data-testid="review-comment"
            placeholder="What should other members know before booking?"
            className="mt-4 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-slate-900" />
          <button onClick={submit} data-testid="submit-review-btn"
            className="mt-4 rounded-full bg-slate-900 text-white px-6 py-2.5 text-sm font-bold">Post review</button>
        </div>
      )}

      <div className="mt-5 space-y-4">
        {data.items.length ? data.items.map((r) => (
          <div key={r.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`review-${r.id}`}>
            <div className="flex items-center gap-3">
              {r.user_photo ? <img src={fileUrl(r.user_photo)} alt="" className="h-9 w-9 rounded-full object-cover" />
                : <span className="h-9 w-9 rounded-full bg-slate-200 grid place-items-center text-xs font-bold">{r.user_name?.[0]}</span>}
              <div>
                <p className="text-sm font-semibold">{r.user_name}</p>
                <p className="text-[11px] text-slate-400">{new Date(r.created_at).toLocaleDateString(undefined)}</p>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {r.status === "hidden" && <Badge tone="red"><EyeOff className="h-3 w-3 mr-1" />hidden</Badge>}
                <Stars value={r.rating} />
              </div>
            </div>
            {r.comment && <p className="mt-3 text-sm text-slate-600 leading-relaxed">{r.comment}</p>}

            {r.reply && (
              <div className="mt-4 rounded-xl border-l-2 border-slate-900 bg-slate-50 px-4 py-3" data-testid={`review-reply-${r.id}`}>
                <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-500">
                  <CornerDownRight className="h-3.5 w-3.5" />{r.reply.by_name} · organiser
                </p>
                <p className="mt-1.5 text-sm text-slate-600 leading-relaxed">{r.reply.body}</p>
              </div>
            )}

            {!r.mine && (
              reporting === r.id
                ? <ReportBox reviewId={r.id} onDone={() => { setReporting(null); load(); }} />
                : <button onClick={() => setReporting(r.id)} data-testid={`report-review-${r.id}`}
                    className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-400 hover:text-red-600 transition-colors">
                    <Flag className="h-3 w-3" /> Report this review
                  </button>
            )}
          </div>
        )) : <p className="text-sm text-slate-500">No reviews yet — attendees can review once the event finishes.</p>}
      </div>
    </div>
  );
};

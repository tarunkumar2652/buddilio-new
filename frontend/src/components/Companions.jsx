import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, fileUrl, fmtDate, money } from "@/lib/api";
import { Spinner, Badge, Stat } from "@/components/Shared";

const TABS = [["pending", "Awaiting review"], ["approved", "Approved"], ["rejected", "Rejected"],
  ["suspended", "Suspended"], ["all", "All"]];

export const Companions = () => {
  const [status, setStatus] = useState("pending");
  const [data, setData] = useState(null);
  const [bookings, setBookings] = useState(null);
  const [notes, setNotes] = useState({});
  const [fee, setFee] = useState("");

  const load = useCallback(() => {
    setData(null);
    api.get(`/admin/companions?status=${status}`).then(({ data }) => setData(data))
      .catch((e) => { toast.error(errMsg(e)); setData({ items: [], counts: {} }); });
    api.get("/admin/companion-bookings").then(({ data }) => setBookings(data)).catch(() => setBookings(null));
    api.get("/admin/settings").then(({ data }) => setFee(String(data.hangout_request_fee ?? 100))).catch(() => {});
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const saveFee = async () => {
    try {
      await api.put("/admin/settings", { hangout_request_fee: Number(fee) });
      toast.success("Request fee updated.");
    } catch (e) { toast.error(errMsg(e)); }
  };

  const act = async (id, action) => {
    try {
      await api.post(`/admin/companions/${id}`, { action, reason: notes[id] || "" });
      toast.success(action === "approve" ? "Approved — they're now listed." : `Marked ${action}ed.`);
      setNotes((n) => ({ ...n, [id]: "" })); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const credit = async (b) => {
    const amount = window.prompt(`Goodwill credit for ${b.member_name} (they paid ${b.paid_total})`);
    if (!amount) return;
    try {
      const { data } = await api.post(`/admin/companion-bookings/${b.id}/credit`,
        { amount: Number(amount), reason: window.prompt("Reason (shown to them)") || "" });
      toast.success(`${money(data.credit_issued)} credit added.`);
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!data) return <Spinner />;

  return (
    <div className="space-y-8" data-testid="companions-panel">
      <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200 bg-white p-5">
        <label className="text-sm">
          <span className="block text-xs font-bold uppercase tracking-wide text-slate-500">Request fee (non-refundable)</span>
          <input type="number" min={0} value={fee} data-testid="request-fee-input"
            onChange={(e) => setFee(e.target.value)}
            className="mt-1 w-40 rounded-xl border border-slate-200 px-3 py-2 text-sm" />
        </label>
        <button onClick={saveFee} data-testid="request-fee-save"
          className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Save fee</button>
        <p className="text-xs text-slate-500">Charged on every hangout request to keep spam out.</p>
      </div>

      {bookings && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Stat label="Bookings" value={bookings.totals.bookings} />
          <Stat label="Gross" value={money(bookings.totals.gross)} />
          <Stat label={`Buddilio (${data.cut_percent}%)`} value={money(bookings.totals.platform)} />
          <Stat label="Owed to companions" value={money(bookings.totals.companions)} />
        </div>
      )}

      <div>
        <div className="flex flex-wrap gap-2">
          {TABS.map(([v, l]) => (
            <button key={v} onClick={() => setStatus(v)} data-testid={`companion-filter-${v}`}
              className={`rounded-full px-4 py-2 text-xs font-bold border ${status === v ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200"}`}>
              {l}{data.counts?.[v] != null ? ` (${data.counts[v]})` : ""}
            </button>
          ))}
        </div>

        {data.items.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500" data-testid="companions-empty">Nothing in this list.</p>
        ) : (
          <div className="mt-6 space-y-4">
            {data.items.map((c) => (
              <div key={c.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`companion-row-${c.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex gap-4">
                    {c.photo ? <img src={fileUrl(c.photo)} alt="" className="h-14 w-14 rounded-xl object-cover" />
                      : <span className="grid h-14 w-14 place-items-center rounded-xl bg-slate-900 text-white font-bold">{(c.full_name || "M")[0]}</span>}
                    <div>
                      <p className="font-bold">{c.full_name}</p>
                      <p className="text-xs text-slate-500">{c.email} · {c.city || "—"} · applied {fmtDate(c.applied_at)}</p>
                      <p className="mt-1 text-sm font-bold">{money(c.hourly_rate)}/hr · {c.min_hours}–{c.max_hours}h
                        {c.packages?.length ? ` · ${c.packages.length} packages` : ""}</p>
                    </div>
                  </div>
                  <Badge tone={c.status === "approved" ? "green" : c.status === "pending" ? "amber" : "red"}>{c.status}</Badge>
                </div>
                {c.headline && <p className="mt-3 text-sm font-semibold">{c.headline}</p>}
                {c.about && <p className="mt-1 line-clamp-3 text-sm text-slate-600">{c.about}</p>}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <input value={notes[c.id] || ""} placeholder="Reason / note (sent to them)" data-testid={`companion-note-${c.id}`}
                    onChange={(e) => setNotes((n) => ({ ...n, [c.id]: e.target.value }))}
                    className="flex-1 min-w-[200px] rounded-xl border border-slate-200 px-3 py-2 text-sm" />
                  {c.status !== "approved" && (
                    <button onClick={() => act(c.id, "approve")} data-testid={`companion-approve-${c.id}`}
                      className="rounded-full bg-slate-900 px-4 py-2 text-xs font-bold text-white">Approve</button>
                  )}
                  {c.status !== "rejected" && (
                    <button onClick={() => act(c.id, "reject")} data-testid={`companion-reject-${c.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold text-rose-600">Reject</button>
                  )}
                  {c.status === "approved" && (
                    <button onClick={() => act(c.id, "suspend")} data-testid={`companion-suspend-${c.id}`}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-bold">Suspend</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {bookings && bookings.items.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-widest text-slate-500">Bookings</h2>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <table className="w-full text-sm" data-testid="companion-bookings-table">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>{["Guest", "Companion", "When", "Paid", "Buddilio", "Companion net", "Status", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {bookings.items.map((b) => (
                  <tr key={b.id} data-testid={`admin-booking-${b.id}`}>
                    <td className="px-4 py-3">{b.member_name}</td>
                    <td className="px-4 py-3">{b.companion_name}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{b.hours}h · {fmtDate(b.starts_at)}</td>
                    <td className="px-4 py-3 font-semibold">{money(b.paid_total)}</td>
                    <td className="px-4 py-3">{money((b.paid_total || 0) - (b.companion_net || 0))}</td>
                    <td className="px-4 py-3">{money(b.companion_net)}</td>
                    <td className="px-4 py-3"><Badge tone={["confirmed", "completed"].includes(b.status) ? "green" : b.status.includes("cancel") || ["declined", "no_show"].includes(b.status) ? "red" : "amber"}>{b.status.replace(/_/g, " ")}</Badge></td>
                    <td className="px-4 py-3">
                      {b.paid_total > 0 && (
                        <button onClick={() => credit(b)} data-testid={`booking-credit-${b.id}`}
                          className="rounded-full border border-slate-200 px-3.5 py-1.5 text-xs font-bold">Give credit</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

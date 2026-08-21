import { useEffect, useState } from "react";
import { api, money, fmtDate } from "@/lib/api";
import { Badge } from "@/components/Shared";

/** Organiser view of door sales: what they collected in person and the commission Buddilio is owed. */
export const DoorTakings = () => {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/partner/door-takings").then(({ data }) => setD(data)).catch(() => setD(null));
  }, []);

  if (!d) return null;
  return (
    <div className="mt-10" data-testid="door-takings">
      <h3 className="text-lg font-black text-slate-900">Door sales you collected</h3>
      <p className="mt-1 text-sm text-slate-500">
        Money taken at the door stays with you. Buddilio's commission on it is recovered from your next payout.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-4">
        {[["Collected at the door", money(d.collected, d.currency), "door-collected"],
          ["Commission owed", money(d.commission_owed, d.currency), "door-owed"],
          ["Commission recovered", money(d.commission_recovered, d.currency), "door-recovered"],
          ["Walk-in guests", d.guests, "door-guests"]].map(([label, value, testid]) => (
            <div key={testid} className="rounded-2xl border border-slate-200 bg-white p-4" data-testid={testid}>
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
              <p className="mt-1 font-display text-xl font-bold text-slate-900">{value}</p>
            </div>
          ))}
      </div>
      <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left"><tr>
            {["When", "Event", "Guest", "Guests", "Collected", "How", "Commission", "Status"].map((h) => (
              <th key={h} className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-slate-500">{h}</th>))}
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {d.items.map((r) => (
              <tr key={r.order_no} data-testid={`door-take-${r.order_no}`}>
                <td className="px-4 py-3 text-xs text-slate-500">{fmtDate(r.at)}</td>
                <td className="px-4 py-3">{r.event}</td>
                <td className="px-4 py-3">{r.guest || "Walk-in"}</td>
                <td className="px-4 py-3">{r.guests}</td>
                <td className="px-4 py-3 font-semibold">{money(r.amount, r.currency)}</td>
                <td className="px-4 py-3 text-xs uppercase">{r.method}</td>
                <td className="px-4 py-3 text-slate-500">− {money(r.commission, r.currency)}</td>
                <td className="px-4 py-3"><Badge tone={r.settled ? "green" : "amber"}>{r.settled ? "recovered" : "owed"}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!d.items.length && (
          <p className="p-6 text-sm text-slate-500" data-testid="door-takings-empty">
            No door sales yet. Use "Guest without a pass" on the door check-in page when someone turns up.
          </p>
        )}
      </div>
    </div>
  );
};

export default DoorTakings;

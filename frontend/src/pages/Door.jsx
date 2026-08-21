import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Camera, CameraOff, CheckCircle2, Download, QrCode, UserPlus, Users, XCircle } from "lucide-react";
import { WalkInDialog } from "@/components/WalkInDialog";
import { api, errMsg } from "@/lib/api";
import { SEO, Spinner, Empty, Badge } from "@/components/Shared";

const PILL = "rounded-full px-4 py-2.5 text-xs font-bold";
const codeOf = (text) => {
  const m = String(text || "").toUpperCase().match(/BUD-[A-Z0-9]{4}-[0-9]{2}/);
  return m ? m[0] : "";
};

/** Door page for organisers: scan a guest's QR (or type the code) and watch arrivals build up. */
export default function Door() {
  const [params] = useSearchParams();
  const wanted = params.get("event") || "";
  const [events, setEvents] = useState(null);
  const [eventId, setEventId] = useState("");
  const [door, setDoor] = useState(null);
  const [code, setCode] = useState("");
  const [q, setQ] = useState("");
  const [walk, setWalk] = useState(null);
  const [last, setLast] = useState(null);
  const [scanning, setScanning] = useState(false);
  const scanner = useRef(null);
  const busy = useRef(false);

  useEffect(() => {
    api.get("/partner/events").then(({ data }) => {
      const live = (data.items || []).filter((e) => e.status === "published");
      setEvents(live);
      if (live.length) setEventId(live.some((e) => e.id === wanted) ? wanted : live[0].id);
    }).catch(() => setEvents([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadDoor = useCallback(() => {
    if (!eventId) return;
    api.get(`/partner/events/${eventId}/check-in`).then(({ data }) => setDoor(data))
      .catch((e) => { setDoor(null); toast.error(errMsg(e)); });
  }, [eventId]);
  useEffect(() => { loadDoor(); }, [loadDoor]);

  const redeem = useCallback(async (raw) => {
    const c = codeOf(raw) || String(raw || "").trim().toUpperCase();
    if (!c || busy.current) return;
    busy.current = true;
    try {
      const { data } = await api.post(`/passes/${c}/redeem`);
      setLast({ ok: true, code: c, name: data.pass?.user_name, item: data.pass?.item_name,
        guests: data.pass?.quantity || 1 });
      toast.success(`Checked in · ${data.pass?.user_name || c}`);
      setCode("");
      loadDoor();
    } catch (e) {
      setLast({ ok: false, code: c, msg: errMsg(e) });
      toast.error(errMsg(e));
    } finally { setTimeout(() => { busy.current = false; }, 1200); }
  }, [loadDoor]);

  const exportCsv = async () => {
    try {
      const res = await api.get(`/partner/events/${eventId}/check-in.csv`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `door-${eventId}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(errMsg(e)); }
  };

  const stop = useCallback(async () => {
    setScanning(false);
    if (scanner.current) {
      try { await scanner.current.stop(); scanner.current.clear(); } catch { /* already stopped */ }
      scanner.current = null;
    }
  }, []);

  const start = async () => {
    try {
      const { Html5Qrcode } = await import("html5-qrcode");
      setScanning(true);
      const inst = new Html5Qrcode("door-reader", { verbose: false });
      scanner.current = inst;
      await inst.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 230, height: 230 } },
        (text) => redeem(text), () => {});
    } catch (e) {
      setScanning(false);
      toast.error("Couldn't open the camera. Allow camera access, or type the code instead.");
    }
  };

  useEffect(() => () => { if (scanner.current) scanner.current.stop().catch(() => {}); }, []);

  if (!events) return <Spinner />;
  const needle = q.trim().toLowerCase();
  const shown = !door ? [] : door.items.filter((p) =>
    !needle || `${p.user_name || ""} ${p.code}`.toLowerCase().includes(needle));
  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 pb-28" data-testid="door-page">
      <SEO title="Door check-in" />
      <p className="overline">At the door</p>
      <h1 className="mt-1 text-3xl font-black text-slate-900">Check guests in</h1>
      <p className="mt-1 text-sm text-slate-500">
        Scan the QR on a guest's Buddilio Pass, or type their code. Each pass works once.
      </p>

      {events.length > 1 && (
        <select value={eventId} onChange={(e) => setEventId(e.target.value)} data-testid="door-event-select"
          className="mt-5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm">
          {events.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
        </select>
      )}
      {!events.length && (
        <Empty title="No live events" sub="Publish an event and its guests will show up here." testid="door-empty" />
      )}

      <div className="mt-5 rounded-3xl border border-slate-200 bg-white p-5">
        <div id="door-reader" data-testid="door-reader"
          className={`overflow-hidden rounded-2xl bg-slate-900 ${scanning ? "" : "hidden"}`} />
        <div className="mt-3 flex flex-wrap gap-2">
          {scanning ? (
            <button onClick={stop} data-testid="door-scan-stop" className={`${PILL} border border-slate-200`}>
              <CameraOff className="mr-1.5 inline h-4 w-4" />Stop camera
            </button>
          ) : (
            <button onClick={start} data-testid="door-scan-start" className={`${PILL} bg-slate-900 text-white`}>
              <Camera className="mr-1.5 inline h-4 w-4" />Scan a QR
            </button>
          )}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); redeem(code); }} className="mt-4 flex gap-2">
          <input value={code} onChange={(e) => setCode(e.target.value)} data-testid="door-code-input"
            placeholder="BUD-4F7K-92" autoComplete="off"
            className="flex-1 rounded-xl border border-slate-200 px-3 py-2.5 font-mono text-sm uppercase" />
          <button data-testid="door-code-submit" className={`${PILL} bg-brand-magenta text-white`}>Check in</button>
        </form>
        <button onClick={() => setWalk({})} data-testid="door-walkin-open"
          className={`${PILL} mt-3 w-full border border-slate-200`}>
          <UserPlus className="mr-1.5 inline h-4 w-4" />Guest without a pass
        </button>
        {last && (
          <div data-testid="door-last-result"
            className={`mt-4 flex items-start gap-3 rounded-2xl p-4 text-sm ${last.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700"}`}>
            {last.ok ? <CheckCircle2 className="h-5 w-5 shrink-0" /> : <XCircle className="h-5 w-5 shrink-0" />}
            <div>
              <p className="font-bold">{last.ok ? `${last.name || "Guest"} is in` : "Not accepted"}</p>
              <p className="text-xs">{last.ok ? `${last.item} · ${last.guests} guest(s) · ${last.code}` : last.msg}</p>
            </div>
          </div>
        )}
      </div>

      {door && (
        <div className="mt-6 pb-20" data-testid="door-list">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-black text-slate-900">{door.event?.title}</h2>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold" data-testid="door-counts">
              <Users className="mr-1 inline h-3.5 w-3.5" />{door.arrived} of {door.guests} arrived
            </span>
            <button onClick={loadDoor} data-testid="door-refresh" className={`${PILL} border border-slate-200`}>Refresh</button>
            <button onClick={exportCsv} data-testid="door-export" className={`${PILL} border border-slate-200`}>
              <Download className="mr-1.5 inline h-4 w-4" />Export CSV
            </button>
          </div>
          <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="door-search"
            placeholder="Search a name or code…"
            className="mt-3 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm" />
          <div className="mt-3 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
            {shown.length ? shown.map((p) => (
              <div key={p.code} className="flex items-center justify-between gap-3 p-4" data-testid={`door-guest-${p.code}`}>
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-slate-900">{p.user_name || "Guest"}</p>
                  <p className="mt-0.5 font-mono text-xs text-slate-500">
                    {p.code}{p.quantity > 1 ? ` · ${p.quantity} guests` : ""}
                    {p.redeemed_at ? ` · in at ${String(p.redeemed_at).slice(11, 16)}` : ""}
                  </p>
                </div>
                <Badge tone={p.status === "redeemed" ? "green" : p.status === "valid" ? "amber" : "red"}>
                  {p.status === "redeemed" ? "arrived" : p.status}
                </Badge>
              </div>
            )) : <p className="p-6 text-sm text-slate-500" data-testid="door-list-empty">
              {door.items.length ? "No guest matches that search." : "No passes for this event yet."}</p>}
          </div>
        </div>
      )}
      <p className="mt-6 flex items-start gap-2 text-xs text-slate-400">
        <QrCode className="h-4 w-4 shrink-0" />
        Camera scanning needs HTTPS and camera permission. If it won't open, type the code — it works the same.
      </p>
      {walk && eventId && (
        <WalkInDialog eventId={eventId} onClose={() => setWalk(null)} onDone={loadDoor} />
      )}
    </div>
  );
}

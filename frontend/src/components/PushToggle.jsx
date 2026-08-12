import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRing, BellOff, Smartphone } from "lucide-react";
import { errMsg } from "@/lib/api";
import { api } from "@/lib/api";
import { disablePush, enablePush, needsInstallFirst, pushStatus, pushSupported } from "@/lib/push";

export const PushToggle = () => {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { pushStatus().then(setState); }, []);

  const flip = async () => {
    setBusy(true);
    try {
      if (state?.on) { await disablePush(); toast.success("Phone alerts turned off"); }
      else { await enablePush(); toast.success("Phone alerts are on — we'll ping you about messages and event reminders"); }
      setState(await pushStatus());
    } catch (e) { toast.error(e.message || errMsg(e)); } finally { setBusy(false); }
  };

  const test = async () => {
    try { await api.post("/push/test"); toast.success("Test alert sent to this device"); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!pushSupported()) return null;

  if (needsInstallFirst()) {
    return (
      <div className="rounded-xl bg-slate-50 p-4 flex items-start gap-3" data-testid="push-ios-hint">
        <Smartphone className="h-4 w-4 mt-0.5 shrink-0 text-slate-500" />
        <p className="text-xs text-slate-500 leading-relaxed">
          On iPhone, add Buddilio to your Home Screen first (Share → Add to Home Screen), open it from the icon,
          then turn on alerts here.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-slate-50 p-4" data-testid="push-toggle">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={flip} disabled={busy || !state} data-testid="push-toggle-btn"
          className={`inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-xs font-bold transition-transform hover:scale-[1.02] active:scale-[.98] disabled:opacity-60 ${
            state?.on ? "border border-slate-300 bg-white text-slate-700" : "bg-slate-900 text-white"}`}>
          {state?.on ? <BellOff className="h-4 w-4" /> : <BellRing className="h-4 w-4" />}
          {busy ? "Working…" : state?.on ? "Turn off phone alerts" : "Turn on phone alerts"}
        </button>
        {state?.on && (
          <button onClick={test} data-testid="push-test-btn" className="text-xs font-bold text-slate-500 hover:text-slate-900">
            Send me a test alert
          </button>
        )}
      </div>
      <p className="mt-2.5 text-xs text-slate-500 leading-relaxed">
        {state?.permission === "denied"
          ? "Notifications are blocked for this site in your browser settings — allow them, then try again."
          : "Buzz my phone for new messages and a reminder 24 hours before an event I've booked."}
      </p>
    </div>
  );
};

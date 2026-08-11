import { useEffect, useState } from "react";
import { Download, Share, X } from "lucide-react";
import { isIOS, isStandalone } from "@/lib/pwa";

const KEY = "bud_install_dismissed";
const SNOOZE_DAYS = 30;

const snoozed = () => {
  const at = Number(localStorage.getItem(KEY) || 0);
  return at > 0 && Date.now() - at < SNOOZE_DAYS * 864e5;
};

export const InstallPrompt = () => {
  const [evt, setEvt] = useState(null);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    if (isStandalone() || snoozed()) return;
    const onPrompt = (e) => { e.preventDefault(); setEvt(e); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    const t = setTimeout(() => { if (isIOS()) setIos(true); }, 2500);
    return () => { window.removeEventListener("beforeinstallprompt", onPrompt); clearTimeout(t); };
  }, []);

  const close = () => { localStorage.setItem(KEY, String(Date.now())); setEvt(null); setIos(false); };

  const install = async () => {
    if (!evt) return;
    evt.prompt();
    await evt.userChoice;
    close();
  };

  if (!evt && !ios) return null;

  return (
    <div data-testid="install-prompt"
      className="fixed z-[60] bottom-20 md:bottom-6 left-4 right-4 md:left-auto md:right-6 md:w-[380px]
                 rounded-3xl border border-slate-200 bg-white/90 backdrop-blur-xl p-5
                 shadow-[0_18px_50px_rgb(15,23,42,0.16)] animate-[fadeUp_.4s_ease-out]">
      <button onClick={close} data-testid="install-dismiss-btn" aria-label="Dismiss"
        className="absolute top-3.5 right-3.5 p-1.5 rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors">
        <X className="h-4 w-4" />
      </button>
      <div className="flex items-start gap-3.5">
        <span className="h-11 w-11 shrink-0 rounded-2xl bg-slate-900 text-white grid place-items-center font-display font-bold text-lg">B</span>
        <div className="pr-6">
          <p className="font-display font-semibold text-[15px] tracking-tight">Keep Buddilio on your home screen</p>
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            {ios
              ? "Tap the Share icon below, then choose “Add to Home Screen”."
              : "Full-screen app, instant chats, and your saved experiences work even on patchy signal."}
          </p>
        </div>
      </div>
      {ios ? (
        <p className="mt-4 flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2.5 text-xs font-semibold text-slate-600">
          <Share className="h-4 w-4" /> Share → Add to Home Screen
        </p>
      ) : (
        <button onClick={install} data-testid="install-accept-btn"
          className="mt-4 w-full inline-flex items-center justify-center gap-2 rounded-full bg-slate-900 text-white
                     py-3 text-sm font-bold transition-transform hover:scale-[1.02] active:scale-[.98]">
          <Download className="h-4 w-4" /> Install the app
        </button>
      )}
    </div>
  );
};

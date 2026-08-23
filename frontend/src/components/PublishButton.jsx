import { useEffect, useState } from "react";
import { toast } from "sonner";
import { UploadCloud } from "lucide-react";
import { api, errMsg, fmtDate } from "@/lib/api";

const PILL = "rounded-full px-4 py-2 text-xs font-bold transition-colors";

export const PublishButton = ({ onDone, className = "" }) => {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/admin/publish").then((r) => setS(r.data)).catch(() => setS(null));
  }, []);

  const go = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/publish");
      if (data.ok) {
        toast.success(data.message);
        setS((p) => ({ ...(p || {}), last_publish: data.at }));
        onDone?.();
      } else toast.message(data.message);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`} data-testid="publish-block">
      <button type="button" onClick={go} disabled={busy} data-testid="publish-btn"
        className={`${PILL} inline-flex items-center gap-2 bg-brand-magenta text-white disabled:opacity-50`}>
        <UploadCloud className="h-3.5 w-3.5" />{busy ? "Publishing…" : "Publish to live site"}
      </button>
      <span className="text-xs font-semibold text-slate-500" data-testid="publish-note">
        {s && s.available === false
          ? "Preview always shows the newest code — use this on buddilio.com."
          : s?.last_publish ? `Last published ${fmtDate(s.last_publish)}` : "Pushes head code, verification files and the Journal."}
      </span>
    </div>
  );
};

export default PublishButton;

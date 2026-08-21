import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";

/** Built-in bot check: server-issued question + hidden honeypot field. */
export const Captcha = ({ value, onChange, honeypot, onHoneypot, testid = "captcha" }) => {
  const [q, setQ] = useState(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    api.get("/captcha").then(({ data }) => {
      setQ(data);
      onChange({ captcha_id: data.captcha_id, captcha_answer: "" });
    }).catch(() => { setQ(null); setFailed(true); });
    // onChange is stable enough for this one-shot fetch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid={testid}>
      <input type="text" name="website" tabIndex={-1} autoComplete="off" value={honeypot || ""}
        onChange={(e) => onHoneypot?.(e.target.value)} aria-hidden="true"
        style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }} />
      <label className="block text-xs font-bold text-slate-500">
        Quick human check
        <div className="mt-1.5 flex items-center gap-2">
          <span className="flex-1 rounded-lg bg-slate-50 px-3 py-2.5 text-sm text-slate-700" data-testid={`${testid}-question`}>
            {q ? q.question : failed ? "Couldn't load the check — tap refresh." : "Loading…"}
          </span>
          <button type="button" onClick={load} data-testid={`${testid}-refresh`} aria-label="New question"
            className="rounded-lg border border-slate-200 p-2.5 text-slate-500 hover:text-slate-900">
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
        <input value={value?.captcha_answer || ""} data-testid={`${testid}-answer`}
          onChange={(e) => onChange({ captcha_id: q?.captcha_id || "", captcha_answer: e.target.value })}
          placeholder="Your answer" autoComplete="off"
          className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-brand-magenta" />
      </label>
    </div>
  );
};

export default Captcha;

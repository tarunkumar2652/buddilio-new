import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Save, RotateCcw, Send } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Spinner, Badge, Empty } from "@/components/Shared";

const cls = "mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm";
const L = ({ label, children, hint }) => (
  <label className="block">
    <span className="text-xs font-bold text-slate-600">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
  </label>
);

export const EmailTemplates = () => {
  const [items, setItems] = useState(null);
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback((keep) => {
    api.get("/admin/email-templates").then(({ data }) => {
      setItems(data.items);
      if (keep) setSel(data.items.find((i) => i.key === keep) || null);
    }).catch((e) => { toast.error(errMsg(e)); setItems([]); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/admin/email-templates/${sel.key}`, {
        subject: sel.subject, title: sel.title, body: sel.body,
        cta_label: sel.cta_label, cta_url: sel.cta_url,
      });
      toast.success("Saved — the next send uses your wording.");
      load(sel.key);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  const reset = async () => {
    if (!window.confirm("Put this email back to the Buddilio default wording?")) return;
    try { const { data } = await api.delete(`/admin/email-templates/${sel.key}`); setSel(data); toast.success("Reset."); load(sel.key); }
    catch (e) { toast.error(errMsg(e)); }
  };

  const test = async () => {
    try { const { data } = await api.post(`/admin/email-templates/${sel.key}/test`); toast.success(`${data.message} (${data.sent_to})`); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!items) return <Spinner />;
  const groups = [...new Set(items.map((i) => i.group))];

  return (
    <div className="grid lg:grid-cols-[300px_1fr] gap-6" data-testid="emails-panel">
      <div className="max-h-[620px] space-y-4 overflow-y-auto pr-1">
        {groups.map((g) => (
          <div key={g}>
            <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">{g}</p>
            <div className="mt-2 space-y-2">
              {items.filter((i) => i.group === g).map((t) => (
                <button key={t.key} onClick={() => setSel({ ...t })} data-testid={`email-select-${t.key}`}
                  className={`w-full rounded-xl border p-3 text-left ${sel?.key === t.key ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"}`}>
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    <Mail className="h-3.5 w-3.5 text-slate-400" />{t.label}
                    {t.customised && <Badge tone="green">edited</Badge>}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-slate-500">{t.subject}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div>
        {!sel ? <Empty title="Pick an email" sub="Choose an automated email to change its subject and wording." /> : (
          <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5" data-testid="email-editor">
            <div>
              <p className="text-sm font-bold">{sel.label}</p>
              <p className="mt-1 text-xs text-slate-500" data-testid="email-vars">
                Available placeholders: {sel.vars.map((v) => `{{${v}}}`).join(", ")}
              </p>
            </div>
            <L label="Subject line">
              <input value={sel.subject} data-testid="email-subject"
                onChange={(e) => setSel({ ...sel, subject: e.target.value })} className={cls} />
            </L>
            <L label="Heading inside the email">
              <input value={sel.title} data-testid="email-title"
                onChange={(e) => setSel({ ...sel, title: e.target.value })} className={cls} />
            </L>
            <L label="Body" hint="Basic HTML is allowed: <p>, <b>, <br/>, links and lists.">
              <textarea rows={12} value={sel.body} data-testid="email-body"
                onChange={(e) => setSel({ ...sel, body: e.target.value })}
                className={`${cls} font-mono text-xs`} />
            </L>
            <div className="grid gap-3 sm:grid-cols-2">
              <L label="Button label"><input value={sel.cta_label} data-testid="email-cta-label"
                onChange={(e) => setSel({ ...sel, cta_label: e.target.value })} className={cls} /></L>
              <L label="Button link"><input value={sel.cta_url} data-testid="email-cta-url"
                onChange={(e) => setSel({ ...sel, cta_url: e.target.value })} className={cls} /></L>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={save} disabled={busy} data-testid="email-save"
                className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-6 py-2.5 text-sm font-bold text-white disabled:opacity-50">
                <Save className="h-4 w-4" />Save wording
              </button>
              <button onClick={test} data-testid="email-test"
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">
                <Send className="h-4 w-4" />Send me a test
              </button>
              <button onClick={reset} data-testid="email-reset"
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-2.5 text-sm font-bold">
                <RotateCcw className="h-4 w-4" />Reset to default
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

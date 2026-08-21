import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, QrCode, ShieldCheck, XCircle } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { SEO, Spinner, Empty, Badge } from "@/components/Shared";
import { useAuth } from "@/context/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL;
const tone = (s) => (s === "valid" ? "green" : s === "redeemed" ? "blue" : "red");

export const MyPasses = () => {
  const [items, setItems] = useState(null);
  const [all, setAll] = useState(false);
  useEffect(() => {
    api.get("/me/passes").then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  }, []);

  const download = async (p) => {
    try {
      const res = await api.get(`/passes/${p.code}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${p.code}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (!items) return <Spinner />;
  if (!items.length) {
    return <Empty title="No passes yet" sub="Every paid booking gets a Buddilio Pass with a QR code you can show at the door."
      testid="passes-empty" />;
  }

  const shown = all ? items : items.slice(0, 4);
  return (
    <>
    <div className="grid gap-4 sm:grid-cols-2" data-testid="my-passes">
      {shown.map((p) => (
        <div key={p.id} className="rounded-2xl border border-slate-200 bg-white p-5" data-testid={`pass-${p.code}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="overline">{p.kind}</p>
              <p className="mt-1 font-display font-bold">{p.item_name}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                #{p.order_no}{p.city ? ` · ${p.city}` : ""}{p.quantity > 1 ? ` · ${p.quantity} guests` : ""}
              </p>
            </div>
            <Badge tone={tone(p.status)}>{p.status}</Badge>
          </div>
          <div className="mt-4 flex items-center gap-4">
            <img src={`${API}/api/passes/${p.code}/qr.png`} alt={`QR for ${p.code}`} width="96" height="96"
              className="h-24 w-24 rounded-lg border border-slate-100" data-testid={`pass-qr-${p.code}`} />
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Verification code</p>
              <p className="font-mono text-lg font-bold" data-testid={`pass-code-${p.code}`}>{p.code}</p>
              {p.status === "redeemed" && (
                <p className="mt-1 text-[11px] text-slate-400">
                  Checked in {String(p.redeemed_at).slice(0, 16).replace("T", " ")}
                  {p.redeemed_by_name ? ` by ${p.redeemed_by_name}` : ""}
                </p>
              )}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={() => download(p)} data-testid={`pass-pdf-${p.code}`}
              className="rounded-full bg-slate-900 px-4 py-2 text-[11px] font-bold text-white">Download / print</button>
            <Link to={`/verify/${p.code}`} data-testid={`pass-verify-${p.code}`}
              className="rounded-full border border-slate-200 px-4 py-2 text-[11px] font-bold">Show verify page</Link>
          </div>
        </div>
      ))}
    </div>
    {items.length > 4 && (
      <button onClick={() => setAll(!all)} data-testid="passes-toggle-all"
        className="mt-3 rounded-full border border-slate-200 px-5 py-2 text-xs font-bold">
        {all ? "Show fewer passes" : `Show all ${items.length} passes`}
      </button>
    )}
    </>
  );
};

export default function VerifyPass() {
  const { code: routeCode } = useParams();
  const { user } = useAuth();
  const [code, setCode] = useState(routeCode || "");
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);

  const check = useCallback(async (value) => {
    const c = (value || "").trim().toUpperCase();
    if (!c) return;
    setBusy(true);
    try {
      const { data } = await api.get(`/passes/${c}/check`);
      setInfo(data);
      if (!data.found) toast.error("No pass matches that code.");
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  }, []);

  useEffect(() => { if (routeCode) check(routeCode); }, [routeCode, check]);

  const redeem = async () => {
    setBusy(true);
    try {
      await api.post(`/passes/${info.code}/redeem`);
      toast.success("Pass accepted — let them in.");
      check(info.code);
    } catch (e) { toast.error(errMsg(e)); setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-lg px-4 sm:px-6 py-14" data-testid="verify-pass-page">
      <SEO title="Verify a Buddilio Pass" description="Check and accept a Buddilio Pass at the door." />
      <p className="overline">At the door</p>
      <h1 className="mt-1.5 font-display text-3xl font-bold">Verify a pass</h1>
      <p className="mt-3 text-slate-600">Scan the QR on the guest's pass, or type the code below.</p>

      <div className="mt-6 flex gap-2">
        <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} data-testid="verify-code-input"
          onKeyDown={(e) => { if (e.key === "Enter") check(code); }} placeholder="BUD-4F7K-92"
          className="flex-1 rounded-full border border-slate-200 px-5 py-3 font-mono text-sm outline-none focus:border-brand-magenta" />
        <button onClick={() => check(code)} disabled={busy} data-testid="verify-check-btn"
          className="rounded-full bg-slate-900 px-6 py-3 text-sm font-bold text-white disabled:opacity-60">Check</button>
      </div>

      {info && (
        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6" data-testid="verify-result">
          {!info.found ? (
            <div className="flex items-start gap-3" data-testid="verify-not-found">
              <XCircle className="h-6 w-6 shrink-0 text-red-500" />
              <div><p className="font-bold">No such pass</p>
                <p className="text-sm text-slate-500">Check the code with the guest — codes look like BUD-4F7K-92.</p></div>
            </div>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="overline">{info.kind}</p>
                  <p className="mt-1 font-display text-lg font-bold">{info.item_name}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    Guest {info.guest_initials} · {info.quantity} guest{info.quantity > 1 ? "s" : ""}
                    {info.city ? ` · ${info.city}` : ""}
                  </p>
                  {info.vendor_name && <p className="text-xs text-slate-400">Host: {info.vendor_name}</p>}
                </div>
                <Badge tone={tone(info.status)}>{info.status}</Badge>
              </div>
              {info.status === "valid" && (
                user ? (
                  <button onClick={redeem} disabled={busy} data-testid="verify-redeem-btn"
                    className="mt-6 w-full rounded-full bg-brand-magenta py-3.5 text-sm font-bold text-white disabled:opacity-60">
                    {busy ? "Accepting…" : "Accept & check in"}
                  </button>
                ) : (
                  <Link to="/login" data-testid="verify-login-link"
                    className="mt-6 block rounded-full bg-slate-900 py-3.5 text-center text-sm font-bold text-white">
                    Sign in to accept this pass
                  </Link>
                )
              )}
              {info.status === "redeemed" && (
                <p className="mt-5 flex items-start gap-2 text-sm font-semibold text-emerald-700" data-testid="verify-already">
                  <CheckCircle2 className="h-5 w-5 shrink-0" />
                  Already checked in {String(info.redeemed_at).slice(0, 16).replace("T", " ")}
                  {info.redeemed_by_name ? ` by ${info.redeemed_by_name}` : ""}.
                </p>
              )}
              {info.status === "void" && (
                <p className="mt-5 text-sm font-semibold text-red-600" data-testid="verify-void">
                  This booking was cancelled or refunded — do not admit on this pass.
                </p>
              )}
            </>
          )}
        </div>
      )}

      <p className="mt-8 flex items-start gap-2 text-xs text-slate-500">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        Each pass works once. Always match the guest's photo ID to the booking, and never accept a code
        that was shared publicly.
      </p>
      <p className="mt-3 flex items-center gap-2 text-xs text-slate-400">
        <QrCode className="h-4 w-4" /> Tip: your phone camera opens this page straight from the guest's QR.
      </p>
    </div>
  );
}

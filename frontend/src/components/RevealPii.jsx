import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Eye, KeyRound, Copy } from "lucide-react";
import { api, errMsg } from "@/lib/api";

/** Masked PII with a 10-second, audited reveal — super admins only. */
export const RevealPii = ({ user, canReveal }) => {
  const [shown, setShown] = useState(null);
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!left) return;
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);

  useEffect(() => { if (left === 0) setShown(null); }, [left]);

  const reveal = async () => {
    try {
      const { data } = await api.post(`/admin/users/${user.id}/reveal`);
      setShown({ email: data.email, mobile: data.mobile });
      setLeft(data.seconds);
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="text-xs text-slate-500">
      <p data-testid={`user-email-${user.id}`}>{shown ? shown.email : user.email}</p>
      {(shown?.mobile || user.mobile) && (
        <p data-testid={`user-mobile-${user.id}`}>{shown ? shown.mobile : user.mobile}</p>
      )}
      {canReveal && (
        shown ? (
          <span className="mt-1 inline-block font-bold text-amber-600" data-testid={`reveal-timer-${user.id}`}>
            Hiding in {left}s
          </span>
        ) : (
          <button onClick={reveal} data-testid={`reveal-${user.id}`}
            className="mt-1 inline-flex items-center gap-1 font-bold text-slate-700 hover:underline">
            <Eye className="h-3 w-3" />Reveal for 10s
          </button>
        )
      )}
    </div>
  );
};

/** Passwords are stored as one-way hashes, so the only safe "view" is a fresh single-use one. */
export const TempPassword = ({ user }) => {
  const [pw, setPw] = useState("");
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!left) return;
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);

  useEffect(() => { if (left === 0) setPw(""); }, [left]);

  const issue = async () => {
    if (!window.confirm(`Issue a new temporary password for ${user.full_name}? Their current one stops working.`)) return;
    try {
      const { data } = await api.post(`/admin/users/${user.id}/temp-password`);
      setPw(data.password);
      setLeft(data.seconds);
    } catch (e) { toast.error(errMsg(e)); }
  };

  if (pw) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1.5 text-[11px] font-bold text-white"
        data-testid={`temp-password-${user.id}`}>
        {pw}
        <button onClick={() => { navigator.clipboard?.writeText(pw); toast.success("Copied."); }}
          data-testid={`copy-password-${user.id}`} title="Copy"><Copy className="h-3 w-3" /></button>
        <span className="text-white/60">{left}s</span>
      </span>
    );
  }
  return (
    <button onClick={issue} data-testid={`show-password-${user.id}`}
      className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-[11px] font-bold">
      <KeyRound className="h-3 w-3" />Password
    </button>
  );
};

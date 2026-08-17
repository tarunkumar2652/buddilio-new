import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { errMsg } from "@/lib/api";
import { Spinner } from "@/components/Shared";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function AuthCallback() {
  const { googleSession } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const sid = new URLSearchParams((loc.hash || "").replace(/^#/, "")).get("session_id");
    if (!sid) { nav("/login", { replace: true }); return; }
    googleSession(sid, localStorage.getItem("bud_ref") || "")
      .then((u) => {
        localStorage.removeItem("bud_ref");
        toast.success(`Signed in as ${(u.full_name || "").split(" ")[0]}`);
        const to = u.profile_complete === false ? "/welcome"
          : u.role === "admin" ? "/admin" : u.role === "partner" ? "/partner" : "/dashboard";
        nav(to, { replace: true });
      })
      .catch((e) => {
        toast.error(errMsg(e));
        nav("/login", { replace: true });
      });
  }, [googleSession, loc.hash, nav]);

  return <div data-testid="auth-callback"><Spinner label="Finishing your Google sign-in" /></div>;
}

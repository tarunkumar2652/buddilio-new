import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, errMsg } from "@/lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!localStorage.getItem("bud_token")) { setUser(false); setLoading(false); return; }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
    } catch {
      localStorage.removeItem("bud_token");
      setUser(false);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    // Returning from the Emergent OAuth redirect: AuthCallback exchanges the session first.
    if (window.location.hash?.includes("session_id=")) { setLoading(false); return; }
    load();
  }, [load]);

  const finish = (data) => {
    localStorage.setItem("bud_token", data.access_token);
    setUser(data.user);
    return data.user;
  };

  const login = async (email, password, extra = {}) => {
    const { data } = await api.post("/auth/login", { email, password, ...extra });
    return finish(data);
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    return finish(data);
  };

  const googleSession = useCallback(async (session_id, referral_code = "") => {
    const { data } = await api.post("/auth/google/session", { session_id, referral_code });
    localStorage.setItem("bud_token", data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* ignore */ }
    localStorage.removeItem("bud_token");
    setUser(false);
  };

  return (
    <AuthCtx.Provider value={{ user, setUser, loading, login, register, logout, googleSession, refresh: load, errMsg }}>
      {children}
    </AuthCtx.Provider>
  );
}

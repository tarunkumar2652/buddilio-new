import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

const Ctx = createContext(null);
export const useCurrency = () => useContext(Ctx);

const FALLBACK = [{ code: "INR", rate: 1, symbol: "₹", label: "Indian Rupee" }];

export function CurrencyProvider({ children }) {
  const [list, setList] = useState(FALLBACK);
  const [code, setCode] = useState(localStorage.getItem("bud_currency") || "INR");

  useEffect(() => {
    api.get("/meta").then(({ data }) => { if (data.currencies?.length) setList(data.currencies); }).catch(() => {});
  }, []);

  const active = useMemo(() => list.find((c) => c.code === code) || list[0], [list, code]);

  const set = (c) => { localStorage.setItem("bud_currency", c); setCode(c); };

  const fmt = (inr) => {
    const v = Number(inr || 0) * Number(active?.rate || 1);
    const digits = active?.code === "INR" ? 0 : 2;
    return `${active?.symbol || ""}${v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  };

  return <Ctx.Provider value={{ list, code, set, active, fmt }}>{children}</Ctx.Provider>;
}

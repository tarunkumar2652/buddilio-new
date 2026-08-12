import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, money, setBaseCurrency } from "@/lib/api";

const Ctx = createContext(null);
export const useCurrency = () => useContext(Ctx);

const FALLBACK = [{ code: "INR", rate: 1, symbol: "₹", label: "Indian Rupee" }];

const TZ_COUNTRY = {
  "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Asia/Dubai": "AE", "Asia/Singapore": "SG",
  "Europe/London": "GB", "America/New_York": "US", "America/Chicago": "US", "America/Denver": "US",
  "America/Los_Angeles": "US", "America/Toronto": "CA", "America/Vancouver": "CA",
  "Australia/Sydney": "AU", "Australia/Melbourne": "AU", "Europe/Berlin": "DE",
  "Europe/Madrid": "ES", "Europe/Paris": "FR", "Asia/Bangkok": "TH", "Asia/Tokyo": "JP",
};

const detectCurrency = (countries, currencies) => {
  const pick = (region) => {
    const match = countries.find((c) => c.code === region);
    return match && currencies.some((x) => x.code === match.currency) ? match.currency : null;
  };
  try {
    const fromLocale = pick(new Intl.Locale(navigator.language).region);
    if (fromLocale) return fromLocale;
  } catch { /* locale unavailable */ }
  try {
    return pick(TZ_COUNTRY[Intl.DateTimeFormat().resolvedOptions().timeZone]);
  } catch { return null; }
};

export function CurrencyProvider({ children }) {
  const [list, setList] = useState(FALLBACK);
  const [countries, setCountries] = useState([]);
  const [code, setCode] = useState(localStorage.getItem("bud_currency") || "");

  useEffect(() => {
    api.get("/meta").then(({ data }) => {
      const currencies = data.currencies?.length ? data.currencies : FALLBACK;
      setList(currencies);
      setCountries(data.countries || []);
      setBaseCurrency(data.base_currency);
      if (!localStorage.getItem("bud_currency")) {
        setCode(detectCurrency(data.countries || [], currencies) || data.base_currency || "INR");
      }
    }).catch(() => {});
  }, []);

  const active = useMemo(() => list.find((c) => c.code === code) || list[0], [list, code]);

  const set = (c) => { localStorage.setItem("bud_currency", c); setCode(c); };

  // Prices are stored in the platform base currency and converted for display.
  const fmt = (base) => money(Number(base || 0) * Number(active?.rate || 1), active?.code);

  // An exact amount set by the organiser in this currency beats the FX conversion.
  const fmtOf = (base, overrides) => {
    const exact = overrides?.[active?.code];
    return exact === undefined || exact === null ? fmt(base) : money(Number(exact), active?.code);
  };

  return <Ctx.Provider value={{ list, countries, code: active?.code, set, active, fmt, fmtOf }}>{children}</Ctx.Provider>;
}

import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;
export const api = axios.create({ baseURL: `${BASE}/api`, withCredentials: true });

api.interceptors.request.use((config) => {
  const t = localStorage.getItem("bud_token");
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d?.msg) return d.msg;
  if (e?.message === "Network Error") return "Network issue. Please check your connection.";
  return "Something went wrong. Please try again.";
}

let baseCurrency = "INR";
export const setBaseCurrency = (c) => { baseCurrency = (c || "INR").toUpperCase(); };

export const money = (n, currency) => {
  const cur = (currency || baseCurrency).toUpperCase();
  const digits = cur === "INR" || cur === "JPY" ? 0 : 2;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: digits }).format(Number(n || 0));
  } catch {
    return `${cur} ${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: digits })}`;
  }
};

export const citySlug = (name) =>
  (name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

export const fileUrl = (u) => {
  if (!u) return "";
  if (u.startsWith("http") || u.startsWith("data:")) return u;
  return `${BASE}${u.startsWith("/") ? "" : "/"}${u}`;
};

export const fmtDate = (s) => {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch { return ""; }
};

export const fmtTime = (s) => {
  if (!s) return "";
  try {
    return new Date(s).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch { return ""; }
};

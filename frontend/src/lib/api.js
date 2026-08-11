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

export const money = (n) =>
  "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

export const fileUrl = (u) => {
  if (!u) return "";
  if (u.startsWith("http") || u.startsWith("data:")) return u;
  return `${BASE}${u.startsWith("/") ? "" : "/"}${u}`;
};

export const fmtDate = (s) => {
  if (!s) return "";
  try {
    return new Date(s).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch { return ""; }
};

export const fmtTime = (s) => {
  if (!s) return "";
  try {
    return new Date(s).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
  } catch { return ""; }
};

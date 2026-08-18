import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let cache = null;
let inflight = null;
const listeners = new Set();

export const loadSite = () => {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = api.get("/site-content").then(({ data }) => {
      cache = data;
      listeners.forEach((fn) => fn(data));
      return data;
    }).catch(() => ({})).finally(() => { inflight = null; });
  }
  return inflight;
};

export const useSite = () => {
  const [site, setSite] = useState(cache);
  useEffect(() => {
    listeners.add(setSite);
    loadSite().then(setSite);
    return () => listeners.delete(setSite);
  }, []);
  return site || {};
};

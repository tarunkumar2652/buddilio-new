import { useEffect } from "react";
import { api } from "@/lib/api";

/** Injects the site-wide ad snippet (AdSense Auto ads or the verification tag) once. */
export const AdsHead = () => {
  useEffect(() => {
    let alive = true;
    api.get("/ads/head").then(({ data }) => {
      if (!alive || !data.code || document.getElementById("ads-head-snippet")) return;
      const holder = document.createElement("div");
      holder.innerHTML = data.code;
      const mark = document.createElement("meta");
      mark.id = "ads-head-snippet";
      document.head.appendChild(mark);
      holder.querySelectorAll("script").forEach((old) => {
        const s = document.createElement("script");
        [...old.attributes].forEach((a) => s.setAttribute(a.name, a.value));
        s.text = old.textContent || "";
        document.head.appendChild(s);
      });
      holder.querySelectorAll("meta").forEach((m) => document.head.appendChild(m.cloneNode(true)));
    }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return null;
};

export default AdsHead;

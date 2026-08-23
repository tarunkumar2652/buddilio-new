import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * Runs a pasted ad snippet. innerHTML never executes <script>, so each one is
 * re-created — that's what makes a copied AdSense block actually work.
 */
const runSnippet = (host, html) => {
  host.innerHTML = "";
  const tpl = document.createElement("div");
  tpl.innerHTML = html;
  tpl.querySelectorAll("script").forEach((old) => {
    const s = document.createElement("script");
    [...old.attributes].forEach((a) => s.setAttribute(a.name, a.value));
    s.text = old.textContent || "";
    old.replaceWith(s);
  });
  [...tpl.childNodes].forEach((n) => host.appendChild(n));
};

/**
 * One ad slot. Shows a house banner if one is scheduled, otherwise the ad network,
 * otherwise nothing at all — an empty slot never leaves a gap.
 */
export const AdSlot = ({ placement, city = "", className = "", variant = "banner" }) => {
  const [d, setD] = useState(null);
  const insRef = useRef(null);
  const codeRef = useRef(null);
  const onAdminPage = typeof window !== "undefined"
    && /^\/(admin|console|partner)/.test(window.location.pathname);

  useEffect(() => {
    let alive = true;
    if (onAdminPage) { setD(false); return () => { alive = false; }; }
    api.get("/ads", { params: { placement, city } })
      .then(({ data }) => { if (alive) setD(data); })
      .catch(() => { if (alive) setD(false); });
    return () => { alive = false; };
  }, [placement, city, onAdminPage]);

  useEffect(() => {
    if (d?.network?.code && codeRef.current) runSnippet(codeRef.current, d.network.code);
  }, [d]);

  useEffect(() => {
    if (!d?.network?.client || !insRef.current) return;
    const id = "adsbygoogle-lib";
    if (!document.getElementById(id)) {
      const s = document.createElement("script");
      s.id = id;
      s.async = true;
      s.crossOrigin = "anonymous";
      s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${d.network.client}`;
      document.head.appendChild(s);
    }
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch { /* blocked */ }
  }, [d]);

  if (!d || d === false || (!d.ad && !d.network)) return null;

  if (d.network?.code) {
    return <div ref={codeRef} className={className} data-testid={`ad-code-${placement}`} />;
  }

  if (d.network) {
    return (
      <div className={className} data-testid={`ad-network-${placement}`}>
        <ins ref={insRef} className="adsbygoogle block w-full" style={{ display: "block" }}
          data-ad-client={d.network.client} data-ad-slot={d.network.slot}
          data-ad-format="auto" data-full-width-responsive="true" />
      </div>
    );
  }

  const a = d.ad;
  const go = async (e) => {
    e.preventDefault();
    try { await api.post(`/ads/${a.id}/click`); } catch { /* still send them on */ }
    window.open(a.url, a.url?.startsWith("/") ? "_self" : "_blank", "noopener");
  };

  if (variant === "strip") {
    return (
      <a href={a.url || "#"} onClick={go} data-testid={`ad-${placement}`}
        className={`group flex flex-wrap items-center justify-center gap-3 border-y border-slate-200 bg-slate-50 px-6 py-3 text-center text-sm transition-colors hover:bg-slate-100 ${className}`}>
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">Promoted</span>
        <span className="font-bold text-slate-900">{a.headline}</span>
        {a.body && <span className="text-slate-500">{a.body}</span>}
        <span className="font-bold text-brand-magenta group-hover:underline">{a.cta_label} →</span>
      </a>
    );
  }

  return (
    <a href={a.url || "#"} onClick={go} data-testid={`ad-${placement}`}
      className={`group block overflow-hidden rounded-3xl border border-slate-200 bg-white transition-shadow hover:shadow-lg ${a.image ? "" : "mx-auto max-w-2xl"} ${className}`}>
      <div className="flex flex-col sm:flex-row">
        {a.image && (
          <img src={a.image} alt={a.headline} loading="lazy"
            className="h-40 w-full object-cover sm:h-auto sm:w-64" />
        )}
        <div className="flex-1 p-6">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
            Promoted{a.advertiser ? ` · ${a.advertiser}` : ""}
          </p>
          <p className="mt-2 font-display text-xl font-bold text-slate-900">{a.headline}</p>
          {a.body && <p className="mt-2 text-sm text-slate-600">{a.body}</p>}
          <span className="mt-4 inline-block rounded-full bg-slate-900 px-5 py-2.5 text-xs font-bold text-white transition-transform group-hover:scale-[1.03]">
            {a.cta_label}
          </span>
        </div>
      </div>
    </a>
  );
};

export default AdSlot;

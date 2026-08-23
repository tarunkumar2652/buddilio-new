/* eslint-disable */
/**
 * Post-build prerender: writes real HTML for the Journal so crawlers see the words
 * without running JavaScript. React still boots and takes over for readers.
 * Never fails the build — if the API is unreachable it simply skips.
 */
const fs = require("fs");
const path = require("path");

// CRA injects env vars into the bundle but not into this script, so read .env ourselves.
const loadEnv = () => {
  if (process.env.REACT_APP_BACKEND_URL) return process.env.REACT_APP_BACKEND_URL;
  try {
    const raw = fs.readFileSync(path.join(__dirname, "..", ".env"), "utf8");
    const line = raw.split("\n").find((l) => l.trim().startsWith("REACT_APP_BACKEND_URL="));
    return line ? line.split("=").slice(1).join("=").trim() : "";
  } catch { return ""; }
};

const BUILD = path.join(__dirname, "..", "build");
const API = loadEnv().replace(/\/$/, "");
const esc = (s) => String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const get = async (p) => {
  const r = await fetch(`${API}/api${p}`, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`${p} -> ${r.status}`);
  return r.json();
};

const write = (route, html) => {
  const dir = route === "/" ? BUILD : path.join(BUILD, route);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "index.html"), html, "utf8");
  console.log(`  prerendered ${route}`);
};

/** Swaps title/description/canonical, injects JSON-LD and the crawlable markup. */
const page = (shell, { title, description, canonical, jsonld, body, verification }) => {
  let out = shell
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`)
    .replace(/<meta name="description" content="[\s\S]*?"\s*\/>/,
      `<meta name="description" content="${esc(description)}" />`)
    .replace(/<meta property="og:title" content="[\s\S]*?"\s*\/>/,
      `<meta property="og:title" content="${esc(title)}" />`);
  const head = [
    `<link rel="canonical" href="${esc(canonical)}" />`,
    verification ? `<meta name="google-site-verification" content="${esc(verification)}" />` : "",
    jsonld ? `<script type="application/ld+json">${JSON.stringify(jsonld)}</script>` : "",
  ].filter(Boolean).join("\n");
  out = out.replace("</head>", `${head}\n</head>`);
  return out.replace('<div id="root"></div>', `<div id="root">${body}</div>`);
};

const cardHtml = (p, site) => `
  <article>
    <h2><a href="${site}/blog/${esc(p.slug)}">${esc(p.title)}</a></h2>
    <p>${esc(p.category)} · ${esc(p.read_minutes)} min read · ${esc(p.published_at || "").slice(0, 10)}</p>
    <p>${esc(p.excerpt)}</p>
  </article>`;

(async () => {
  if (!API) return console.log("[prerender] no REACT_APP_BACKEND_URL — skipped");
  const shellPath = path.join(BUILD, "index.html");
  if (!fs.existsSync(shellPath)) return console.log("[prerender] no build/index.html — skipped");
  const shell = fs.readFileSync(shellPath, "utf8");

  let pub = {};
  try { pub = await get("/seo/public"); } catch (e) { /* optional */ }
  const site = (pub.site_url || "https://buddilio.com").replace(/\/$/, "");
  const verification = pub.gsc_verification || "";

  // key file for IndexNow, served from the site root
  if (pub.indexnow_key) {
    fs.writeFileSync(path.join(BUILD, `${pub.indexnow_key}.txt`), pub.indexnow_key, "utf8");
    console.log("  wrote IndexNow key file");
  }

  // fresh sitemap alongside the dynamic one
  try {
    const r = await fetch(`${API}/api/sitemap.xml`);
    if (r.ok) fs.writeFileSync(path.join(BUILD, "sitemap.xml"), await r.text(), "utf8");
  } catch (e) { /* keep the shipped sitemap index */ }

  let index;
  try { index = await get("/blog?limit=48"); } catch (e) {
    return console.log(`[prerender] blog API unavailable (${e.message}) — skipped`);
  }
  const posts = [index.featured, ...(index.items || [])].filter(Boolean);
  const seen = new Set();
  const unique = posts.filter((p) => !seen.has(p.slug) && seen.add(p.slug));

  write("blog", page(shell, {
    title: "The Buddilio Journal — city guides, night-out playbooks and safety notes",
    description: "City guides, night-out playbooks and honest safety notes from the Buddilio editorial desk.",
    canonical: `${site}/blog`,
    verification,
    jsonld: {
      "@context": "https://schema.org", "@type": "Blog", name: "The Buddilio Journal",
      url: `${site}/blog`,
      blogPost: unique.slice(0, 20).map((p) => ({
        "@type": "BlogPosting", headline: p.title, url: `${site}/blog/${p.slug}`,
        datePublished: p.published_at, description: p.excerpt,
      })),
    },
    body: `<main><h1>Going out, done well.</h1>
      <p>City guides, night-out playbooks and honest safety notes from the Buddilio editorial desk.</p>
      <nav>${(index.all_categories || []).map((c) =>
        `<a href="${site}/blog?category=${encodeURIComponent(c).replace(/%20/g, "+")}">${esc(c)}</a>`).join(" ")}</nav>
      ${unique.map((p) => cardHtml(p, site)).join("")}</main>`,
  }));

  let count = 0;
  for (const p of unique) {
    try {
      const { post, jsonld } = await get(`/blog/${p.slug}`);
      write(`blog/${post.slug}`, page(shell, {
        title: post.seo_title || post.title,
        description: post.seo_description || post.excerpt,
        canonical: `${site}/blog/${post.slug}`,
        verification, jsonld,
        body: `<main><article>
          <p>${esc(post.category)} · ${esc(post.read_minutes)} min read</p>
          <h1>${esc(post.title)}</h1>
          <p>${esc(post.excerpt)}</p>
          <p>By ${esc(post.author_name || "Buddilio Editorial")}${post.published_at ? ` · ${esc(String(post.published_at).slice(0, 10))}` : ""}</p>
          ${post.cover_image ? `<img src="${esc(post.cover_image)}" alt="${esc(post.title)}" />` : ""}
          ${post.body || ""}
          <p><a href="${site}/blog">Back to the Journal</a></p>
        </article></main>`,
      }));
      count += 1;
    } catch (e) { console.log(`  skipped ${p.slug}: ${e.message}`); }
  }
  console.log(`[prerender] done — Journal index + ${count} articles`);
})().catch((e) => console.log(`[prerender] skipped: ${e.message}`));

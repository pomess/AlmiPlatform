// Pulls candidate building photos for each pharma competitor from
// Wikimedia Commons into apps/web/public/competitors/candidates/<slug>/.
// Bruno picks the winner per company; we then move the chosen file to
// public/competitors/<slug>.jpg and set its photoUrl in pharma.ts.
//
// Usage (from repo root):
//   node apps/web/scripts/fetch-competitor-photos.mjs
//
// One Commons search term per company plus a slug for the folder name.
// The script:
//   1. hits the Commons search API for the term
//   2. picks the top N image results
//   3. downloads ~1200px renders into the candidates folder
//
// No API key needed; Commons is public. We send a descriptive User-Agent
// because the Wikimedia API rate-limits anonymous requests harder.

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT_ROOT = join(HERE, "..", "public", "competitors", "candidates");
const CANDIDATES_PER = 4;
const TARGET_WIDTH = 1280;
const UA =
  "Disease360-CompetitorPhotoFetcher/0.1 (https://signkairos.com; bruno@signkairos.com)";

// Per-company Commons search seeds. Barcelona-area only — the rest of
// the COMPETITORS list is in Madrid / abroad and is left out on purpose.
// We try each query in order until we have at least CANDIDATES_PER
// images, broadening from the actual local site to the surrounding
// business park / municipality when needed.
const TARGETS = [
  { slug: "sanofi", queries: [
    "Sanofi Barcelona",
    "Sanofi Diagonal Barcelona",
    "Diagonal Mar Barcelona office",
  ]},
  { slug: "novartis", queries: [
    "Novartis Gran Via Barcelona",
    "Novartis Hospitalet de Llobregat",
    "Gran Via L'Hospitalet office",
  ]},
  { slug: "leo-pharma", queries: [
    "LEO Pharma Sant Cugat",
    "Sant Cugat del Vallès office building",
    "Parc Empresarial Sant Cugat",
  ]},
  { slug: "roche", queries: [
    "Roche Sant Cugat",
    "Roche Diagnostics Sant Cugat",
    "Roche Spain headquarters",
  ]},
  { slug: "bayer", queries: [
    "Bayer Sant Joan Despí",
    "Bayer Hispania",
    "Sant Joan Despí office building",
  ]},
  { slug: "boehringer-ingelheim", queries: [
    "Boehringer Ingelheim Sant Cugat",
    "Boehringer Ingelheim España",
    "Boehringer Ingelheim Spain",
  ]},
];

async function fetchJson(url) {
  const res = await fetch(url, { headers: { "User-Agent": UA, Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

async function commonsSearch(query) {
  // 1. text search across the File: namespace.
  const searchUrl =
    "https://commons.wikimedia.org/w/api.php?" +
    new URLSearchParams({
      action: "query",
      list: "search",
      srsearch: query,
      srnamespace: "6", // File:
      srlimit: "20",
      format: "json",
      origin: "*",
    });
  const search = await fetchJson(searchUrl);
  const hits = (search.query?.search ?? []).map((h) => h.title);
  if (!hits.length) return [];

  // 2. resolve to actual rendered URLs at TARGET_WIDTH plus the
  //    descriptive metadata so we can pick non-logo, non-portrait shots.
  const titlesParam = hits.slice(0, CANDIDATES_PER * 3).join("|");
  const infoUrl =
    "https://commons.wikimedia.org/w/api.php?" +
    new URLSearchParams({
      action: "query",
      titles: titlesParam,
      prop: "imageinfo",
      iiprop: "url|size|mime|extmetadata",
      iiurlwidth: String(TARGET_WIDTH),
      format: "json",
      origin: "*",
    });
  const info = await fetchJson(infoUrl);
  const pages = Object.values(info.query?.pages ?? {});
  const candidates = [];
  for (const p of pages) {
    const ii = p.imageinfo?.[0];
    if (!ii) continue;
    if (!ii.mime?.startsWith("image/")) continue;
    if (ii.mime === "image/svg+xml") continue; // skip vector logos
    if ((ii.width ?? 0) < 600) continue; // skip thumbnails
    // Aspect-ratio sanity: drop strips / extreme portraits that won't
    // crop well to 16:9.
    const w = ii.thumbwidth || ii.width;
    const h = ii.thumbheight || ii.height;
    if (w && h) {
      const ar = w / h;
      if (ar < 0.6 || ar > 3.0) continue;
    }
    // Skip obvious logos, scans, ads, and unrelated junk based on title.
    const title = (p.title || "").toLowerCase();
    const denylist = [
      "logo", "wordmark", "symbol", "seal", "icon",
      "confederate", "djvu", "bundesarchiv", "advertisement",
      "portrait", "diagram", "chart", "map of",
      ".pdf", "flickr - usdagov",
    ];
    if (denylist.some((d) => title.includes(d))) continue;
    candidates.push({
      title: p.title,
      url: ii.thumburl || ii.url,
      width: ii.thumbwidth || ii.width,
      height: ii.thumbheight || ii.height,
    });
    if (candidates.length >= CANDIDATES_PER) break;
  }
  return candidates;
}

async function download(url, destPath) {
  // Wikimedia returns 429 when we hit the same upload host too fast.
  // Two short retries with backoff are enough in practice.
  for (let attempt = 0; attempt < 3; attempt++) {
    const res = await fetch(url, { headers: { "User-Agent": UA } });
    if (res.ok) {
      const buf = Buffer.from(await res.arrayBuffer());
      await writeFile(destPath, buf);
      return buf.length;
    }
    if (res.status === 429 && attempt < 2) {
      await new Promise((r) => setTimeout(r, 600 * (attempt + 1)));
      continue;
    }
    throw new Error(`${res.status} ${url}`);
  }
  throw new Error(`download retries exhausted ${url}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function fileNameFromTitle(title, idx) {
  // "File:Roche Tower Basel.jpg" -> "01-roche-tower-basel.jpg"
  const stripped = title.replace(/^File:/i, "").replace(/\s+/g, "_");
  const safe = stripped.replace(/[^A-Za-z0-9._-]/g, "_");
  const ext = safe.match(/\.(jpe?g|png|webp)$/i)?.[0] ?? ".jpg";
  const base = safe.replace(/\.(jpe?g|png|webp)$/i, "");
  return `${String(idx + 1).padStart(2, "0")}-${base.slice(0, 80)}${ext}`;
}

async function processOne(target) {
  const dir = join(OUT_ROOT, target.slug);
  await mkdir(dir, { recursive: true });
  const seen = new Set();
  const collected = [];
  for (const q of target.queries) {
    if (collected.length >= CANDIDATES_PER) break;
    console.log(`\n[${target.slug}] searching: "${q}"`);
    let cs;
    try {
      cs = await commonsSearch(q);
    } catch (err) {
      console.error(`  ! search failed: ${err.message}`);
      continue;
    }
    for (const c of cs) {
      if (seen.has(c.title)) continue;
      seen.add(c.title);
      collected.push(c);
      if (collected.length >= CANDIDATES_PER) break;
    }
    console.log(`  found ${cs.length} (${collected.length} total)`);
  }
  if (!collected.length) {
    console.warn(`  ! no candidates for ${target.slug}`);
    return;
  }
  for (let i = 0; i < collected.length; i++) {
    const c = collected[i];
    const name = fileNameFromTitle(c.title, i);
    const dest = join(dir, name);
    try {
      const bytes = await download(c.url, dest);
      console.log(`  ✓ ${name}  (${c.width}×${c.height}, ${(bytes / 1024).toFixed(0)} KB)`);
    } catch (err) {
      console.error(`  ! ${c.title} -> ${err.message}`);
    }
    // Be polite to upload.wikimedia.org.
    await sleep(250);
  }
}

async function main() {
  await mkdir(OUT_ROOT, { recursive: true });
  for (const t of TARGETS) {
    await processOne(t);
  }
  console.log(`\nDone. Browse ${OUT_ROOT}`);
  console.log(`Pick the winner per company, then:`);
  console.log(`  1. move it to apps/web/public/competitors/<slug>.jpg`);
  console.log(`  2. set photoUrl: "/competitors/<slug>.jpg" in pharma.ts`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

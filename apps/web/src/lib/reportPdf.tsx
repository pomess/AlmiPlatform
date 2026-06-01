// Client-side "download as PDF" for the deep-research report.
//
// We deliberately avoid a PDF library (jsPDF/html2pdf add weight and render
// markdown poorly). Instead we mirror the repo's existing approach in
// scripts/build_docs.py — render to clean, print-optimised HTML and let the
// browser's print engine produce the PDF via "Save as PDF". This yields
// crisp, selectable, vector text with proper page breaks for free.
import { renderToStaticMarkup } from "react-dom/server";
import { renderMarkdown } from "./markdown";

// Pull a human title out of the report. Prefer the first markdown H1/H2;
// fall back to the user's query, then a generic label.
function deriveTitle(markdown: string, query?: string | null): string {
  for (const raw of markdown.split("\n")) {
    const line = raw.trim();
    const m = /^#{1,2}\s+(.+?)\s*#*$/.exec(line);
    if (m) return m[1].trim();
  }
  if (query && query.trim()) return query.trim();
  return "Deep Research Report";
}

// Filesystem-safe slug for the suggested "Save as PDF" filename.
function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60) || "report"
  );
}

// Print stylesheet. Self-contained (no app tokens) so the print window
// renders identically regardless of the cockpit's runtime theme.
const PRINT_CSS = `
  @page { size: A4; margin: 18mm 16mm 20mm; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1b1d22;
    font-size: 11pt;
    line-height: 1.55;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .doc { max-width: 720px; margin: 0 auto; }
  .doc-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 16px;
    padding-bottom: 10px;
    margin-bottom: 22px;
    border-bottom: 2px solid #0d7d72;
  }
  .doc-brand {
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    font-size: 11pt;
    color: #0d7d72;
  }
  .doc-brand small {
    display: block;
    font-weight: 500;
    letter-spacing: 0.16em;
    font-size: 7.5pt;
    color: #6b7280;
    margin-top: 3px;
  }
  .doc-meta { text-align: right; font-size: 8pt; color: #6b7280; line-height: 1.5; }
  .doc-query {
    margin: 0 0 22px;
    padding: 10px 14px;
    background: #f1f7f6;
    border-left: 3px solid #0d7d72;
    border-radius: 0 6px 6px 0;
    font-size: 9.5pt;
    color: #374151;
  }
  .doc-query b { color: #0d7d72; letter-spacing: 0.06em; text-transform: uppercase; font-size: 7.5pt; }
  .doc-body h1 { font-size: 17pt; margin: 0 0 8px; color: #111317; }
  .doc-body h2 { font-size: 13.5pt; margin: 22px 0 6px; color: #0d7d72; border-bottom: 1px solid #e5e7eb; padding-bottom: 3px; }
  .doc-body h3 { font-size: 11.5pt; margin: 16px 0 4px; color: #1b1d22; }
  .doc-body h4 { font-size: 10.5pt; margin: 12px 0 4px; color: #374151; }
  .doc-body p { margin: 0 0 9px; }
  .doc-body ul, .doc-body ol { margin: 6px 0 10px; padding-left: 22px; }
  .doc-body li { margin: 2px 0; }
  .doc-body a { color: #0d7d72; text-decoration: none; word-break: break-word; }
  .doc-body strong { color: #111317; }
  .doc-body code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 9pt;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-radius: 3px;
    padding: 0.5px 4px;
  }
  .doc-body pre {
    background: #f6f8fa;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 10px 12px;
    overflow-x: auto;
    font-size: 8.5pt;
  }
  .doc-body pre code { background: none; border: none; padding: 0; }
  .doc-body blockquote {
    margin: 10px 0;
    padding-left: 12px;
    border-left: 3px solid #cbd5e1;
    color: #4b5563;
  }
  .doc-body table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9pt; }
  .doc-body th, .doc-body td { border: 1px solid #e5e7eb; padding: 5px 8px; text-align: left; vertical-align: top; }
  .doc-body th { background: #f1f7f6; color: #0d7d72; }
  .doc-body h1, .doc-body h2, .doc-body h3, .doc-body h4 { break-after: avoid; }
  .doc-body table, .doc-body pre, .doc-body blockquote { break-inside: avoid; }
`;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Open a print window containing the deep-research report rendered as a
 * branded document, then invoke the browser's print dialog so the user can
 * "Save as PDF". Returns false if a popup blocker prevented the window.
 */
export function downloadResearchReportPdf(
  markdown: string,
  opts?: { query?: string | null },
): boolean {
  const query = opts?.query ?? null;
  const title = deriveTitle(markdown, query);
  // renderMarkdown returns React nodes (ReactMarkdown + remark-gfm); render
  // them to a static HTML string so we can drop them into the print window.
  const bodyHtml = renderToStaticMarkup(<>{renderMarkdown(markdown)}</>);

  const now = new Date();
  const dateStr = now.toLocaleString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const queryBlock = query
    ? `<div class="doc-query"><b>Query</b><br>${escapeHtml(query)}</div>`
    : "";

  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(slugify(title))}</title>
<style>${PRINT_CSS}</style>
</head>
<body>
  <div class="doc">
    <header class="doc-header">
      <div class="doc-brand">Disease360<small>Competitive Intelligence · Deep Research</small></div>
      <div class="doc-meta">Generated ${escapeHtml(dateStr)}</div>
    </header>
    ${queryBlock}
    <div class="doc-body">${bodyHtml}</div>
  </div>
</body>
</html>`;

  const win = window.open("", "_blank", "noopener,noreferrer,width=860,height=1000");
  if (!win) return false;
  win.document.open();
  win.document.write(html);
  win.document.close();

  // Wait for layout/fonts before printing so headings + tables paginate
  // correctly. `onload` is the reliable signal in freshly-written windows;
  // a timeout backstops browsers that don't fire it for document.write.
  const triggerPrint = () => {
    win.focus();
    win.print();
  };
  let printed = false;
  const once = () => {
    if (printed) return;
    printed = true;
    triggerPrint();
  };
  win.onload = once;
  win.setTimeout(once, 400);
  return true;
}

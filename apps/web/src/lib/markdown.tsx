// Markdown renderer for brain pages + chat.
// Uses react-markdown + remark-gfm for tables, task lists, strikethrough, etc.
// Wikilinks ([[target|alias]]) are rewritten to anchor tags with an onClick
// handler installed at a parent level — see BrainDetail for the handler.
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";

// Wikilinks: [[Page Name]] or [[Page#section|alias]]. Require at least one
// non-digit character in the target so numeric refs like [[1]] (which can
// arise from malformed citation rendering, e.g. "[\[1\]](url)") do NOT
// match — those should fall through to plain markdown link rendering.
const WIKILINK_RE = /\[\[(?=[^\]|#]*[A-Za-z_])([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g;

// Strip a leading YAML frontmatter block (---\n...\n---) so it doesn't render as a table.
function stripFrontmatter(src: string): string {
  if (!src.startsWith("---")) return src;
  const end = src.indexOf("\n---", 3);
  if (end === -1) return src;
  const after = src.indexOf("\n", end + 1);
  return after === -1 ? "" : src.slice(after + 1);
}

// Encode wikilinks as regular markdown links so react-markdown renders them as <a>.
// We use a `wiki:` scheme so the surrounding component can intercept clicks.
function rewriteWikilinks(src: string): string {
  return src.replace(WIKILINK_RE, (_m, target: string, alias?: string) => {
    const t = target.trim();
    const label = (alias ?? t).trim();
    return `[${label}](wiki:${encodeURIComponent(t)})`;
  });
}

export function renderMarkdown(text: string | null | undefined): ReactNode {
  if (!text) return null;
  const prepared = rewriteWikilinks(stripFrontmatter(text));
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      urlTransform={(url) => url}
      components={{
        a: ({ href, children, ...rest }) => {
          if (href && href.startsWith("wiki:")) {
            const target = decodeURIComponent(href.slice(5));
            return (
              <a
                className="wikilink"
                href={`#wiki:${target}`}
                data-wikilink={target}
                {...rest}
              >
                {children}
              </a>
            );
          }
          return (
            <a href={href} target="_blank" rel="noreferrer" {...rest}>
              {children}
            </a>
          );
        },
      }}
    >
      {prepared}
    </ReactMarkdown>
  );
}

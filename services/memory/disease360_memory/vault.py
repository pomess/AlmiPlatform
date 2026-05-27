"""Vault disk I/O: read/write markdown, parse frontmatter + wikilinks."""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from .schemas import Page, WikiLink

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")


def parse_wikilinks(body: str) -> list[WikiLink]:
    out: list[WikiLink] = []
    for m in WIKILINK_RE.finditer(body):
        target = m.group(1).strip()
        alias = m.group(2).strip() if m.group(2) else None
        out.append(WikiLink(target=target, alias=alias))
    return out


def title_from_body(path: Path, body: str) -> str:
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def title_from_body_str(path: str, body: str) -> str:
    """Path-free variant for the Postgres backend.

    Same heuristic as `title_from_body`: first H1 wins; otherwise derive
    from the filename stem in the rel path.
    """
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    stem = path.rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[:-3]
    return stem.replace("-", " ").replace("_", " ").title()


def read_page(root: Path, rel_path: str) -> Page:
    abs_path = (root / rel_path).resolve()
    if root.resolve() not in abs_path.parents and abs_path != root.resolve():
        raise ValueError(f"Path escapes vault root: {rel_path}")
    if not abs_path.is_file():
        raise FileNotFoundError(f"No such page: {rel_path}")
    raw = abs_path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    body = post.content
    fm = dict(post.metadata) if post.metadata else {}
    title = fm.get("title") or title_from_body(abs_path, body)
    return Page(
        path=rel_path.replace("\\", "/"),
        title=title,
        frontmatter=fm,
        body=body,
        wikilinks=parse_wikilinks(body),
    )


def write_page(root: Path, rel_path: str, body: str, fm: dict | None = None) -> Page:
    abs_path = (root / rel_path).resolve()
    if root.resolve() not in abs_path.parents:
        raise ValueError(f"Path escapes vault root: {rel_path}")
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(content=body, **(fm or {}))
    abs_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return read_page(root, rel_path)


def list_markdown(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def append_to_section(text: str, section: str, addition: str) -> str:
    """Append `addition` under markdown `## section`. Create the section if missing."""
    header = f"## {section}".rstrip()
    if header in text:
        lines = text.splitlines()
        out: list[str] = []
        injected = False
        i = 0
        while i < len(lines):
            out.append(lines[i])
            if not injected and lines[i].strip() == header:
                # find end of this section (next "## " or EOF)
                j = i + 1
                while j < len(lines) and not lines[j].lstrip().startswith("## "):
                    j += 1
                # walk back over trailing blanks
                k = j - 1
                while k > i and lines[k].strip() == "":
                    k -= 1
                # copy through k
                for line in lines[i + 1 : k + 1]:
                    out.append(line)
                out.append("")
                out.append(addition.rstrip())
                out.append("")
                i = j
                injected = True
                continue
            i += 1
        return "\n".join(out).rstrip() + "\n"
    sep = "" if text.endswith("\n") or text == "" else "\n"
    return f"{text}{sep}\n{header}\n\n{addition.rstrip()}\n"

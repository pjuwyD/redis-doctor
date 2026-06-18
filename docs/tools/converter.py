#!/usr/bin/env python3
"""Build the HTML documentation in docs/html/ from the Markdown in docs/md/.

Stdlib only — no external Markdown library. Supports the subset of Markdown used
by the docs: ATX headings (with slug anchors), paragraphs, fenced code blocks,
inline code / bold / italic / links, GFM pipe tables, unordered and ordered lists
(one level of nesting), blockquotes, and horizontal rules.

Intra-doc links to `*.md` (optionally with `#anchor`) are rewritten to `*.html`,
preserving relative paths so the site works opened directly from disk.

Usage:
    python docs/tools/converter.py            # build docs/md -> docs/html
    python docs/tools/converter.py --src X --out Y
    python docs/tools/converter.py --clean    # remove docs/html first
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path

# --- navigation order -----------------------------------------------------
# (Section title, [relative md paths]). Pages not listed are appended under
# "More" in discovery order.
NAV: list[tuple[str, list[str]]] = [
    ("Overview", ["index.md"]),
    ("Start here", ["getting-started.md", "installation.md", "examples.md"]),
    (
        "Reference",
        [
            "commands/index.md",
            "commands/analyze.md",
            "commands/scan-keys.md",
            "commands/inspect-stream.md",
            "commands/inspect-clients.md",
            "commands/config-check.md",
            "commands/analyze-sentinel.md",
            "commands/analyze-cluster.md",
            "commands/report.md",
            "commands/diff.md",
            "configuration.md",
            "findings-catalog.md",
            "output-and-exit-codes.md",
            "safety.md",
        ],
    ),
    ("Guides", ["guides/explore.md", "guides/tui.md", "guides/gui.md", "guides/ci.md"]),
    (
        "Developer",
        [
            "developer/architecture.md",
            "developer/collectors.md",
            "developer/analyzers.md",
            "developer/rule-engine.md",
            "developer/adding-a-module.md",
            "developer/testing.md",
        ],
    ),
]

CSS = """
:root { --fg:#1f2330; --muted:#5b6472; --bg:#fdfdfd; --side:#1b1b2b;
        --side-fg:#cfd3e0; --accent:#2f6fed; --crit:#d12b2b; --warn:#c47f00;
        --code-bg:#f4f5f8; --border:#e3e6ec; }
* { box-sizing: border-box; }
body { margin:0; font-family: -apple-system, system-ui, "Segoe UI", Roboto, sans-serif;
       color: var(--fg); background: var(--bg); line-height: 1.6; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.layout { display: flex; min-height: 100vh; }
nav.side { width: 270px; background: var(--side); color: var(--side-fg);
           padding: 1.2rem 1rem; flex-shrink: 0; overflow-y: auto;
           position: sticky; top: 0; height: 100vh; }
nav.side .brand { color:#fff; font-weight:700; font-size:1.15rem; margin-bottom:.2rem; }
nav.side .tag { color:#8b90a6; font-size:.8rem; margin-bottom:1rem; display:block; }
nav.side .sect { color:#8b90a6; text-transform:uppercase; font-size:.72rem;
                 letter-spacing:.08em; margin:1rem 0 .35rem; }
nav.side ul { list-style:none; margin:0; padding:0; }
nav.side li { margin:.1rem 0; }
nav.side a { color: var(--side-fg); display:block; padding:.2rem .5rem; border-radius:5px;
             font-size:.92rem; }
nav.side a:hover { background:#2a2a40; text-decoration:none; }
nav.side a.active { background: var(--accent); color:#fff; }
main { flex:1; min-width:0; }
article { max-width: 860px; margin:0 auto; padding: 2rem 2.4rem 4rem; }
h1,h2,h3,h4 { line-height:1.25; }
h1 { font-size:2rem; margin:.2rem 0 1rem; }
h2 { font-size:1.4rem; margin-top:2rem; border-bottom:1px solid var(--border);
     padding-bottom:.3rem; }
h3 { font-size:1.12rem; margin-top:1.5rem; }
h4 { font-size:1rem; margin-top:1.2rem; color: var(--muted); }
.anchor { color: var(--border); margin-left:.4rem; font-weight:400; opacity:0; }
h2:hover .anchor, h3:hover .anchor, h4:hover .anchor { opacity:1; }
code { background: var(--code-bg); padding:.1rem .35rem; border-radius:4px;
       font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; font-size:.88em; }
pre { background: var(--code-bg); border:1px solid var(--border); border-radius:8px;
      padding:1rem; overflow:auto; }
pre code { background:none; padding:0; font-size:.85rem; line-height:1.45; }
table { border-collapse: collapse; width:100%; margin:1rem 0; font-size:.92rem; }
th, td { border:1px solid var(--border); padding:.45rem .6rem; text-align:left;
         vertical-align:top; }
th { background: var(--code-bg); }
blockquote { margin:1rem 0; padding:.4rem 1rem; border-left:4px solid var(--accent);
             background: var(--code-bg); color: var(--muted); }
hr { border:none; border-top:1px solid var(--border); margin:2rem 0; }
.pager { display:flex; justify-content:space-between; margin-top:3rem;
         border-top:1px solid var(--border); padding-top:1rem; font-size:.92rem; }
.pager .next { margin-left:auto; text-align:right; }
footer { color: var(--muted); font-size:.8rem; margin-top:2rem; }
@media (max-width: 800px) {
  .layout { flex-direction: column; }
  nav.side { width:100%; height:auto; position:static; }
}
"""

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title} · Redis Doctor docs</title>
<link rel="stylesheet" href="{css_href}" />
</head>
<body>
<div class="layout">
<nav class="side">
<div class="brand">Redis Doctor</div>
<span class="tag">documentation</span>
{nav}
</nav>
<main><article>
{body}
{pager}
<footer>Built from docs/md by docs/tools/converter.py</footer>
</article></main>
</div>
</body>
</html>
"""


# --- helpers --------------------------------------------------------------

def slugify(text: str) -> str:
    text = re.sub(r"`", "", text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text


def rewrite_link(url: str) -> str:
    if re.match(r"^[a-z]+://", url) or url.startswith("#") or url.startswith("mailto:"):
        return url
    # split anchor
    base, sep, anchor = url.partition("#")
    if base.endswith(".md"):
        base = base[:-3] + ".html"
    return base + (sep + anchor if sep else "")


def inline(text: str) -> str:
    """Inline markdown -> HTML. Code spans are protected from other rules."""
    placeholders: list[str] = []

    def stash(htmlspan: str) -> str:
        placeholders.append(htmlspan)
        return f"\x00{len(placeholders) - 1}\x00"

    # 1. code spans (escape contents, protect from further processing)
    def code_sub(m: re.Match) -> str:
        return stash(f"<code>{html.escape(m.group(1))}</code>")

    text = re.sub(r"`([^`]+)`", code_sub, text)

    # 2. escape the rest
    text = html.escape(text)

    # 3. links [text](url)
    def link_sub(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        return f'<a href="{html.escape(rewrite_link(url), quote=True)}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_sub, text)

    # 4. bold then italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)

    # restore code spans
    text = re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)
    return text


def is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", line))


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


# --- block parser ---------------------------------------------------------

def render_body(md: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Return (html, headings) where headings is [(level, text, slug)]."""
    lines = md.split("\n")
    out: list[str] = []
    headings: list[tuple[int, str, str]] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # fenced code
        if line.startswith("```"):
            lang = line[3:].strip()
            code: list[str] = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code))}</code></pre>")
            continue

        # heading
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            slug = slugify(text)
            headings.append((level, text, slug))
            inner = inline(text)
            anchor = f'<a class="anchor" href="#{slug}">#</a>'
            out.append(f'<h{level} id="{slug}">{inner}{anchor}</h{level}>')
            i += 1
            continue

        # horizontal rule
        if re.match(r"^\s*([-*_])\1\1+\s*$", line):
            out.append("<hr />")
            i += 1
            continue

        # table
        if line.strip().startswith("|") and i + 1 < n and is_table_sep(lines[i + 1]):
            header = split_row(line)
            rows: list[list[str]] = []
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            thead = "".join(f"<th>{inline(c)}</th>" for c in header)
            body_rows = []
            for r in rows:
                cells = "".join(f"<td>{inline(c)}</td>" for c in r)
                body_rows.append(f"<tr>{cells}</tr>")
            out.append(
                f"<table><thead><tr>{thead}</tr></thead>"
                f"<tbody>{''.join(body_rows)}</tbody></table>"
            )
            continue

        # blockquote
        if line.startswith(">"):
            quote: list[str] = []
            while i < n and lines[i].startswith(">"):
                quote.append(lines[i][1:].lstrip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue

        # list (unordered or ordered), with one level of nesting
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            block: list[str] = []
            while i < n and (re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) or
                             (lines[i].strip() == "" and i + 1 < n and
                              re.match(r"^\s+([-*]|\d+\.)\s+", lines[i + 1]))):
                if lines[i].strip() == "":
                    i += 1
                    continue
                block.append(lines[i])
                i += 1
            out.append(render_list(block))
            continue

        # blank line
        if line.strip() == "":
            i += 1
            continue

        # paragraph: gather until blank or a block starter
        para: list[str] = []
        while i < n and lines[i].strip() != "" and not _starts_block(lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out), headings


def _starts_block(line: str) -> bool:
    return (
        line.startswith("```")
        or bool(re.match(r"^#{1,6}\s", line))
        or line.strip().startswith("|")
        or line.startswith(">")
        or bool(re.match(r"^\s*([-*]|\d+\.)\s+", line))
        or bool(re.match(r"^\s*([-*_])\1\1+\s*$", line))
    )


def render_list(block: list[str]) -> str:
    """Render a (possibly one-level nested) list block."""
    root_ordered = bool(re.match(r"^\s*\d+\.", block[0]))
    root_tag = "ol" if root_ordered else "ul"
    html_parts = [f"<{root_tag}>"]
    sub: list[str] = []

    def flush_sub() -> None:
        if sub:
            html_parts.append(render_list([s[2:] for s in sub]))
            sub.clear()

    for line in block:
        indent = len(line) - len(line.lstrip())
        if indent >= 2:
            sub.append(line)
            continue
        flush_sub()
        content = re.sub(r"^\s*([-*]|\d+\.)\s+", "", line)
        html_parts.append(f"<li>{inline(content)}</li>")
    flush_sub()
    html_parts.append(f"</{root_tag}>")
    return "".join(html_parts)


# --- site assembly --------------------------------------------------------

def discover(src: Path) -> list[str]:
    found = sorted(str(p.relative_to(src).as_posix()) for p in src.rglob("*.md"))
    ordered: list[str] = []
    for _section, paths in NAV:
        for p in paths:
            if p in found and p not in ordered:
                ordered.append(p)
    for p in found:
        if p not in ordered:
            ordered.append(p)
    return ordered


def page_title(md: str, fallback: str) -> str:
    for line in md.split("\n"):
        m = re.match(r"^#\s+(.*)$", line)
        if m:
            return m.group(1).strip()
    return fallback


def rel_href(from_rel: str, to_rel_html: str) -> str:
    from_dir = Path(from_rel).parent
    rel = Path(to_rel_html)
    import os

    return os.path.relpath(rel, from_dir) if str(from_dir) != "." else to_rel_html


def build_nav(current_rel: str, titles: dict[str, str]) -> str:
    cur_html = current_rel[:-3] + ".html"
    parts: list[str] = []
    listed = {p for _s, ps in NAV for p in ps}
    extra = [p for p in titles if p not in listed]
    sections = list(NAV)
    if extra:
        sections = sections + [("More", extra)]
    for title, paths in sections:
        items = [p for p in paths if p in titles]
        if not items:
            continue
        parts.append(f'<div class="sect">{html.escape(title)}</div><ul>')
        for p in items:
            target_html = p[:-3] + ".html"
            href = rel_href(current_rel, target_html)
            active = " class=\"active\"" if target_html == cur_html else ""
            parts.append(f'<li><a{active} href="{href}">{html.escape(titles[p])}</a></li>')
        parts.append("</ul>")
    return "\n".join(parts)


def build_pager(current_rel: str, order: list[str], titles: dict[str, str]) -> str:
    if current_rel not in order:
        return ""
    idx = order.index(current_rel)
    bits = ['<div class="pager">']
    if idx > 0:
        prev = order[idx - 1]
        href = rel_href(current_rel, prev[:-3] + ".html")
        bits.append(f'<a class="prev" href="{href}">← {html.escape(titles[prev])}</a>')
    if idx < len(order) - 1:
        nxt = order[idx + 1]
        href = rel_href(current_rel, nxt[:-3] + ".html")
        bits.append(f'<a class="next" href="{href}">{html.escape(titles[nxt])} →</a>')
    bits.append("</div>")
    return "\n".join(bits)


def build(src: Path, out: Path, clean: bool = False) -> int:
    if not src.is_dir():
        raise SystemExit(f"source directory not found: {src}")
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    order = discover(src)
    titles: dict[str, str] = {}
    sources: dict[str, str] = {}
    for rel in order:
        text = (src / rel).read_text(encoding="utf-8")
        sources[rel] = text
        titles[rel] = page_title(text, Path(rel).stem)

    (out / "assets").mkdir(exist_ok=True)
    (out / "assets" / "styles.css").write_text(CSS, encoding="utf-8")

    for rel in order:
        body, _headings = render_body(sources[rel])
        nav = build_nav(rel, titles)
        pager = build_pager(rel, order, titles)
        css_href = rel_href(rel, "assets/styles.css")
        html_doc = PAGE.format(
            title=html.escape(titles[rel]),
            css_href=css_href,
            nav=nav,
            body=body,
            pager=pager,
        )
        dest = out / (rel[:-3] + ".html")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html_doc, encoding="utf-8")

    print(f"Built {len(order)} pages into {out}")
    return len(order)


def main() -> None:
    here = Path(__file__).resolve().parent
    docs = here.parent  # docs/
    ap = argparse.ArgumentParser(description="Build HTML docs from Markdown.")
    ap.add_argument("--src", default=str(docs / "md"), help="source markdown dir")
    ap.add_argument("--out", default=str(docs / "html"), help="output html dir")
    ap.add_argument("--clean", action="store_true", help="remove output dir first")
    args = ap.parse_args()
    build(Path(args.src), Path(args.out), clean=args.clean)


if __name__ == "__main__":
    main()

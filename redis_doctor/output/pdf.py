"""PDF export. Renders the markdown report to HTML then PDF via WeasyPrint."""

from __future__ import annotations

import re

from ..models.report import Report
from .markdown import render_markdown


def _markdown_to_html(md: str) -> str:
    """Minimal markdown -> HTML (headings, lists, code fences, bold)."""
    lines = md.splitlines()
    html: list[str] = []
    in_code = False
    in_list = False
    for line in lines:
        if line.startswith("```"):
            if in_code:
                html.append("</pre>")
                in_code = False
            else:
                html.append("<pre>")
                in_code = True
            continue
        if in_code:
            html.append(_escape(line))
            continue
        if line.startswith("### "):
            html.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            html.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            html.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{_inline(line[2:])}</li>")
            continue
        elif line.strip() == "":
            html.append("<br/>")
        else:
            html.append(f"<p>{_inline(line)}</p>")
        if in_list and not line.startswith("- "):
            html.insert(-1, "</ul>")
            in_list = False
    if in_list:
        html.append("</ul>")
    return "\n".join(html)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


_STYLE = """
body { font-family: sans-serif; font-size: 11px; color: #222; }
h1 { color: #b00; } h2 { border-bottom: 1px solid #ccc; }
pre { background: #f4f4f4; padding: 6px; font-size: 9px; white-space: pre-wrap; }
code { background: #f4f4f4; padding: 1px 3px; }
"""


def render_pdf(report: Report, path: str) -> None:
    import weasyprint

    md = render_markdown(report)
    html = f"<html><head><style>{_STYLE}</style></head><body>{_markdown_to_html(md)}</body></html>"
    weasyprint.HTML(string=html).write_pdf(path)

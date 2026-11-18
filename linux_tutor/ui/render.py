"""Turn lesson Markdown into HTML for the lecture screen.

Supports normal Markdown (headings, lists, tables, fenced code) plus call-out boxes::

    :::note | :::tip | :::warning | :::important
    text (Markdown)
    :::
"""
from __future__ import annotations

import html
import re
from urllib.parse import quote

import markdown

from .theme import colors

_BLOCK = re.compile(r"^:::(note|tip|warning|important)\s*\n(.*?)^:::\s*$", re.M | re.S)
_TITLES = {"note": "Note", "tip": "Tip", "warning": "Warning", "important": "Important"}
_ICONS = {"note": "i", "tip": "*", "warning": "!", "important": "!"}


def md(text: str) -> str:
    return markdown.markdown(text or "", extensions=["fenced_code", "tables", "sane_lists"])


def render_markdown(text: str, theme: str) -> str:
    c = colors(theme)
    bgs = {"note": c["note_bg"], "tip": c["tip_bg"], "warning": c["warn_bg"], "important": c["warn_bg"]}
    fgs = {"note": c["accent"], "tip": c["good"], "warning": c["warn"], "important": c["bad"]}
    parts = []
    pos = 0
    for m in _BLOCK.finditer(text or ""):
        parts.append(md(text[pos:m.start()]))
        kind, body = m.group(1), m.group(2)
        parts.append(
            f'<table width="100%" cellpadding="8" cellspacing="0" style="margin: 8px 0px;" '
            f'bgcolor="{bgs[kind]}"><tr><td>'
            f'<span style="color:{fgs[kind]}; font-weight:bold;">[{_ICONS[kind]}] {_TITLES[kind]}</span>'
            f'{md(body)}</td></tr></table>')
        pos = m.end()
    parts.append(md((text or "")[pos:]))
    return "\n".join(parts)


def examples_html(examples: list[dict], theme: str) -> str:
    if not examples:
        return ""
    c = colors(theme)
    rows = []
    for ex in examples:
        cmd = ex.get("command", "")
        out = ex.get("output", "")
        rows.append(
            f'<tr><td valign="top"><code>$ {html.escape(cmd)}</code>'
            + (f'<pre>{html.escape(out)}</pre>' if out else "")
            + f'<br><span style="color:{c["muted"]}">{html.escape(ex.get("explanation", ""))}</span></td>'
            f'<td valign="top" align="right"><a href="tutor-try:{quote(cmd)}">Try&nbsp;it&nbsp;&#9654;</a></td></tr>')
    return (f'<h3>Examples</h3><table width="100%" cellspacing="0" cellpadding="6" '
            f'bgcolor="{c["alt"]}">' + "".join(rows) + "</table>")


def page(body: str, css: str) -> str:
    return f"<html><head><style>{css}</style></head><body>{body}</body></html>"

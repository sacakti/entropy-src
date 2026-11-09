"""
Markdown documents as knowledge base entries.

Descriptions are already Markdown's common forms (lib/tasks/markup.py), so most of a
Markdown file reads as it is. This turns what descriptions write differently into their
forms: __bold__ and _italic_, <u>underline</u>, setext headings, six heading levels,
"1)" lists, block quotes, and links (kept as their text and address). Images that point
elsewhere are kept as text, as nothing is fetched. HTML tags are dropped.
"""

from __future__ import annotations

import re
from typing import List, Tuple

MAX_MARKDOWN_BYTES = 5 * 1024 * 1024

_FENCE = re.compile(r"^\s*(```|~~~)")
_SETEXT = re.compile(r"^\s*(=+|-+)\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_ATTACHMENT = re.compile(r"!\[[^\]\n]*\]\(attachment:\d+\)")


def _inline(text: str) -> str:
    # Images first (the "!" belongs to them), then links.
    text = re.sub(
        r"!\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        lambda m: f"{m.group(1) or 'image'} ({m.group(2)})",
        text,
    )
    text = re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", r"\1 (\2)", text)
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)
    text = re.sub(r"<u>(.+?)</u>", r"++\1++", text, flags=re.IGNORECASE)
    text = re.sub(r"<(b|strong)>(.+?)</\1>", r"**\2**", text, flags=re.IGNORECASE)
    text = re.sub(r"<(i|em)>(.+?)</\1>", r"*\2*", text, flags=re.IGNORECASE)
    text = re.sub(r"<(s|del|strike)>(.+?)</\1>", r"~~\2~~", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    # __bold__ and _italic_, only at word edges so snake_case stays as it is.
    text = re.sub(r"(?<![\w\\])__(?=\S)(.+?)(?<=\S)__(?!\w)", r"**\1**", text)
    text = re.sub(r"(?<![\w\\_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])", r"*\1*", text)
    return text


def convert_markdown(source: str, fallback_title: str) -> Tuple[str, str]:
    """The title (the first top heading, else `fallback_title`) and the description."""

    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[str] = []
    in_code = False
    for index, raw in enumerate(lines):
        if _FENCE.match(raw):
            in_code = not in_code
            out.append(re.sub(r"~~~", "```", raw, count=1))
            continue
        if in_code:
            out.append(raw)
            continue
        line = raw.rstrip()
        following = lines[index + 1] if index + 1 < len(lines) else ""
        # Setext headings: a line underlined with === or ---.
        if (
            line.strip()
            and _SETEXT.match(following)
            and not re.match(r"^\s*([-*+]|\d+[.)])\s", line)
        ):
            level = 1 if following.strip().startswith("=") else 2
            out.append(f"{'#' * level} {_inline(line.strip())}")
            lines[index + 1] = ""
            continue
        if _RULE.match(line):
            out.append("")
            continue
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            out.append(f"{'#' * min(5, len(heading.group(1)))} {_inline(heading.group(2))}")
            continue
        # Block quotes read as their text.
        line = re.sub(r"^\s{0,3}(>\s?)+", "", line)
        line = re.sub(r"^(\s*)(\d+)\)(\s)", r"\1\2.\3", line)
        line = re.sub(r"^(\s*)[*+](\s)", r"\1-\2", line)
        out.append(line if _ATTACHMENT.search(line) else _inline(line))

    text = "\n".join(out).strip()
    title = fallback_title
    first = re.match(r"^# (.+)\n?", text)
    if first:
        title = first.group(1).strip()
        text = text[first.end() :].lstrip("\n")
    return title[:200] or fallback_title[:200], re.sub(r"\n{3,}", "\n\n", text)

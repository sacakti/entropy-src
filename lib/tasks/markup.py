"""
What a task description can hold, read from its plain text (Markdown's common forms): headings,
paragraphs, lists, checklists, tables, code blocks and attachments in place, with bold, italic,
underline (++text++, Markdown has none), strikethrough and `code` inside. Headings go from
# to #####. The browser reads it the same way
(frontend/src/features/tools/tasks/markup.ts): change both together.
tests/tools/test_task_markup.py holds them to the same cases.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^(#{1,5})\s+(.+?)\s*$")
_LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(?:\[([ xX])\](?:\s+|$))?(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
_CELL_BREAK = re.compile(r"(?<!\\)\|")
ATTACHMENT = re.compile(r"!\[([^\]\n]*)\]\(attachment:(\d+)\)")
_INLINE = re.compile(
    r"\\([\\*~`|+#.-])|`([^`\n]+)`"
    r"|\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*"
    r"|\*\*(?=\S)(.+?)(?<=\S)\*\*"
    r"|~~(?=\S)(.+?)(?<=\S)~~"
    r"|\+\+(?=\S)(.+?)(?<=\S)\+\+"
    r"|\*(?=[^\s*])(.+?)(?<=[^\s*])\*"
)


def table_cells(line: str) -> List[str]:
    inner = re.sub(r"(?<!\\)\|$", "", line.strip().removeprefix("|"))
    return [cell.strip().replace("\\|", "|") for cell in _CELL_BREAK.split(inner)]


def _is_table_start(line: str, following: Optional[str]) -> bool:
    return (
        "|" in line
        and following is not None
        and "|" in following
        and "-" in following
        and _TABLE_RULE.match(following) is not None
    )


def parse_blocks(source: str) -> List[Dict[str, Any]]:
    """The description's blocks, in order."""

    lines = source.replace("\r\n", "\n").split("\n")
    blocks: List[Dict[str, Any]] = []
    paragraph: List[str] = []

    def flush() -> None:
        text = "\n".join(paragraph).strip()
        if text:
            blocks.append({"type": "paragraph", "text": text})
        paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]

        if _FENCE.match(line):
            flush()
            code: List[str] = []
            index += 1
            while index < len(lines) and not _FENCE.match(lines[index]):
                code.append(lines[index])
                index += 1
            blocks.append({"type": "code", "text": "\n".join(code)})
            index += 1
            continue

        if not line.strip():
            flush()
            index += 1
            continue

        references = list(ATTACHMENT.finditer(line))
        if references:
            flush()
            position = 0
            for match in references:
                before = line[position : match.start()].strip()
                if before:
                    blocks.append({"type": "paragraph", "text": before})
                blocks.append({"type": "attachment", "id": int(match[2]), "caption": match[1]})
                position = match.end()
            after = line[position:].strip()
            if after:
                blocks.append({"type": "paragraph", "text": after})
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush()
            blocks.append({"type": "heading", "level": len(heading[1]), "text": heading[2]})
            index += 1
            continue

        if _is_table_start(line, lines[index + 1] if index + 1 < len(lines) else None):
            flush()
            header = table_cells(line)
            rows: List[List[str]] = []
            index += 2
            while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                cells = table_cells(lines[index])
                rows.append(
                    [cells[column] if column < len(cells) else "" for column in range(len(header))]
                )
                index += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        item = _LIST_ITEM.match(line)
        if item:
            flush()
            ordered = item[2].endswith(".")
            start = int(item[2][:-1]) if ordered else 1
            items: List[Dict[str, Any]] = []
            while index < len(lines):
                current = _LIST_ITEM.match(lines[index])
                if not current or current[2].endswith(".") != ordered:
                    break
                items.append(
                    {
                        "text": current[4].strip(),
                        "checked": None if current[3] is None else current[3] != " ",
                        "indent": len(current[1].replace("\t", "  ")) // 2,
                        "line": index,
                    }
                )
                index += 1
            blocks.append({"type": "list", "ordered": ordered, "start": start, "items": items})
            continue

        paragraph.append(line)
        index += 1
    flush()
    return blocks


def parse_inline(text: str, style: Optional[Dict[str, bool]] = None) -> List[Dict[str, Any]]:
    """
    The text in runs of one style: {"text", and any of "bold", "italic", "underline",
    "strike", "code"}.
    """

    style = style or {}
    runs: List[Dict[str, Any]] = []
    position = 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            runs.append({**style, "text": text[position : match.start()]})
        escaped, code, both, bold, strike, underline, italic = match.groups()
        if escaped is not None:
            runs.append({**style, "text": escaped})
        elif code is not None:
            runs.append({**style, "text": code, "code": True})
        elif both is not None:
            runs.extend(parse_inline(both, {**style, "bold": True, "italic": True}))
        elif bold is not None:
            runs.extend(parse_inline(bold, {**style, "bold": True}))
        elif strike is not None:
            runs.extend(parse_inline(strike, {**style, "strike": True}))
        elif underline is not None:
            runs.extend(parse_inline(underline, {**style, "underline": True}))
        elif italic is not None:
            runs.extend(parse_inline(italic, {**style, "italic": True}))
        position = match.end()
    if position < len(text):
        runs.append({**style, "text": text[position:]})
    return runs


def _inline_text(text: str) -> str:
    return "".join(run["text"] for run in parse_inline(text))


def plain_text(source: str) -> str:
    """The description without its formatting, for notifications and e-mail."""

    parts: List[str] = []
    for block in parse_blocks(source):
        if block["type"] in ("heading", "paragraph"):
            parts.append(_inline_text(block["text"]))
        elif block["type"] == "code":
            parts.append(block["text"])
        elif block["type"] == "list":
            for item in block["items"]:
                mark = "" if item["checked"] is None else "[x] " if item["checked"] else "[ ] "
                parts.append(f"{mark}{_inline_text(item['text'])}")
        elif block["type"] == "table":
            for row in [block["header"], *block["rows"]]:
                parts.append(" | ".join(_inline_text(cell) for cell in row))
    return "\n".join(parts)

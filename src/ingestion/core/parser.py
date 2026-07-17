"""
ingestion/parser.py
===================
Markdown structural parser.

Converts raw Markdown text into a list of typed Block objects
that preserve reading order, heading hierarchy, and table structure.

Block types
-----------
HeadingBlock   → # H1 / ## H2 / …
ParagraphBlock → any prose paragraph
TableBlock     → | col | col | …
ListBlock      → - item / 1. item
CodeBlock      → ``` … ```

The parser is intentionally simple (regex-based, no AST library)
so it runs fast on thousands of files with no extra dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Block types
# ─────────────────────────────────────────────────────────────────────────────

class BlockType(Enum):
    HEADING   = auto()
    PARAGRAPH = auto()
    TABLE     = auto()
    LIST      = auto()
    CODE      = auto()
    DIVIDER   = auto()


@dataclass
class Block:
    """Base class — all block types inherit from this."""
    type: BlockType
    text: str            # Raw markdown text of this block
    position: int        # 0-indexed block order in document

    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class HeadingBlock(Block):
    level: int = 1       # 1–6
    heading_text: str = ""  # Text without #


@dataclass
class TableBlock(Block):
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "headers":    self.headers,
            "rows":       self.rows,
            "row_count":  len(self.rows),
            "col_count":  len(self.headers),
            "raw":        self.text,
        }


@dataclass
class ListBlock(Block):
    items: list[str] = field(default_factory=list)
    ordered: bool = False


@dataclass
class CodeBlock(Block):
    language: str = ""


@dataclass
class ParagraphBlock(Block):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

_HEADING_RE    = re.compile(r"^(#{1,6})\s+(.+)$")
_TABLE_ROW_RE  = re.compile(r"^\s*\|.+\|\s*$")
_TABLE_SEP_RE  = re.compile(r"^\s*\|[\s|:\-]+\|\s*$")
_OL_ITEM_RE    = re.compile(r"^\s*\d+[.)]\s+")
_UL_ITEM_RE    = re.compile(r"^\s*[-*+]\s+")
_CODE_FENCE_RE = re.compile(r"^```(\w*)$")
_DIVIDER_RE    = re.compile(r"^[-*_]{3,}$")
_BLANK_RE      = re.compile(r"^\s*$")


# ─────────────────────────────────────────────────────────────────────────────
# Table parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_table_rows(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Given raw table lines (including separator), return (headers, data_rows).
    """
    def _split_row(line: str) -> list[str]:
        # Strip leading/trailing pipes and split
        cells = line.strip().strip("|").split("|")
        return [c.strip() for c in cells]

    data_lines = [l for l in lines if not _TABLE_SEP_RE.match(l)]
    if not data_lines:
        return [], []

    headers = _split_row(data_lines[0])
    rows = [_split_row(l) for l in data_lines[1:]]
    return headers, rows


# ─────────────────────────────────────────────────────────────────────────────
# Main parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_markdown(text: str) -> list[Block]:
    """
    Parse Markdown into an ordered list of Block objects.

    Algorithm:
    1. Split into physical lines
    2. Walk line-by-line accumulating into the current block type
    3. On type change, flush the current block and start a new one
    """
    lines = text.splitlines()
    blocks: list[Block] = []
    pos = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Code fence ────────────────────────────────────────────────────
        m = _CODE_FENCE_RE.match(line)
        if m:
            lang = m.group(1)
            code_lines = []
            i += 1
            while i < len(lines) and not _CODE_FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            raw = "```" + lang + "\n" + "\n".join(code_lines) + "\n```"
            blocks.append(CodeBlock(
                type=BlockType.CODE, text=raw,
                position=pos, language=lang,
            ))
            pos += 1
            i += 1  # skip closing fence
            continue

        # ── Heading ───────────────────────────────────────────────────────
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            blocks.append(HeadingBlock(
                type=BlockType.HEADING, text=line,
                position=pos, level=level,
                heading_text=heading_text,
            ))
            pos += 1
            i += 1
            continue

        # ── Divider ───────────────────────────────────────────────────────
        if _DIVIDER_RE.match(line):
            blocks.append(Block(type=BlockType.DIVIDER, text=line, position=pos))
            pos += 1
            i += 1
            continue

        # ── Table ─────────────────────────────────────────────────────────
        if _TABLE_ROW_RE.match(line):
            table_lines = []
            while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
                table_lines.append(lines[i])
                i += 1
            raw = "\n".join(table_lines)
            headers, rows = _parse_table_rows(table_lines)
            blocks.append(TableBlock(
                type=BlockType.TABLE, text=raw,
                position=pos, headers=headers, rows=rows,
            ))
            pos += 1
            continue

        # ── List ──────────────────────────────────────────────────────────
        if _UL_ITEM_RE.match(line) or _OL_ITEM_RE.match(line):
            ordered = bool(_OL_ITEM_RE.match(line))
            list_lines = []
            while i < len(lines) and (
                _UL_ITEM_RE.match(lines[i])
                or _OL_ITEM_RE.match(lines[i])
                or (list_lines and lines[i].startswith("  "))  # continuation indent
            ):
                list_lines.append(lines[i])
                i += 1
            raw = "\n".join(list_lines)
            items = [
                re.sub(r"^\s*[-*+\d.]+\s+", "", l)
                for l in list_lines
                if _UL_ITEM_RE.match(l) or _OL_ITEM_RE.match(l)
            ]
            blocks.append(ListBlock(
                type=BlockType.LIST, text=raw,
                position=pos, items=items, ordered=ordered,
            ))
            pos += 1
            continue

        # ── Blank line ────────────────────────────────────────────────────
        if _BLANK_RE.match(line):
            i += 1
            continue

        # ── Paragraph (accumulate until blank/heading/table/list) ─────────
        para_lines = []
        while i < len(lines):
            l = lines[i]
            if (
                _BLANK_RE.match(l)
                or _HEADING_RE.match(l)
                or _TABLE_ROW_RE.match(l)
                or _UL_ITEM_RE.match(l)
                or _OL_ITEM_RE.match(l)
                or _CODE_FENCE_RE.match(l)
                or _DIVIDER_RE.match(l)
            ):
                break
            para_lines.append(l)
            i += 1

        if para_lines:
            raw = "\n".join(para_lines)
            blocks.append(ParagraphBlock(
                type=BlockType.PARAGRAPH, text=raw, position=pos,
            ))
            pos += 1

    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# Convenience extractors
# ─────────────────────────────────────────────────────────────────────────────

def extract_headings(blocks: list[Block]) -> list[dict[str, Any]]:
    """Return ordered list of {level, text} for all headings."""
    return [
        {"level": b.level, "text": b.heading_text}  # type: ignore[attr-defined]
        for b in blocks
        if b.type == BlockType.HEADING
    ]


def extract_tables(blocks: list[Block]) -> list[dict[str, Any]]:
    """Return all parsed tables as dicts."""
    return [
        b.to_dict()  # type: ignore[attr-defined]
        for b in blocks
        if b.type == BlockType.TABLE
    ]


def extract_title(blocks: list[Block], fallback: str = "") -> str:
    """Return text of first H1, or fallback."""
    for b in blocks:
        if b.type == BlockType.HEADING:
            hb: HeadingBlock = b  # type: ignore[assignment]
            if hb.level == 1:
                return hb.heading_text
    # Try first heading of any level
    for b in blocks:
        if b.type == BlockType.HEADING:
            hb = b  # type: ignore[assignment]
            return hb.heading_text
    return fallback


def blocks_to_text(blocks: list[Block]) -> str:
    """Reconstruct clean plain text from blocks (for word-count etc.)."""
    parts = []
    for b in blocks:
        if b.type not in (BlockType.DIVIDER,):
            parts.append(b.text)
    return "\n\n".join(parts)

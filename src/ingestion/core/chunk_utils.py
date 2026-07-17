from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

import tiktoken


_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    if not text.strip():
        return 0
    return len(_TOKENIZER.encode(text))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_table_block(block: dict[str, Any]) -> bool:
    return bool(block.get("type") == "table")


def is_list_block(block: dict[str, Any]) -> bool:
    return bool(block.get("type") == "list")


def block_text(block: dict[str, Any]) -> str:
    return (block.get("text") or "").strip()


def collect_section_blocks(node: dict[str, Any], *, prefix: list[str] | None = None) -> list[tuple[list[str], dict[str, Any]]]:
    prefix = list(prefix or [])
    results: list[tuple[list[str], dict[str, Any]]] = []
    if node.get("type") == "heading":
        prefix = prefix + [node.get("title", "")]
    if node.get("type") in {"paragraph", "list", "table", "blockquote", "code_block"}:
        results.append((prefix, node))
    for child in node.get("children", []):
        results.extend(collect_section_blocks(child, prefix=prefix))
    return results

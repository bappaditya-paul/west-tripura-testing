from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from markdown_it import MarkdownIt

from .config import DEFAULT_CONFIG
from .utils import parse_frontmatter, safe_json_dump


@dataclass(slots=True)
class ParseNode:
    """Tree node used to represent the parsed document structure."""

    type: str
    title: str = ""
    level: int = 0
    text: str = ""
    children: list["ParseNode"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "title": self.title,
            "level": self.level,
            "text": self.text,
            "metadata": self.metadata,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(slots=True)
class ParsedDocument:
    document_id: str
    source_path: str
    title: str
    tree: ParseNode
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "title": self.title,
            "metadata": self.metadata,
            "tree": self.tree.to_dict(),
        }


class MarkdownParser:
    """Parse cleaned markdown into a heading-aware tree of structural nodes."""

    def __init__(self) -> None:
        self._parser = MarkdownIt("commonmark")

    def parse_document(self, markdown: str, *, metadata: Mapping[str, Any] | None = None, source_path: str | None = None) -> ParsedDocument:
        frontmatter, body = parse_frontmatter(markdown)
        body_text = body.strip() if body else markdown.strip()
        metadata = dict(metadata or {})
        metadata.update({k: v for k, v in frontmatter.items() if v})
        source_path = source_path or metadata.get("source_path") or "document.md"
        title = self._infer_title(body_text, metadata)
        document_id = self._make_document_id(source_path, metadata)

        root = ParseNode(type="document", title="Document", metadata={"source_path": source_path})
        heading_stack: list[ParseNode] = [root]
        pending_heading: tuple[int, str] | None = None
        current_list: ParseNode | None = None
        body_lines = body_text.splitlines()

        tokens = self._parser.parse(body_text)
        for index, token in enumerate(tokens):
            if token.type == "heading_open":
                pending_heading = (self._heading_level(token), "")
                continue

            if token.type == "inline" and pending_heading is not None and index > 0 and tokens[index - 1].type == "heading_open":
                level, _ = pending_heading
                title_text = (token.content or "").strip()
                while len(heading_stack) > 1 and heading_stack[-1].type == "heading" and heading_stack[-1].level >= level:
                    heading_stack.pop()
                parent = heading_stack[-1]
                heading_node = ParseNode(type="heading", title=title_text, level=level, text=title_text)
                heading_node.metadata["heading_chain"] = [
                    node.title for node in heading_stack[1:] if node.type == "heading"
                ] + [title_text]
                parent.children.append(heading_node)
                heading_stack.append(heading_node)
                pending_heading = None
                current_list = None
                continue

            if token.type in {"bullet_list_open", "ordered_list_open"}:
                list_node = ParseNode(type="list", title="", metadata={"ordered": token.type == "ordered_list_open", "items": []})
                heading_stack[-1].children.append(list_node)
                current_list = list_node
                continue

            if token.type == "list_item_open":
                if current_list is None:
                    current_list = ParseNode(type="list", title="", metadata={"ordered": False, "items": []})
                    heading_stack[-1].children.append(current_list)
                item_text = self._extract_item_text(tokens, index)
                current_list.metadata.setdefault("items", []).append(item_text)
                continue

            if token.type in {"bullet_list_close", "ordered_list_close"}:
                current_list = None
                continue

            if token.type == "paragraph_open":
                paragraph_text, links, images = self._extract_paragraph(tokens, index)
                if paragraph_text.strip():
                    paragraph_node = ParseNode(type="paragraph", text=paragraph_text)
                    paragraph_node.metadata["links"] = links
                    paragraph_node.metadata["images"] = images
                    heading_stack[-1].children.append(paragraph_node)
                continue

            if token.type == "fence":
                code_node = ParseNode(type="code_block", text=token.content or "")
                code_node.metadata["info"] = token.info or ""
                heading_stack[-1].children.append(code_node)
                continue

            if token.type == "blockquote_open":
                blockquote_text = self._extract_blockquote_text(tokens, index)
                if blockquote_text.strip():
                    blockquote_node = ParseNode(type="blockquote", text=blockquote_text)
                    heading_stack[-1].children.append(blockquote_node)
                continue

            if token.type == "hr":
                heading_stack[-1].children.append(ParseNode(type="horizontal_rule", text="---"))
                continue

            if token.type == "image":
                image_node = ParseNode(type="image", title=token.attrGet("alt") or "")
                image_node.metadata["src"] = token.attrGet("src") or ""
                heading_stack[-1].children.append(image_node)
                continue

            if token.type == "table_open":
                table_lines = self._read_table_lines(token, body_lines)
                table_node = ParseNode(type="table", text="\n".join(table_lines))
                table_node.metadata["rows"] = self._parse_table_rows(table_lines)
                heading_stack[-1].children.append(table_node)
                continue

        if not root.children and body_text:
            paragraph_node = ParseNode(type="paragraph", text=body_text)
            root.children.append(paragraph_node)

        return ParsedDocument(
            document_id=document_id,
            source_path=source_path,
            title=title,
            tree=root,
            metadata=metadata,
        )

    def _heading_level(self, token: Any) -> int:
        tag = getattr(token, "tag", "")
        if tag.startswith("h") and len(tag) > 1:
            try:
                return int(tag[1:])
            except ValueError:
                return 1
        return 1

    def _infer_title(self, body_text: str, metadata: Mapping[str, Any]) -> str:
        for line in body_text.splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return str(metadata.get("title") or metadata.get("source_path") or "Untitled Document")

    def _make_document_id(self, source_path: str, metadata: Mapping[str, Any]) -> str:
        candidate = str(metadata.get("document_id") or metadata.get("id") or source_path or "document")
        stem = Path(candidate).stem.replace(".", "_") if candidate else "document"
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_") or "document"
        return f"{slug}_md"

    def _extract_item_text(self, tokens: list[Any], start_index: int) -> str:
        for index in range(start_index + 1, len(tokens)):
            token = tokens[index]
            if token.type == "inline":
                return (token.content or "").strip()
            if token.type == "list_item_close":
                break
        return ""

    def _extract_paragraph(self, tokens: list[Any], start_index: int) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        text = ""
        links: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        for index in range(start_index + 1, len(tokens)):
            token = tokens[index]
            if token.type == "inline":
                text = (token.content or "").strip()
                if getattr(token, "children", None):
                    for child in token.children:
                        if child.type == "link_open":
                            links.append({"href": child.attrGet("href") or "", "text": ""})
                        elif child.type == "image":
                            images.append({"src": child.attrGet("src") or "", "alt": child.attrGet("alt") or ""})
                break
            if token.type == "paragraph_close":
                break
        return text, links, images

    def _extract_blockquote_text(self, tokens: list[Any], start_index: int) -> str:
        text = ""
        for index in range(start_index + 1, len(tokens)):
            token = tokens[index]
            if token.type == "inline":
                text = (token.content or "").strip()
                break
            if token.type == "blockquote_close":
                break
        return text

    def _read_table_lines(self, token: Any, body_lines: list[str]) -> list[str]:
        if not getattr(token, "map", None):
            return []
        start_line, end_line = token.map
        lines = body_lines[start_line:end_line]
        return [line.rstrip() for line in lines if line.rstrip()]

    def _parse_table_rows(self, table_lines: list[str]) -> list[list[str]]:
        if not table_lines:
            return []
        rows = []
        for line in table_lines:
            if not line.strip():
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(cells)
        return rows


def parse_markdown_document(markdown: str, *, metadata: Mapping[str, Any] | None = None, source_path: str | None = None) -> ParsedDocument:
    return MarkdownParser().parse_document(markdown, metadata=metadata, source_path=source_path)


def parse_processed_documents(input_dir: str | Path | None = None, output_dir: str | Path | None = None) -> dict[str, Any]:
    input_dir = Path(input_dir or DEFAULT_CONFIG.processed_docs_dir)
    output_dir = Path(output_dir or DEFAULT_CONFIG.processed_docs_dir.parent / "parsed_documents")
    output_dir.mkdir(parents=True, exist_ok=True)

    markdown_files = sorted(input_dir.glob("*.md"))
    written = 0
    for markdown_path in markdown_files:
        meta_path = markdown_path.with_suffix(".json")
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        parsed = parse_markdown_document(
            markdown_path.read_text(encoding="utf-8"),
            metadata=metadata,
            source_path=str(markdown_path.name),
        )
        out_path = output_dir / f"{parsed.document_id}.json"
        safe_json_dump(parsed.to_dict(), out_path)
        written += 1

    summary_path = output_dir / "index.json"
    safe_json_dump({"written": written, "input_dir": str(input_dir), "output_dir": str(output_dir)}, summary_path)
    return {"written": written, "input_dir": str(input_dir), "output_dir": str(output_dir)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse cleaned markdown documents into heading-aware document trees")
    parser.add_argument("--input-dir", default="processed_documents", help="Directory containing cleaned markdown and metadata")
    parser.add_argument("--output-dir", default="parsed_documents", help="Directory for parsed document trees")
    args = parser.parse_args()
    result = parse_processed_documents(args.input_dir, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))

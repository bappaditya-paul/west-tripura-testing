from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, IngestionConfig
from .utils import (
    clean_text,
    content_hash,
    detect_language,
    parse_frontmatter,
    setup_logger,
    log_event,
)


@dataclass(slots=True)
class PreprocessorConfig:
    input_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.pages_dir)
    output_dir: Path = field(default_factory=lambda: DEFAULT_CONFIG.processed_docs_dir)
    log_path: Path | None = field(default_factory=lambda: DEFAULT_CONFIG.logs_dir / "preprocess_documents.log")
    preserve_frontmatter: bool = True
    deduplicate_by_url: bool = True
    deduplicate_by_hash: bool = True


@dataclass(slots=True)
class PreprocessedDocument:
    document_id: str
    source_path: str
    url: str
    depth: int
    crawled_at: str
    title: str
    content: str
    language: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "url": self.url,
            "depth": self.depth,
            "crawled_at": self.crawled_at,
            "title": self.title,
            "content": self.content,
            "language": self.language,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }


class DocumentPreprocessor:
    def __init__(self, config: PreprocessorConfig | None = None, logger: logging.Logger | None = None) -> None:
        self.config = config or PreprocessorConfig()
        self.logger = logger or setup_logger("document_preprocessor", self.config.log_path)
        self.seen_urls: set[str] = set()
        self.seen_hashes: set[str] = set()
        self._ensure_output_dir()

    def _ensure_output_dir(self) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.log_path is not None:
            self.config.log_path.parent.mkdir(parents=True, exist_ok=True)

    def preprocess_file(self, path: Path) -> PreprocessedDocument | None:
        raw_text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(raw_text)

        url = (frontmatter.get("url") or "").strip()
        depth = int(frontmatter.get("depth", 0) or 0)
        crawled_at = (frontmatter.get("crawled_at") or "").strip()

        cleaned_markdown = preprocess_markdown_text(raw_text, config=self.config)
        if not cleaned_markdown.strip():
            log_event(self.logger, "SKIP", f"Empty content after cleanup: {path.name}", level="WARNING")
            return None

        title = self._extract_title(cleaned_markdown, path)
        language = detect_language(cleaned_markdown)
        doc_hash = content_hash(cleaned_markdown)

        if self.config.deduplicate_by_url and url and url in self.seen_urls:
            log_event(self.logger, "DUPLICATE", f"Duplicate URL skipped: {url}", level="INFO")
            return None
        if self.config.deduplicate_by_hash and doc_hash in self.seen_hashes:
            log_event(self.logger, "DUPLICATE", f"Duplicate content hash skipped: {path.name}", level="INFO")
            return None

        self.seen_urls.add(url)
        self.seen_hashes.add(doc_hash)

        document_id = self._make_document_id(url, path.name, doc_hash)
        metadata = {
            "source_path": str(path.name),
            "url": url,
            "depth": depth,
            "crawled_at": crawled_at,
            "language": language,
            "content_hash": doc_hash,
        }

        document = PreprocessedDocument(
            document_id=document_id,
            source_path=str(path.name),
            url=url,
            depth=depth,
            crawled_at=crawled_at,
            title=title,
            content=cleaned_markdown,
            language=language,
            content_hash=doc_hash,
            metadata=metadata,
        )
        return document

    def write_document(self, document: PreprocessedDocument) -> Path:
        out_path = self.config.output_dir / f"{document.document_id}.md"
        out_path.write_text(document.content, encoding="utf-8")
        meta_path = self.config.output_dir / f"{document.document_id}.json"
        meta_path.write_text(json.dumps(document.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path

    def process_directory(self) -> dict[str, Any]:
        if not self.config.input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {self.config.input_dir}")

        files = sorted(self.config.input_dir.glob("*.md"))
        log_event(self.logger, "START", f"Processing {len(files)} markdown files from {self.config.input_dir}")

        written = 0
        skipped = 0
        for path in files:
            try:
                document = self.preprocess_file(path)
                if document is None:
                    skipped += 1
                    continue
                self.write_document(document)
                written += 1
                log_event(self.logger, "WRITE", f"Wrote {document.document_id} from {path.name}")
            except Exception as exc:  # pragma: no cover - defensive logging
                skipped += 1
                log_event(self.logger, "ERROR", f"Failed to process {path.name}: {exc}", level="ERROR")

        index_path = self.config.output_dir / "index.json"
        index_path.write_text(json.dumps({"written": written, "skipped": skipped}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"written": written, "skipped": skipped, "output_dir": str(self.config.output_dir)}

    def _make_document_id(self, url: str, filename: str, content_hash_value: str) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", Path(filename).stem).strip("_") or "document"
        anchor = hashlib.sha256(f"{url}:{content_hash_value}".encode("utf-8")).hexdigest()[:12]
        return f"{safe_name}__{anchor}"

    def _extract_title(self, content: str, path: Path) -> str:
        for line in content.splitlines():
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return path.stem.replace("_", " ").replace("-", " ").strip()


def preprocess_markdown_text(raw_text: str, *, config: PreprocessorConfig | None = None) -> str:
    config = config or PreprocessorConfig()
    frontmatter, body = parse_frontmatter(raw_text)
    cleaned_body = _remove_noise(body)
    cleaned_body = _normalize_markdown(cleaned_body)
    cleaned_body = _normalize_whitespace(cleaned_body)
    if config.preserve_frontmatter:
        frontmatter_lines = [f"---", *[f"{key}: {value}" for key, value in frontmatter.items() if value], "---", ""]
        return "\n".join(frontmatter_lines) + cleaned_body.strip()
    return cleaned_body.strip()


def _remove_noise(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\s*Back to Top\s*\]\([^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[\s*back to top\s*\]\([^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?im)^\s*(Copyright|©|Hosted and maintained by NIC|Hosted by NIC).*?$", "", text)
    text = re.sub(r"(?im)^\s*(Disclaimer|Privacy Policy|Terms & Conditions).*$", "", text)
    text = re.sub(r"(?im)^\s*(Disclaimer|Privacy Policy|Terms & Conditions).*$", "", text)
    text = re.sub(r"(?i)\blogo\b", "", text)
    text = re.sub(r"(?i)\bbar\d+\.gif\b", "", text)
    text = re.sub(r"(?i)\bback2top\b", "", text)
    text = re.sub(r"(?im)^\s*\*{0,2}\s*(Home|About|Contact|Courses|Faculty|Office Staff|Tenders|Alumni|Syllabus|Scholarships|Academic Calender|Newsletters)\s*\*{0,2}\s*$", "", text)
    text = re.sub(r"(?im)^\s*\|\s*\[.*?\]\(.*?\)\s*\|.*\|\s*$", "", text)
    text = re.sub(r"(?im)^\s*\|\s*\*\*.*?\*\*\s*\|\s*$", "", text)
    text = re.sub(r"(?im)^\s*\|\s*\[.*\]\(.*\)\s*$", "", text)
    text = re.sub(r"(?im)^\s*\|\s*$", "", text)
    text = re.sub(r"(?im)^\s*\[.*\]\(.*\)\s*$", "", text)
    text = re.sub(r"(?im)^\s*\*{0,2}\s*(The Institute|The Departments|Other Activities|Objectives|Information for Admission|Financial Requirements|Disciplinary guidelines)\s*\*{0,2}\s*$", "", text)
    return text


def _normalize_markdown(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?m)^\s*$", "", text)
    return text.strip()


def _normalize_whitespace(text: str) -> str:
    lines = []
    previous_blank = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if previous_blank:
                continue
            previous_blank = True
            lines.append("")
            continue
        previous_blank = False
        lines.append(line)
    return "\n".join(lines).strip()


def preprocess_directory(input_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config = PreprocessorConfig(input_dir=Path(input_dir), output_dir=Path(output_dir))
    preprocessor = DocumentPreprocessor(config=config)
    return preprocessor.process_directory()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Preprocess markdown pages into cleaned documents")
    parser.add_argument("--input-dir", default="output/pages", help="Directory containing markdown page files")
    parser.add_argument("--output-dir", default="processed_documents", help="Output directory for cleaned markdown")
    args = parser.parse_args()
    result = preprocess_directory(args.input_dir, args.output_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))

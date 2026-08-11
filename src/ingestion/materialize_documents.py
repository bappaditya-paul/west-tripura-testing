"""Turn downloaded official files into searchable Markdown documents."""
from __future__ import annotations

import json
from pathlib import Path

from src.ingestion.document_assets import ASSET_MANIFEST, extract_document_text

OUTPUT_PAGES = Path("output/pages")


def materialize_documents() -> dict[str, int]:
    OUTPUT_PAGES.mkdir(parents=True, exist_ok=True)
    if not ASSET_MANIFEST.exists():
        return {"documents": 0, "indexed": 0, "errors": 0}

    documents = indexed = errors = 0
    for line in ASSET_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            local_path = row.get("local_path")
            if not local_path or not Path(local_path).exists():
                continue
            documents += 1
            text = extract_document_text(local_path)
            if not text.strip():
                continue

            title = row.get("title") or Path(local_path).stem
            source_url = row.get("source_url") or "https://westtripura.nic.in/"
            document_url = row.get("url") or row.get("resolved_url") or ""
            output_name = Path(local_path).stem + ".md"
            output_path = OUTPUT_PAGES / f"document__{output_name}"
            frontmatter = (
                "---\n"
                f"url: {document_url}\n"
                f"source_url: {source_url}\n"
                f"document_url: {document_url}\n"
                f"document_type: {row.get('extension', '').lstrip('.')}\n"
                f"title: {title}\n"
                "depth: 0\n"
                "---\n\n"
            )
            body = (
                f"# {title}\n\n"
                f"Official document from West Tripura District.\n\n"
                f"Source page: {source_url}\n\n"
                f"Document download: {document_url}\n\n"
                "## Document content\n\n"
                f"{text}\n"
            )
            output_path.write_text(frontmatter + body, encoding="utf-8")
            indexed += 1
        except Exception:
            errors += 1

    return {"documents": documents, "indexed": indexed, "errors": errors}


if __name__ == "__main__":
    print(json.dumps(materialize_documents(), indent=2))

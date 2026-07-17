"""
build_documents.py — CLI for Module 1: Unified Document Builder

Usage:
    python build_documents.py
    python build_documents.py --pages output/pages --json output/json
    python build_documents.py --out processed_documents
    python build_documents.py --help
"""

from __future__ import annotations

import argparse
import asyncio
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from src.ingestion.core.config import IngestionConfig
from src.ingestion.core.document_builder import build_documents


def main() -> int:
    p = argparse.ArgumentParser(
        prog="build_documents",
        description="West Tripura RAG — Module 1: Unified Document Builder",
    )
    p.add_argument("--pages",    default="output/pages",    help="HTML Markdown pages dir")
    p.add_argument("--json",     default="output/json",     help="Docling JSON dir")
    p.add_argument("--metadata", default="output/metadata", help="Metadata JSON dir")
    p.add_argument("--manifest", default="output/manifest.jsonl", help="Manifest JSONL")
    p.add_argument("--out",      default="processed_documents", help="Output directory")
    p.add_argument("--logs",     default="logs",            help="Logs directory")
    args = p.parse_args()

    config = IngestionConfig(
        pages_dir           = Path(args.pages),
        json_dir            = Path(args.json),
        metadata_dir        = Path(args.metadata),
        manifest_path       = Path(args.manifest),
        processed_docs_dir  = Path(args.out),
        logs_dir            = Path(args.logs),
    )

    print("\n" + "=" * 60)
    print("  West Tripura RAG — Document Builder")
    print("=" * 60)
    print(f"  Pages dir  : {config.pages_dir.resolve()}")
    print(f"  JSON dir   : {config.json_dir.resolve()}")
    print(f"  Output     : {config.processed_docs_dir.resolve()}")
    print("=" * 60 + "\n")

    summary = build_documents(config)

    print("\n" + "=" * 60)
    print("  COMPLETE")
    print("=" * 60)
    print(f"  Documents built : {summary['processed']}")
    print(f"  Skipped         : {summary['skipped']}")
    print(f"  Errors          : {summary['errors']}")
    print(f"  Index           : {summary['index']}")
    print("=" * 60 + "\n")
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

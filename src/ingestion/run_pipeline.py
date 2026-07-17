"""
run_pipeline.py — CLI entry point for the Document Extraction Pipeline.

Usage:
    python run_pipeline.py                    # process all failed docs from crawl.log
    python run_pipeline.py --resume           # skip already-processed URLs
    python run_pipeline.py --url URL [URL …]  # process specific URLs only
    python run_pipeline.py --concurrency 5    # override concurrency
    python run_pipeline.py --no-ocr          # disable OCR fallback (faster)
    python run_pipeline.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent.parent))

from src.ingestion.document_pipeline.config import PipelineConfig
from src.ingestion.document_pipeline.pipeline import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_pipeline",
        description=(
            "West Tripura RAG — Document Extraction Pipeline\n"
            "Extracts PDFs, DOCX and XLSX from failed crawl URLs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument(
        "--output",
        default="output",
        metavar="DIR",
        help="Root output directory (default: output/)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=3,
        metavar="N",
        help="Number of parallel downloads (default: 3)",
    )
    p.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback for scanned PDFs (faster, may miss content)",
    )
    p.add_argument(
        "--url",
        nargs="+",
        metavar="URL",
        help="Process specific URLs instead of reading crawl.log",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="Skip URLs already recorded in manifest.jsonl",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=60,
        metavar="SEC",
        help="HTTP request timeout in seconds (default: 60)",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=3,
        metavar="N",
        help="Max download retries per URL (default: 3)",
    )
    return p


async def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    config = PipelineConfig(
        output_root=Path(args.output),
        download_concurrency=args.concurrency,
        enable_ocr=not args.no_ocr,
        request_timeout=args.timeout,
        max_retries=args.retries,
    )

    extra_urls: list[str] | None = args.url if args.url else None

    print("\n" + "=" * 60)
    print("  West Tripura RAG — Document Extraction Pipeline")
    print("=" * 60)
    print(f"  Output root  : {config.output_root.resolve()}")
    print(f"  Concurrency  : {config.download_concurrency}")
    print(f"  OCR enabled  : {config.enable_ocr}")
    if extra_urls:
        print(f"  URLs (manual): {len(extra_urls)}")
    print("=" * 60 + "\n")

    summary = await run_pipeline(config=config, extra_urls=extra_urls)

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Processed : {summary['processed']}")
    print(f"  Failed    : {summary['failed']}")
    print(f"  Skipped   : {summary['skipped']}")
    print(f"  Time      : {summary.get('elapsed_s', 0)}s")
    print(f"\n  Markdown  → {config.markdown_dir.resolve()}")
    print(f"  JSON      → {config.json_dir.resolve()}")
    print(f"  Metadata  → {config.metadata_dir.resolve()}")
    print(f"  Manifest  → {config.manifest_path.resolve()}")
    print(f"  Failures  → {config.failed_docs_path.resolve()}")
    print("=" * 60 + "\n")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""One-command West Tripura ingestion pipeline.

Run from the repository root:
    python src/ingestion/auto_ingest.py

Pipeline:
    Crawl4AI -> official document download -> document text extraction
    -> preprocessing -> semantic chunking -> NVIDIA embeddings -> Pinecone.

The downloaded binaries stay in output/documents and are NOT committed to Git.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def run(cmd: list[str]) -> None:
    print("\n$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl, collect documents, chunk, embed and index West Tripura data.")
    parser.add_argument("--resume", action="store_true", help="Resume the Crawl4AI crawl from its checkpoint.")
    parser.add_argument("--force-embed", action="store_true", help="Force re-embedding instead of reusing cached embeddings.")
    parser.add_argument("--clear-index", action="store_true", help="Delete the existing Pinecone vectors before loading. Use only for a full rebuild.")
    parser.add_argument("--min-tokens", type=int, default=30)
    args = parser.parse_args()

    run([PYTHON, "src/ingestion/crawler.py", *( ["--resume"] if args.resume else [] )])
    run([PYTHON, "src/ingestion/materialize_documents.py"])
    run([
        PYTHON,
        "-c",
        "from src.ingestion.core.preprocess_documents import preprocess_directory; print(preprocess_directory('output/pages', 'processed_documents'))",
    ])
    run([
        PYTHON,
        "src/ingestion/build_chunks.py",
        "--docs", "processed_documents",
        "--out", "processed_chunks",
        "--engine", "production",
    ])

    embed_cmd = [PYTHON, "src/ingestion/embed_and_load.py", "--chunks-dir", str(ROOT / "processed_chunks"), "--min-tokens", str(args.min_tokens)]
    if args.force_embed:
        # embed_and_load always recomputes vectors; this flag is kept for CLI compatibility.
        print("Note: embed_and_load recomputes embeddings for the current chunk corpus.")
    if args.clear_index:
        embed_cmd.append("--clear-index")
    run(embed_cmd)

    print("\n✓ West Tripura ingestion complete.")
    print("  Pages/documents: output/")
    print("  Downloaded files: output/documents/")
    print("  Chunks: processed_chunks/")
    print("  Vector index: Pinecone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

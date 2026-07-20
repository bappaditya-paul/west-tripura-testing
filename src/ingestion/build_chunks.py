"""
build_chunks.py — CLI for Module 2: Semantic Chunk Builder

Usage:
    python build_chunks.py                                    # production chunker (default)
    python build_chunks.py --engine legacy                    # legacy chunk_builder
    python build_chunks.py --docs processed_documents --out processed_chunks
    python build_chunks.py --target-tokens 550 --max-tokens 700 --min-tokens 100
    python build_chunks.py --help
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent.parent))

from src.ingestion.core.config import IngestionConfig


def main() -> int:
    p = argparse.ArgumentParser(
        prog="build_chunks",
        description="West Tripura RAG — Module 2: Semantic Chunk Builder",
    )
    p.add_argument("--docs",      default="processed_documents", help="Input documents directory")
    p.add_argument("--out",       default="processed_chunks",    help="Chunks output directory")
    p.add_argument("--logs",      default="logs",                help="Logs directory")
    p.add_argument("--engine",    choices=["production", "legacy"], default="production",
                   help="Chunking engine to use (default: production)")
    p.add_argument("--target-tokens", type=int, default=550,     help="Target tokens per chunk (production)")
    p.add_argument("--max-tokens",    type=int, default=700,     help="Maximum tokens per chunk (production)")
    p.add_argument("--min-tokens",    type=int, default=100,     help="Minimum tokens per chunk (production)")
    p.add_argument("--overlap-tokens",type=int, default=60,      help="Overlap tokens between chunks (production)")
    p.add_argument("--min-words", type=int, default=30,          help="Min words per chunk (legacy)")
    p.add_argument("--max-words", type=int, default=1000,        help="Max words per chunk (legacy)")
    args = p.parse_args()

    if args.engine == "legacy":
        from src.ingestion.core.chunk_builder import build_chunks
        config = IngestionConfig(
            processed_docs_dir   = Path(args.docs),
            processed_chunks_dir = Path(args.out),
            logs_dir             = Path(args.logs),
            chunk_min_words      = args.min_words,
            chunk_max_words      = args.max_words,
        )
        print("\n" + "=" * 60)
        print("  West Tripura RAG — Legacy Chunk Builder")
        print("=" * 60)
        print(f"  Input  : {config.processed_docs_dir.resolve()}")
        print(f"  Output : {config.processed_chunks_dir.resolve()}")
        print(f"  Min    : {config.chunk_min_words} words")
        print(f"  Max    : {config.chunk_max_words} words")
        print("=" * 60 + "\n")
        summary = build_chunks(config)
    else:
        from src.ingestion.core.production_chunker import ProductionChunker, ProductionChunkerConfig
        config = ProductionChunkerConfig(
            target_tokens=args.target_tokens,
            max_tokens=args.max_tokens,
            min_tokens=args.min_tokens,
            overlap_tokens=args.overlap_tokens,
            input_dir=Path(args.docs),
            output_dir=Path(args.out),
            logs_dir=Path(args.logs),
        )
        print("\n" + "=" * 60)
        print("  West Tripura RAG — Production Semantic Chunker")
        print("=" * 60)
        print(f"  Input     : {config.input_dir.resolve()}")
        print(f"  Output    : {config.output_dir.resolve()}")
        print(f"  Target    : {config.target_tokens} tokens")
        print(f"  Max       : {config.max_tokens} tokens")
        print(f"  Min       : {config.min_tokens} tokens")
        print(f"  Overlap   : {config.overlap_tokens} tokens")
        print("=" * 60 + "\n")
        chunker = ProductionChunker(config=config)
        summary = chunker.process_directory()

    print("\n" + "=" * 60)
    print("  COMPLETE")
    print("=" * 60)
    print(f"  Documents     : {summary.get('documents', summary.get('total_docs', 0))}")
    print(f"  Total chunks  : {summary.get('total_chunks', 0)}")
    print(f"  Avg per doc   : {summary.get('avg_chunks_per_doc', 0)}")
    print(f"  Errors        : {summary.get('errors', 0)}")
    print(f"  Elapsed       : {summary.get('elapsed_s', 'N/A')}s")
    print(f"  Output        : {Path(args.out).resolve()}")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

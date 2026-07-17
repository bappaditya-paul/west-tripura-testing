"""
West Tripura NIC Website Full Crawler
======================================
Crawls https://westtripura.nic.in/ completely using BFS deep crawl,
extracts all content as clean Markdown, and saves it in a structured
way that is ready for chunking & ingestion into a vector database.

Features:
  - BFS deep crawl (all pages, no depth limit override needed)
  - Crash/resume recovery via JSON checkpoint
  - Per-page Markdown files + a JSONL manifest
  - Configurable concurrency & politeness delay
  - Detailed progress logging
  - Robust error handling (skips bad pages, continues crawl)

Usage:
  python crawler.py              # fresh crawl
  python crawler.py --resume     # resume from last checkpoint
  python crawler.py --help
"""

import asyncio
import argparse
import json
import logging
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
START_URL = "https://westtripura.nic.in/"
TARGET_DOMAIN = "westtripura.nic.in"

OUTPUT_DIR = Path("output")
PAGES_DIR = OUTPUT_DIR / "pages"
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"
MANIFEST_FILE = OUTPUT_DIR / "manifest.jsonl"
LOG_FILE = OUTPUT_DIR / "crawl.log"

MAX_DEPTH = 5          # How many link-levels deep to crawl
MAX_PAGES = 2000       # Safety cap – increase if the site is huge
CONCURRENCY = 3        # Parallel browser contexts (be polite to govt server)
DELAY_BETWEEN_REQUESTS = 1.5   # seconds between batches (politeness)

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
def setup_logging() -> logging.Logger:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("west_tripura_crawler")


log = setup_logging()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def url_to_filename(url: str) -> str:
    """Convert a URL to a safe filesystem filename (md extension)."""
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__") or "index"
    query = re.sub(r"[^\w-]", "_", parsed.query) if parsed.query else ""
    slug = f"{path}__{query}" if query else path
    slug = re.sub(r"[^\w\-.]", "_", slug)[:200]  # safe chars, max 200
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{slug}__{url_hash}.md"


def save_checkpoint(state: dict):
    """Persist crawl state for crash recovery."""
    tmp = CHECKPOINT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(CHECKPOINT_FILE)


def load_checkpoint() -> dict | None:
    """Load a previously saved checkpoint, if any."""
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"Could not read checkpoint: {e}")
    return None


def write_page(url: str, markdown: str, metadata: dict):
    """Write a page's markdown to disk and append to manifest."""
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = url_to_filename(url)
    filepath = PAGES_DIR / filename

    # ── Frontmatter header ──
    frontmatter = f"""---
url: {url}
depth: {metadata.get('depth', 0)}
score: {metadata.get('score', 0)}
crawled_at: {datetime.utcnow().isoformat()}Z
---

"""
    filepath.write_text(frontmatter + (markdown or ""), encoding="utf-8")

    # ── Manifest entry (JSONL) ──
    entry = {
        "url": url,
        "file": str(filepath.relative_to(OUTPUT_DIR)),
        "depth": metadata.get("depth", 0),
        "score": metadata.get("score", 0),
        "char_count": len(markdown or ""),
        "crawled_at": datetime.utcnow().isoformat() + "Z",
    }
    with MANIFEST_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return filename


# ─────────────────────────────────────────────────────────────────────────────
# Crash recovery callback
# ─────────────────────────────────────────────────────────────────────────────
async def on_state_change(state: dict):
    save_checkpoint(state)
    pages = state.get("pages_crawled", 0)
    pending = len(state.get("pending", []))
    if pages % 10 == 0 or pages < 5:
        log.info(f"[Checkpoint] {pages} pages crawled | {pending} URLs pending")


# ─────────────────────────────────────────────────────────────────────────────
# Main crawl
# ─────────────────────────────────────────────────────────────────────────────
async def run_crawl(resume: bool = False):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    # ── Optional: clear manifest on fresh start ──
    if not resume and MANIFEST_FILE.exists():
        MANIFEST_FILE.unlink()

    # ── Load checkpoint if resuming ──
    saved_state = None
    if resume:
        saved_state = load_checkpoint()
        if saved_state:
            already = saved_state.get("pages_crawled", 0)
            log.info(f"Resuming from checkpoint: {already} pages already crawled.")
        else:
            log.info("No checkpoint found – starting fresh.")

    # ── BFS strategy ──
    strategy = BFSDeepCrawlStrategy(
        max_depth=MAX_DEPTH,
        include_external=False,          # stay on westtripura.nic.in
        max_pages=MAX_PAGES,
        resume_state=saved_state,
        on_state_change=on_state_change,
    )

    # ── CrawlerRunConfig ──
    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        stream=True,                      # process results as they arrive
        verbose=False,                    # reduce terminal noise (we have our own log)
        word_count_threshold=20,          # skip near-empty pages
        remove_overlay_elements=True,     # remove cookie banners, popups
        remove_consent_popups=True,       # remove GDPR/cookie consent popups
        exclude_external_links=True,      # strip external links from extracted content
        exclude_social_media_links=True,
        preserve_https_for_internal_links=True,
        check_robots_txt=True,            # respect robots.txt (good citizen)
        max_retries=2,                    # retry failed pages up to 2 times
        # Politeness delay between requests
        mean_delay=DELAY_BETWEEN_REQUESTS,
        max_range=1.0,
    )

    # ── Browser config ──
    browser_cfg = BrowserConfig(
        headless=True,
        verbose=False,
    )

    start_time = time.time()
    total_pages = 0
    total_errors = 0

    log.info("=" * 60)
    log.info(f"Starting crawl of {START_URL}")
    log.info(f"Max depth: {MAX_DEPTH} | Max pages: {MAX_PAGES}")
    log.info(f"Output directory: {OUTPUT_DIR.resolve()}")
    log.info("=" * 60)

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            async for result in await crawler.arun(START_URL, config=config):
                url = result.url

                if not result.success:
                    total_errors += 1
                    log.warning(f"FAILED [{result.status_code or '?'}]: {url}")
                    continue

                markdown = result.markdown or ""
                metadata = result.metadata or {}
                depth = metadata.get("depth", 0)

                filename = write_page(url, markdown, metadata)
                total_pages += 1

                log.info(
                    f"[{total_pages:>4}] depth={depth} | "
                    f"{len(markdown):>7} chars | {url}"
                )

    except KeyboardInterrupt:
        log.info("Crawl interrupted by user (Ctrl+C). State saved – use --resume to continue.")
    except Exception as e:
        log.error(f"Unexpected error: {e}", exc_info=True)
        log.info("State checkpoint saved – use --resume to continue.")

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info(f"Crawl finished in {elapsed:.1f}s")
    log.info(f"  Pages saved  : {total_pages}")
    log.info(f"  Pages failed : {total_errors}")
    log.info(f"  Output dir   : {OUTPUT_DIR.resolve()}")
    log.info(f"  Manifest     : {MANIFEST_FILE.resolve()}")
    log.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl westtripura.nic.in and save all content as Markdown."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the last saved checkpoint.",
    )
    args = parser.parse_args()
    asyncio.run(run_crawl(resume=args.resume))

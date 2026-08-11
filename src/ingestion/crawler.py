"""
West Tripura NIC Citizen Knowledge Crawler
===========================================
Crawls https://westtripura.nic.in/ with Crawl4AI, prioritizing pages that are
most useful to citizens and discovering official downloadable documents from
those pages.

Priority areas are based on the live West Tripura site structure:
services, certificates, forms, schemes, documents, notices/announcements,
helplines, offices/contacts, e-governance, public utilities, and local
administration information.
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
from urllib.parse import urlparse

try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
    from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
    from crawl4ai.deep_crawling.filters import ContentTypeFilter, DomainFilter, FilterChain, URLPatternFilter
    from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
    from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
    HAS_CRAWL4AI = True
except ImportError:
    HAS_CRAWL4AI = False
    AsyncWebCrawler = None
    CrawlerRunConfig = None
    BrowserConfig = None

from src.ingestion.document_assets import discover_document_links, download_documents

START_URL = "https://westtripura.nic.in/"
TARGET_DOMAIN = "westtripura.nic.in"
OUTPUT_DIR = Path("output")
PAGES_DIR = OUTPUT_DIR / "pages"
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"
MANIFEST_FILE = OUTPUT_DIR / "manifest.jsonl"
LOG_FILE = OUTPUT_DIR / "crawl.log"

# The live portal currently exposes citizen-focused areas such as Services,
# Certificates, Forms, Documents, Schemes, Notices, E-Governance and Helpline.
# BestFirst uses these terms to visit those URLs before low-value site pages.
CITIZEN_PRIORITY_KEYWORDS = [
    "service", "services", "certificate", "certificates", "form", "forms",
    "scheme", "schemes", "document", "documents", "download", "notice",
    "announcement", "notification", "helpline", "contact", "who-is-who",
    "division", "office", "department", "e-governance", "public-utility",
    "utility", "hospital", "school", "bank", "postal", "electricity",
    "subdivision", "block", "tehsil", "village", "panchayat", "rti",
    "grievance", "recruitment", "tender", "order", "government-order",
    "disaster", "emergency", "phone", "email", "address", "pin-code",
]

# Obvious utility/auth/media URLs add little value to a citizen RAG index.
LOW_VALUE_URL_PATTERNS = [
    "*/login*", "*/logout*", "*/admin*", "*/wp-admin*", "*/wp-login*",
    "*/feed*", "*/search*", "*/tag/*", "*/gallery/*", "*/media-gallery*",
    "*/photo-gallery*", "*/audio-gallery*", "*/video-gallery*",
    "*.css", "*.js", "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg",
    "*.webp", "*.ico", "*.woff", "*.woff2", "*.ttf", "*.xml",
    "*.json", "*.zip",
]

MAX_DEPTH = 4
MAX_PAGES = 400
DELAY_BETWEEN_REQUESTS = 1.0


def setup_logging() -> logging.Logger:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )
    return logging.getLogger("west_tripura_crawler")


log = setup_logging()


def url_to_filename(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__") or "index"
    query = re.sub(r"[^\w-]", "_", parsed.query) if parsed.query else ""
    slug = f"{path}__{query}" if query else path
    slug = re.sub(r"[^\w\-.]", "_", slug)[:200]
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{slug}__{url_hash}.md"


def save_checkpoint(state: dict):
    tmp = CHECKPOINT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(CHECKPOINT_FILE)


def load_checkpoint() -> dict | None:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not read checkpoint: %s", exc)
    return None


def write_page(url: str, markdown: str, metadata: dict, document_urls: list[str] | None = None):
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = url_to_filename(url)
    filepath = PAGES_DIR / filename
    document_urls = document_urls or []
    document_lines = "\n".join(f"- {u}" for u in document_urls)
    frontmatter = f"""---
url: {url}
depth: {metadata.get('depth', 0)}
score: {metadata.get('score', 0)}
crawled_at: {datetime.utcnow().isoformat()}Z
document_urls: {json.dumps(document_urls, ensure_ascii=False)}
---

"""
    body = markdown or ""
    if document_lines:
        body += "\n\n## Official documents\n" + document_lines + "\n"
    filepath.write_text(frontmatter + body, encoding="utf-8")

    entry = {
        "url": url,
        "file": str(filepath.relative_to(OUTPUT_DIR)),
        "depth": metadata.get("depth", 0),
        "score": metadata.get("score", 0),
        "char_count": len(markdown or ""),
        "document_urls": document_urls,
        "crawled_at": datetime.utcnow().isoformat() + "Z",
    }
    with MANIFEST_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return filename


async def on_state_change(state: dict):
    save_checkpoint(state)
    pages = state.get("pages_crawled", 0)
    pending = len(state.get("pending", []))
    if pages % 10 == 0 or pages < 5:
        log.info("[Checkpoint] %s pages crawled | %s URLs pending", pages, pending)


async def run_crawl(resume: bool = False):
    if not HAS_CRAWL4AI:
        raise RuntimeError("crawl4ai is not installed. Run: pip install crawl4ai")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    if not resume and MANIFEST_FILE.exists():
        MANIFEST_FILE.unlink()

    saved_state = load_checkpoint() if resume else None
    if saved_state:
        log.info("Resuming from checkpoint: %s pages already crawled.", saved_state.get("pages_crawled", 0))

    priority_scorer = KeywordRelevanceScorer(
        keywords=CITIZEN_PRIORITY_KEYWORDS,
        weight=0.9,
    )
    filter_chain = FilterChain([
        DomainFilter(allowed_domains=[TARGET_DOMAIN]),
        ContentTypeFilter(allowed_types=["text/html"]),
        URLPatternFilter(patterns=LOW_VALUE_URL_PATTERNS, reverse=True),
    ])

    strategy = BestFirstCrawlingStrategy(
        max_depth=MAX_DEPTH,
        include_external=False,
        max_pages=MAX_PAGES,
        resume_state=saved_state,
        on_state_change=on_state_change,
        url_scorer=priority_scorer,
        filter_chain=filter_chain,
    )
    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        stream=True,
        verbose=False,
        word_count_threshold=20,
        remove_overlay_elements=True,
        remove_consent_popups=True,
        exclude_external_links=False,
        exclude_social_media_links=True,
        preserve_https_for_internal_links=True,
        check_robots_txt=True,
        max_retries=2,
        mean_delay=DELAY_BETWEEN_REQUESTS,
        max_range=1.0,
    )
    browser_cfg = BrowserConfig(headless=True, verbose=False)

    start_time = time.time()
    total_pages = 0
    total_errors = 0
    total_assets = 0

    log.info("Starting citizen-priority crawl of %s", START_URL)
    log.info("Priority keywords: %d | Max depth: %s | Max pages: %s", len(CITIZEN_PRIORITY_KEYWORDS), MAX_DEPTH, MAX_PAGES)

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            async for result in await crawler.arun(START_URL, config=config):
                url = result.url
                if not result.success:
                    total_errors += 1
                    log.warning("FAILED [%s]: %s", result.status_code or "?", url)
                    continue

                markdown = result.markdown or ""
                metadata = result.metadata or {}
                html = getattr(result, "html", "") or ""
                links = discover_document_links(html, url)
                asset_records = await download_documents(links)
                downloaded = [r for r in asset_records if r.get("local_path")]
                total_assets += len(downloaded)
                document_urls = [r["url"] for r in asset_records if r.get("url")]
                write_page(url, markdown, metadata, document_urls)
                total_pages += 1

                log.info(
                    "[%4d] depth=%s score=%.3f | %7d chars | %s | assets=%d",
                    total_pages,
                    metadata.get("depth", 0),
                    float(metadata.get("score", 0) or 0),
                    len(markdown),
                    url,
                    len(downloaded),
                )

    except KeyboardInterrupt:
        log.info("Crawl interrupted. Use --resume to continue.")
    except Exception as exc:
        log.error("Crawler failed before producing a usable corpus: %s", exc, exc_info=True)
        raise

    elapsed = time.time() - start_time
    log.info("Crawl finished in %.1fs | pages=%d failed=%d documents=%d", elapsed, total_pages, total_errors, total_assets)
    log.info("Output: %s", OUTPUT_DIR.resolve())

    if total_pages == 0:
        raise RuntimeError("Crawl produced 0 pages. Check Playwright/browser installation, network access, and robots.txt before continuing ingestion.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl West Tripura citizen-critical content and collect official documents.")
    parser.add_argument("--resume", action="store_true", help="Resume from the last crawl checkpoint.")
    args = parser.parse_args()
    asyncio.run(run_crawl(resume=args.resume))

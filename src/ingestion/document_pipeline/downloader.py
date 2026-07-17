"""
downloader.py — Async HTTP downloader with retry + exponential back-off.

Features:
  - aiohttp-based streaming download (memory-safe for large PDFs)
  - Semaphore-controlled concurrency (polite to govt servers)
  - Exponential back-off with jitter on transient failures
  - Structured logging at each stage (DOWNLOAD / RETRY / FAIL)
  - Returns raw bytes + final resolved URL (handles redirects)
"""

from __future__ import annotations

import asyncio
import random
import traceback
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

from .config import PipelineConfig
from .logger import get_logger, log_event
from .utils import normalize_url

log = get_logger()


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DownloadResult:
    url: str
    data: Optional[bytes] = None        # None on failure
    final_url: str = ""                 # after redirects
    content_type_header: str = ""       # server-reported MIME type
    status_code: int = 0
    success: bool = False
    error: str = ""
    retry_count: int = 0
    duration_s: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Downloader
# ─────────────────────────────────────────────────────────────────────────────

class AsyncDownloader:
    """
    Downloads multiple URLs concurrently using a semaphore to limit parallelism.

    Usage::

        async with AsyncDownloader(config) as dl:
            results = await dl.download_many(urls)
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config
        self._semaphore = asyncio.Semaphore(config.download_concurrency)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "AsyncDownloader":
        timeout = aiohttp.ClientTimeout(total=self._config.request_timeout)
        connector = aiohttp.TCPConnector(
            limit=self._config.download_concurrency * 2,
            ssl=False,           # many NIC sites have self-signed / expired certs
        )
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": self._config.user_agent},
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session:
            await self._session.close()

    # ── Single URL ──────────────────────────────────────────────────────────

    async def download_one(self, url: str) -> DownloadResult:
        """Download a single URL with retry / back-off. Thread-safe."""
        async with self._semaphore:
            return await self._download_with_retry(url)

    async def _download_with_retry(self, url: str) -> DownloadResult:
        cfg = self._config
        # Normalize URL once: encode spaces + unsafe chars in path
        # e.g. "Fee _Structure.pdf" → "Fee%20_Structure.pdf"
        normalized_url = normalize_url(url)
        if normalized_url != url:
            log_event(log, "DOWNLOAD", f"URL normalized: {url!r} → {normalized_url!r}")

        last_error = ""
        for attempt in range(cfg.max_retries + 1):
            if attempt > 0:
                delay = cfg.retry_base_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, delay * 0.3)
                wait = delay + jitter
                log_event(
                    log, "RETRY",
                    f"Retry {attempt}/{cfg.max_retries} in {wait:.1f}s",
                    url=url, retry=attempt,
                )
                await asyncio.sleep(wait)

            result = await self._fetch(normalized_url, attempt, original_url=url)
            if result.success:
                return result
            last_error = result.error

        # All retries exhausted
        log_event(log, "FAIL", f"Download failed after {cfg.max_retries} retries: {last_error}",
                  level="ERROR", url=url)
        return DownloadResult(url=url, success=False, error=last_error,
                              retry_count=cfg.max_retries)

    async def _fetch(self, url: str, attempt: int, original_url: str = "") -> DownloadResult:
        """Make one HTTP GET attempt. url is already normalized."""
        display_url = original_url or url
        t0 = time.monotonic()
        try:
            assert self._session is not None, "Call inside async context manager"
            async with self._session.get(url, allow_redirects=True) as resp:
                status = resp.status
                final_url = str(resp.url)
                ct = resp.headers.get("Content-Type", "")

                if status == 200:
                    chunks: list[bytes] = []
                    async for chunk in resp.content.iter_chunked(self._config.chunk_size):
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    elapsed = time.monotonic() - t0

                    log_event(
                        log, "DOWNLOAD",
                        f"Downloaded {len(data):,} bytes in {elapsed:.2f}s",
                        url=display_url, duration_s=round(elapsed, 3),
                    )
                    return DownloadResult(
                        url=display_url,   # preserve original URL (with spaces)
                        data=data,
                        final_url=final_url,
                        content_type_header=ct,
                        status_code=status,
                        success=True,
                        retry_count=attempt,
                        duration_s=round(elapsed, 3),
                    )
                else:
                    # Non-200: don't retry on 403/404
                    elapsed = time.monotonic() - t0
                    error = f"HTTP {status}"
                    permanent = status in (403, 404, 410)
                    log_event(
                        log, "FAIL" if permanent else "RETRY",
                        error, level="WARNING", url=url,
                    )
                    result = DownloadResult(
                        url=url, success=False, error=error,
                        status_code=status, duration_s=round(elapsed, 3),
                        retry_count=attempt,
                    )
                    if permanent:
                        result.retry_count = self._config.max_retries  # force no more retries
                    return result

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            return DownloadResult(
                url=url, success=False,
                error=f"Timeout after {elapsed:.1f}s",
                retry_count=attempt, duration_s=round(elapsed, 3),
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            return DownloadResult(
                url=url, success=False,
                error=f"{type(exc).__name__}: {exc}",
                retry_count=attempt, duration_s=round(elapsed, 3),
            )

    # ── Batch ───────────────────────────────────────────────────────────────

    async def download_many(self, urls: list[str]) -> list[DownloadResult]:
        """Download all URLs concurrently (semaphore-limited). Returns results in order."""
        tasks = [self.download_one(url) for url in urls]
        return list(await asyncio.gather(*tasks))

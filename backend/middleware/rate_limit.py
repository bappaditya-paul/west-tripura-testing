"""
middleware/rate_limit.py
=======================
In-memory sliding-window rate limiter.
For production, swap with Redis-backed limiter.
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/ready", "/live", "/version"):
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.time()
        window_start = now - self.window

        self._hits[ip] = [t for t in self._hits[ip] if t > window_start]

        if len(self._hits[ip]) >= self.max_requests:
            retry_after = int(self._hits[ip][0] + self.window - now) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Max {self.max_requests} requests per minute.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        self._hits[ip].append(now)
        return await call_next(request)

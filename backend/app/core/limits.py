"""Small in-process safeguards: a sliding-window rate limit and security headers.

The rate limit protects the LLM quota (each chat can cost several provider calls). It is per
client address and per process; behind a load balancer use a shared store instead.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimit:
    def __init__(self, limit: int, window_seconds: float):
        self.limit, self.window = limit, window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        if self.limit <= 0:
            return
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry = int(self.window - (now - q[0])) + 1
            raise HTTPException(429, f"Too many questions in a short time. Try again in {retry}s.",
                                headers={"Retry-After": str(retry)})
        q.append(now)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",
}

"""Limite simples de tentativas (memória do processo) contra adivinhação de senha."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, max_hits: int, window_s: float):
        self.max_hits, self.window_s = max_hits, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.max_hits:
                wait = int(self.window_s - (now - q[0])) + 1
                raise HTTPException(429, f"Muitas tentativas. Tente de novo em {max(1, wait // 60)} min.",
                                    headers={"Retry-After": str(wait)})
            q.append(now)
            if len(self._hits) > 10_000:                       # evita crescer sem limite
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window_s]:
                    del self._hits[k]


def client_ip(request: Request) -> str:
    # atrás do Caddy o uvicorn roda com --proxy-headers, então request.client já é o IP real
    return request.client.host if request.client else "?"


login_limiter = RateLimiter(max_hits=10, window_s=15 * 60)     # 10 tentativas / 15 min por IP+e-mail
register_limiter = RateLimiter(max_hits=5, window_s=60 * 60)   # 5 cadastros / hora por IP

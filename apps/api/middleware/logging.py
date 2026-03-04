"""
Structured request logging middleware.

Uses raw ASGI middleware (not Starlette BaseHTTPMiddleware) because
BaseHTTPMiddleware has known issues with StreamingResponse — it consumes
the response body, breaking SSE streams.

Logs a JSON object on every HTTP request completion:
    {"timestamp", "method", "path", "status_code", "duration_ms", "session_id"}
"""

import json
import logging
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger("ballot_guide.access")

_SESSION_ID_RE = re.compile(r"/session/([^/]+)")


class RequestLoggingMiddleware:
    """ASGI middleware that logs structured request data on completion."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = round((time.monotonic() - start) * 1000)
        path = scope.get("path", "")
        method = scope.get("method", "")
        match = _SESSION_ID_RE.search(path)
        session_id = match.group(1) if match else None

        logger.info(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "session_id": session_id,
                }
            )
        )

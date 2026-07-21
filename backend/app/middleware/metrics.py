"""HTTP request metrics middleware."""

import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.metrics import MetricsRegistry, metrics_registry


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Record method, route template, status code, and latency for each request."""

    def __init__(
        self,
        app: ASGIApp,
        registry: MetricsRegistry = metrics_registry,
    ) -> None:
        super().__init__(app)
        self.registry = registry

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = time.perf_counter() - started_at
            self.registry.record_http_request(
                method=request.method,
                path=self._route_path(request),
                status_code=status_code,
                duration_seconds=duration_seconds,
            )

    @staticmethod
    def _route_path(request: Request) -> str:
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str):
            return route_path
        return request.url.path

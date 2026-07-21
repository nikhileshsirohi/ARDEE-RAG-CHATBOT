"""Prometheus-compatible application metrics."""

import math
import threading
from collections import defaultdict
from collections.abc import Iterable

DEFAULT_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    math.inf,
)


class MetricsRegistry:
    """Thread-safe in-process metrics registry for HTTP requests."""

    def __init__(self, latency_buckets: Iterable[float] = DEFAULT_LATENCY_BUCKETS) -> None:
        self.latency_buckets = tuple(latency_buckets)
        self._request_totals: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._latency_bucket_totals: defaultdict[tuple[str, str, str, float], int] = defaultdict(
            int
        )
        self._latency_sums: defaultdict[tuple[str, str, str], float] = defaultdict(float)
        self._latency_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one completed HTTP request."""
        labels = (method.upper(), path, str(status_code))
        with self._lock:
            self._request_totals[labels] += 1
            self._latency_sums[labels] += duration_seconds
            self._latency_counts[labels] += 1
            for bucket in self.latency_buckets:
                if duration_seconds <= bucket:
                    self._latency_bucket_totals[(*labels, bucket)] += 1

    def render_prometheus(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        with self._lock:
            request_totals = dict(self._request_totals)
            latency_bucket_totals = dict(self._latency_bucket_totals)
            latency_sums = dict(self._latency_sums)
            latency_counts = dict(self._latency_counts)

        lines = [
            "# HELP http_requests_total Total HTTP requests.",
            "# TYPE http_requests_total counter",
        ]
        for (method, path, status_code), count in sorted(request_totals.items()):
            lines.append(
                "http_requests_total"
                f'{{method="{method}",path="{self._escape_label(path)}",'
                f'status_code="{status_code}"}} '
                f"{count}"
            )

        lines.extend(
            [
                "# HELP http_request_duration_seconds HTTP request latency in seconds.",
                "# TYPE http_request_duration_seconds histogram",
            ]
        )
        for method, path, status_code in sorted(latency_counts):
            for bucket in self.latency_buckets:
                bucket_count = latency_bucket_totals.get((method, path, status_code, bucket), 0)
                lines.append(
                    "http_request_duration_seconds_bucket"
                    f'{{method="{method}",path="{self._escape_label(path)}",'
                    f'status_code="{status_code}",le="{self._format_bucket(bucket)}"}} '
                    f"{bucket_count}"
                )
            label_text = (
                f'{{method="{method}",path="{self._escape_label(path)}",'
                f'status_code="{status_code}"}}'
            )
            lines.append(
                f"http_request_duration_seconds_count{label_text} "
                f"{latency_counts[method, path, status_code]}"
            )
            lines.append(
                f"http_request_duration_seconds_sum{label_text} "
                f"{latency_sums[method, path, status_code]:.6f}"
            )

        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_bucket(bucket: float) -> str:
        if math.isinf(bucket):
            return "+Inf"
        return f"{bucket:g}"

    @staticmethod
    def _escape_label(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


metrics_registry = MetricsRegistry()

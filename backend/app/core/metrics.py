"""Prometheus-compatible application and RAG business metrics."""

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

BUSINESS_COUNTER_NAMES = (
    "rag_queries_total",
    "rag_cache_hits_total",
    "rag_cache_misses_total",
    "rag_low_confidence_total",
    "rag_documents_ingested_total",
    "rag_ingestion_errors_total",
    "llm_calls_total",
    "llm_errors_total",
    "embedding_calls_total",
)

BUSINESS_GAUGE_NAMES = (
    "rag_active_documents",
    "rag_total_chunks",
)

BUSINESS_HISTOGRAM_NAMES = (
    "rag_query_duration_seconds",
    "llm_call_duration_seconds",
    "embedding_call_duration_seconds",
)


class CounterRegistry:
    """Thread-safe named counter registry."""

    def __init__(self) -> None:
        self._values: defaultdict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a named counter."""
        with self._lock:
            self._values[name] += amount

    def snapshot(self) -> dict[str, int]:
        """Return a point-in-time counter snapshot."""
        with self._lock:
            return dict(self._values)


class GaugeRegistry:
    """Thread-safe named gauge registry."""

    def __init__(self) -> None:
        self._values: dict[str, float] = {}
        self._lock = threading.Lock()

    def set(self, name: str, value: float) -> None:
        """Set a named gauge."""
        with self._lock:
            self._values[name] = value

    def snapshot(self) -> dict[str, float]:
        """Return a point-in-time gauge snapshot."""
        with self._lock:
            return dict(self._values)


class MetricsRegistry:
    """Thread-safe in-process metrics registry."""

    def __init__(self, latency_buckets: Iterable[float] = DEFAULT_LATENCY_BUCKETS) -> None:
        self.latency_buckets = tuple(latency_buckets)
        self.counters = CounterRegistry()
        self.gauges = GaugeRegistry()
        self._histogram_names = set(BUSINESS_HISTOGRAM_NAMES)
        self._histogram_bucket_totals: defaultdict[tuple[str, float], int] = defaultdict(int)
        self._histogram_sums: defaultdict[str, float] = defaultdict(float)
        self._histogram_counts: defaultdict[str, int] = defaultdict(int)
        self._request_totals: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._latency_bucket_totals: defaultdict[tuple[str, str, str, float], int] = defaultdict(
            int
        )
        self._latency_sums: defaultdict[tuple[str, str, str], float] = defaultdict(float)
        self._latency_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._lock = threading.Lock()
        for counter_name in BUSINESS_COUNTER_NAMES:
            self.counters.increment(counter_name, 0)
        for gauge_name in BUSINESS_GAUGE_NAMES:
            self.gauges.set(gauge_name, 0)

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

    def increment_counter(self, name: str, amount: int = 1) -> None:
        """Increment a named counter."""
        self.counters.increment(name, amount)

    def set_gauge(self, name: str, value: float) -> None:
        """Set a named gauge value."""
        self.gauges.set(name, value)

    def observe_histogram(self, name: str, value: float) -> None:
        """Observe a value for a named histogram."""
        with self._lock:
            self._histogram_names.add(name)
            self._histogram_sums[name] += value
            self._histogram_counts[name] += 1
            for bucket in self.latency_buckets:
                if value <= bucket:
                    self._histogram_bucket_totals[name, bucket] += 1

    def render_prometheus(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        counters = self.counters.snapshot()
        gauges = self.gauges.snapshot()
        with self._lock:
            histogram_bucket_totals = dict(self._histogram_bucket_totals)
            histogram_sums = dict(self._histogram_sums)
            histogram_counts = dict(self._histogram_counts)
            histogram_names = set(self._histogram_names)
            request_totals = dict(self._request_totals)
            latency_bucket_totals = dict(self._latency_bucket_totals)
            latency_sums = dict(self._latency_sums)
            latency_counts = dict(self._latency_counts)

        lines: list[str] = []
        for name, counter_value in sorted(counters.items()):
            lines.extend(
                [
                    f"# HELP {name} Business counter {name}.",
                    f"# TYPE {name} counter",
                    f"{name} {counter_value}",
                ]
            )

        for name, gauge_value in sorted(gauges.items()):
            lines.extend(
                [
                    f"# HELP {name} Business gauge {name}.",
                    f"# TYPE {name} gauge",
                    f"{name} {gauge_value:g}",
                ]
            )

        for name in sorted(histogram_names):
            lines.extend(
                [
                    f"# HELP {name} Business duration histogram {name}.",
                    f"# TYPE {name} histogram",
                ]
            )
            for bucket in self.latency_buckets:
                bucket_count = histogram_bucket_totals.get((name, bucket), 0)
                lines.append(
                    f'{name}_bucket{{le="{self._format_bucket(bucket)}"}} {bucket_count}'
                )
            lines.append(f"{name}_count {histogram_counts.get(name, 0)}")
            lines.append(f"{name}_sum {histogram_sums.get(name, 0):.6f}")

        lines.extend(
            [
                "# HELP http_requests_total Total HTTP requests.",
                "# TYPE http_requests_total counter",
            ]
        )
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

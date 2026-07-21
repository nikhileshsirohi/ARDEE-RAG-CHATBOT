"""Tests for Prometheus-style application metrics."""

from app.core.metrics import MetricsRegistry


def test_metrics_registry_renders_request_counter_and_latency_histogram() -> None:
    """Recorded HTTP requests should render as Prometheus counters and histograms."""
    registry = MetricsRegistry(latency_buckets=(0.1, 1.0, float("inf")))

    registry.record_http_request(
        method="get",
        path="/api/v1/chat/sessions/{session_id}",
        status_code=200,
        duration_seconds=0.25,
    )

    output = registry.render_prometheus()

    assert "# TYPE http_requests_total counter" in output
    assert (
        'http_requests_total{method="GET",path="/api/v1/chat/sessions/{session_id}",'
        'status_code="200"} 1'
    ) in output
    assert (
        'http_request_duration_seconds_bucket{method="GET",'
        'path="/api/v1/chat/sessions/{session_id}",status_code="200",le="0.1"} 0'
    ) in output
    assert (
        'http_request_duration_seconds_bucket{method="GET",'
        'path="/api/v1/chat/sessions/{session_id}",status_code="200",le="1"} 1'
    ) in output
    assert (
        'http_request_duration_seconds_bucket{method="GET",'
        'path="/api/v1/chat/sessions/{session_id}",status_code="200",le="+Inf"} 1'
    ) in output
    assert (
        'http_request_duration_seconds_count{method="GET",'
        'path="/api/v1/chat/sessions/{session_id}",status_code="200"} 1'
    ) in output


def test_metrics_registry_escapes_label_values() -> None:
    """Label values must be escaped for Prometheus text output."""
    registry = MetricsRegistry(latency_buckets=(float("inf"),))

    registry.record_http_request(
        method="GET",
        path='/path/"quoted"',
        status_code=404,
        duration_seconds=0.01,
    )

    output = registry.render_prometheus()

    assert 'path="/path/\\"quoted\\""' in output


def test_metrics_registry_renders_business_metrics() -> None:
    """Business counters, gauges, and histograms should render for Prometheus."""
    registry = MetricsRegistry(latency_buckets=(0.5, float("inf")))

    registry.increment_counter("rag_queries_total")
    registry.increment_counter("rag_cache_hits_total", 2)
    registry.set_gauge("rag_active_documents", 3)
    registry.observe_histogram("rag_query_duration_seconds", 0.75)

    output = registry.render_prometheus()

    assert "# TYPE rag_queries_total counter" in output
    assert "rag_queries_total 1" in output
    assert "rag_cache_hits_total 2" in output
    assert "# TYPE rag_active_documents gauge" in output
    assert "rag_active_documents 3" in output
    assert '# TYPE rag_query_duration_seconds histogram' in output
    assert 'rag_query_duration_seconds_bucket{le="0.5"} 0' in output
    assert 'rag_query_duration_seconds_bucket{le="+Inf"} 1' in output

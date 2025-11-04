"""
Comprehensive Metrics Collection

Tracks performance metrics for all pipeline components with
Prometheus-compatible export format.
"""
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics
import threading
import time

from logger import get_logger

logger = get_logger(__name__)


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"           # Monotonically increasing
    GAUGE = "gauge"               # Can go up or down
    HISTOGRAM = "histogram"       # Distribution of values
    SUMMARY = "summary"           # Like histogram but with quantiles


@dataclass
class Metric:
    """Individual metric data point"""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    help_text: str = ""


@dataclass
class MetricsSnapshot:
    """Snapshot of all metrics at a point in time"""
    timestamp: datetime
    metrics: List[Metric]

    # Aggregated statistics
    request_count: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_rate: float = 0.0
    throughput_per_second: float = 0.0


class MetricsCollector:
    """
    Comprehensive metrics collector for pipeline monitoring

    Collects and aggregates metrics for:
    - HTTP requests (latency, status codes, throughput)
    - Pipeline stages (NER, KB, patterns, post-processing)
    - Component performance (models, KBs, pattern matchers)
    - Resource usage (CPU, memory, cache hit rates)
    - Business metrics (entities extracted, accuracy, coverage)

    Export formats:
    - Prometheus format
    - JSON
    - Internal snapshot for dashboards

    Example:
        collector = MetricsCollector()
        collector.start()

        # Record request
        collector.record_request("/process", duration_ms=150, status_code=200)

        # Record pipeline stage
        collector.record_stage("ner", duration_ms=100, entity_count=10)

        # Get snapshot
        snapshot = collector.get_snapshot()
        print(f"Throughput: {snapshot.throughput_per_second:.2f} req/s")
    """

    def __init__(
        self,
        history_size: int = 10000,
        aggregation_window_seconds: int = 60
    ):
        """
        Initialize metrics collector

        Args:
            history_size: Number of data points to keep per metric
            aggregation_window_seconds: Time window for aggregations
        """
        self.history_size = history_size
        self.aggregation_window = timedelta(seconds=aggregation_window_seconds)

        # Counters
        self._counters: Dict[str, float] = defaultdict(float)

        # Gauges
        self._gauges: Dict[str, float] = {}

        # Histograms (store recent values for percentile calculation)
        self._histograms: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=history_size)
        )

        # Metric metadata
        self._help_texts: Dict[str, str] = {}
        self._labels: Dict[str, Dict[str, str]] = {}

        # Request tracking
        self._request_times: deque = deque(maxlen=history_size)
        self._request_statuses: deque = deque(maxlen=history_size)

        # Thread safety
        self._lock = threading.Lock()

        # Export thread
        self._running = False
        self._export_thread = None

    def start(self):
        """Start metrics collection"""
        if self._running:
            return

        self._running = True
        logger.info("Metrics collector started")

    def stop(self):
        """Stop metrics collection"""
        self._running = False
        logger.info("Metrics collector stopped")

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
        help_text: str = ""
    ):
        """Increment a counter metric"""
        key = self._make_key(name, labels)

        with self._lock:
            self._counters[key] += value
            if help_text:
                self._help_texts[name] = help_text
            if labels:
                self._labels[key] = labels

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        help_text: str = ""
    ):
        """Set a gauge metric"""
        key = self._make_key(name, labels)

        with self._lock:
            self._gauges[key] = value
            if help_text:
                self._help_texts[name] = help_text
            if labels:
                self._labels[key] = labels

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        help_text: str = ""
    ):
        """Observe a value in a histogram"""
        key = self._make_key(name, labels)

        with self._lock:
            self._histograms[key].append(value)
            if help_text:
                self._help_texts[name] = help_text
            if labels:
                self._labels[key] = labels

    def record_request(
        self,
        endpoint: str,
        duration_ms: float,
        status_code: int,
        method: str = "POST"
    ):
        """Record an HTTP request"""
        with self._lock:
            self._request_times.append((time.time(), duration_ms))
            self._request_statuses.append((time.time(), status_code))

        # Increment counters
        self.increment_counter(
            "http_requests_total",
            labels={"endpoint": endpoint, "method": method, "status": str(status_code)},
            help_text="Total HTTP requests"
        )

        # Observe latency
        self.observe_histogram(
            "http_request_duration_ms",
            duration_ms,
            labels={"endpoint": endpoint, "method": method},
            help_text="HTTP request latency in milliseconds"
        )

        # Track errors
        if status_code >= 400:
            self.increment_counter(
                "http_requests_errors_total",
                labels={"endpoint": endpoint, "status": str(status_code)},
                help_text="Total HTTP request errors"
            )

    def record_stage(
        self,
        stage: str,
        duration_ms: float,
        entity_count: int = 0,
        error: bool = False
    ):
        """Record pipeline stage execution"""
        # Stage duration
        self.observe_histogram(
            "pipeline_stage_duration_ms",
            duration_ms,
            labels={"stage": stage},
            help_text="Pipeline stage duration in milliseconds"
        )

        # Entity count
        if entity_count > 0:
            self.observe_histogram(
                "pipeline_entities_extracted",
                entity_count,
                labels={"stage": stage},
                help_text="Number of entities extracted per stage"
            )

        # Errors
        if error:
            self.increment_counter(
                "pipeline_stage_errors_total",
                labels={"stage": stage},
                help_text="Total pipeline stage errors"
            )

    def record_component_performance(
        self,
        component_type: str,
        component_id: str,
        duration_ms: float,
        success: bool = True
    ):
        """Record component performance"""
        labels = {
            "component_type": component_type,
            "component_id": component_id
        }

        # Duration
        self.observe_histogram(
            "component_duration_ms",
            duration_ms,
            labels=labels,
            help_text="Component execution duration"
        )

        # Success/failure
        status = "success" if success else "failure"
        self.increment_counter(
            "component_executions_total",
            labels={**labels, "status": status},
            help_text="Total component executions"
        )

    def record_kb_lookup(
        self,
        kb_id: str,
        duration_ms: float,
        cache_hit: bool,
        found: bool
    ):
        """Record knowledge base lookup"""
        labels = {"kb_id": kb_id}

        # Duration
        self.observe_histogram(
            "kb_lookup_duration_ms",
            duration_ms,
            labels=labels,
            help_text="KB lookup duration"
        )

        # Cache hits
        cache_status = "hit" if cache_hit else "miss"
        self.increment_counter(
            "kb_cache_lookups_total",
            labels={**labels, "status": cache_status},
            help_text="KB cache lookups"
        )

        # Found/not found
        result = "found" if found else "not_found"
        self.increment_counter(
            "kb_lookups_total",
            labels={**labels, "result": result},
            help_text="KB lookups"
        )

    def record_model_prediction(
        self,
        model_id: str,
        duration_ms: float,
        entity_count: int,
        confidence_avg: float
    ):
        """Record model prediction"""
        labels = {"model_id": model_id}

        # Duration
        self.observe_histogram(
            "model_prediction_duration_ms",
            duration_ms,
            labels=labels,
            help_text="Model prediction duration"
        )

        # Entity count
        self.observe_histogram(
            "model_entities_extracted",
            entity_count,
            labels=labels,
            help_text="Entities extracted by model"
        )

        # Confidence
        self.observe_histogram(
            "model_confidence",
            confidence_avg,
            labels=labels,
            help_text="Average entity confidence"
        )

    def record_hot_swap(
        self,
        component_type: str,
        component_id: str,
        duration_ms: float,
        success: bool
    ):
        """Record hot-swap operation"""
        labels = {
            "component_type": component_type,
            "component_id": component_id,
            "status": "success" if success else "failure"
        }

        # Duration
        self.observe_histogram(
            "hot_swap_duration_ms",
            duration_ms,
            labels=labels,
            help_text="Hot-swap operation duration"
        )

        # Count
        self.increment_counter(
            "hot_swaps_total",
            labels=labels,
            help_text="Total hot-swap operations"
        )

    def get_snapshot(self) -> MetricsSnapshot:
        """Get current metrics snapshot"""
        with self._lock:
            metrics = []

            # Counters
            for key, value in self._counters.items():
                name, labels = self._parse_key(key)
                metrics.append(Metric(
                    name=name,
                    type=MetricType.COUNTER,
                    value=value,
                    labels=labels,
                    help_text=self._help_texts.get(name, "")
                ))

            # Gauges
            for key, value in self._gauges.items():
                name, labels = self._parse_key(key)
                metrics.append(Metric(
                    name=name,
                    type=MetricType.GAUGE,
                    value=value,
                    labels=labels,
                    help_text=self._help_texts.get(name, "")
                ))

            # Histograms (export percentiles)
            for key, values in self._histograms.items():
                if not values:
                    continue

                name, labels = self._parse_key(key)

                # Calculate percentiles
                sorted_values = sorted(values)
                p50 = self._percentile(sorted_values, 0.50)
                p95 = self._percentile(sorted_values, 0.95)
                p99 = self._percentile(sorted_values, 0.99)

                # Export as multiple metrics
                for quantile, value in [("0.5", p50), ("0.95", p95), ("0.99", p99)]:
                    metrics.append(Metric(
                        name=f"{name}_quantile",
                        type=MetricType.HISTOGRAM,
                        value=value,
                        labels={**labels, "quantile": quantile},
                        help_text=self._help_texts.get(name, "")
                    ))

            # Calculate aggregated stats
            request_count = len(self._request_times)
            avg_latency = 0.0
            p95_latency = 0.0
            p99_latency = 0.0
            error_rate = 0.0
            throughput = 0.0

            if self._request_times:
                latencies = [lat for _, lat in self._request_times]
                avg_latency = statistics.mean(latencies)
                p95_latency = self._percentile(sorted(latencies), 0.95)
                p99_latency = self._percentile(sorted(latencies), 0.99)

                # Error rate
                errors = sum(1 for _, status in self._request_statuses if status >= 400)
                error_rate = errors / len(self._request_statuses)

                # Throughput (requests in last window)
                cutoff = time.time() - self.aggregation_window.total_seconds()
                recent_requests = sum(1 for ts, _ in self._request_times if ts >= cutoff)
                throughput = recent_requests / self.aggregation_window.total_seconds()

            return MetricsSnapshot(
                timestamp=datetime.utcnow(),
                metrics=metrics,
                request_count=request_count,
                avg_latency_ms=avg_latency,
                p95_latency_ms=p95_latency,
                p99_latency_ms=p99_latency,
                error_rate=error_rate,
                throughput_per_second=throughput
            )

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format"""
        snapshot = self.get_snapshot()
        lines = []

        # Group metrics by name
        metrics_by_name = defaultdict(list)
        for metric in snapshot.metrics:
            metrics_by_name[metric.name].append(metric)

        for name, metrics in metrics_by_name.items():
            # Help text
            if metrics[0].help_text:
                lines.append(f"# HELP {name} {metrics[0].help_text}")

            # Type
            lines.append(f"# TYPE {name} {metrics[0].type.value}")

            # Values
            for metric in metrics:
                if metric.labels:
                    labels_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
                    lines.append(f"{name}{{{labels_str}}} {metric.value}")
                else:
                    lines.append(f"{name} {metric.value}")

            lines.append("")  # Blank line between metric groups

        return "\n".join(lines)

    def export_json(self) -> Dict[str, Any]:
        """Export metrics as JSON"""
        snapshot = self.get_snapshot()

        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "summary": {
                "request_count": snapshot.request_count,
                "avg_latency_ms": snapshot.avg_latency_ms,
                "p95_latency_ms": snapshot.p95_latency_ms,
                "p99_latency_ms": snapshot.p99_latency_ms,
                "error_rate": snapshot.error_rate,
                "throughput_per_second": snapshot.throughput_per_second
            },
            "metrics": [
                {
                    "name": m.name,
                    "type": m.type.value,
                    "value": m.value,
                    "labels": m.labels,
                    "timestamp": m.timestamp.isoformat()
                }
                for m in snapshot.metrics
            ]
        }

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create unique key for metric with labels"""
        if not labels:
            return name

        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _parse_key(self, key: str) -> tuple:
        """Parse key back into name and labels"""
        if "{" not in key:
            return key, {}

        name, labels_str = key.split("{", 1)
        labels_str = labels_str.rstrip("}")

        labels = {}
        if labels_str:
            for pair in labels_str.split(","):
                k, v = pair.split("=", 1)
                labels[k] = v

        return name, labels

    def _percentile(self, sorted_data: List[float], percentile: float) -> float:
        """Calculate percentile from sorted data"""
        if not sorted_data:
            return 0.0

        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def reset(self):
        """Reset all metrics (for testing)"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._request_times.clear()
            self._request_statuses.clear()

        logger.info("Metrics reset")


# Global metrics collector instance
_global_collector: Optional[MetricsCollector] = None


def get_global_collector() -> MetricsCollector:
    """Get global metrics collector (singleton)"""
    global _global_collector

    if _global_collector is None:
        _global_collector = MetricsCollector()
        _global_collector.start()
        logger.info("Created global metrics collector")

    return _global_collector


def reset_global_collector():
    """Reset global collector (for testing)"""
    global _global_collector
    _global_collector = None

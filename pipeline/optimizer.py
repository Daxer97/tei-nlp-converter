"""
Self-Optimization Engine

Learns from performance metrics and automatically adjusts
model and knowledge base selection for optimal results.
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from collections import defaultdict, deque
import statistics

from logger import get_logger

logger = get_logger(__name__)


class OptimizationStrategy(Enum):
    """Optimization strategies"""
    LATENCY = "latency"           # Minimize latency
    ACCURACY = "accuracy"         # Maximize accuracy
    THROUGHPUT = "throughput"     # Maximize throughput
    BALANCED = "balanced"         # Balance latency and accuracy
    COST = "cost"                 # Minimize cost


@dataclass
class PerformanceMetrics:
    """Performance metrics for a component"""
    component_id: str
    component_type: str

    # Performance
    latency_ms: float
    throughput: float  # items/second
    accuracy: float    # 0-1 score

    # Resource usage
    cpu_usage: float = 0.0
    memory_mb: float = 0.0

    # Quality
    entity_count: int = 0
    confidence_avg: float = 0.0
    error_rate: float = 0.0

    # Cost (for API-based services)
    cost_per_request: float = 0.0

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    domain: Optional[str] = None


@dataclass
class OptimizationDecision:
    """Decision made by optimizer"""
    component_type: str
    old_component_id: Optional[str]
    new_component_id: str
    reason: str
    expected_improvement: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)


class SelfOptimizer:
    """
    Self-optimizing engine that learns from performance

    Features:
    - Tracks performance metrics over time
    - Compares components (models, KBs) for same task
    - Automatically selects optimal components
    - Adapts to changing workloads
    - A/B testing for component comparison

    Example:
        optimizer = SelfOptimizer(strategy=OptimizationStrategy.BALANCED)

        # Record performance
        metrics = PerformanceMetrics(
            component_id="biobert",
            component_type="ner_model",
            latency_ms=150,
            accuracy=0.92,
            throughput=6.67
        )
        optimizer.record_metrics(metrics)

        # Get optimization recommendations
        recommendations = optimizer.get_recommendations("ner_model", domain="medical")
    """

    def __init__(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        history_size: int = 1000,
        min_samples_for_decision: int = 10,
        performance_threshold: float = 0.05
    ):
        """
        Initialize optimizer

        Args:
            strategy: Optimization strategy
            history_size: Number of metrics to keep per component
            min_samples_for_decision: Minimum samples before making decisions
            performance_threshold: Minimum improvement required to switch components
        """
        self.strategy = strategy
        self.history_size = history_size
        self.min_samples_for_decision = min_samples_for_decision
        self.performance_threshold = performance_threshold

        # Performance history: component_id -> metrics queue
        self._metrics_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=history_size)
        )

        # Optimization decisions made
        self._decisions: List[OptimizationDecision] = []

        # A/B testing experiments
        self._experiments: Dict[str, Dict[str, Any]] = {}

    def record_metrics(self, metrics: PerformanceMetrics):
        """Record performance metrics for a component"""
        key = f"{metrics.component_type}:{metrics.component_id}"
        self._metrics_history[key].append(metrics)

        logger.debug(
            f"Recorded metrics for {key}: "
            f"latency={metrics.latency_ms:.2f}ms, "
            f"accuracy={metrics.accuracy:.2f}, "
            f"throughput={metrics.throughput:.2f}/s"
        )

    def get_recommendations(
        self,
        component_type: str,
        domain: Optional[str] = None,
        current_component_id: Optional[str] = None
    ) -> List[OptimizationDecision]:
        """
        Get optimization recommendations

        Args:
            component_type: Type of component (e.g., "ner_model", "kb")
            domain: Optional domain filter
            current_component_id: Current component in use

        Returns:
            List of recommended optimization decisions
        """
        logger.debug(f"Getting recommendations for {component_type} (domain: {domain})")

        # Get all components of this type
        components = self._get_components_of_type(component_type)

        if len(components) < 2:
            logger.debug(f"Not enough components to compare ({len(components)})")
            return []

        # Filter by domain if specified
        if domain:
            components = [c for c in components if self._is_for_domain(c, domain)]

        if len(components) < 2:
            logger.debug(f"Not enough components for domain {domain}")
            return []

        # Calculate aggregate metrics for each component
        component_stats = {}
        for component_id in components:
            stats = self._calculate_aggregate_stats(component_id, domain)
            if stats:
                component_stats[component_id] = stats

        if len(component_stats) < 2:
            logger.debug("Not enough statistics to compare")
            return []

        # Find optimal component based on strategy
        optimal_id, optimal_stats = self._find_optimal_component(component_stats)

        # If no current component or optimal is better, recommend switch
        recommendations = []

        if current_component_id and current_component_id != optimal_id:
            # Compare current vs optimal
            current_stats = component_stats.get(current_component_id)

            if current_stats:
                improvement = self._calculate_improvement(current_stats, optimal_stats)

                if improvement['total'] >= self.performance_threshold:
                    decision = OptimizationDecision(
                        component_type=component_type,
                        old_component_id=current_component_id,
                        new_component_id=optimal_id,
                        reason=self._generate_recommendation_reason(improvement),
                        expected_improvement=improvement
                    )
                    recommendations.append(decision)

        elif not current_component_id:
            # No current component, recommend optimal
            decision = OptimizationDecision(
                component_type=component_type,
                old_component_id=None,
                new_component_id=optimal_id,
                reason=f"Recommended optimal component based on {self.strategy.value} strategy",
                expected_improvement={}
            )
            recommendations.append(decision)

        return recommendations

    def _get_components_of_type(self, component_type: str) -> List[str]:
        """Get all components of a given type"""
        components = set()

        for key in self._metrics_history.keys():
            ctype, cid = key.split(":", 1)
            if ctype == component_type:
                components.add(cid)

        return list(components)

    def _is_for_domain(self, component_id: str, domain: str) -> bool:
        """Check if component has metrics for domain"""
        key = f"*:{component_id}"

        for metrics_key, metrics_list in self._metrics_history.items():
            if metrics_key.endswith(f":{component_id}"):
                for metrics in metrics_list:
                    if metrics.domain == domain:
                        return True

        return False

    def _calculate_aggregate_stats(
        self,
        component_id: str,
        domain: Optional[str] = None
    ) -> Optional[Dict[str, float]]:
        """Calculate aggregate statistics for a component"""
        # Find metrics for this component
        metrics_list = []

        for key, history in self._metrics_history.items():
            if key.endswith(f":{component_id}"):
                for metrics in history:
                    if domain is None or metrics.domain == domain:
                        metrics_list.append(metrics)

        if len(metrics_list) < self.min_samples_for_decision:
            return None

        # Calculate statistics
        latencies = [m.latency_ms for m in metrics_list]
        accuracies = [m.accuracy for m in metrics_list]
        throughputs = [m.throughput for m in metrics_list]
        error_rates = [m.error_rate for m in metrics_list]
        costs = [m.cost_per_request for m in metrics_list if m.cost_per_request > 0]

        stats = {
            'latency_avg': statistics.mean(latencies),
            'latency_p50': statistics.median(latencies),
            'latency_p95': self._percentile(latencies, 0.95),
            'accuracy_avg': statistics.mean(accuracies),
            'accuracy_min': min(accuracies),
            'throughput_avg': statistics.mean(throughputs),
            'error_rate_avg': statistics.mean(error_rates),
            'sample_count': len(metrics_list)
        }

        if costs:
            stats['cost_avg'] = statistics.mean(costs)
        else:
            stats['cost_avg'] = 0.0

        return stats

    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def _find_optimal_component(
        self,
        component_stats: Dict[str, Dict[str, float]]
    ) -> Tuple[str, Dict[str, float]]:
        """Find optimal component based on strategy"""
        if not component_stats:
            raise ValueError("No components to compare")

        # Calculate scores for each component
        scores = {}

        for component_id, stats in component_stats.items():
            score = self._calculate_score(stats)
            scores[component_id] = score

        # Find component with best score
        optimal_id = max(scores, key=scores.get)
        optimal_stats = component_stats[optimal_id]

        logger.debug(f"Optimal component: {optimal_id} (score: {scores[optimal_id]:.4f})")

        return optimal_id, optimal_stats

    def _calculate_score(self, stats: Dict[str, float]) -> float:
        """Calculate score for component based on strategy"""
        if self.strategy == OptimizationStrategy.LATENCY:
            # Lower latency is better
            return 1.0 / (1.0 + stats['latency_avg'])

        elif self.strategy == OptimizationStrategy.ACCURACY:
            # Higher accuracy is better
            return stats['accuracy_avg']

        elif self.strategy == OptimizationStrategy.THROUGHPUT:
            # Higher throughput is better
            return stats['throughput_avg']

        elif self.strategy == OptimizationStrategy.COST:
            # Lower cost is better
            if stats['cost_avg'] > 0:
                return 1.0 / (1.0 + stats['cost_avg'])
            else:
                return 1.0

        elif self.strategy == OptimizationStrategy.BALANCED:
            # Balance latency and accuracy
            # Normalize latency (lower is better, typical range: 10-500ms)
            latency_score = 1.0 / (1.0 + stats['latency_avg'] / 100.0)

            # Accuracy is already 0-1 (higher is better)
            accuracy_score = stats['accuracy_avg']

            # Weighted combination (60% accuracy, 40% latency)
            return 0.6 * accuracy_score + 0.4 * latency_score

        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def _calculate_improvement(
        self,
        current_stats: Dict[str, float],
        optimal_stats: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate improvement from current to optimal"""
        improvement = {}

        # Latency improvement (negative means faster)
        latency_delta = optimal_stats['latency_avg'] - current_stats['latency_avg']
        improvement['latency'] = -latency_delta / current_stats['latency_avg']

        # Accuracy improvement
        accuracy_delta = optimal_stats['accuracy_avg'] - current_stats['accuracy_avg']
        improvement['accuracy'] = accuracy_delta

        # Throughput improvement
        throughput_delta = optimal_stats['throughput_avg'] - current_stats['throughput_avg']
        improvement['throughput'] = throughput_delta / current_stats['throughput_avg']

        # Overall improvement (strategy-weighted)
        if self.strategy == OptimizationStrategy.LATENCY:
            improvement['total'] = improvement['latency']
        elif self.strategy == OptimizationStrategy.ACCURACY:
            improvement['total'] = improvement['accuracy']
        elif self.strategy == OptimizationStrategy.THROUGHPUT:
            improvement['total'] = improvement['throughput']
        elif self.strategy == OptimizationStrategy.BALANCED:
            improvement['total'] = 0.6 * improvement['accuracy'] + 0.4 * improvement['latency']
        else:
            improvement['total'] = improvement['accuracy']

        return improvement

    def _generate_recommendation_reason(self, improvement: Dict[str, float]) -> str:
        """Generate human-readable reason for recommendation"""
        reasons = []

        if improvement.get('latency', 0) > 0.1:
            reasons.append(f"{improvement['latency']*100:.1f}% faster")

        if improvement.get('accuracy', 0) > 0.01:
            reasons.append(f"{improvement['accuracy']*100:.1f}% more accurate")

        if improvement.get('throughput', 0) > 0.1:
            reasons.append(f"{improvement['throughput']*100:.1f}% higher throughput")

        if not reasons:
            return "Marginal improvement based on overall performance"

        return "Expected improvements: " + ", ".join(reasons)

    def start_ab_test(
        self,
        experiment_id: str,
        component_type: str,
        component_a: str,
        component_b: str,
        traffic_split: float = 0.5,
        duration_hours: int = 24
    ):
        """
        Start an A/B test between two components

        Args:
            experiment_id: Unique identifier for experiment
            component_type: Type of component being tested
            component_a: First component ID
            component_b: Second component ID
            traffic_split: Fraction of traffic to component A (0-1)
            duration_hours: Duration of experiment
        """
        logger.info(
            f"Starting A/B test: {experiment_id} "
            f"({component_a} vs {component_b}, split={traffic_split})"
        )

        self._experiments[experiment_id] = {
            'component_type': component_type,
            'component_a': component_a,
            'component_b': component_b,
            'traffic_split': traffic_split,
            'started_at': datetime.utcnow(),
            'duration': timedelta(hours=duration_hours),
            'status': 'running'
        }

    def get_ab_test_results(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get results of an A/B test"""
        if experiment_id not in self._experiments:
            return None

        experiment = self._experiments[experiment_id]

        # Calculate stats for both components
        stats_a = self._calculate_aggregate_stats(experiment['component_a'])
        stats_b = self._calculate_aggregate_stats(experiment['component_b'])

        if not stats_a or not stats_b:
            return {
                'experiment_id': experiment_id,
                'status': 'insufficient_data',
                'message': 'Not enough data collected yet'
            }

        # Determine winner
        score_a = self._calculate_score(stats_a)
        score_b = self._calculate_score(stats_b)

        winner = experiment['component_a'] if score_a > score_b else experiment['component_b']
        improvement = abs(score_a - score_b) / min(score_a, score_b)

        return {
            'experiment_id': experiment_id,
            'component_a': experiment['component_a'],
            'component_b': experiment['component_b'],
            'stats_a': stats_a,
            'stats_b': stats_b,
            'score_a': score_a,
            'score_b': score_b,
            'winner': winner,
            'improvement': improvement,
            'significant': improvement >= self.performance_threshold,
            'started_at': experiment['started_at'].isoformat(),
            'status': experiment['status']
        }

    def stop_ab_test(self, experiment_id: str):
        """Stop an A/B test"""
        if experiment_id in self._experiments:
            self._experiments[experiment_id]['status'] = 'stopped'
            logger.info(f"Stopped A/B test: {experiment_id}")

    def get_decisions(
        self,
        limit: int = 10,
        component_type: Optional[str] = None
    ) -> List[OptimizationDecision]:
        """Get recent optimization decisions"""
        decisions = self._decisions

        if component_type:
            decisions = [d for d in decisions if d.component_type == component_type]

        # Sort by timestamp (most recent first)
        decisions = sorted(decisions, key=lambda d: d.timestamp, reverse=True)

        return decisions[:limit]

    def apply_decision(self, decision: OptimizationDecision):
        """Record that a decision was applied"""
        self._decisions.append(decision)
        logger.info(
            f"Applied optimization decision: "
            f"{decision.old_component_id} -> {decision.new_component_id} "
            f"({decision.reason})"
        )

    def get_performance_summary(
        self,
        component_type: Optional[str] = None,
        domain: Optional[str] = None,
        time_window_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get performance summary across components"""
        cutoff_time = None
        if time_window_hours:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_window_hours)

        summary = {
            'components': {},
            'totals': {
                'total_requests': 0,
                'avg_latency_ms': 0.0,
                'avg_accuracy': 0.0,
                'avg_throughput': 0.0
            }
        }

        all_latencies = []
        all_accuracies = []
        all_throughputs = []

        for key, history in self._metrics_history.items():
            ctype, cid = key.split(":", 1)

            # Filter by component type
            if component_type and ctype != component_type:
                continue

            # Filter by domain and time
            filtered_metrics = []
            for metrics in history:
                if domain and metrics.domain != domain:
                    continue
                if cutoff_time and metrics.timestamp < cutoff_time:
                    continue
                filtered_metrics.append(metrics)

            if not filtered_metrics:
                continue

            # Calculate component stats
            latencies = [m.latency_ms for m in filtered_metrics]
            accuracies = [m.accuracy for m in filtered_metrics]
            throughputs = [m.throughput for m in filtered_metrics]

            summary['components'][cid] = {
                'type': ctype,
                'requests': len(filtered_metrics),
                'latency_avg': statistics.mean(latencies),
                'latency_p95': self._percentile(latencies, 0.95),
                'accuracy_avg': statistics.mean(accuracies),
                'throughput_avg': statistics.mean(throughputs)
            }

            # Accumulate for totals
            all_latencies.extend(latencies)
            all_accuracies.extend(accuracies)
            all_throughputs.extend(throughputs)

        # Calculate totals
        if all_latencies:
            summary['totals']['total_requests'] = len(all_latencies)
            summary['totals']['avg_latency_ms'] = statistics.mean(all_latencies)
            summary['totals']['avg_accuracy'] = statistics.mean(all_accuracies)
            summary['totals']['avg_throughput'] = statistics.mean(all_throughputs)

        return summary

    def clear_history(self, component_id: Optional[str] = None):
        """Clear performance history"""
        if component_id:
            # Clear specific component
            keys_to_remove = [k for k in self._metrics_history.keys() if k.endswith(f":{component_id}")]
            for key in keys_to_remove:
                del self._metrics_history[key]
            logger.info(f"Cleared history for component: {component_id}")
        else:
            # Clear all
            self._metrics_history.clear()
            logger.info("Cleared all performance history")

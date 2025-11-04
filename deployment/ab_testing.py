"""
A/B Testing Framework

Integrated A/B testing for comparing component performance with
statistical significance testing.
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import statistics
import hashlib

from logger import get_logger

logger = get_logger(__name__)


class TestVariant(Enum):
    """A/B test variants"""
    CONTROL = "control"      # Variant A (baseline)
    TREATMENT = "treatment"  # Variant B (new feature)


@dataclass
class TestResult:
    """Result of A/B test"""
    test_id: str
    control_metrics: Dict[str, List[float]] = field(default_factory=dict)
    treatment_metrics: Dict[str, List[float]] = field(default_factory=dict)

    # Statistics
    control_mean: Dict[str, float] = field(default_factory=dict)
    treatment_mean: Dict[str, float] = field(default_factory=dict)
    improvement: Dict[str, float] = field(default_factory=dict)
    significant: bool = False
    confidence_level: float = 0.95

    # Test details
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    sample_size: int = 0


@dataclass
class ABTest:
    """A/B test configuration"""
    test_id: str
    description: str
    control_component: str
    treatment_component: str

    # Traffic split (0-1)
    traffic_split: float = 0.5

    # Duration
    duration: timedelta = timedelta(days=7)

    # Metrics to track
    tracked_metrics: List[str] = field(default_factory=lambda: [
        "latency", "accuracy", "throughput"
    ])

    # Status
    active: bool = False
    started_at: Optional[datetime] = None


class ABTestManager:
    """
    A/B testing manager integrated with feature flags and metrics

    Example:
        manager = ABTestManager(flag_manager, metrics_collector)

        # Create A/B test
        test = manager.create_test(
            test_id="new_ner_model_test",
            description="Compare BioBERT vs PubMedBERT",
            control_component="biobert",
            treatment_component="pubmedbert",
            traffic_split=0.5,
            duration_days=7
        )

        # Start test
        await manager.start_test(test.test_id)

        # Assign user to variant
        variant = manager.get_variant(test.test_id, user_id="user123")

        # Record metrics
        manager.record_metric(test.test_id, variant, "latency", 150.0)

        # Get results
        results = manager.get_test_results(test.test_id)
        if results.significant:
            print(f"Treatment is significantly better!")
            print(f"Improvement: {results.improvement}")
    """

    def __init__(self, flag_manager, metrics_collector=None):
        """
        Initialize A/B test manager

        Args:
            flag_manager: FeatureFlagManager instance
            metrics_collector: Optional MetricsCollector instance
        """
        self.flag_manager = flag_manager
        self.metrics_collector = metrics_collector

        # Active tests
        self._tests: Dict[str, ABTest] = {}

        # Test results
        self._results: Dict[str, TestResult] = {}

    def create_test(
        self,
        test_id: str,
        description: str,
        control_component: str,
        treatment_component: str,
        traffic_split: float = 0.5,
        duration_days: int = 7,
        tracked_metrics: Optional[List[str]] = None
    ) -> ABTest:
        """
        Create an A/B test

        Args:
            test_id: Unique test identifier
            description: Test description
            control_component: Control variant (A)
            treatment_component: Treatment variant (B)
            traffic_split: Traffic to treatment (0-1)
            duration_days: Test duration in days
            tracked_metrics: Metrics to track

        Returns:
            ABTest configuration
        """
        test = ABTest(
            test_id=test_id,
            description=description,
            control_component=control_component,
            treatment_component=treatment_component,
            traffic_split=traffic_split,
            duration=timedelta(days=duration_days),
            tracked_metrics=tracked_metrics or ["latency", "accuracy", "throughput"]
        )

        self._tests[test_id] = test

        logger.info(
            f"Created A/B test: {test_id} "
            f"({control_component} vs {treatment_component})"
        )

        return test

    async def start_test(self, test_id: str):
        """Start an A/B test"""
        if test_id not in self._tests:
            raise ValueError(f"Test not found: {test_id}")

        test = self._tests[test_id]
        test.active = True
        test.started_at = datetime.utcnow()

        # Initialize results
        self._results[test_id] = TestResult(
            test_id=test_id,
            started_at=test.started_at
        )

        logger.info(f"Started A/B test: {test_id}")

    async def stop_test(self, test_id: str):
        """Stop an A/B test"""
        if test_id not in self._tests:
            raise ValueError(f"Test not found: {test_id}")

        test = self._tests[test_id]
        test.active = False

        # Finalize results
        if test_id in self._results:
            result = self._results[test_id]
            result.completed_at = datetime.utcnow()

            # Calculate statistics
            self._calculate_test_statistics(result)

        logger.info(f"Stopped A/B test: {test_id}")

    def get_variant(self, test_id: str, user_id: str) -> TestVariant:
        """
        Assign user to variant using consistent hashing

        Args:
            test_id: Test identifier
            user_id: User identifier

        Returns:
            TestVariant (CONTROL or TREATMENT)
        """
        if test_id not in self._tests:
            return TestVariant.CONTROL

        test = self._tests[test_id]

        if not test.active:
            return TestVariant.CONTROL

        # Use consistent hashing
        hash_input = f"{test_id}:{user_id}".encode('utf-8')
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16)
        user_percentage = (hash_value % 100) / 100.0

        # Assign based on traffic split
        if user_percentage < test.traffic_split:
            return TestVariant.TREATMENT
        else:
            return TestVariant.CONTROL

    def record_metric(
        self,
        test_id: str,
        variant: TestVariant,
        metric_name: str,
        value: float
    ):
        """
        Record a metric for a variant

        Args:
            test_id: Test identifier
            variant: Variant (CONTROL or TREATMENT)
            metric_name: Metric name
            value: Metric value
        """
        if test_id not in self._results:
            return

        result = self._results[test_id]

        # Store metric
        if variant == TestVariant.CONTROL:
            if metric_name not in result.control_metrics:
                result.control_metrics[metric_name] = []
            result.control_metrics[metric_name].append(value)
        else:
            if metric_name not in result.treatment_metrics:
                result.treatment_metrics[metric_name] = []
            result.treatment_metrics[metric_name].append(value)

        result.sample_size += 1

    def get_test_results(self, test_id: str) -> Optional[TestResult]:
        """Get test results with statistics"""
        if test_id not in self._results:
            return None

        result = self._results[test_id]

        # Calculate statistics if not already done
        if not result.control_mean:
            self._calculate_test_statistics(result)

        return result

    def _calculate_test_statistics(self, result: TestResult):
        """Calculate statistical measures for test results"""
        # Calculate means
        for metric_name, values in result.control_metrics.items():
            if values:
                result.control_mean[metric_name] = statistics.mean(values)

        for metric_name, values in result.treatment_metrics.items():
            if values:
                result.treatment_mean[metric_name] = statistics.mean(values)

        # Calculate improvement
        for metric_name in result.control_mean.keys():
            if metric_name in result.treatment_mean:
                control = result.control_mean[metric_name]
                treatment = result.treatment_mean[metric_name]

                if control > 0:
                    improvement = (treatment - control) / control
                    result.improvement[metric_name] = improvement

        # Check statistical significance (simplified t-test)
        result.significant = self._is_significant(result)

    def _is_significant(self, result: TestResult) -> bool:
        """
        Check if results are statistically significant

        Simplified significance test - in production would use proper t-test
        """
        # Need sufficient sample size
        min_sample_size = 100

        for metric_name, control_values in result.control_metrics.items():
            if metric_name not in result.treatment_metrics:
                continue

            treatment_values = result.treatment_metrics[metric_name]

            if len(control_values) < min_sample_size or len(treatment_values) < min_sample_size:
                continue

            # Calculate standard deviations
            control_std = statistics.stdev(control_values) if len(control_values) > 1 else 0
            treatment_std = statistics.stdev(treatment_values) if len(treatment_values) > 1 else 0

            # Check if means are significantly different
            # Simplified: if difference is > 2 standard deviations
            control_mean = result.control_mean[metric_name]
            treatment_mean = result.treatment_mean[metric_name]

            diff = abs(treatment_mean - control_mean)
            combined_std = (control_std + treatment_std) / 2

            if combined_std > 0 and diff > 2 * combined_std:
                return True

        return False

    def list_active_tests(self) -> List[ABTest]:
        """List all active tests"""
        return [test for test in self._tests.values() if test.active]

    def get_test(self, test_id: str) -> Optional[ABTest]:
        """Get test configuration"""
        return self._tests.get(test_id)

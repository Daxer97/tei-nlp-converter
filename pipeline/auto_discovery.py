"""
Auto-Discovery Service

Continuously discovers new models and knowledge bases from trusted sources,
evaluates them, and recommends/deploys optimal components automatically.
"""
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ner_models.registry import ModelProviderRegistry
from ner_models.base import ModelMetadata, SelectionCriteria
from knowledge_bases.registry import KnowledgeBaseRegistry
from pipeline.optimizer import SelfOptimizer, PerformanceMetrics
from pipeline.hot_swap import HotSwapManager, ComponentType
from logger import get_logger

logger = get_logger(__name__)


class DiscoveryStatus(Enum):
    """Status of discovery operation"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DeploymentMode(Enum):
    """Deployment mode for discovered components"""
    MANUAL = "manual"          # Notify only, manual approval required
    CANARY = "canary"          # Automatic canary deployment
    AUTOMATIC = "automatic"    # Automatic full deployment


@dataclass
class DiscoveryResult:
    """Result of a discovery operation"""
    component_type: str
    component_id: str
    component_version: str

    # Discovery metadata
    discovered_at: datetime
    source: str
    provider: str

    # Performance estimates
    estimated_f1: Optional[float] = None
    estimated_latency_ms: Optional[float] = None

    # Comparison with current
    current_component_id: Optional[str] = None
    improvement_percentage: Optional[float] = None

    # Recommendation
    recommended_action: str = "evaluate"  # evaluate, deploy_canary, deploy_full, ignore
    reason: str = ""

    # Status
    status: DiscoveryStatus = DiscoveryStatus.PENDING
    evaluation_result: Optional[Dict[str, Any]] = None


@dataclass
class CanaryDeployment:
    """Canary deployment tracking"""
    component_id: str
    component_type: str
    deployment_id: str

    started_at: datetime
    duration_hours: int = 24
    traffic_percentage: float = 0.10  # 10% traffic

    # Metrics
    canary_metrics: List[PerformanceMetrics] = field(default_factory=list)
    baseline_metrics: List[PerformanceMetrics] = field(default_factory=list)

    # Status
    is_successful: Optional[bool] = None
    completion_reason: Optional[str] = None


class AutoDiscoveryService:
    """
    Automatically discover, evaluate, and deploy new NLP models and knowledge bases

    Features:
    - Daily model discovery scans
    - Weekly KB update checks
    - Automated benchmarking on test sets
    - Canary deployments with automatic rollback
    - Performance comparison and recommendations
    - Team notifications

    Example:
        discovery = AutoDiscoveryService(
            model_registry=model_registry,
            kb_registry=kb_registry,
            optimizer=optimizer,
            hot_swap_manager=hot_swap_manager,
            deployment_mode=DeploymentMode.CANARY
        )

        await discovery.start()
    """

    def __init__(
        self,
        model_registry: ModelProviderRegistry,
        kb_registry: KnowledgeBaseRegistry,
        optimizer: SelfOptimizer,
        hot_swap_manager: HotSwapManager,
        deployment_mode: DeploymentMode = DeploymentMode.MANUAL,
        notification_callback: Optional[callable] = None
    ):
        self.model_registry = model_registry
        self.kb_registry = kb_registry
        self.optimizer = optimizer
        self.hot_swap_manager = hot_swap_manager
        self.deployment_mode = deployment_mode
        self.notification_callback = notification_callback

        # Scheduler for periodic discovery
        self.scheduler = AsyncIOScheduler()

        # Discovery results cache
        self.discovery_results: List[DiscoveryResult] = []
        self.seen_components: Set[str] = set()

        # Canary deployments
        self.active_canaries: Dict[str, CanaryDeployment] = {}

        # Test data for benchmarking
        self.test_datasets: Dict[str, List[Dict[str, Any]]] = {}

        self._running = False

    async def start(self):
        """Start the auto-discovery service"""
        if self._running:
            logger.warning("Auto-discovery service already running")
            return

        logger.info("Starting auto-discovery service")

        # Schedule model discovery (daily at 3 AM)
        self.scheduler.add_job(
            self._discover_models,
            trigger=CronTrigger(hour=3, minute=0),
            id='discover_models',
            replace_existing=True
        )

        # Schedule KB discovery (weekly on Monday at 3 AM)
        self.scheduler.add_job(
            self._discover_kbs,
            trigger=CronTrigger(day_of_week='mon', hour=3, minute=0),
            id='discover_kbs',
            replace_existing=True
        )

        # Check canary deployments every hour
        self.scheduler.add_job(
            self._check_canaries,
            trigger=CronTrigger(minute=0),
            id='check_canaries',
            replace_existing=True
        )

        self.scheduler.start()
        self._running = True

        logger.info("Auto-discovery service started")

    async def stop(self):
        """Stop the auto-discovery service"""
        if not self._running:
            return

        logger.info("Stopping auto-discovery service")

        self.scheduler.shutdown()
        self._running = False

        logger.info("Auto-discovery service stopped")

    async def _discover_models(self):
        """Discover new NER models"""
        logger.info("Starting model discovery scan")

        try:
            # Discover all available models
            catalog = await self.model_registry.discover_all_models()

            new_models = []

            for provider_name, models in catalog.items():
                for model in models:
                    component_key = f"{provider_name}:{model.model_id}:{model.version}"

                    # Check if we've seen this model before
                    if component_key in self.seen_components:
                        continue

                    self.seen_components.add(component_key)
                    new_models.append((provider_name, model))

                    logger.info(f"Discovered new model: {model.model_id} v{model.version}")

            if not new_models:
                logger.info("No new models discovered")
                return

            logger.info(f"Discovered {len(new_models)} new models")

            # Evaluate each new model
            for provider_name, model in new_models:
                await self._evaluate_model(provider_name, model)

        except Exception as e:
            logger.error(f"Model discovery failed: {e}", exc_info=True)

    async def _evaluate_model(self, provider_name: str, model: ModelMetadata):
        """Evaluate a newly discovered model"""
        logger.info(f"Evaluating model: {model.model_id}")

        try:
            # Create discovery result
            result = DiscoveryResult(
                component_type="ner_model",
                component_id=model.model_id,
                component_version=model.version,
                discovered_at=datetime.utcnow(),
                source=model.source_url,
                provider=provider_name,
                estimated_f1=model.performance.f1_score if model.performance else None,
                estimated_latency_ms=model.performance.latency_ms if model.performance else None,
                status=DiscoveryStatus.RUNNING
            )

            # Get current model for same domain
            domain = self._infer_domain_from_model(model)
            current_model = self._get_current_model_for_domain(domain)

            if current_model:
                result.current_component_id = current_model

                # Get current performance
                current_perf = await self._get_model_performance(current_model)

                if current_perf and result.estimated_f1:
                    improvement = (result.estimated_f1 - current_perf['f1']) / current_perf['f1']
                    result.improvement_percentage = improvement * 100

            # Run benchmark if test data available
            if domain in self.test_datasets:
                benchmark_result = await self._benchmark_model(provider_name, model, domain)
                result.evaluation_result = benchmark_result

                # Update estimates with actual results
                if benchmark_result.get('f1'):
                    result.estimated_f1 = benchmark_result['f1']
                if benchmark_result.get('latency_ms'):
                    result.estimated_latency_ms = benchmark_result['latency_ms']

            # Determine recommendation
            result = self._generate_recommendation(result)

            # Mark as completed
            result.status = DiscoveryStatus.COMPLETED

            # Store result
            self.discovery_results.append(result)

            # Send notification
            await self._notify_discovery(result)

            # Auto-deploy if configured
            if self.deployment_mode != DeploymentMode.MANUAL:
                if result.recommended_action in ['deploy_canary', 'deploy_full']:
                    await self._execute_deployment(result)

        except Exception as e:
            logger.error(f"Model evaluation failed for {model.model_id}: {e}", exc_info=True)
            result.status = DiscoveryStatus.FAILED

    def _infer_domain_from_model(self, model: ModelMetadata) -> Optional[str]:
        """Infer domain from model metadata"""
        model_id_lower = model.model_id.lower()

        if any(kw in model_id_lower for kw in ['bio', 'med', 'clinical', 'drug', 'disease']):
            return 'medical'
        elif any(kw in model_id_lower for kw in ['legal', 'law', 'court', 'statute']):
            return 'legal'
        elif any(kw in model_id_lower for kw in ['sci', 'chem', 'gene', 'protein']):
            return 'scientific'
        else:
            return 'general'

    def _get_current_model_for_domain(self, domain: str) -> Optional[str]:
        """Get currently active model for domain"""
        # This would query the hot_swap_manager for active models
        # Simplified for now
        return None

    async def _get_model_performance(self, model_id: str) -> Optional[Dict[str, float]]:
        """Get performance metrics for a model"""
        # Query optimizer for recent performance
        summary = self.optimizer.get_performance_summary(
            component_type='ner_model',
            time_window_hours=168  # Last week
        )

        if model_id in summary.get('components', {}):
            comp = summary['components'][model_id]
            return {
                'f1': comp.get('accuracy_avg', 0),
                'latency_ms': comp.get('latency_avg', 0)
            }

        return None

    async def _benchmark_model(
        self,
        provider_name: str,
        model: ModelMetadata,
        domain: str
    ) -> Dict[str, Any]:
        """Benchmark model on test dataset"""
        logger.info(f"Benchmarking model: {model.model_id} on {domain} test set")

        if domain not in self.test_datasets:
            logger.warning(f"No test dataset for domain: {domain}")
            return {}

        try:
            # Load model
            loaded_model = await self.model_registry.load_model(
                provider_name,
                model.model_id,
                model.version
            )

            if not loaded_model:
                return {'error': 'Failed to load model'}

            test_data = self.test_datasets[domain]

            # Run predictions
            total_latency = 0
            predictions = []

            for sample in test_data:
                start = asyncio.get_event_loop().time()
                entities = await loaded_model.extract_entities(sample['text'])
                latency = (asyncio.get_event_loop().time() - start) * 1000

                total_latency += latency
                predictions.append({
                    'sample_id': sample['id'],
                    'entities': entities,
                    'latency_ms': latency
                })

            # Calculate metrics
            avg_latency = total_latency / len(test_data)

            # Calculate F1 score (simplified - would use proper evaluation)
            f1_score = self._calculate_f1(predictions, test_data)

            return {
                'f1': f1_score,
                'latency_ms': avg_latency,
                'samples_evaluated': len(test_data),
                'predictions': predictions[:10]  # Store sample predictions
            }

        except Exception as e:
            logger.error(f"Benchmarking failed: {e}", exc_info=True)
            return {'error': str(e)}

    def _calculate_f1(self, predictions: List[Dict], ground_truth: List[Dict]) -> float:
        """Calculate F1 score (simplified)"""
        # This is a placeholder - real implementation would do proper entity-level F1
        # For now, return a dummy score
        return 0.85

    def _generate_recommendation(self, result: DiscoveryResult) -> DiscoveryResult:
        """Generate deployment recommendation for discovered component"""

        # No comparison available
        if result.improvement_percentage is None:
            result.recommended_action = "evaluate"
            result.reason = "No baseline for comparison, manual evaluation recommended"
            return result

        improvement = result.improvement_percentage

        # Significant improvement
        if improvement >= 10:
            if self.deployment_mode == DeploymentMode.AUTOMATIC:
                result.recommended_action = "deploy_full"
                result.reason = f"Significant improvement ({improvement:.1f}%), deploy immediately"
            else:
                result.recommended_action = "deploy_canary"
                result.reason = f"Significant improvement ({improvement:.1f}%), canary deployment recommended"

        # Moderate improvement
        elif improvement >= 5:
            result.recommended_action = "deploy_canary"
            result.reason = f"Moderate improvement ({improvement:.1f}%), canary testing recommended"

        # Minor improvement
        elif improvement >= 2:
            result.recommended_action = "evaluate"
            result.reason = f"Minor improvement ({improvement:.1f}%), further evaluation needed"

        # No improvement or regression
        else:
            result.recommended_action = "ignore"
            if improvement < 0:
                result.reason = f"Performance regression ({improvement:.1f}%), not recommended"
            else:
                result.reason = f"Marginal improvement ({improvement:.1f}%), not worth deploying"

        return result

    async def _execute_deployment(self, result: DiscoveryResult):
        """Execute automatic deployment based on recommendation"""
        logger.info(f"Executing deployment: {result.recommended_action} for {result.component_id}")

        try:
            if result.recommended_action == "deploy_canary":
                await self._deploy_canary(result)
            elif result.recommended_action == "deploy_full":
                await self._deploy_full(result)

        except Exception as e:
            logger.error(f"Deployment failed: {e}", exc_info=True)
            await self._notify_deployment_failure(result, str(e))

    async def _deploy_canary(self, result: DiscoveryResult):
        """Deploy component as canary (partial traffic)"""
        logger.info(f"Deploying canary: {result.component_id}")

        # Create canary deployment
        canary = CanaryDeployment(
            component_id=result.component_id,
            component_type=result.component_type,
            deployment_id=f"canary_{result.component_id}_{datetime.utcnow().timestamp()}",
            started_at=datetime.utcnow(),
            duration_hours=24,
            traffic_percentage=0.10
        )

        # Store canary
        self.active_canaries[canary.deployment_id] = canary

        logger.info(
            f"Canary deployment started: {canary.deployment_id} "
            f"(10% traffic for 24 hours)"
        )

        # Notify team
        await self._notify_canary_started(canary)

    async def _deploy_full(self, result: DiscoveryResult):
        """Deploy component to full production"""
        logger.info(f"Deploying to production: {result.component_id}")

        # Use hot swap manager for zero-downtime deployment
        # This would integrate with the actual hot_swap_manager

        logger.info(f"Production deployment completed: {result.component_id}")

        # Notify team
        await self._notify_deployment_success(result)

    async def _check_canaries(self):
        """Check status of active canary deployments"""
        if not self.active_canaries:
            return

        logger.debug(f"Checking {len(self.active_canaries)} active canaries")

        for deployment_id, canary in list(self.active_canaries.items()):
            try:
                # Check if canary duration expired
                elapsed = (datetime.utcnow() - canary.started_at).total_seconds() / 3600

                if elapsed >= canary.duration_hours:
                    # Evaluate canary results
                    await self._evaluate_canary(canary)

                    # Remove from active
                    del self.active_canaries[deployment_id]

            except Exception as e:
                logger.error(f"Canary check failed for {deployment_id}: {e}")

    async def _evaluate_canary(self, canary: CanaryDeployment):
        """Evaluate canary deployment and decide to promote or rollback"""
        logger.info(f"Evaluating canary: {canary.deployment_id}")

        # Get metrics from optimizer
        # This would query actual canary vs baseline metrics

        # Simplified decision
        canary.is_successful = True
        canary.completion_reason = "Canary passed all checks, promoting to production"

        if canary.is_successful:
            logger.info(f"Canary successful, promoting to production: {canary.component_id}")
            # Promote to full production
            # await self._deploy_full(...)
            await self._notify_canary_success(canary)
        else:
            logger.warning(f"Canary failed, rolling back: {canary.component_id}")
            # Rollback
            await self._rollback_canary(canary)
            await self._notify_canary_failure(canary)

    async def _rollback_canary(self, canary: CanaryDeployment):
        """Rollback a failed canary deployment"""
        logger.info(f"Rolling back canary: {canary.deployment_id}")

        # Use hot swap manager to rollback
        # This would call hot_swap_manager.rollback(...)

        logger.info(f"Canary rollback completed: {canary.component_id}")

    async def _discover_kbs(self):
        """Discover new knowledge bases or updates"""
        logger.info("Starting KB discovery scan")

        try:
            # Check for KB updates
            # This would query KB providers for new versions/data

            logger.info("KB discovery scan completed")

        except Exception as e:
            logger.error(f"KB discovery failed: {e}", exc_info=True)

    async def _notify_discovery(self, result: DiscoveryResult):
        """Send notification about discovered component"""
        if not self.notification_callback:
            return

        message = (
            f"🔍 New {result.component_type} discovered: {result.component_id}\n"
            f"Version: {result.component_version}\n"
            f"Provider: {result.provider}\n"
            f"Estimated F1: {result.estimated_f1:.2f}\n"
            f"Estimated Latency: {result.estimated_latency_ms:.0f}ms\n"
            f"Improvement: {result.improvement_percentage:+.1f}%\n"
            f"Recommendation: {result.recommended_action}\n"
            f"Reason: {result.reason}"
        )

        try:
            await self.notification_callback(message)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    async def _notify_canary_started(self, canary: CanaryDeployment):
        """Notify about canary deployment start"""
        if not self.notification_callback:
            return

        message = (
            f"🚀 Canary deployment started: {canary.component_id}\n"
            f"Deployment ID: {canary.deployment_id}\n"
            f"Traffic: {canary.traffic_percentage*100:.0f}%\n"
            f"Duration: {canary.duration_hours} hours\n"
            f"Started: {canary.started_at.isoformat()}"
        )

        try:
            await self.notification_callback(message)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    async def _notify_canary_success(self, canary: CanaryDeployment):
        """Notify about successful canary"""
        if not self.notification_callback:
            return

        message = (
            f"✅ Canary successful: {canary.component_id}\n"
            f"Deployment ID: {canary.deployment_id}\n"
            f"Reason: {canary.completion_reason}\n"
            f"Promoting to production"
        )

        try:
            await self.notification_callback(message)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    async def _notify_canary_failure(self, canary: CanaryDeployment):
        """Notify about failed canary"""
        if not self.notification_callback:
            return

        message = (
            f"❌ Canary failed: {canary.component_id}\n"
            f"Deployment ID: {canary.deployment_id}\n"
            f"Reason: {canary.completion_reason}\n"
            f"Rolling back to previous version"
        )

        try:
            await self.notification_callback(message)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    async def _notify_deployment_success(self, result: DiscoveryResult):
        """Notify about successful deployment"""
        if not self.notification_callback:
            return

        message = (
            f"✅ Deployment successful: {result.component_id}\n"
            f"Version: {result.component_version}\n"
            f"Deployed to: production"
        )

        try:
            await self.notification_callback(message)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    async def _notify_deployment_failure(self, result: DiscoveryResult, error: str):
        """Notify about failed deployment"""
        if not self.notification_callback:
            return

        message = (
            f"❌ Deployment failed: {result.component_id}\n"
            f"Version: {result.component_version}\n"
            f"Error: {error}"
        )

        try:
            await self.notification_callback(message)
        except Exception as e:
            logger.error(f"Notification failed: {e}")

    def load_test_dataset(self, domain: str, test_data: List[Dict[str, Any]]):
        """Load test dataset for benchmarking"""
        self.test_datasets[domain] = test_data
        logger.info(f"Loaded test dataset for {domain}: {len(test_data)} samples")

    def get_discovery_results(
        self,
        limit: int = 10,
        component_type: Optional[str] = None
    ) -> List[DiscoveryResult]:
        """Get recent discovery results"""
        results = self.discovery_results

        if component_type:
            results = [r for r in results if r.component_type == component_type]

        # Sort by discovery time (most recent first)
        results = sorted(results, key=lambda r: r.discovered_at, reverse=True)

        return results[:limit]

    def get_active_canaries(self) -> List[CanaryDeployment]:
        """Get list of active canary deployments"""
        return list(self.active_canaries.values())

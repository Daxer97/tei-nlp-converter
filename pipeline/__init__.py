"""
Pipeline Orchestration Module

This module provides dynamic pipeline orchestration for NLP processing,
combining NER, knowledge base enrichment, and pattern matching with:
- Trust validation and security
- Hot-swapping capabilities
- Self-optimization
- Configuration-driven behavior

Quick Start:
    from pipeline import Pipeline, PipelineConfig

    # Initialize pipeline
    config = PipelineConfig.from_yaml("config/pipeline.yaml")
    pipeline = Pipeline(config)
    await pipeline.initialize()

    # Process text
    result = await pipeline.process(text, domain="medical")
"""

from .trust import (
    TrustLevel,
    TrustPolicy,
    TrustValidator,
    ModelTrustInfo,
    KBTrustInfo
)

from .hot_swap import (
    HotSwapManager,
    SwapResult,
    SwapStatus,
    ComponentType
)

from .pipeline import (
    Pipeline,
    PipelineConfig,
    PipelineResult,
    ProcessingStage
)

from .optimizer import (
    SelfOptimizer,
    OptimizationStrategy,
    PerformanceMetrics
)

__all__ = [
    # Trust validation
    "TrustLevel",
    "TrustPolicy",
    "TrustValidator",
    "ModelTrustInfo",
    "KBTrustInfo",

    # Hot swapping
    "HotSwapManager",
    "SwapResult",
    "SwapStatus",
    "ComponentType",

    # Pipeline
    "Pipeline",
    "PipelineConfig",
    "PipelineResult",
    "ProcessingStage",

    # Optimization
    "SelfOptimizer",
    "OptimizationStrategy",
    "PerformanceMetrics",
]

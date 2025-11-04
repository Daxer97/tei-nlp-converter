# Production Rollout System

The deployment system provides safe production rollout with feature flags, gradual rollout strategies, A/B testing, and emergency rollback procedures.

## Table of Contents

- [Overview](#overview)
- [Components](#components)
- [Quick Start](#quick-start)
- [Rollout Strategies](#rollout-strategies)
- [Feature Flags](#feature-flags)
- [A/B Testing](#ab-testing)
- [Rollback Procedures](#rollback-procedures)
- [Best Practices](#best-practices)

## Overview

Safe production deployment with:
- **Feature Flags**: Percentage-based rollout control
- **Gradual Rollout**: Canary, blue-green, ring deployments
- **A/B Testing**: Compare component performance
- **Rollback**: Immediate, gradual, or targeted rollback

## Components

### Feature Flags

Control feature rollout with percentage targeting:

```python
from deployment import FeatureFlagManager

manager = FeatureFlagManager()

# Create flag with 10% rollout
manager.set_flag(
    "new_ner_model",
    enabled=True,
    rollout_percentage=10,
    description="New BioBERT model"
)

# Check if enabled for user
if manager.is_enabled("new_ner_model", user_id="user123"):
    # Use new feature
    pass
else:
    # Use old feature
    pass

# Gradually increase
manager.set_rollout_percentage("new_ner_model", 25)
manager.set_rollout_percentage("new_ner_model", 50)
manager.set_rollout_percentage("new_ner_model", 100)
```

**Features:**
- Percentage-based rollout (consistent hashing)
- User/group whitelisting
- Condition-based enabling
- Kill switches (immediate disable)
- Persistent configuration

### Gradual Rollout

Multiple rollout strategies:

```python
from deployment import RolloutManager, RolloutStrategy

manager = RolloutManager(flag_manager)

# Canary: 1% -> 5% -> 10% -> 25% -> 50% -> 100%
await manager.start_rollout(
    "new_ner_model",
    strategy=RolloutStrategy.CANARY,
    validation_func=validate_model
)

# Blue-Green: validate -> switch
await manager.start_rollout(
    "new_ner_model",
    strategy=RolloutStrategy.BLUE_GREEN,
    validation_func=validate_model
)

# Check status
status = manager.get_rollout_status("new_ner_model")
print(f"Phase: {status.phase.value}")
print(f"Current: {status.current_percentage}%")
```

**Strategies:**
- **Canary**: Small percentage first, validate, increase
- **Blue-Green**: Full switch after validation
- **Percentage**: Custom percentage increases
- **Ring**: Internal -> Beta -> Production

### A/B Testing

Compare component performance:

```python
from deployment import ABTestManager

manager = ABTestManager(flag_manager, metrics_collector)

# Create test
test = manager.create_test(
    test_id="biobert_vs_pubmedbert",
    description="Compare NER models",
    control_component="biobert",
    treatment_component="pubmedbert",
    traffic_split=0.5,
    duration_days=7
)

# Start test
await manager.start_test(test.test_id)

# Assign variant
variant = manager.get_variant(test.test_id, user_id="user123")

# Record metrics
manager.record_metric(test.test_id, variant, "latency", 150.0)
manager.record_metric(test.test_id, variant, "accuracy", 0.92)

# Get results
results = manager.get_test_results(test.test_id)
if results.significant:
    print(f"Treatment is significantly better!")
    print(f"Improvement: {results.improvement}")
```

### Rollback

Emergency rollback procedures:

```python
from deployment import RollbackManager, RollbackStrategy

manager = RollbackManager(flag_manager, hot_swap_manager)

# Immediate rollback (kill switch)
result = await manager.rollback_immediate(
    "new_ner_model",
    reason="High error rate detected"
)

# Gradual rollback (100% -> 75% -> 50% -> 0%)
result = await manager.rollback_gradual(
    "new_ner_model",
    reason="Performance degradation"
)

# Targeted rollback (specific users)
result = await manager.rollback_targeted(
    "new_ner_model",
    reason="User reports",
    user_ids=["user123", "user456"]
)

# Check history
history = manager.get_rollback_history()
```

## Quick Start

### 1. Initialize Components

```python
from deployment import (
    FeatureFlagManager,
    RolloutManager,
    ABTestManager,
    RollbackManager
)
from monitoring import MetricsCollector

# Feature flags
flags = FeatureFlagManager()

# Rollout
rollout = RolloutManager(flags)

# A/B testing
metrics = MetricsCollector()
ab_test = ABTestManager(flags, metrics)

# Rollback
rollback = RollbackManager(flags)
```

### 2. Configure Feature Flags

```python
# Create flags for new features
flags.set_flag("dynamic_ner_models", enabled=True, rollout_percentage=0)
flags.set_flag("kb_enrichment", enabled=True, rollout_percentage=0)
flags.set_flag("pattern_matching", enabled=True, rollout_percentage=0)
```

### 3. Start Canary Rollout

```python
# Define validation
async def validate_model(percentage):
    # Check metrics at current percentage
    metrics = get_current_metrics()
    return metrics['error_rate'] < 0.05

# Start rollout
await rollout.start_rollout(
    "dynamic_ner_models",
    strategy=RolloutStrategy.CANARY,
    validation_func=validate_model
)
```

### 4. Monitor Progress

```python
# Check rollout status
status = rollout.get_rollout_status("dynamic_ner_models")

if status.phase == RolloutPhase.COMPLETED:
    print("Rollout completed successfully!")
elif status.phase == RolloutPhase.FAILED:
    print(f"Rollout failed: {status.error}")
    # Automatic rollback already triggered
```

## Rollout Strategies

### Canary Deployment

Best for: Gradual, low-risk rollouts

**Stages**: 1% -> 5% -> 10% -> 25% -> 50% -> 100%

**Process**:
1. Deploy to 1% of traffic
2. Monitor for 5 minutes
3. Run validation
4. If successful, advance to next stage
5. If failed, automatic rollback

**Example**:
```python
await rollout.start_rollout(
    "new_feature",
    strategy=RolloutStrategy.CANARY,
    validation_func=validate,
    target_percentage=100
)
```

### Blue-Green Deployment

Best for: Full switch after validation

**Process**:
1. Keep current version running (blue)
2. Deploy new version alongside (green)
3. Validate green environment
4. Switch all traffic to green
5. If issues, switch back to blue

**Example**:
```python
await rollout.start_rollout(
    "new_feature",
    strategy=RolloutStrategy.BLUE_GREEN,
    validation_func=validate
)
```

### Ring Deployment

Best for: Staged rollout by user groups

**Rings**:
- Internal (1%): Internal users
- Beta (10%): Beta testers
- Production (100%): All users

**Example**:
```python
await rollout.start_rollout(
    "new_feature",
    strategy=RolloutStrategy.RING,
    validation_func=validate
)
```

## Feature Flags

### Configuration

Flags are stored in `config/feature_flags.json`:

```json
{
  "flags": [
    {
      "name": "dynamic_ner_models",
      "status": "percentage",
      "rollout_percentage": 10.0,
      "enabled_users": [],
      "enabled_groups": ["internal"],
      "conditions": {}
    }
  ]
}
```

### Usage in Code

```python
# Pipeline code
if flags.is_enabled("dynamic_ner_models", user_id=user_id):
    # Use dynamic NER model selection
    models = ner_registry.get_optimal_models(domain, criteria)
else:
    # Use legacy model
    models = [legacy_model]
```

### Management

```python
# Enable for all
flags.enable_flag("feature_name")

# Disable (kill switch)
flags.disable_flag("feature_name")

# Update percentage
flags.set_rollout_percentage("feature_name", 50)

# Add users to whitelist
flags.add_user_to_flag("feature_name", "user123")

# Get stats
stats = flags.get_flag_stats("feature_name")
```

## A/B Testing

### Create Test

```python
test = ab_test.create_test(
    test_id="model_comparison",
    description="BioBERT vs PubMedBERT",
    control_component="biobert",
    treatment_component="pubmedbert",
    traffic_split=0.5,
    duration_days=7,
    tracked_metrics=["latency", "accuracy", "throughput"]
)
```

### Assign Variants

```python
# Consistent assignment per user
variant = ab_test.get_variant(test.test_id, user_id="user123")

if variant == TestVariant.CONTROL:
    model = biobert_model
else:
    model = pubmedbert_model
```

### Record Metrics

```python
# Record performance
ab_test.record_metric(test.test_id, variant, "latency", duration_ms)
ab_test.record_metric(test.test_id, variant, "accuracy", accuracy_score)
```

### Analyze Results

```python
results = ab_test.get_test_results(test.test_id)

print(f"Control mean latency: {results.control_mean['latency']:.2f}ms")
print(f"Treatment mean latency: {results.treatment_mean['latency']:.2f}ms")
print(f"Improvement: {results.improvement['latency']*100:.1f}%")
print(f"Significant: {results.significant}")

# Stop test
await ab_test.stop_test(test.test_id)
```

## Rollback Procedures

### Automatic Rollback

Triggered by validation failure:

```python
async def validate(percentage):
    metrics = get_current_metrics()

    # Check error rate
    if metrics['error_rate'] > 0.05:
        return False  # Triggers rollback

    # Check latency
    if metrics['p95_latency'] > 1000:
        return False

    return True
```

### Manual Rollback

Emergency rollback:

```python
# Immediate (kill switch)
await rollback.rollback_immediate(
    "feature_name",
    reason="Critical bug discovered"
)

# Gradual (staged reduction)
await rollback.rollback_gradual(
    "feature_name",
    reason="Performance issues",
    stages=[75, 50, 25, 0]
)
```

### Rollback to Version

```python
# Register versions
rollback.register_version("ner_model", "1.0.0")
rollback.register_version("ner_model", "2.0.0")

# Rollback to specific version
await rollback.rollback_immediate(
    "ner_model",
    reason="Bug in 2.0.0",
    rollback_to_version="1.0.0"
)
```

## Best Practices

### Feature Flags

1. **Start small**: Begin with 1-5% rollout
2. **Monitor closely**: Watch metrics during rollout
3. **Gradual increase**: Double percentage at each stage
4. **Set timeouts**: Auto-advance or require manual approval
5. **Document reasons**: Record why flags are changed

### Rollout

1. **Validate at each stage**: Don't skip validation
2. **Wait between stages**: Allow metrics to stabilize
3. **Have rollback ready**: Test rollback before rollout
4. **Communicate**: Keep stakeholders informed
5. **Monitor continuously**: Watch dashboards

### A/B Testing

1. **Sufficient sample size**: At least 100 samples per variant
2. **Equal traffic split**: Use 50/50 for unbiased results
3. **Run long enough**: Typically 7-14 days
4. **Single variable**: Test one change at a time
5. **Check significance**: Don't act on insignificant results

### Rollback

1. **Fast rollback**: Practice rollback procedures
2. **Clear triggers**: Define what triggers rollback
3. **Communication plan**: Who to notify
4. **Post-mortem**: Document what went wrong
5. **Fix forward**: Consider fixing vs rolling back

## Troubleshooting

### Feature Flag Not Working

**Symptom**: Flag enabled but feature not active

**Solution**:
- Check flag status: `flags.get_flag("name")`
- Verify percentage: User may not be in rollout
- Check conditions: Context conditions may not match
- Reload config: `flags._load_flags()`

### Rollout Stuck

**Symptom**: Rollout not advancing

**Solution**:
- Check validation: May be failing validation
- Review logs: Look for errors
- Check auto_advance: May require manual approval
- Monitor metrics: Ensure validation criteria met

### A/B Test No Results

**Symptom**: Test running but no statistical significance

**Solution**:
- Increase sample size: Run longer
- Check traffic split: Ensure users assigned
- Verify metrics recording: Check data collection
- Review implementation: Ensure variants properly assigned

## Next Steps

- See [config/deployment/rollout_plan.yaml](../config/deployment/rollout_plan.yaml) for rollout plan
- See [DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) for complete integration guide
- Configure monitoring alerts for rollout metrics
- Test rollback procedures before production
- Schedule rollout with stakeholders

# Complete Deployment Guide

This guide covers the complete deployment of the NLP Architecture v2.0, transforming from superficial label-renaming to true domain-specific entity recognition.

## Table of Contents

- [Executive Summary](#executive-summary)
- [Architecture Overview](#architecture-overview)
- [Pre-Deployment](#pre-deployment)
- [Deployment Steps](#deployment-steps)
- [Post-Deployment](#post-deployment)
- [Rollback Procedures](#rollback-procedures)

## Executive Summary

**Transformation**: Superficial label-renaming → True domain-specific NLP

**Key Improvements**:
- Dynamic NER model selection (not hardcoded)
- Knowledge base enrichment (UMLS, RxNorm, USC, CourtListener)
- Pattern matching for structured data (ICD codes, citations)
- Zero-downtime hot-swapping
- Self-optimization
- Comprehensive monitoring

**Rollout Strategy**: Canary deployment (1% → 5% → 10% → 25% → 50% → 100%)

**Timeline**: 4-6 weeks from start to 100% rollout

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    NLP Pipeline v2.0                      │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │     NER     │  │     KB      │  │   Pattern   │      │
│  │   Models    │  │ Enrichment  │  │  Matching   │      │
│  └─────────────┘  └─────────────┘  └─────────────┘      │
│         │                │                │               │
│         └────────────────┴────────────────┘               │
│                          │                                │
│                          ▼                                │
│              ┌──────────────────────┐                     │
│              │Pipeline Orchestration│                     │
│              └──────────────────────┘                     │
│                          │                                │
│         ┌────────────────┼────────────────┐              │
│         ▼                ▼                ▼              │
│  ┌──────────┐     ┌──────────┐    ┌──────────┐         │
│  │  Trust   │     │Hot-Swap  │    │Optimizer │         │
│  │Validation│     │ Manager  │    │          │         │
│  └──────────┘     └──────────┘    └──────────┘         │
│                                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Monitoring & Observability            │  │
│  │  - Metrics    - Health     - Discovery - Reload   │  │
│  └────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │            Deployment & Rollout Control            │  │
│  │  - Flags   - Rollout   - A/B Test  - Rollback    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                            │
└──────────────────────────────────────────────────────────┘
```

## Pre-Deployment

### 1. Prerequisites

**Infrastructure**:
- [ ] PostgreSQL database (14+)
- [ ] Redis cache (6+)
- [ ] Python 3.9+
- [ ] Sufficient RAM (8GB+ recommended)
- [ ] GPU optional (for models)

**External Services**:
- [ ] UMLS API key (https://uts.nlm.nih.gov)
- [ ] Network access to RxNorm API
- [ ] Network access to GovInfo API
- [ ] Network access to CourtListener API

**Monitoring**:
- [ ] Prometheus server
- [ ] Grafana dashboard
- [ ] Alert manager configured

### 2. Installation

```bash
# Clone repository
git clone <repository-url>
cd tei-nlp-converter

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Download spaCy models
python -m spacy download en_core_web_lg
python -m spacy download en_ner_bc5cdr_md

# Configure environment
cp .env.example .env
# Edit .env with API keys and configuration
```

### 3. Configuration

**Database** (`.env`):
```env
DATABASE_URL=postgresql://user:pass@localhost/nlp_db
REDIS_URL=redis://localhost:6379
```

**API Keys** (`.env`):
```env
UMLS_API_KEY=your_umls_api_key_here
```

**Feature Flags** (`config/feature_flags.json`):
```json
{
  "flags": [
    {
      "name": "dynamic_ner_models",
      "status": "percentage",
      "rollout_percentage": 0.0
    }
  ]
}
```

### 4. Testing

Run comprehensive tests:

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# End-to-end tests
pytest tests/e2e/

# Performance tests
pytest tests/performance/
```

### 5. Backup

Create backup of current system:

```bash
# Database backup
pg_dump nlp_db > backup_$(date +%Y%m%d).sql

# Configuration backup
tar -czf config_backup.tar.gz config/

# Application backup
tar -czf app_backup.tar.gz .
```

## Deployment Steps

### Phase 1: Monitoring Setup (Day 1)

**Goal**: Establish observability before rollout

```python
from monitoring import MetricsCollector, HealthCheckManager

# Initialize metrics
metrics = MetricsCollector()
metrics.start()

# Initialize health checks
health = HealthCheckManager()
health.register_check("database", check_database, interval_seconds=30)
health.register_check("redis", check_redis, interval_seconds=30)
await health.start()

# Verify dashboards
# - Grafana: http://localhost:3000
# - Prometheus: http://localhost:9090
# - Metrics: http://localhost:8000/metrics
# - Health: http://localhost:8000/health
```

**Validation**:
- [ ] Metrics endpoint responding
- [ ] Health checks passing
- [ ] Grafana dashboard showing data
- [ ] Alerts configured

### Phase 2: Feature Flag Setup (Day 2)

**Goal**: Configure feature flags for gradual rollout

```python
from deployment import FeatureFlagManager

flags = FeatureFlagManager()

# Create flags (all disabled initially)
flags.set_flag("dynamic_ner_models", enabled=True, rollout_percentage=0)
flags.set_flag("kb_enrichment", enabled=True, rollout_percentage=0)
flags.set_flag("pattern_matching", enabled=True, rollout_percentage=0)
flags.set_flag("pipeline_orchestration", enabled=True, rollout_percentage=0)
```

**Validation**:
- [ ] Flags created in config file
- [ ] All flags at 0% rollout
- [ ] Feature check working in code

### Phase 3: Canary Rollout - 1% (Days 3-4)

**Goal**: Deploy to internal users (1%)

```python
from deployment import RolloutManager, RolloutStrategy

rollout = RolloutManager(flags)

# Start canary rollout
await rollout.start_rollout(
    "dynamic_ner_models",
    strategy=RolloutStrategy.CANARY,
    validation_func=validate_stage,
    target_percentage=100
)

# Validation function
async def validate_stage(percentage):
    snapshot = metrics.get_snapshot()

    # Check error rate < 5%
    if snapshot.error_rate > 0.05:
        return False

    # Check latency P95 < 500ms
    if snapshot.p95_latency_ms > 500:
        return False

    return True
```

**Monitoring** (24 hours):
- [ ] Error rate < 5%
- [ ] P95 latency < 500ms
- [ ] No critical alerts
- [ ] User feedback positive

**Rollback Trigger**:
```python
if error_rate > 0.10:
    await rollback.rollback_immediate(
        "dynamic_ner_models",
        reason="High error rate"
    )
```

### Phase 4: Canary Rollout - 5% (Days 5-7)

**Goal**: Expand to early adopters

```python
# Automatic advance if Phase 3 successful
# Rollout manager will advance to 5%
```

**Monitoring** (48 hours):
- [ ] Error rate < 3%
- [ ] Accuracy improvement visible
- [ ] KB enrichment working
- [ ] Pattern matching accurate

### Phase 5: Canary Rollout - 10% (Days 8-11)

**Goal**: Beta user validation

```python
# Add beta users to whitelist
flags.add_group_to_flag("dynamic_ner_models", "beta_users")
```

**Monitoring** (72 hours):
- [ ] Error rate < 2%
- [ ] User satisfaction > 4.0/5.0
- [ ] Performance acceptable
- [ ] No major bugs

### Phase 6: Canary Rollout - 25% (Days 12-19)

**Goal**: Quarter rollout

**Monitoring** (1 week):
- [ ] Error rate < 2%
- [ ] Throughput maintained
- [ ] Cost within budget
- [ ] Scaling working

### Phase 7: Canary Rollout - 50% (Days 20-33)

**Goal**: Half rollout

**Monitoring** (2 weeks):
- [ ] Error rate < 1%
- [ ] All components stable
- [ ] Self-optimization learning
- [ ] Hot-swapping tested

### Phase 8: Full Rollout - 100% (Day 34+)

**Goal**: Complete deployment

```python
# Advance to 100%
flags.set_rollout_percentage("dynamic_ner_models", 100)
flags.enable_flag("dynamic_ner_models")

# Enable additional features
flags.enable_flag("hot_swapping")
flags.enable_flag("self_optimization")
```

**Validation**:
- [ ] All users on new system
- [ ] Old system decommissioned
- [ ] Monitoring continuous
- [ ] Documentation updated

## Post-Deployment

### 1. Monitoring

**Continuous Monitoring**:
- Check Grafana dashboards daily
- Review alerts immediately
- Monitor error rates
- Track performance trends

**Key Metrics**:
- Error rate < 1%
- P95 latency < 300ms
- Accuracy > 90%
- Cache hit rate > 70%

### 2. Optimization

**Enable Self-Optimization**:
```python
# After 1-2 weeks of data collection
flags.enable_flag("self_optimization")

# Review optimization recommendations
from pipeline import SelfOptimizer

optimizer = SelfOptimizer(strategy=OptimizationStrategy.BALANCED)
recommendations = optimizer.get_recommendations("ner_model", domain="medical")

for rec in recommendations:
    print(f"Switch to {rec.new_component_id}: {rec.reason}")
```

### 3. A/B Testing

**Test Component Variants**:
```python
from deployment import ABTestManager

ab_test = ABTestManager(flags, metrics)

# Compare models
test = ab_test.create_test(
    test_id="biobert_vs_pubmedbert",
    control_component="biobert",
    treatment_component="pubmedbert",
    traffic_split=0.5,
    duration_days=7
)

await ab_test.start_test(test.test_id)
```

### 4. Documentation

**Update Documentation**:
- [ ] Update API documentation
- [ ] Document new features
- [ ] Update runbooks
- [ ] Train team members

### 5. Feedback Collection

**Gather Feedback**:
- [ ] User surveys
- [ ] Stakeholder interviews
- [ ] Performance analysis
- [ ] Cost analysis

## Rollback Procedures

### Emergency Rollback (Immediate)

**Trigger Conditions**:
- Error rate > 10%
- Critical bug discovered
- Data corruption
- Security incident

**Procedure**:
```python
from deployment import RollbackManager

rollback = RollbackManager(flags, hot_swap_manager)

# Immediate rollback (kill switch)
result = await rollback.rollback_immediate(
    "dynamic_ner_models",
    reason="Critical bug - ticket #123",
    rollback_to_version="1.0.0"
)

# Verify rollback
status = rollout.get_rollout_status("dynamic_ner_models")
assert status.phase == RolloutPhase.ROLLED_BACK
```

**Duration**: < 5 minutes

### Gradual Rollback

**Trigger Conditions**:
- Performance degradation
- Increased latency
- User complaints
- Non-critical bugs

**Procedure**:
```python
# Gradual rollback (staged)
result = await rollback.rollback_gradual(
    "dynamic_ner_models",
    reason="Performance issues - ticket #124",
    stages=[75, 50, 25, 10, 0]
)
```

**Duration**: 2-4 hours

### Validation After Rollback

```python
# Verify system health
health_status = await health.get_health_status()
assert health_status['overall_status'] == 'healthy'

# Verify metrics
snapshot = metrics.get_snapshot()
assert snapshot.error_rate < 0.01

# Verify feature flags
flag = flags.get_flag("dynamic_ner_models")
assert flag.rollout_percentage == 0.0
```

## Troubleshooting

### High Error Rate

**Symptom**: Error rate > 5%

**Investigation**:
1. Check logs: `tail -f logs/app.log`
2. Check metrics: Grafana dashboard
3. Check health: `/health` endpoint
4. Check external APIs: UMLS, RxNorm status

**Solution**:
- If > 10%: Immediate rollback
- If 5-10%: Pause rollout, investigate
- If < 5%: Monitor closely

### High Latency

**Symptom**: P95 latency > 1000ms

**Investigation**:
1. Check pipeline stage times
2. Check KB lookup times
3. Check cache hit rates
4. Check model loading

**Solution**:
- Enable caching
- Reduce concurrent KB lookups
- Use faster models
- Scale horizontally

### Failed Health Checks

**Symptom**: Components unhealthy

**Investigation**:
1. Database connection
2. Redis connection
3. External API access
4. Model loading

**Solution**:
- Restart failed components
- Check network connectivity
- Verify credentials
- Check resource limits

## Success Criteria

**Technical**:
- [ ] Error rate < 1%
- [ ] P95 latency < 300ms
- [ ] Accuracy > 90%
- [ ] Zero critical incidents
- [ ] Hot-swapping working
- [ ] Self-optimization active

**Business**:
- [ ] Entity extraction improved
- [ ] Knowledge enrichment accurate
- [ ] Pattern matching precise
- [ ] Cost neutral or reduced
- [ ] User satisfaction high
- [ ] Stakeholder approval

## Contact

**Primary On-Call**: nlp-on-call@example.com
**Team Lead**: nlp-team-lead@example.com
**Slack**: #nlp-alerts

## References

- [Architecture Overview](ARCHITECTURE.md)
- [NER Models](ner_models/README.md)
- [Knowledge Bases](knowledge_bases/README.md)
- [Pattern Matching](pattern_matching/README.md)
- [Pipeline](pipeline/README.md)
- [Monitoring](monitoring/README.md)
- [Deployment](deployment/README.md)
- [Rollout Plan](config/deployment/rollout_plan.yaml)

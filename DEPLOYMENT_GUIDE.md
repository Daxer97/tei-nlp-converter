# Deployment & Migration Guide

**TEI NLP Converter - Domain-Specific NLP Architecture**
**Version:** 2.2.0
**Date:** 2025-11-05

---

## Executive Summary

This guide provides step-by-step instructions for deploying the new domain-specific NLP pipeline to production with zero downtime. The deployment follows a 4-week gradual rollout strategy with automatic monitoring, A/B testing, and rollback capabilities.

### Key Points

- **Deployment Strategy**: Gradual rollout (0% → 10% → 50% → 100%)
- **Timeline**: 4 weeks from canary to full production
- **Risk Level**: Low (feature flags + automatic rollback)
- **Rollback Time**: Instant (kill switch) or gradual
- **Expected Downtime**: Zero

---

## Quick Start

For experienced operators who want to deploy immediately:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download models
python scripts/download_models.sh

# 3. Configure environment
export UMLS_API_KEY="your-key"
export FEATURE_FLAG_NEW_PIPELINE_PERCENTAGE=0.0

# 4. Initialize
python scripts/initialize_components.py

# 5. Enable for 10% of users
python scripts/enable_canary.py --percentage=10

# 6. Monitor
open http://grafana.local/d/pipeline-overview

# 7. Gradually increase over 4 weeks
python scripts/gradual_rollout.py --days=28
```

---

## Prerequisites

### System Requirements
- **CPU**: 8 cores recommended
- **RAM**: 32GB recommended
- **Disk**: 50GB free
- **GPU**: Optional (2x faster inference)

### Required Services
- PostgreSQL 14+
- Redis 7+
- Kubernetes (for production)
- Grafana + Prometheus (monitoring)

### API Keys
- **UMLS**: https://uts.nlm.nih.gov/uts/
- **CourtListener**: https://www.courtlistener.com/api/ (optional)

---

## Deployment Timeline

### Week 1: Internal Testing (0%)
- Deploy infrastructure
- Enable for internal users only
- Run integration tests
- Verify metrics

### Week 2: Canary (10%)
- Enable for 10% of production users
- Monitor A/B test results
- Compare old vs new pipeline
- Ready rollback if needed

### Week 3: Expansion (50%)
- Gradually increase to 50%
- Daily monitoring
- Performance optimization
- Verify stability

### Week 4: Full Production (100%)
- Complete rollout to 100%
- Monitor for 48 hours
- Decommission old pipeline
- Archive legacy code

---

## Monitoring

### Grafana Dashboards

Import dashboards from `config/monitoring/`:
1. **Pipeline Overview**: Entity extraction rates, latency, success rate
2. **Model Performance**: Per-model metrics, ensemble agreement
3. **KB Performance**: Cache hit rates, enrichment success

### Key Metrics

**Performance:**
- Pipeline latency p95 < 500ms
- Throughput > 100 docs/sec
- Success rate > 95%

**Accuracy:**
- Medical F1 > 0.85
- Legal detection > 0.80
- KB enrichment > 90%

**System:**
- CPU < 80%
- Memory < 85%
- Disk > 15% free

### Alerts

Prometheus alerts in `config/monitoring/prometheus-alerts.yml`:
- High latency (> 1s)
- High error rate (> 10%)
- Low cache hit rate (< 60%)
- Low ensemble agreement (< 50%)

---

## Rollback Procedures

### Emergency Rollback (Instant)

```python
from feature_flags import get_feature_flags

flags = get_feature_flags()
flags.activate_kill_switch(
    "new_nlp_pipeline",
    reason="Critical error rate spike"
)
```

### Gradual Rollback

```python
# Reduce to 10%
flags.update_flag("new_nlp_pipeline", rollout_percentage=10.0)

# Or disable completely
flags.update_flag("new_nlp_pipeline", rollout_percentage=0.0)
```

### When to Rollback

| Trigger | Severity | Action |
|---------|----------|--------|
| Error rate > 2x | Critical | Kill switch |
| Latency > 2s | Critical | Kill switch |
| F1 drop > 10% | High | Gradual to 10% |
| User complaints | Medium | Investigate first |

---

## Troubleshooting

### High Latency

**Diagnosis:**
```bash
python scripts/analyze_latency.py
```

**Solutions:**
1. Scale horizontally: `kubectl scale deployment nlp-service --replicas=10`
2. Reduce ensemble size: `config.max_models = 2`
3. Use faster models: `config.max_latency_ms = 200`

### Low Accuracy

**Diagnosis:**
```bash
python scripts/analyze_failures.py --days=7
```

**Solutions:**
1. Add more models: `config.max_models = 4`
2. Lower confidence threshold: `config.ner_min_confidence = 0.6`
3. Check ensemble agreement: Should be > 70%

### KB Failures

**Diagnosis:**
```bash
python scripts/check_kb_health.py
```

**Solutions:**
1. Verify API keys: `echo $UMLS_API_KEY`
2. Check connectivity: `curl https://uts-ws.nlm.nih.gov/rest/`
3. Increase cache: `config.memory_cache_size = 20000`

### High Memory Usage

**Diagnosis:**
```bash
ps aux | grep python | sort -k4 -nr
```

**Solutions:**
1. Unload unused models: `model_registry.unload_model("model-id")`
2. Reduce cache: `config.memory_cache_size = 5000`
3. Increase pod memory: Edit Kubernetes deployment

---

## Success Criteria

### Phase Completion Checklist

**Week 1 (Internal):**
- [ ] 0 critical errors
- [ ] F1 improvements verified
- [ ] Latency < 500ms
- [ ] Positive feedback

**Week 2 (Canary 10%):**
- [ ] Error rate ≤ baseline
- [ ] Latency stable
- [ ] A/B test favorable
- [ ] No complaints

**Week 3 (50%):**
- [ ] Metrics stable
- [ ] No degradation
- [ ] Accuracy confirmed

**Week 4 (100%):**
- [ ] 48h stable operation
- [ ] All metrics met
- [ ] Ready to decommission old

---

## Support

**Documentation**: See `docs/` directory
**Issues**: https://github.com/Daxer97/tei-nlp-converter/issues
**Runbooks**: See `docs/runbooks/`

For urgent issues during deployment, use the kill switch immediately and investigate afterwards.

---

**Document Version:** 1.0
**Last Updated:** 2025-11-05

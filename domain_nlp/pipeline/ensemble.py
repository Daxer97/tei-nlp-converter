"""
Ensemble merging strategies for combining results from multiple models.
"""

import logging
from collections import defaultdict, Counter
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from ..model_providers.base import Entity

logger = logging.getLogger(__name__)


@dataclass
class SpanKey:
    """Key for grouping entities by span"""
    start: int
    end: int

    def __hash__(self):
        return hash((self.start, self.end))

    def __eq__(self, other):
        return self.start == other.start and self.end == other.end


class EnsembleMerger:
    """Merges entity predictions from multiple models"""

    def __init__(self, strategy: str = "majority_vote"):
        """
        Initialize merger with strategy.

        Args:
            strategy: "majority_vote", "weighted_vote", "union", "intersection"
        """
        self.strategy = strategy

    def merge(
        self,
        model_results: List[List[Entity]],
        weights: List[float] = None
    ) -> List[Entity]:
        """
        Merge results from multiple models.

        Args:
            model_results: List of entity lists, one per model
            weights: Optional weights for each model (for weighted_vote)

        Returns:
            Consolidated list of entities
        """
        if not model_results:
            return []

        if len(model_results) == 1:
            return model_results[0]

        if self.strategy == "majority_vote":
            return self._majority_vote(model_results)
        elif self.strategy == "weighted_vote":
            return self._weighted_vote(model_results, weights)
        elif self.strategy == "union":
            return self._union_merge(model_results)
        elif self.strategy == "intersection":
            return self._intersection_merge(model_results)
        else:
            logger.warning(f"Unknown strategy '{self.strategy}', using majority_vote")
            return self._majority_vote(model_results)

    def _majority_vote(self, model_results: List[List[Entity]]) -> List[Entity]:
        """Merge using majority voting on entity type"""
        # Group entities by span
        span_groups = self._group_by_span(model_results)

        consolidated = []
        for span_key, entities in span_groups.items():
            if len(entities) == 1:
                # Only one model found this span
                entity = entities[0]
                entity.confidence = entity.confidence * 0.7  # Lower confidence
                consolidated.append(entity)
            else:
                # Multiple models - vote on type
                type_votes = Counter([e.type for e in entities])
                winning_type, vote_count = type_votes.most_common(1)[0]

                # Calculate confidence based on agreement
                agreement_ratio = vote_count / len(entities)

                # Average confidence of agreeing models
                agreeing_confidences = [
                    e.confidence for e in entities if e.type == winning_type
                ]
                avg_confidence = sum(agreeing_confidences) / len(agreeing_confidences)

                # Boost confidence based on agreement
                final_confidence = avg_confidence * (0.5 + 0.5 * agreement_ratio)

                # Use text from first agreeing entity
                base_entity = next(e for e in entities if e.type == winning_type)

                merged_entity = Entity(
                    text=base_entity.text,
                    type=winning_type,
                    start=span_key.start,
                    end=span_key.end,
                    confidence=min(final_confidence, 1.0),
                    model_id="ensemble",
                    sources=[e.model_id for e in entities if e.model_id],
                    metadata={
                        "vote_count": vote_count,
                        "total_models": len(entities),
                        "agreement_ratio": agreement_ratio,
                        "all_types": dict(type_votes)
                    }
                )
                consolidated.append(merged_entity)

        # Sort by position
        consolidated.sort(key=lambda e: (e.start, e.end))
        return consolidated

    def _weighted_vote(
        self,
        model_results: List[List[Entity]],
        weights: List[float] = None
    ) -> List[Entity]:
        """Merge using weighted voting"""
        if weights is None:
            weights = [1.0] * len(model_results)

        if len(weights) != len(model_results):
            logger.warning("Weight count mismatch, using equal weights")
            weights = [1.0] * len(model_results)

        # Normalize weights
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        # Group by span with weights
        span_groups: Dict[SpanKey, List[Tuple[Entity, float]]] = defaultdict(list)

        for model_idx, entities in enumerate(model_results):
            weight = weights[model_idx]
            for entity in entities:
                key = SpanKey(entity.start, entity.end)
                span_groups[key].append((entity, weight))

        consolidated = []
        for span_key, weighted_entities in span_groups.items():
            # Weighted vote on type
            type_weights: Dict[str, float] = defaultdict(float)
            for entity, weight in weighted_entities:
                type_weights[entity.type] += weight

            winning_type = max(type_weights.items(), key=lambda x: x[1])[0]
            winning_weight = type_weights[winning_type]

            # Calculate weighted average confidence
            agreeing_entities = [
                (e, w) for e, w in weighted_entities if e.type == winning_type
            ]
            weighted_conf = sum(e.confidence * w for e, w in agreeing_entities)
            total_weight = sum(w for _, w in agreeing_entities)
            avg_confidence = weighted_conf / total_weight if total_weight > 0 else 0.5

            # Confidence based on winning weight
            final_confidence = avg_confidence * winning_weight

            base_entity = agreeing_entities[0][0]

            merged_entity = Entity(
                text=base_entity.text,
                type=winning_type,
                start=span_key.start,
                end=span_key.end,
                confidence=min(final_confidence, 1.0),
                model_id="ensemble",
                sources=[e.model_id for e, _ in weighted_entities if e.model_id],
                metadata={
                    "winning_weight": winning_weight,
                    "type_weights": dict(type_weights)
                }
            )
            consolidated.append(merged_entity)

        consolidated.sort(key=lambda e: (e.start, e.end))
        return consolidated

    def _union_merge(self, model_results: List[List[Entity]]) -> List[Entity]:
        """Merge by taking union of all entities (resolve conflicts)"""
        # Collect all entities
        all_entities = []
        for entities in model_results:
            all_entities.extend(entities)

        if not all_entities:
            return []

        # Sort by start position
        all_entities.sort(key=lambda e: (e.start, e.end))

        # Resolve overlapping entities (keep highest confidence)
        consolidated = []
        for entity in all_entities:
            # Check if overlaps with any consolidated entity
            overlaps = False
            for i, existing in enumerate(consolidated):
                if self._entities_overlap(entity, existing):
                    overlaps = True
                    # Keep one with higher confidence
                    if entity.confidence > existing.confidence:
                        consolidated[i] = entity
                    break

            if not overlaps:
                consolidated.append(entity)

        return consolidated

    def _intersection_merge(self, model_results: List[List[Entity]]) -> List[Entity]:
        """Merge by keeping only entities found by all models"""
        if not model_results:
            return []

        if len(model_results) == 1:
            return model_results[0]

        # Get spans found by each model
        model_spans: List[set] = []
        for entities in model_results:
            spans = {SpanKey(e.start, e.end) for e in entities}
            model_spans.append(spans)

        # Find intersection of all spans
        common_spans = model_spans[0]
        for spans in model_spans[1:]:
            common_spans = common_spans.intersection(spans)

        # Build consolidated list from common spans
        consolidated = []
        for span_key in common_spans:
            # Get entities for this span from all models
            span_entities = []
            for entities in model_results:
                for entity in entities:
                    if entity.start == span_key.start and entity.end == span_key.end:
                        span_entities.append(entity)
                        break

            if span_entities:
                # Majority vote on type
                type_votes = Counter([e.type for e in span_entities])
                winning_type = type_votes.most_common(1)[0][0]

                # High confidence since all models agree on span
                avg_confidence = sum(e.confidence for e in span_entities) / len(span_entities)

                base_entity = span_entities[0]
                merged_entity = Entity(
                    text=base_entity.text,
                    type=winning_type,
                    start=span_key.start,
                    end=span_key.end,
                    confidence=min(avg_confidence * 1.2, 1.0),  # Boost for consensus
                    model_id="ensemble",
                    sources=[e.model_id for e in span_entities if e.model_id]
                )
                consolidated.append(merged_entity)

        consolidated.sort(key=lambda e: (e.start, e.end))
        return consolidated

    def _group_by_span(
        self,
        model_results: List[List[Entity]]
    ) -> Dict[SpanKey, List[Entity]]:
        """Group entities by their text span"""
        span_groups: Dict[SpanKey, List[Entity]] = defaultdict(list)

        for entities in model_results:
            for entity in entities:
                key = SpanKey(entity.start, entity.end)
                span_groups[key].append(entity)

        return span_groups

    def _entities_overlap(self, e1: Entity, e2: Entity) -> bool:
        """Check if two entities overlap in text span"""
        return not (e1.end <= e2.start or e2.end <= e1.start)

    def calculate_agreement_score(self, model_results: List[List[Entity]]) -> float:
        """
        Calculate overall agreement score between models.

        Returns value between 0 (no agreement) and 1 (perfect agreement).
        """
        if len(model_results) <= 1:
            return 1.0

        span_groups = self._group_by_span(model_results)

        if not span_groups:
            return 1.0  # No entities found by any model

        # Calculate agreement for each span
        agreements = []
        for span_key, entities in span_groups.items():
            if len(entities) == len(model_results):
                # All models found this span
                type_votes = Counter([e.type for e in entities])
                max_agreement = max(type_votes.values()) / len(entities)
                agreements.append(max_agreement)
            else:
                # Not all models found this span
                agreements.append(len(entities) / len(model_results) * 0.5)

        return sum(agreements) / len(agreements) if agreements else 1.0

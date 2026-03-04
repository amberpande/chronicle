"""
SnowMemory Compound Salience Engine (CSS)
Patent-grade novelty scoring with 5 components:

  CSS(e) = α·Semantic_Novelty
         + β·Temporal_Decay_Gap
         + γ·Relational_Orphan_Score   ← novel: graph position as salience signal
         + δ·Access_Frequency_Inverse
         + ε·Momentum

Plus Domain-Normalized Novelty Score (DNNS) — normalizes for vocabulary bias
across heterogeneous data sources (the enterprise moat).
"""
from __future__ import annotations
import math
from collections import deque
from datetime import datetime, timedelta
from typing import List, Optional

from ..core.models import Memory, MemoryEvent, MemoryType, SalienceScore
from ..config.schema import SalienceConfig
from ..backends.base import MemoryBackend


def _cosine_distance(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    sim = dot / (na * nb + 1e-9)
    return 1.0 - max(-1.0, min(1.0, sim))


class SalienceEngine:
    """
    Computes the Compound Salience Score (CSS) for a candidate memory.
    High CSS → write to store. Low CSS → skip (already known).
    """

    def __init__(self, config: SalienceConfig, backend: MemoryBackend):
        self.config  = config
        self.backend = backend
        # Sliding window of recent salience scores for momentum
        self._recent: deque = deque(maxlen=config.momentum_window)

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def score(
        self,
        event: MemoryEvent,
        embedding: List[float],
        domain: str,
        agent_id: str,
        existing_entities: Optional[List[str]] = None,
    ) -> SalienceScore:
        """
        Compute CSS for event. All components are in [0, 1].
        Returns SalienceScore with final score and breakdown.
        """
        k = self.config.k_neighbors

        # ── 1. Semantic Novelty (core) ────────────────────────────
        neighbors = self.backend.get_neighbors(
            embedding, k=k, agent_id=agent_id
        )
        if not neighbors or not any(m.embedding for m in neighbors):
            raw_novelty = 1.0  # completely new territory
        else:
            distances   = [_cosine_distance(embedding, m.embedding)
                           for m in neighbors if m.embedding]
            raw_novelty = float(sum(distances) / len(distances))

        # ── 2. Domain-Normalized Novelty (DNNS) ──────────────────
        if self.config.domain_normalization:
            stats = self.backend.get_domain_stats(domain)
            mean, std = stats["mean"], stats.get("std", 0.2)
            std = max(std, self.config.domain_smoothing)
            # z-score normalized, then sigmoid to [0,1]
            z_novelty = (raw_novelty - mean) / std
            novelty   = 1.0 / (1.0 + math.exp(-z_novelty * 0.5))
        else:
            novelty = raw_novelty

        # Update domain stats (online)
        self.backend.update_domain_stats(domain, raw_novelty)

        # ── 3. Temporal Decay Gap ─────────────────────────────────
        temporal_gap = self._temporal_gap_score(neighbors)

        # ── 4. Relational Orphan Score ────────────────────────────
        orphan_score = self._orphan_score(
            existing_entities or [], agent_id
        )

        # ── 5. Access Frequency Inverse ──────────────────────────
        access_inv = self._access_inverse(neighbors)

        # ── 6. Momentum ──────────────────────────────────────────
        momentum = self._momentum_score()

        # ── 7. Cross-Domain Bridge Score ─────────────────────────
        bridge = self._bridge_score(embedding, domain, agent_id)

        # ── CSS Final Score ───────────────────────────────────────
        cfg  = self.config
        css  = (
            cfg.novelty_weight      * novelty
          + cfg.temporal_gap_weight * temporal_gap
          + cfg.orphan_score_weight * orphan_score
          + cfg.access_inv_weight   * access_inv
          + cfg.momentum_weight     * momentum
        )
        css  = max(0.0, min(1.0, css))

        # Record for future momentum calculations
        self._recent.append(css)

        return SalienceScore(
            score        = css,
            novelty      = novelty,
            temporal_gap = temporal_gap,
            orphan_score = orphan_score,
            access_inv   = access_inv,
            momentum     = momentum,
            bridge_score = bridge,
            domain       = domain,
            nearest_ids  = [m.memory_id for m in neighbors],
        )

    # ─────────────────────────────────────────────────────────────
    # Component Methods
    # ─────────────────────────────────────────────────────────────

    def _temporal_gap_score(self, neighbors: List[Memory]) -> float:
        """
        Score based on how long since any similar memory was ACCESSED
        (not just written). Memories accessed recently suggest the topic
        is active — new info on it has lower temporal gap score.
        
        Novelty: a memory that was written 6mo ago but accessed yesterday
        is NOT a candidate for overwrite (gap = low score).
        """
        if not neighbors:
            return 1.0
        now   = datetime.utcnow()
        gaps  = []
        for m in neighbors:
            ref_time = m.last_accessed_at or m.created_at
            days_ago = (now - ref_time).total_seconds() / 86400
            # Normalize: 0 days ago = 0.0 score, 90+ days ago = 1.0 score
            gaps.append(min(days_ago / 90.0, 1.0))
        return float(sum(gaps) / len(gaps))

    def _orphan_score(self, entities: List[str], agent_id: str) -> float:
        """
        Relational Orphan Score: fraction of entities in the new memory
        that have ZERO existing edges in the graph store.
        
        Orphaned entities = structurally novel information.
        High orphan score = the event introduces new nodes to the graph.
        
        Patent-novel: graph structural position as a write-gate signal.
        """
        if not entities:
            return 0.5  # neutral when no entities extracted yet
        orphan_count = 0
        for entity in entities:
            neighbors = self.backend.get_graph_neighbors(entity, depth=1, agent_id=agent_id)
            if not neighbors:
                orphan_count += 1
        return orphan_count / len(entities)

    def _access_inverse(self, neighbors: List[Memory]) -> float:
        """
        If nearest neighbors are rarely accessed (access_count low),
        even semantically similar content may be worth storing
        because the existing memories aren't proving useful.
        
        Inverts the usual 'frequently accessed = important' assumption.
        """
        if not neighbors:
            return 1.0
        mean_access = sum(m.access_count for m in neighbors) / len(neighbors)
        # Sigmoid inverse: low access → high score
        return 1.0 / (1.0 + math.exp(mean_access * 0.3 - 2))

    def _momentum_score(self) -> float:
        """
        If recent events were high-surprise, current event inherits
        elevated write probability (captures contextually adjacent info).
        Titans-inspired: not just the surprise event but its neighborhood.
        """
        if not self._recent:
            return 0.0
        recent_high = [s for s in self._recent
                       if s > self.config.momentum_threshold]
        if not recent_high:
            return 0.0
        return sum(recent_high) / len(self._recent)

    def _bridge_score(
        self, embedding: List[float], domain: str, agent_id: str
    ) -> float:
        """
        Cross-domain bridge score: events that are semantically close to
        memories in a DIFFERENT domain get a structural novelty bonus.
        They form conceptual bridges between domains.
        """
        cross_neighbors = self.backend.get_neighbors(
            embedding, k=3, agent_id=agent_id
        )
        cross_neighbors = [m for m in cross_neighbors if m.domain != domain]
        if not cross_neighbors:
            return 0.0
        distances = [_cosine_distance(embedding, m.embedding)
                     for m in cross_neighbors if m.embedding]
        if not distances:
            return 0.0
        # Low distance to cross-domain = high bridge potential
        avg_dist = sum(distances) / len(distances)
        return max(0.0, 1.0 - avg_dist * 2)

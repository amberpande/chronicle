"""
SnowMemory Adaptive Write Threshold (Retrieval-Calibrated Threshold — RCT)
Patent-novel: the write gate threshold adjusts itself based on
observed retrieval utility of previously written memories.

Feedback loop absent from ALL prior art (Titans, Mem0, RAG systems).
"""
from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from ..config.schema import SalienceConfig


@dataclass
class RetrievalFeedback:
    """Signal emitted every time a memory is retrieved."""
    memory_id:     str
    agent_id:      str
    salience_at_write: float   # what was the CSS score when this was written?
    was_used:      bool        # did the agent actually use this memory?
    timestamp:     datetime    = field(default_factory=datetime.utcnow)


class AdaptiveWriteGate:
    """
    Monitors write → retrieval → usage pipeline.
    Raises threshold when low-salience memories are never retrieved.
    Lowers threshold when queries return sparse results (memory gap detected).

    This makes the write gate self-calibrating over time.
    """

    def __init__(self, config: SalienceConfig):
        self.config    = config
        self.threshold = config.write_threshold
        # Ring buffer: (salience_at_write, was_retrieved, was_used)
        self._write_log:     deque = deque(maxlen=500)
        # query gap tracking: True = returned < half k results
        self._query_gaps:    deque = deque(maxlen=100)
        self._update_counter = 0
        self._update_every   = 50   # recalibrate every 50 writes

    def should_write(self, salience_score: float) -> bool:
        return salience_score >= self.threshold

    def record_write(self, memory_id: str, salience_score: float):
        self._write_log.append({
            "memory_id": memory_id,
            "salience":  salience_score,
            "retrieved": False,
            "used":      False,
            "written_at": datetime.utcnow(),
        })
        self._update_counter += 1
        if self._update_counter >= self._update_every:
            self._recalibrate()
            self._update_counter = 0

    def record_retrieval(self, memory_id: str, was_used: bool = True):
        """Call this when a retrieved memory was actually consumed by the agent."""
        for entry in self._write_log:
            if entry["memory_id"] == memory_id:
                entry["retrieved"] = True
                entry["used"]      = was_used
                break

    def record_query_result(self, returned_k: int, requested_k: int):
        """Call after every query to track result sparsity."""
        is_gap = returned_k < max(1, requested_k // 2)
        self._query_gaps.append(is_gap)

    def _recalibrate(self):
        """
        Core calibration logic:
        - If low-salience memories are never being retrieved → raise threshold
          (we're writing too much noise)
        - If queries frequently return sparse results → lower threshold
          (we're not writing enough)
        """
        if len(self._write_log) < 20:
            return   # not enough data yet

        cfg = self.config

        # Compute retrieval rate for low-salience writes
        low_writes = [e for e in self._write_log
                      if e["salience"] < self.threshold * 1.2]
        if low_writes:
            low_retrieval_rate = sum(1 for e in low_writes if e["retrieved"]) / len(low_writes)
        else:
            low_retrieval_rate = 1.0

        # Query gap rate
        if self._query_gaps:
            gap_rate = sum(self._query_gaps) / len(self._query_gaps)
        else:
            gap_rate = 0.0

        old_threshold = self.threshold

        # Queries returning sparse results → lower threshold (write more)
        # This takes priority: an empty store is worse than a noisy store
        if gap_rate > cfg.gap_tolerance:
            self.threshold = max(
                self.threshold * (1.0 - cfg.adjustment_rate),
                cfg.min_threshold,
            )

        # Too many low-salience memories never being retrieved → raise threshold
        elif low_retrieval_rate < cfg.low_utility_cutoff:
            self.threshold = min(
                self.threshold * (1.0 + cfg.adjustment_rate),
                cfg.max_threshold,
            )

        if abs(self.threshold - old_threshold) > 0.001:
            direction = "↑" if self.threshold > old_threshold else "↓"
            print(
                f"[AdaptiveGate] Threshold {direction} "
                f"{old_threshold:.3f} → {self.threshold:.3f} "
                f"(low_ret={low_retrieval_rate:.2f}, gap={gap_rate:.2f})"
            )

    @property
    def stats(self) -> Dict:
        total    = len(self._write_log)
        ret      = sum(1 for e in self._write_log if e["retrieved"])
        used     = sum(1 for e in self._write_log if e["used"])
        gaps     = sum(self._query_gaps)
        return {
            "current_threshold": self.threshold,
            "total_writes_tracked": total,
            "retrieval_rate": ret / total if total else 0,
            "usage_rate":     used / total if total else 0,
            "query_gap_rate": gaps / len(self._query_gaps) if self._query_gaps else 0,
        }

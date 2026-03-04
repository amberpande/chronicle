"""
SnowMemory Memory Type Classifier
Classifies incoming MemoryEvent into Working / Experiential / Factual.
"""
from __future__ import annotations
from ..core.models import MemoryEvent, MemoryType
from ..config.schema import ClassifierConfig


class MemoryTypeClassifier:

    def __init__(self, config: ClassifierConfig):
        self.config = config

    def classify(self, event: MemoryEvent) -> MemoryType:
        if self.config.mode == "rule_based":
            return self._rule_based(event)
        return self._rule_based(event)  # fallback; LLM mode extensible here

    def _rule_based(self, event: MemoryEvent) -> MemoryType:
        text = event.content.lower()

        # Explicit override from metadata
        if "memory_type" in event.metadata:
            return MemoryType(event.metadata["memory_type"].upper())

        # Factual patterns take priority
        for pattern in self.config.factual_patterns:
            if pattern in text:
                return MemoryType.FACTUAL

        # Working memory patterns
        for pattern in self.config.working_patterns:
            if pattern in text:
                return MemoryType.WORKING

        # Session-scoped events without persistence signals
        if event.session_id and not any(
            kw in text for kw in ["remember", "always", "past", "previously", "history"]
        ):
            # Short ephemeral content → working
            if len(event.content.split()) < 20:
                return MemoryType.WORKING

        # Default: experiential
        return MemoryType.EXPERIENTIAL

"""
SnowMemory Graph Extractor  — DOMAIN AGNOSTIC
Extracts entities and relations from any text content.
Uses universal linguistic patterns, not domain-specific vocabulary.

Works for: e-commerce, healthcare, coding, customer support,
           finance, HR, legal, research, gaming — anything.

Rule-based mode: zero deps, works out of the box.
LLM mode: richer extraction via Anthropic/OpenAI.
"""
from __future__ import annotations
import re, json
from typing import List, Tuple

from ..core.models import GraphPayload, GraphRelation
from ..config.schema import GraphConfig


# ─────────────────────────────────────────────────────────────────────
# Universal entity patterns  (domain-agnostic)
# ─────────────────────────────────────────────────────────────────────

# Named identifiers: anything that looks like ID/code  (e.g. USR-001, ORDER_42, v2.3.1)
_ID_RE = re.compile(
    r"\b([A-Z]{1,8}[-_]?[A-Z0-9]{1,12})\b"          # ACC-1234, USR-42, SKU-XYZ
    r"|\b([a-z][a-z0-9_]{2,}[-_][a-z0-9_]{1,})\b"   # order_id, user_session
    r"|\bv\d+\.\d+(?:\.\d+)?\b"                       # v2.3.1  (version strings)
)

# Proper noun phrases  (Title Case runs of 1–4 words)
_PROPER_RE = re.compile(
    r"\b([A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){0,3})\b"
)

# Quoted strings  → treat as named entities
_QUOTED_RE = re.compile(r'"([^"]{2,40})"|\'([^\']{2,40})\'')

# URLs / hostnames
_URL_RE = re.compile(r"https?://[\w./%-]+|[\w-]+\.(?:com|io|org|net|dev|ai)\b")

# Numeric quantities with units  (generic)
_QUANTITY_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ms|s|min|hours?|days?|weeks?|months?|years?|"
    r"kb|mb|gb|tb|%|px|rpm|rps|req/s|tokens?|users?|items?|records?)\b",
    re.I
)

# Date/time  (ISO or natural)
_DATE_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"\s+\d{1,2},?\s+\d{4}\b",
    re.I
)


# ─────────────────────────────────────────────────────────────────────
# Universal relation patterns  (domain-agnostic verb-anchored)
# ─────────────────────────────────────────────────────────────────────

_RELATION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Causation
    (re.compile(r"(\b\w+\b)\s+(?:caused?|triggered?|resulted?\s+in|led\s+to)\s+(\b\w+\b)", re.I), "CAUSED"),
    # Ownership / belonging
    (re.compile(r"(\b\w+\b)\s+(?:owned?\s+by|belongs?\s+to|assigned?\s+to)\s+(\b\w+\b)", re.I), "OWNED_BY"),
    # Resolution
    (re.compile(r"(\b\w+\b)\s+(?:resolved?|fixed?|closed?|solved?)\s+(?:by|via|using|with)\s+(\b\w+\b)", re.I), "RESOLVED_BY"),
    # Dependency
    (re.compile(r"(\b\w+\b)\s+(?:depends?\s+on|requires?|needs?)\s+(\b\w+\b)", re.I), "DEPENDS_ON"),
    # Failure / error
    (re.compile(r"(\b\w+\b)\s+(?:failed?|errored?|crashed?|threw?)\s+(?:on|at|in|with)?\s*(\b\w+\b)", re.I), "FAILED_ON"),
    # Usage / interaction
    (re.compile(r"(\b\w+\b)\s+(?:uses?|calls?|invokes?|imports?)\s+(\b\w+\b)", re.I), "USES"),
    # Association
    (re.compile(r"(\b\w+\b)\s+(?:relates?\s+to|associated?\s+with|linked?\s+to)\s+(\b\w+\b)", re.I), "RELATED_TO"),
    # Occurrence location
    (re.compile(r"(?:error|bug|issue|problem|exception|failure|incident)\s+(?:in|on|at|within)\s+(\b\w+\b)", re.I), "OCCURS_IN"),
    # Version / update
    (re.compile(r"(\b\w+\b)\s+(?:updated?\s+to|upgraded?\s+to|migrated?\s+to)\s+(\b\w+\b)", re.I), "UPDATED_TO"),
    # Reported by
    (re.compile(r"(\b\w+\b)\s+(?:reported?\s+by|flagged?\s+by|raised?\s+by)\s+(\b\w+\b)", re.I), "REPORTED_BY"),
]


# ─────────────────────────────────────────────────────────────────────
# Stop words to filter from entities
# ─────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    "The", "This", "That", "These", "Those", "There", "Their", "They",
    "When", "Where", "What", "Which", "With", "From", "Into", "Over",
    "After", "Before", "During", "Also", "Some", "Many", "Such",
    "More", "Most", "Both", "Each", "Every", "All", "Any", "None",
    "Note", "Please", "Today", "Yesterday", "Tomorrow", "Now",
    "Then", "Here", "Been", "Have", "Will", "Would", "Could", "Should",
}


class RuleBasedExtractor:
    """
    Universal, zero-dependency entity and relation extractor.
    Works on any domain — e-commerce, healthcare, code, support, etc.
    """

    def extract(self, content: str, memory_id: str = "") -> GraphPayload:
        entities  = self._extract_entities(content)
        relations = self._extract_relations(content, entities, memory_id)
        return GraphPayload(entities=entities, relations=relations)

    def _extract_entities(self, text: str) -> List[str]:
        found = set()

        # Named identifiers (IDs, codes, version strings)
        for m in _ID_RE.finditer(text):
            for g in m.groups():
                if g and len(g) > 1:
                    found.add(g.strip())

        # Proper noun phrases — filter stop words
        for m in _PROPER_RE.finditer(text):
            ent = m.group(1).strip()
            if ent not in _STOP_WORDS and len(ent) > 2:
                found.add(ent)

        # Quoted strings → strong entity signal
        for m in _QUOTED_RE.finditer(text):
            for g in m.groups():
                if g:
                    found.add(g.strip())

        # URLs / hostnames
        for m in _URL_RE.finditer(text):
            found.add(m.group(0))

        # Tag numeric quantities as generic type markers
        if _QUANTITY_RE.search(text):
            # Extract the actual quantity, not just a tag
            for m in _QUANTITY_RE.finditer(text):
                found.add(m.group(0).strip())

        # Tag date references
        if _DATE_RE.search(text):
            found.add("DATE_REFERENCE")

        # Remove single chars and very generic tokens
        found = {e for e in found if len(e) > 1 and not e.isdigit()}

        return list(found)[:20]  # cap at 20

    def _extract_relations(
        self, text: str, entities: List[str], memory_id: str
    ) -> List[GraphRelation]:
        relations = []

        # Verb-anchored relations from universal patterns
        for pattern, rel_type in _RELATION_PATTERNS:
            for m in pattern.finditer(text):
                groups = [g.strip() for g in m.groups() if g]
                if len(groups) >= 2 and groups[0] not in _STOP_WORDS:
                    relations.append(GraphRelation(
                        from_entity=groups[0],
                        relation_type=rel_type,
                        to_entity=groups[1],
                        confidence=0.70,
                        memory_id=memory_id,
                    ))

        # Co-occurrence: entities that appear together share a weak relation
        for i, e1 in enumerate(entities[:10]):  # limit combinatorics
            for e2 in entities[i + 1:10]:
                if e1 != e2:
                    relations.append(GraphRelation(
                        from_entity=e1,
                        relation_type="CO_OCCURS_WITH",
                        to_entity=e2,
                        confidence=0.40,
                        memory_id=memory_id,
                    ))

        return relations[:50]  # cap


class LLMExtractor:
    """
    LLM-powered extraction — richest results, requires API key.
    Falls back to RuleBasedExtractor on any error.
    """

    PROMPT = """Extract all entities (things: people, places, systems, products, IDs, concepts)
and relations (how they connect) from the text below.

Return ONLY valid JSON, no explanation:
{{
  "entities": ["entity1", "entity2"],
  "relations": [{{"from": "A", "type": "VERB_RELATION", "to": "B", "confidence": 0.9}}]
}}

Text: {content}

JSON:"""

    def __init__(self, config: GraphConfig):
        self.config = config
        self._client = None
        self._provider = None
        self._init_client()

    def _init_client(self):
        try:
            import anthropic
            self._client   = anthropic.Anthropic()
            self._provider = "anthropic"
            return
        except ImportError:
            pass
        try:
            import openai
            self._client   = openai.OpenAI()
            self._provider = "openai"
            return
        except ImportError:
            pass
        raise ImportError("pip install anthropic or openai for LLM extraction")

    def extract(self, content: str, memory_id: str = "") -> GraphPayload:
        try:
            raw = self._call_llm(content)
            # Strip markdown fences if present
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            data      = json.loads(raw)
            entities  = [str(e) for e in data.get("entities", [])]
            relations = [
                GraphRelation(
                    from_entity=str(r.get("from", "")),
                    relation_type=str(r.get("type", "RELATED_TO")).upper(),
                    to_entity=str(r.get("to", "")),
                    confidence=float(r.get("confidence", 0.8)),
                    memory_id=memory_id,
                )
                for r in data.get("relations", [])
                if r.get("from") and r.get("to")
            ]
            return GraphPayload(entities=entities, relations=relations)
        except Exception:
            return RuleBasedExtractor().extract(content, memory_id)

    def _call_llm(self, content: str) -> str:
        prompt = self.PROMPT.format(content=content[:1000])  # cap input
        if self._provider == "anthropic":
            msg = self._client.messages.create(
                model=self.config.llm_model or "claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()
        else:  # openai
            resp = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
            )
            return resp.choices[0].message.content.strip()


def build_extractor(config: GraphConfig):
    if config.extraction_mode == "llm":
        try:
            return LLMExtractor(config)
        except ImportError:
            return RuleBasedExtractor()
    return RuleBasedExtractor()

"""
SnowMemory Configuration Schema
All config loaded from YAML or env vars. Zero hardcoded values.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import yaml, os


class SalienceConfig(BaseModel):
    write_threshold:        float = 0.35
    max_threshold:          float = 0.75
    min_threshold:          float = 0.10
    k_neighbors:            int   = 5
    # CSS weights
    novelty_weight:         float = 0.35
    temporal_gap_weight:    float = 0.20
    orphan_score_weight:    float = 0.20
    access_inv_weight:      float = 0.10
    momentum_weight:        float = 0.15
    # Momentum
    momentum_window:        int   = 5
    momentum_threshold:     float = 0.40
    # Adaptive threshold
    adaptive_threshold:     bool  = True
    adjustment_rate:        float = 0.05
    low_utility_cutoff:     float = 0.10
    gap_tolerance:          float = 0.30
    # Domain normalization
    domain_normalization:   bool  = True
    domain_smoothing:       float = 1e-6


class DecayConfig(BaseModel):
    strategy:           str   = "exponential"   # exponential | linear | step
    half_life_days:     float = 30.0
    min_weight:         float = 0.05
    # Resurrection
    resurrection_enabled:            bool  = True
    resurrection_eligibility:        float = 0.30
    resurrection_window_hours:       int   = 48
    resurrection_confirmation_count: int   = 2
    resurrection_boost:              float = 0.25
    max_resurrection_weight:         float = 0.70


class GraphConfig(BaseModel):
    enabled:          bool  = True
    extraction_mode:  str   = "rule_based"   # rule_based | llm
    llm_model:        str   = "gpt-4o-mini"
    max_depth:        int   = 2
    min_confidence:   float = 0.60


class WorkingMemoryConfig(BaseModel):
    enabled:          bool = True
    ttl_seconds:      int  = 7200
    max_entries:      int  = 1000
    backend:          str  = "in_memory"   # in_memory | redis


class ExperientialMemoryConfig(BaseModel):
    enabled:          bool  = True
    ttl_days:         int   = 90
    backend:          str   = "in_memory"  # in_memory | snowflake | postgres


class FactualMemoryConfig(BaseModel):
    enabled:          bool  = True
    versioned:        bool  = True
    backend:          str   = "in_memory"


class SnowflakeBackendConfig(BaseModel):
    account:          str = ""
    user:             str = ""
    password:         str = ""
    warehouse:        str = "MEMORY_WH"
    database:         str = "SNOWMEMORY_DB"
    schema_name:      str = "AGENT_MEMORY"
    role:             str = ""
    private_key_path: str = ""          # alternative to password (RSA key pair)
    authenticator:    str = ""          # e.g. "externalbrowser" for SSO


class CortexConfig(BaseModel):
    """
    Snowflake Cortex AI integration.
    Embeddings + search + LLM graph extraction run entirely inside Snowflake.
    No data leaves the warehouse for any AI operation.
    """
    # Embedding model (runs via SNOWFLAKE.CORTEX.EMBED_TEXT inside Snowflake SQL)
    embedding_model:  str  = "e5-base-v2"
    # Available models and their dimensions:
    #   e5-base-v2                  → 768d  (good default, cost-effective)
    #   snowflake-arctic-embed-m    → 768d  (Snowflake native)
    #   snowflake-arctic-embed-l    → 1024d (higher quality)
    #   multilingual-e5-large       → 1024d (multilingual)
    #   voyage-multilingual-2       → 1024d (highest quality)
    embedding_dim:    int  = 768

    # LLM for graph extraction + optional classification
    complete_model:   str  = "mistral-7b"
    # Available: mistral-7b | mixtral-8x7b | llama3-8b | llama3-70b
    #            llama3.1-8b | llama3.1-70b | snowflake-arctic
    #            reka-flash | reka-core | jamba-instruct

    # Cortex Search (optional — managed semantic search service)
    use_cortex_search:     bool = False
    cortex_search_service: str  = ""    # e.g. "MY_DB.MY_SCHEMA.MEMORY_SEARCH_SVC"

    # Feature toggles — disable individually if Cortex not available in your region
    use_cortex_embed:    bool = True   # False → fall back to client-side embedder
    use_cortex_complete: bool = True   # False → fall back to rule-based extractor
    use_vector_column:   bool = True   # False → use ARRAY column (legacy mode)


class RedisBackendConfig(BaseModel):
    url:              str = "redis://localhost:6379"
    ttl_seconds:      int = 7200


class BackendsConfig(BaseModel):
    snowflake:        SnowflakeBackendConfig  = Field(default_factory=SnowflakeBackendConfig)
    cortex:           CortexConfig            = Field(default_factory=CortexConfig)
    redis:            RedisBackendConfig       = Field(default_factory=RedisBackendConfig)


class AuditConfig(BaseModel):
    enabled:          bool = True
    log_reads:        bool = False
    backend:          str  = "in_memory"   # in_memory | snowflake | file
    log_file:         str  = "snowmemory_audit.jsonl"


class InheritanceConfig(BaseModel):
    enabled:          bool  = True
    default_decay:    float = 0.80
    min_salience:     float = 0.40
    contradiction_check: bool = True


class ClassifierConfig(BaseModel):
    mode:             str         = "rule_based"  # rule_based | llm
    working_patterns: List[str]   = Field(default_factory=lambda: [
        "right now", "this session", "current task", "at the moment", "just now"
    ])
    factual_patterns: List[str]   = Field(default_factory=lambda: [
        "definition", "policy", "regulation", "rule", "always", "standard",
        "requirement", "guideline", "framework", "protocol"
    ])


class EmbedderConfig(BaseModel):
    mode:             str   = "simple"   # simple (TF-IDF proxy) | openai | sentence_transformers
    model:            str   = "all-MiniLM-L6-v2"
    dimension:        int   = 384
    openai_api_key:   str   = ""


class MemoryConfig(BaseModel):
    agent_id:         str                    = "default_agent"
    description:      str                    = ""
    # Optional domain keyword map: {"my_domain": ["keyword1", "keyword2"]}
    # When an event's content matches keywords, it's tagged with that domain.
    # Leave empty to tag everything as "general".
    domain_keywords:  Dict[str, List[str]]   = Field(default_factory=dict)

    working:          WorkingMemoryConfig     = Field(default_factory=WorkingMemoryConfig)
    experiential:     ExperientialMemoryConfig = Field(default_factory=ExperientialMemoryConfig)
    factual:          FactualMemoryConfig     = Field(default_factory=FactualMemoryConfig)

    salience:         SalienceConfig          = Field(default_factory=SalienceConfig)
    decay:            DecayConfig             = Field(default_factory=DecayConfig)
    graph:            GraphConfig             = Field(default_factory=GraphConfig)
    classifier:       ClassifierConfig        = Field(default_factory=ClassifierConfig)
    embedder:         EmbedderConfig          = Field(default_factory=EmbedderConfig)
    backends:         BackendsConfig          = Field(default_factory=BackendsConfig)
    audit:            AuditConfig             = Field(default_factory=AuditConfig)
    inheritance:      InheritanceConfig       = Field(default_factory=InheritanceConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "MemoryConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        # substitute env vars
        data = _substitute_env(data)
        return cls(**data)

    @classmethod
    def default(cls, agent_id: str = "default_agent") -> "MemoryConfig":
        return cls(agent_id=agent_id)

    def to_yaml(self, path: str):
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)


def _substitute_env(obj: Any) -> Any:
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            key = obj[2:-1]
            return os.environ.get(key, "")
        return obj
    if isinstance(obj, dict):
        return {k: _substitute_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env(i) for i in obj]
    return obj

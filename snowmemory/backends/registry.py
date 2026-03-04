"""Backend registry — maps config strings to backend classes."""
from __future__ import annotations
from .base import MemoryBackend
from .in_memory import InMemoryBackend
from ..config.schema import MemoryConfig


def build_backend(backend_type: str, config: MemoryConfig) -> MemoryBackend:
    """
    backend_type options:
      "in_memory"       — zero deps, for local dev & testing
      "snowflake"       — Snowflake with ARRAY columns + client-side cosine (legacy)
      "snowflake_cortex" — Snowflake with native VECTOR + Cortex AI (production)
      "redis"           — Redis for working memory tier
    """
    if backend_type == "in_memory":
        return InMemoryBackend()

    if backend_type == "snowflake":
        from .snowflake_backend import SnowflakeMemoryBackend
        return SnowflakeMemoryBackend(config.backends.snowflake)

    if backend_type == "snowflake_cortex":
        from .snowflake_cortex import SnowflakeCortexBackend
        return SnowflakeCortexBackend(
            sf=config.backends.snowflake,
            cortex=config.backends.cortex,
        )

    if backend_type == "redis":
        try:
            from .redis_backend import RedisMemoryBackend
            return RedisMemoryBackend(config.backends.redis)
        except ImportError:
            print("[Registry] redis not available, falling back to in_memory")
            return InMemoryBackend()

    raise ValueError(
        f"Unknown backend: '{backend_type}'. "
        "Choose: in_memory | snowflake | snowflake_cortex | redis"
    )

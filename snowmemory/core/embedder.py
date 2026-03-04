"""
SnowMemory Embedder
Supports: simple TF-IDF-based vectors (zero deps), 
          OpenAI embeddings, sentence-transformers.
The simple mode is the MVP default — works out of the box.
"""
from __future__ import annotations
import math, re, hashlib
from collections import Counter
from typing import List, Dict, Optional
from ..config.schema import EmbedderConfig


class SimpleEmbedder:
    """
    Lightweight TF-IDF inspired embedder.
    Produces consistent fixed-dim vectors without any ML framework.
    Good enough for MVP novelty scoring; swap for sentence-transformers in prod.
    """

    DIM = 384  # matches all-MiniLM output dim

    def __init__(self, config: EmbedderConfig):
        self.config = config
        self.vocab: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count = 0
        self.df: Dict[str, int] = {}

    def _tokenize(self, text: str) -> List[str]:
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        return [t for t in text.split() if len(t) > 1]

    def _get_or_add(self, token: str) -> int:
        if token not in self.vocab:
            self.vocab[token] = len(self.vocab) % self.DIM
        return self.vocab[token]

    def fit(self, texts: List[str]):
        """Update IDF estimates from a corpus."""
        self.doc_count += len(texts)
        for text in texts:
            tokens = set(self._tokenize(text))
            for t in tokens:
                self.df[t] = self.df.get(t, 0) + 1
        for t, df in self.df.items():
            self.idf[t] = math.log((self.doc_count + 1) / (df + 1)) + 1.0

    def embed(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self.DIM

        tf = Counter(tokens)
        vec = [0.0] * self.DIM
        total = sum(tf.values())

        for token, count in tf.items():
            idx = self._get_or_add(token)
            tf_val = count / total
            idf_val = self.idf.get(token, 1.0)
            # Distribute weight across multiple buckets via hashing
            for salt in range(3):
                h = int(hashlib.md5(f"{token}{salt}".encode()).hexdigest(), 16)
                bucket = h % self.DIM
                vec[bucket] += tf_val * idf_val

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        self.fit(texts)
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    """OpenAI text-embedding-3-small. Requires openai package."""

    DIM = 1536

    def __init__(self, config: EmbedderConfig):
        self.config = config
        try:
            import openai
            self.client = openai.OpenAI(api_key=config.openai_api_key)
        except ImportError:
            raise ImportError("pip install openai to use OpenAI embedder")

    def embed(self, text: str) -> List[float]:
        resp = self.client.embeddings.create(
            input=text, model="text-embedding-3-small"
        )
        return resp.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        resp = self.client.embeddings.create(
            input=texts, model="text-embedding-3-small"
        )
        return [r.embedding for r in resp.data]


def build_embedder(config: EmbedderConfig):
    """Factory function."""
    if config.mode == "openai":
        return OpenAIEmbedder(config)
    return SimpleEmbedder(config)

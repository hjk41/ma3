"""Local sentence-transformer embedding service.

Provides graceful degradation: if ``sentence-transformers`` is not installed,
all functions return ``None`` and callers simply skip vector scoring.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

_model = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_text(text: str) -> np.ndarray | None:
    """Encode *text* into a unit-norm embedding vector.

    Returns ``None`` if ``sentence-transformers`` is not installed.
    """
    if not text.strip():
        return None
    try:
        model = _get_model()
        return model.encode(text, normalize_embeddings=True)
    except ImportError:
        return None


def embed_record(record) -> np.ndarray | None:
    """Build a single embedding for a Record by concatenating its key fields."""
    parts = [record.title, record.summary, record.claim]
    if record.tags:
        parts.append(" ".join(record.tags))
    text = ". ".join(p for p in parts if p)
    return embed_text(text)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two L2-normalised vectors (dot product)."""
    return float(np.dot(a, b))


def serialize_embedding(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()


def deserialize_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)

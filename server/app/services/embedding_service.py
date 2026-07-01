"""Local sentence-transformer embedding service.

Provides graceful degradation: if ``sentence-transformers`` is not installed,
all functions return ``None`` and callers simply skip vector scoring.
"""
from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

_model = None
_model_lock = threading.Lock()
_MODEL_NAME = os.environ.get("MA3_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_DISABLE_EMBEDDINGS = os.environ.get("MA3_DISABLE_EMBEDDINGS") == "1"


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            _model = SentenceTransformer(_MODEL_NAME)
    return _model


def warm_up_model() -> bool:
    """Load the embedding model into memory (uses MA3_HF_HOME cache when populated)."""
    if _DISABLE_EMBEDDINGS:
        return False
    try:
        _get_model()
        return True
    except Exception:
        return False


def embed_text(text: str) -> np.ndarray | None:
    """Encode *text* into a unit-norm embedding vector.

    Returns ``None`` if ``sentence-transformers`` is not installed.
    """
    if _DISABLE_EMBEDDINGS:
        return None
    if not text.strip():
        return None
    try:
        model = _get_model()
        return model.encode(text, normalize_embeddings=True)
    except ImportError:
        return None
    except Exception:
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

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

            _model = SentenceTransformer(settings.embedding_model)
    return _model


def warm_up_model(*, required: bool = False) -> bool:
    if settings.disable_embeddings:
        if required:
            raise RuntimeError("MA3_DISABLE_EMBEDDINGS is set; cannot warm up embedding model")
        return False
    try:
        _get_model()
        return True
    except Exception:
        logger.exception("embedding model warm-up failed model=%s", settings.embedding_model)
        if required:
            raise
        return False


def embed_text(text: str) -> Any | None:
    if settings.disable_embeddings:
        return None
    if not text.strip():
        return None
    try:
        model = _get_model()
        return model.encode(text, normalize_embeddings=True)
    except Exception:
        return None


def embed_record_text(*, problem: str, outcome: str, result_summary: str, payload: dict) -> Any | None:
    parts = [problem, outcome, result_summary]
    tags = payload.get("tags") or []
    if tags:
        parts.append(" ".join(str(t) for t in tags))
    text = ". ".join(p for p in parts if p)
    return embed_text(text)


def cosine_similarity(a: Any, b: Any) -> float:
    import numpy as np

    return float(np.dot(a, b))


def serialize_embedding(vector: Any) -> bytes:
    return vector.astype("float32").tobytes()


def deserialize_embedding(blob: bytes) -> Any:
    import numpy as np

    return np.frombuffer(blob, dtype=np.float32)


def vector_as_list(vector: Any) -> list[float]:
    import numpy as np

    arr = np.asarray(vector, dtype=np.float32).reshape(-1)
    if arr.shape[0] != settings.embedding_dim:
        raise ValueError(f"embedding dimension {arr.shape[0]} != {settings.embedding_dim}")
    return arr.tolist()

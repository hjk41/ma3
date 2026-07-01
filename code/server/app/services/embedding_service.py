from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    import numpy as np

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


def warm_up_model() -> bool:
    if settings.disable_embeddings:
        return False
    try:
        _get_model()
        return True
    except Exception:
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

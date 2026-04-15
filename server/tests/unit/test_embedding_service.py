"""Unit tests for embedding_service.py (model-independent parts)."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.embedding_service import (
    cosine_similarity,
    deserialize_embedding,
    serialize_embedding,
)


# ── serialize / deserialize roundtrip ─────────────────────────────────────────

def test_serialize_deserialize_roundtrip():
    v = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    blob = serialize_embedding(v)
    recovered = deserialize_embedding(blob)
    np.testing.assert_array_almost_equal(v, recovered)


def test_serialize_produces_bytes():
    v = np.ones(8, dtype=np.float32)
    blob = serialize_embedding(v)
    assert isinstance(blob, bytes)
    # float32 = 4 bytes/element
    assert len(blob) == 8 * 4


def test_deserialize_float32_dtype():
    v = np.zeros(4, dtype=np.float32)
    blob = serialize_embedding(v)
    recovered = deserialize_embedding(blob)
    assert recovered.dtype == np.float32


def test_serialize_converts_float64_to_float32():
    v64 = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    blob = serialize_embedding(v64)
    recovered = deserialize_embedding(blob)
    assert recovered.dtype == np.float32
    np.testing.assert_array_almost_equal(v64.astype(np.float32), recovered)


# ── cosine_similarity ─────────────────────────────────────────────────────────

def test_cosine_similarity_identical_unit_vectors():
    v = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_similarity_partial():
    a = np.array([1.0, 1.0], dtype=np.float32) / np.sqrt(2)
    b = np.array([1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(1.0 / np.sqrt(2))


def test_cosine_similarity_returns_float():
    v = np.array([0.5, 0.5], dtype=np.float32)
    result = cosine_similarity(v, v)
    assert isinstance(result, float)


# ── embed_record ──────────────────────────────────────────────────────────────
# embed_record is mocked in tests, but we can test the mock via conftest helpers

def test_mock_embed_text_returns_unit_vector():
    """The mock embed function must return L2-normalised vectors (conftest guarantee)."""
    from tests.conftest import _mock_embed_text
    v = _mock_embed_text("hello world")
    norm = float(np.linalg.norm(v))
    assert norm == pytest.approx(1.0, abs=1e-5)


def test_mock_embed_text_deterministic():
    from tests.conftest import _mock_embed_text
    v1 = _mock_embed_text("same text")
    v2 = _mock_embed_text("same text")
    np.testing.assert_array_equal(v1, v2)


def test_mock_embed_text_different_inputs_differ():
    from tests.conftest import _mock_embed_text
    v1 = _mock_embed_text("text alpha")
    v2 = _mock_embed_text("text beta")
    assert not np.allclose(v1, v2)


def test_mock_embed_text_correct_dimension():
    from tests.conftest import EMBED_DIM, _mock_embed_text
    v = _mock_embed_text("dimension check")
    assert v.shape == (EMBED_DIM,)

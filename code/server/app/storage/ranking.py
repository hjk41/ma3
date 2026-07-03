"""Search ranking core — Scheme B "Gate-Then-Nudge" (design/12).

Pure functions over per-record signals (relevance + votes + flags). No DB access,
no I/O — so they are cheap to unit-test and reused by both the lexical and hybrid
search paths in ``search.py``.

Model (design/12 §4.1):
    is_wrong  = superseded or refuted or (wilson_U <= t_floor)
    rel_eff   = min(relevance, cap) if is_wrong else relevance
    Q         = +q_verified  if verified and not wrong
                -q_lean      if leaning_wrong
                0            otherwise (unknown / cold-start)
    final     = rel_eff + Q
    sort_key  = (wrong_tier ASC, final DESC, recency DESC, record_id ASC)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings

LABEL_VERIFIED = "verified"
LABEL_UNKNOWN = "unknown"
LABEL_LEANING_WRONG = "leaning_wrong"
LABEL_CLEARLY_WRONG = "clearly_wrong"


def wilson_bounds(up: int, down: int, z: float | None = None) -> tuple[float, float]:
    """Wilson score interval (lower, upper) for the positive-vote proportion.

    n=0 is pinned to (0.0, 1.0): no evidence → widest interval, so a cold-start
    record is neither verified (needs L>=t_high) nor clearly_wrong (needs U<=t_floor).
    """
    z = settings.search_wilson_z if z is None else z
    n = up + down
    if n <= 0:
        return 0.0, 1.0
    phat = up / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = phat + z2 / (2 * n)
    margin = z * math.sqrt((phat * (1.0 - phat) + z2 / (4 * n)) / n)
    low = (center - margin) / denom
    high = (center + margin) / denom
    return max(0.0, low), min(1.0, high)


def correctness_label(
    up: int,
    down: int,
    *,
    superseded: bool = False,
    refuted: bool = False,
    verified_override: bool = False,
) -> tuple[str, float, float]:
    """Return (label, wilson_L, wilson_U).

    Precedence (design/12 §3.1): clearly_wrong > verified > leaning_wrong > unknown.
    ``superseded``/``refuted`` force clearly_wrong regardless of votes;
    ``verified_override`` (an explicit verify report) bumps to at least verified.
    """
    low, high = wilson_bounds(up, down)
    if superseded or refuted or high <= settings.search_t_floor:
        return LABEL_CLEARLY_WRONG, low, high
    if verified_override or low >= settings.search_t_high:
        return LABEL_VERIFIED, low, high
    if high < settings.search_t_mid:
        return LABEL_LEANING_WRONG, low, high
    return LABEL_UNKNOWN, low, high


def rel_eff(relevance: float, *, is_wrong: bool) -> float:
    return min(relevance, settings.search_cap) if is_wrong else relevance


def q_adjust(label: str) -> float:
    """Bounded trust nudge Q. Invariant 2·max(q) < epsilon keeps it from flipping
    a relevance gap of epsilon (design/12 §4.2)."""
    if label == LABEL_VERIFIED:
        return settings.search_q_verified
    if label == LABEL_LEANING_WRONG:
        return -settings.search_q_lean
    return 0.0


def recency(created_at: str | None, *, now: datetime | None = None) -> float:
    """exp(-age_days/tau) tie-breaker in [0,1]; 0 when timestamp is missing/unparseable."""
    if not created_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(created_at))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    tau = settings.search_recency_tau_days or 180.0
    return math.exp(-age_days / tau)


@dataclass(slots=True)
class RankInput:
    record_id: str
    relevance: float
    up: int = 0
    down: int = 0
    superseded: bool = False
    refuted: bool = False
    verified_override: bool = False
    created_at: str | None = None


@dataclass(slots=True)
class RankResult:
    record_id: str
    relevance: float
    rel_eff: float
    capped: bool
    label: str
    wilson_L: float
    wilson_U: float
    Q: float
    final_score: float
    wrong_tier: int
    recency: float

    @property
    def is_wrong(self) -> bool:
        return self.wrong_tier == 1

    def explain(self) -> dict[str, object]:
        return {
            "relevance": round(self.relevance, 6),
            "rel_eff": round(self.rel_eff, 6),
            "capped": self.capped,
            "label": self.label,
            "wilson_L": round(self.wilson_L, 6),
            "wilson_U": round(self.wilson_U, 6),
            "Q": round(self.Q, 6),
            "final_score": round(self.final_score, 6),
            "wrong_tier": self.wrong_tier,
            "recency": round(self.recency, 6),
        }


def score_one(ri: RankInput, *, now: datetime | None = None) -> RankResult:
    label, low, high = correctness_label(
        ri.up,
        ri.down,
        superseded=ri.superseded,
        refuted=ri.refuted,
        verified_override=ri.verified_override,
    )
    wrong = label == LABEL_CLEARLY_WRONG
    effective = rel_eff(ri.relevance, is_wrong=wrong)
    q = q_adjust(label)
    return RankResult(
        record_id=ri.record_id,
        relevance=ri.relevance,
        rel_eff=effective,
        capped=effective < ri.relevance,
        label=label,
        wilson_L=low,
        wilson_U=high,
        Q=q,
        final_score=effective + q,
        wrong_tier=1 if wrong else 0,
        recency=recency(ri.created_at, now=now),
    )


def _sort_key(r: RankResult) -> tuple[int, float, float, str]:
    # wrong_tier ASC, final_score DESC, recency DESC, record_id ASC
    return (r.wrong_tier, -r.final_score, -r.recency, r.record_id)


def rank(inputs: list[RankInput], *, now: datetime | None = None) -> list[RankResult]:
    """Score and order records by the GTN sort key. Deterministic (record_id tiebreak)."""
    now = now or datetime.now(timezone.utc)
    results = [score_one(ri, now=now) for ri in inputs]
    results.sort(key=_sort_key)
    return results

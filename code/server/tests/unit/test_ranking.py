"""Unit tests for the GTN search-ranking core (design/12 §7.2)."""
from __future__ import annotations

import pytest

from app.core.config import RankingConfigError, Settings, settings, validate_ranking_config
from app.storage.ranking import (
    LABEL_CLEARLY_WRONG,
    LABEL_LEANING_WRONG,
    LABEL_UNKNOWN,
    LABEL_VERIFIED,
    RankInput,
    correctness_label,
    q_adjust,
    rank,
    rel_eff,
    score_one,
    wilson_bounds,
)


# --- Wilson ---------------------------------------------------------------

def test_wilson_n0_pinned_to_widest_interval():
    low, high = wilson_bounds(0, 0)
    assert low == 0.0 and high == 1.0


def test_wilson_bounds_within_unit_interval():
    for up, down in [(1, 0), (0, 1), (5, 5), (100, 3), (3, 100), (1, 1)]:
        low, high = wilson_bounds(up, down)
        assert 0.0 <= low <= high <= 1.0


def test_wilson_lower_monotonic_in_upvotes():
    prev = -1.0
    for up in range(0, 30):
        low, _ = wilson_bounds(up, 2)
        assert low >= prev - 1e-9
        prev = low


def test_wilson_upper_monotonic_in_downvotes():
    prev = 2.0
    for down in range(0, 30):
        _, high = wilson_bounds(2, down)
        assert high <= prev + 1e-9
        prev = high


# --- Labels + precedence --------------------------------------------------

def test_label_cold_start_is_unknown():
    label, low, high = correctness_label(0, 0)
    assert label == LABEL_UNKNOWN and (low, high) == (0.0, 1.0)


def test_label_verified_needs_confidence_not_just_ratio():
    # 2/0 is a perfect ratio but too little evidence to be verified;
    # 10/0 clears L >= t_high.
    assert correctness_label(2, 0)[0] != LABEL_VERIFIED
    assert correctness_label(10, 0)[0] == LABEL_VERIFIED


def test_label_100_98_is_unknown_not_verified():
    assert correctness_label(100, 98)[0] == LABEL_UNKNOWN


def test_label_strong_downvotes_clearly_wrong():
    assert correctness_label(0, 20)[0] == LABEL_CLEARLY_WRONG


def test_label_leaning_wrong_band():
    # (1,8): U ~= 0.44 -> below t_mid (0.5) but above t_floor (0.25)
    label, low, high = correctness_label(1, 8)
    assert label == LABEL_LEANING_WRONG
    assert high < 0.5 and high > 0.25


def test_superseded_overrides_verified():
    # 20/0 would be verified, but superseded forces clearly_wrong (design/12 Sup oracle)
    assert correctness_label(20, 0)[0] == LABEL_VERIFIED
    assert correctness_label(20, 0, superseded=True)[0] == LABEL_CLEARLY_WRONG


def test_refuted_forces_clearly_wrong():
    assert correctness_label(20, 0, refuted=True)[0] == LABEL_CLEARLY_WRONG


def test_verified_override_bumps_unknown():
    assert correctness_label(1, 0)[0] != LABEL_VERIFIED
    assert correctness_label(1, 0, verified_override=True)[0] == LABEL_VERIFIED


def test_label_partition_single_valued():
    # every (up,down) yields exactly one of the four labels
    valid = {LABEL_VERIFIED, LABEL_UNKNOWN, LABEL_LEANING_WRONG, LABEL_CLEARLY_WRONG}
    for up in range(0, 12):
        for down in range(0, 12):
            assert correctness_label(up, down)[0] in valid


# --- rel_eff / Q / final --------------------------------------------------

def test_rel_eff_caps_only_wrong():
    assert rel_eff(0.9, is_wrong=False) == 0.9
    assert rel_eff(0.9, is_wrong=True) == pytest.approx(0.25)
    assert rel_eff(0.1, is_wrong=True) == pytest.approx(0.1)  # below cap unchanged


def test_q_adjust_values():
    assert q_adjust(LABEL_VERIFIED) == pytest.approx(0.02)
    assert q_adjust(LABEL_LEANING_WRONG) == pytest.approx(-0.02)
    assert q_adjust(LABEL_UNKNOWN) == 0.0
    assert q_adjust(LABEL_CLEARLY_WRONG) == 0.0


def test_cold_start_final_equals_relevance():
    r = score_one(RankInput("a", relevance=0.9, up=0, down=0))
    assert r.label == LABEL_UNKNOWN
    assert r.Q == 0.0
    assert r.final_score == pytest.approx(0.9)
    assert r.capped is False


def test_clearly_wrong_capped_flag():
    r = score_one(RankInput("a", relevance=0.9, up=0, down=30))
    assert r.is_wrong and r.wrong_tier == 1
    assert r.rel_eff == pytest.approx(0.25) and r.capped is True


# --- Oracle ordering (R1-R6) ---------------------------------------------

def _order(inputs):
    return [r.record_id for r in rank(inputs)]


def test_R1_relevant_unknown_beats_irrelevant_verified():
    order = _order([
        RankInput("hi", relevance=0.8, up=0, down=0),
        RankInput("lo", relevance=0.1, up=10, down=0),
    ])
    assert order == ["hi", "lo"]


def test_R2_near_tie_verified_beats_unknown():
    order = _order([
        RankInput("ver", relevance=0.8, up=10, down=0),
        RankInput("unk", relevance=0.8, up=0, down=0),
    ])
    assert order == ["ver", "unk"]


def test_R3_clearly_wrong_sinks_below_unknown():
    order = _order([
        RankInput("wrong", relevance=0.9, superseded=True),
        RankInput("ok", relevance=0.5, up=0, down=0),
    ])
    assert order == ["ok", "wrong"]


def test_R3b_low_relevance_nonwrong_still_beats_high_relevance_wrong():
    # C2 must hold via wrong_tier even when the wrong record's relevance is far higher
    order = _order([
        RankInput("wrong", relevance=0.95, up=0, down=30),
        RankInput("weak", relevance=0.20, up=0, down=0),
    ])
    assert order == ["weak", "wrong"]


def test_R4_more_confident_verified_wins_same_relevance():
    order = _order([
        RankInput("small", relevance=0.7, up=2, down=0),
        RankInput("big", relevance=0.7, up=10, down=0),
    ])
    assert order == ["big", "small"]


def test_C3_verified_unknown_leaning_ordering_at_equal_relevance():
    order = _order([
        RankInput("unknown", relevance=0.6, up=0, down=0),
        RankInput("verified", relevance=0.6, up=12, down=0),
        RankInput("leaning", relevance=0.6, up=1, down=8),
    ])
    assert order == ["verified", "unknown", "leaning"]


def test_C1_relevance_gap_beats_trust_nudge():
    # Δrel >= epsilon: leaning_wrong high-rel must still beat verified low-rel
    order = _order([
        RankInput("hi_lean", relevance=0.80, up=1, down=8),
        RankInput("lo_ver", relevance=0.60, up=12, down=0),
    ])
    assert order[0] == "hi_lean"


def test_deterministic_tiebreak_by_record_id():
    order = _order([
        RankInput("b", relevance=0.5, up=0, down=0),
        RankInput("a", relevance=0.5, up=0, down=0),
    ])
    assert order == ["a", "b"]


def test_permutation_gives_same_order():
    a = RankInput("a", relevance=0.5, up=1, down=0)
    b = RankInput("b", relevance=0.9, up=0, down=0)
    c = RankInput("c", relevance=0.3, up=0, down=5)
    assert _order([a, b, c]) == _order([c, a, b])


# --- Recency tie-break (D4) -----------------------------------------------

def test_recency_breaks_near_ties_newer_first():
    # identical relevance + label(unknown) => only recency separates them
    order = _order([
        RankInput("old", relevance=0.6, created_at="2020-01-01T00:00:00+00:00"),
        RankInput("new", relevance=0.6, created_at="2026-01-01T00:00:00+00:00"),
    ])
    assert order == ["new", "old"]


def test_recency_does_not_override_final_score():
    # a newer but lower-final record must NOT jump a much better one
    order = _order([
        RankInput("new_weak", relevance=0.3, created_at="2026-06-01T00:00:00+00:00"),
        RankInput("old_strong", relevance=0.9, created_at="2020-01-01T00:00:00+00:00"),
    ])
    assert order == ["old_strong", "new_weak"]


def test_missing_created_at_is_zero_recency():
    from app.storage.ranking import recency
    assert recency(None) == 0.0
    assert recency("not-a-date") == 0.0


# --- Boundary semantics (open/closed edges) -------------------------------

def test_t_floor_is_closed_upper_bound(monkeypatch):
    # U == t_floor must count as clearly_wrong (design uses U <= t_floor)
    _, _, high = correctness_label(0, 20)
    monkeypatch.setattr(settings, "search_t_floor", high)
    assert correctness_label(0, 20)[0] == LABEL_CLEARLY_WRONG
    monkeypatch.setattr(settings, "search_t_floor", high - 1e-9)
    assert correctness_label(0, 20)[0] != LABEL_CLEARLY_WRONG


def test_t_high_is_closed_lower_bound(monkeypatch):
    # L == t_high must count as verified (design uses L >= t_high)
    _, low, _ = correctness_label(10, 0)
    monkeypatch.setattr(settings, "search_t_high", low)
    assert correctness_label(10, 0)[0] == LABEL_VERIFIED
    monkeypatch.setattr(settings, "search_t_high", low + 1e-9)
    assert correctness_label(10, 0)[0] != LABEL_VERIFIED


def test_t_mid_is_open_upper_bound(monkeypatch):
    # U == t_mid must NOT be leaning_wrong (design uses U < t_mid)
    _, _, high = correctness_label(1, 8)
    monkeypatch.setattr(settings, "search_t_mid", high)
    assert correctness_label(1, 8)[0] != LABEL_LEANING_WRONG
    monkeypatch.setattr(settings, "search_t_mid", high + 1e-9)
    assert correctness_label(1, 8)[0] == LABEL_LEANING_WRONG


def test_relevance_gap_exactly_epsilon_not_flipped_by_Q():
    # Δrel == epsilon (0.05): higher-relevance unknown beats verified just below
    order = _order([
        RankInput("hi_unknown", relevance=0.80, up=0, down=0),
        RankInput("lo_verified", relevance=0.75, up=12, down=0),
    ])
    assert order == ["hi_unknown", "lo_verified"]


# --- Config invariant guard ----------------------------------------------

def test_default_config_passes_invariant():
    validate_ranking_config(Settings())


def test_cap_equals_rel_min_minus_delta():
    assert Settings().search_cap == pytest.approx(0.25)


def test_invariant_guard_rejects_oversized_q(monkeypatch):
    monkeypatch.setenv("MA3_SEARCH_Q_VERIFIED", "0.03")  # 2*0.03=0.06 > epsilon 0.05
    with pytest.raises(RankingConfigError):
        Settings()


def test_invariant_guard_rejects_bad_threshold_order(monkeypatch):
    monkeypatch.setenv("MA3_SEARCH_T_MID", "0.7")  # mid > high
    with pytest.raises(RankingConfigError):
        Settings()


def test_invariant_guard_rejects_epsilon_ge_delta(monkeypatch):
    monkeypatch.setenv("MA3_SEARCH_EPSILON", "0.2")  # epsilon > delta 0.10
    with pytest.raises(RankingConfigError):
        Settings()

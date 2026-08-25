from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coinfinder.config import load_config
from coinfinder.models import Candidate
from coinfinder.scoring import apply_filters, rank, score_candidate
from tests.fixtures.pairs import make_pair


def config():
    return load_config()


def candidate(**kwargs) -> Candidate:
    return Candidate.from_dexscreener_pair(make_pair(**kwargs))


def test_healthy_pair_passes_filters():
    assert apply_filters(candidate(), config()) == []


def test_thin_liquidity_is_rejected():
    reasons = apply_filters(candidate(liquidity_usd=500), config())
    assert any("liquidity" in r for r in reasons)


def test_dead_volume_is_rejected():
    reasons = apply_filters(candidate(volume_h24=100), config())
    assert any("volume" in r for r in reasons)


def test_brand_new_pair_is_rejected():
    reasons = apply_filters(candidate(age_hours=0.1), config())
    assert any("age" in r for r in reasons)


def test_stale_pair_is_rejected():
    reasons = apply_filters(candidate(age_hours=24 * 90), config())
    assert any("age" in r for r in reasons)


def test_extreme_fdv_to_liquidity_is_rejected():
    reasons = apply_filters(candidate(liquidity_usd=20_000, fdv=50_000_000), config())
    assert any("FDV" in r for r in reasons)


def test_heavy_selling_is_rejected():
    reasons = apply_filters(candidate(buys_h1=10, sells_h1=200), config())
    assert any("buy ratio" in r for r in reasons)


def test_missing_creation_time_does_not_trip_age_filter():
    pair = make_pair()
    del pair["pairCreatedAt"]
    assert apply_filters(Candidate.from_dexscreener_pair(pair), config()) == []


def test_score_is_bounded():
    scored = score_candidate(candidate(), config())
    assert 0 <= scored.score <= 100
    assert set(scored.score_breakdown) == {
        "liquidity",
        "turnover",
        "momentum",
        "buy_pressure",
        "age_fit",
        "safety",
    }
    assert all(0 <= v <= 1 for v in scored.score_breakdown.values())


def test_stronger_pair_outscores_weaker_one():
    strong = score_candidate(
        candidate(liquidity_usd=250_000, volume_h24=1_500_000, buys_h1=400, sells_h1=120), config()
    )
    weak = score_candidate(
        candidate(liquidity_usd=16_000, volume_h24=25_000, buys_h1=12, sells_h1=11, socials=False), config()
    )
    assert strong.score > weak.score


def test_already_pumped_pair_scores_lower_momentum_than_steady_climber():
    steady = score_candidate(candidate(price_change_h1=100, price_change_h6=120), config())
    blown_off = score_candidate(candidate(price_change_h1=900, price_change_h6=1200), config())
    assert blown_off.score_breakdown["momentum"] < steady.score_breakdown["momentum"]
    assert any("already pumped" in f for f in blown_off.flags)


def test_small_sample_buy_pressure_is_discounted():
    few = score_candidate(candidate(buys_h1=6, sells_h1=1), config())
    many = score_candidate(candidate(buys_h1=600, sells_h1=100), config())
    assert few.score_breakdown["buy_pressure"] < many.score_breakdown["buy_pressure"]


def test_missing_socials_costs_safety_points():
    with_socials = score_candidate(candidate(socials=True), config())
    without = score_candidate(candidate(socials=False), config())
    assert without.score_breakdown["safety"] < with_socials.score_breakdown["safety"]
    assert any("no socials" in f for f in without.flags)


def test_rank_splits_and_sorts():
    candidates = [
        candidate(symbol="GOOD", pair_address="P1", liquidity_usd=200_000, volume_h24=900_000),
        candidate(symbol="BAD", pair_address="P2", liquidity_usd=100),
        candidate(symbol="OKAY", pair_address="P3", liquidity_usd=20_000, volume_h24=40_000),
    ]
    passing, rejected = rank(candidates, config())
    assert [c.symbol for c in rejected] == ["BAD"]
    assert [c.symbol for c in passing] == ["GOOD", "OKAY"]
    assert passing[0].score >= passing[1].score

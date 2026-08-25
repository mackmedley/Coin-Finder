"""Hard filters and the composite buy score.

Two separate stages, deliberately:

1. `apply_filters` — binary disqualifiers. A pair that can't be exited safely is
   worthless no matter how good it looks, so these run before scoring and are
   not tradeable against a high score.
2. `score_candidate` — six 0..1 components combined by configured weights into a
   0..100 score. Every component is normalized independently so a weight change
   never silently rescales the others.
"""

from __future__ import annotations

from typing import Any

from .models import Candidate


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def apply_filters(candidate: Candidate, config: dict[str, Any]) -> list[str]:
    """Return the reasons this candidate is disqualified. Empty list = passes."""
    f = config.get("filters", {})
    reasons: list[str] = []

    min_liq = float(f.get("min_liquidity_usd", 0))
    if candidate.liquidity_usd < min_liq:
        reasons.append(f"liquidity ${candidate.liquidity_usd:,.0f} < ${min_liq:,.0f}")

    min_vol = float(f.get("min_volume_h24_usd", 0))
    if candidate.volume_h24 < min_vol:
        reasons.append(f"24h volume ${candidate.volume_h24:,.0f} < ${min_vol:,.0f}")

    # Age 0 means the provider omitted pairCreatedAt; treat it as unknown rather
    # than as "brand new", otherwise every pair without the field gets rejected.
    if candidate.pair_created_at_ms > 0:
        min_age = float(f.get("min_age_minutes", 0))
        if candidate.age_minutes < min_age:
            reasons.append(f"age {candidate.age_minutes:.0f}m < {min_age:.0f}m")
        max_age_days = float(f.get("max_age_days", 10_000))
        if candidate.age_hours > max_age_days * 24:
            reasons.append(f"age {candidate.age_hours / 24:.1f}d > {max_age_days:.0f}d")

    max_ratio = float(f.get("max_fdv_to_liquidity_ratio", 0))
    if max_ratio > 0 and candidate.fdv > 0 and candidate.fdv_to_liquidity > max_ratio:
        reasons.append(f"FDV/liquidity {candidate.fdv_to_liquidity:.0f}x > {max_ratio:.0f}x")

    min_buy_ratio = float(f.get("min_buy_ratio_h1", 0))
    if candidate.buys_h1 + candidate.sells_h1 > 0 and candidate.buy_ratio_h1 < min_buy_ratio:
        reasons.append(f"1h buy ratio {candidate.buy_ratio_h1:.0%} < {min_buy_ratio:.0%}")

    return reasons


def _liquidity_component(candidate: Candidate, scoring: dict[str, Any]) -> float:
    saturation = float(scoring.get("liquidity_saturation_usd", 300_000))
    if saturation <= 0:
        return 0.0
    # Square root: getting off the floor matters far more than the top end.
    return _clamp((candidate.liquidity_usd / saturation) ** 0.5)


def _turnover_component(candidate: Candidate, scoring: dict[str, Any]) -> float:
    saturation = float(scoring.get("turnover_saturation_ratio", 4.0))
    if saturation <= 0:
        return 0.0
    return _clamp(candidate.turnover_ratio / saturation)


def _momentum_component(candidate: Candidate, scoring: dict[str, Any]) -> float:
    late = float(scoring.get("momentum_late_pump_threshold_pct", 150))
    if late <= 0:
        return 0.0
    blended = 0.6 * candidate.price_change_h1 + 0.4 * candidate.price_change_h6

    if blended <= -50:
        return 0.0
    if blended < 0:
        return 0.2 * (1 + blended / 50)
    if blended <= late:
        return 0.2 + 0.8 * (blended / late)
    # Past the threshold the move is likely already spent: decay, don't reward.
    return max(0.25, 1.0 - (blended - late) / (late * 3))


def _buy_pressure_component(candidate: Candidate) -> float:
    total = candidate.buys_h1 + candidate.sells_h1
    if total == 0:
        return 0.0
    # A 60/40 split off five trades means nothing; scale by sample size.
    confidence = _clamp(total / 50)
    ratio_score = _clamp((candidate.buy_ratio_h1 - 0.35) / 0.40)
    return ratio_score * confidence


def _age_fit_component(candidate: Candidate, scoring: dict[str, Any]) -> float:
    if candidate.pair_created_at_ms <= 0:
        return 0.5  # unknown age: neither rewarded nor punished
    low, high = (float(x) for x in scoring.get("age_fit_sweet_spot_hours", [2, 240]))
    age = candidate.age_hours
    if low <= age <= high:
        return 1.0
    if age < low:
        return _clamp(age / low) * 0.7
    return max(0.0, 1.0 - (age - high) / (high * 2))


def _safety_component(candidate: Candidate, config: dict[str, Any]) -> tuple[float, list[str]]:
    """Rug-risk proxy. Starts at 1.0 and subtracts for each warning sign."""
    score = 1.0
    flags: list[str] = []

    max_ratio = float(config.get("filters", {}).get("max_fdv_to_liquidity_ratio", 60))
    if candidate.fdv > 0 and max_ratio > 0:
        # Half the hard cap is where the ratio starts costing points.
        overhang = candidate.fdv_to_liquidity / max_ratio
        if overhang > 0.5:
            score -= _clamp((overhang - 0.5) / 0.5) * 0.35
            flags.append(f"FDV {candidate.fdv_to_liquidity:.0f}x liquidity")

    if not candidate.socials and not candidate.websites:
        score -= 0.25
        flags.append("no socials/website")

    if candidate.liquidity_usd < 30_000:
        score -= 0.20
        flags.append("thin liquidity")

    total_h24 = candidate.buys_h24 + candidate.sells_h24
    if total_h24 >= 50 and candidate.buys_h24 / total_h24 < 0.45:
        score -= 0.20
        flags.append("24h net selling")

    if candidate.volume_h1 > 0 and candidate.volume_h24 > 0:
        hourly_average = candidate.volume_h24 / 24
        if candidate.volume_h1 < hourly_average * 0.25:
            score -= 0.15
            flags.append("volume fading")

    return _clamp(score), flags


def score_candidate(candidate: Candidate, config: dict[str, Any]) -> Candidate:
    """Compute the 0..100 score in place and attach the per-component breakdown."""
    scoring = config.get("scoring", {})
    weights = {k: float(v) for k, v in scoring.get("weights", {}).items()}
    total_weight = sum(weights.values())

    safety, safety_flags = _safety_component(candidate, config)
    components = {
        "liquidity": _liquidity_component(candidate, scoring),
        "turnover": _turnover_component(candidate, scoring),
        "momentum": _momentum_component(candidate, scoring),
        "buy_pressure": _buy_pressure_component(candidate),
        "age_fit": _age_fit_component(candidate, scoring),
        "safety": safety,
    }

    weighted = sum(components[name] * weights.get(name, 0.0) for name in components)
    candidate.score = round(100 * weighted / total_weight, 1) if total_weight > 0 else 0.0
    candidate.score_breakdown = {name: round(value, 3) for name, value in components.items()}

    flags = list(safety_flags)
    late = float(scoring.get("momentum_late_pump_threshold_pct", 150))
    if candidate.price_change_h1 > late:
        flags.append(f"already pumped {candidate.price_change_h1:.0f}% in 1h")
    if candidate.boost_amount > 0:
        flags.append(f"paid boost {candidate.boost_amount:.0f}")
    candidate.flags = flags
    return candidate


def rank(candidates: list[Candidate], config: dict[str, Any]) -> tuple[list[Candidate], list[Candidate]]:
    """Filter, score, and sort. Returns (passing, rejected)."""
    passing: list[Candidate] = []
    rejected: list[Candidate] = []
    for candidate in candidates:
        reasons = apply_filters(candidate, config)
        if reasons:
            candidate.reject_reasons = reasons
            rejected.append(candidate)
            continue
        passing.append(score_candidate(candidate, config))
    passing.sort(key=lambda c: c.score, reverse=True)
    return passing, rejected

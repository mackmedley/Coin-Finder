"""Exit signals for open positions.

Rules are evaluated in severity order and the most severe one wins the verdict.
A liquidity collapse outranks a profit target: if the pool is draining, the
take-profit number no longer matters because the exit may not be fillable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Candidate, Position

URGENT_SELL = "URGENT SELL"
SELL = "SELL"
TRIM = "TRIM"
HOLD = "HOLD"

_SEVERITY = {HOLD: 0, TRIM: 1, SELL: 2, URGENT_SELL: 3}


@dataclass
class SellSignal:
    position: Position
    verdict: str
    reasons: list[str]
    price_usd: float
    pnl_pct: float
    pnl_usd: float
    drawdown_from_peak_pct: float
    liquidity_change_pct: float
    stale: bool = False

    @property
    def is_actionable(self) -> bool:
        return self.verdict != HOLD


def _pct_change(current: float, reference: float) -> float:
    if reference <= 0:
        return 0.0
    return (current - reference) / reference * 100


def evaluate(position: Position, current: Candidate | None, config: dict[str, Any]) -> SellSignal:
    """Compare a position against live pair data and produce a verdict."""
    rules = config.get("sell_rules", {})

    if current is None or current.price_usd <= 0:
        return SellSignal(
            position=position,
            verdict=HOLD,
            reasons=["no live price available — could not evaluate, check manually"],
            price_usd=0.0,
            pnl_pct=0.0,
            pnl_usd=0.0,
            drawdown_from_peak_pct=0.0,
            liquidity_change_pct=0.0,
            stale=True,
        )

    price = current.price_usd
    pnl_pct = _pct_change(price, position.entry_price_usd)
    pnl_usd = position.amount_usd * pnl_pct / 100
    peak = max(position.peak_price_usd, price)
    drawdown = _pct_change(price, peak)
    liquidity_change = _pct_change(current.liquidity_usd, position.entry_liquidity_usd)

    verdict = HOLD
    reasons: list[str] = []

    def escalate(new_verdict: str, reason: str) -> None:
        nonlocal verdict
        reasons.append(reason)
        if _SEVERITY[new_verdict] > _SEVERITY[verdict]:
            verdict = new_verdict

    liquidity_drop = float(rules.get("liquidity_drop_pct", -40))
    if position.entry_liquidity_usd > 0 and liquidity_change <= liquidity_drop:
        escalate(
            URGENT_SELL,
            f"liquidity down {liquidity_change:.0f}% since entry "
            f"(${position.entry_liquidity_usd:,.0f} → ${current.liquidity_usd:,.0f}) — possible rug",
        )

    stop_loss = float(rules.get("stop_loss_pct", -25))
    if pnl_pct <= stop_loss:
        escalate(SELL, f"stop loss hit: {pnl_pct:+.1f}% (limit {stop_loss:+.0f}%)")

    take_profit = float(rules.get("take_profit_pct", 60))
    if pnl_pct >= take_profit:
        escalate(SELL, f"take profit hit: {pnl_pct:+.1f}% (target {take_profit:+.0f}%)")

    trailing = float(rules.get("trailing_stop_pct", -30))
    if drawdown <= trailing and price < peak:
        escalate(
            SELL,
            f"trailing stop: down {drawdown:.0f}% from peak ${peak:.8g} (limit {trailing:.0f}%)",
        )

    min_hold = float(rules.get("momentum_decay_min_hold_hours", 2))
    decay_ratio = float(rules.get("momentum_decay_volume_ratio", 0.15))
    if position.hold_hours >= min_hold and current.volume_h24 > 0:
        hourly_average = current.volume_h24 / 24
        if hourly_average > 0 and current.volume_h1 < hourly_average * decay_ratio:
            escalate(
                TRIM,
                f"volume collapsing: 1h ${current.volume_h1:,.0f} vs "
                f"${hourly_average:,.0f}/h average — interest is gone",
            )

    total_h1 = current.buys_h1 + current.sells_h1
    if total_h1 >= 20 and current.buy_ratio_h1 < 0.35:
        escalate(TRIM, f"sellers taking over: only {current.buy_ratio_h1:.0%} of 1h trades are buys")

    if not reasons:
        reasons.append(f"holding at {pnl_pct:+.1f}%, no exit rule triggered")

    return SellSignal(
        position=position,
        verdict=verdict,
        reasons=reasons,
        price_usd=price,
        pnl_pct=pnl_pct,
        pnl_usd=pnl_usd,
        drawdown_from_peak_pct=drawdown,
        liquidity_change_pct=liquidity_change,
    )

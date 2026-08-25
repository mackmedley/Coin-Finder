"""Terminal and JSON rendering."""

from __future__ import annotations

import json
from typing import Any

from .models import Candidate
from .sell import SellSignal, HOLD, TRIM, SELL, URGENT_SELL

_VERDICT_LABEL = {
    URGENT_SELL: "!! URGENT SELL",
    SELL: " ! SELL",
    TRIM: " ~ TRIM",
    HOLD: "   HOLD",
}


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def _price(value: float) -> str:
    if value == 0:
        return "-"
    if value >= 0.01:
        return f"${value:,.4f}"
    return f"${value:.8g}"


def _age(candidate: Candidate) -> str:
    if candidate.pair_created_at_ms <= 0:
        return "?"
    hours = candidate.age_hours
    if hours < 1:
        return f"{candidate.age_minutes:.0f}m"
    if hours < 48:
        return f"{hours:.0f}h"
    return f"{hours / 24:.0f}d"


def render_scan(passing: list[Candidate], rejected: list[Candidate], limit: int) -> str:
    lines: list[str] = []
    shown = passing[:limit]

    lines.append("")
    lines.append(f"BUY CANDIDATES  —  {len(passing)} passed filters, {len(rejected)} rejected")
    lines.append("=" * 100)
    if not shown:
        lines.append("  Nothing passed the filters this scan. That is a normal result — most scans")
        lines.append("  should be empty. Loosen config/default.yaml filters only if it never fills.")
        lines.append("")
        return "\n".join(lines)

    header = f"{'#':>2}  {'SCORE':>5}  {'SYMBOL':<12} {'CHAIN':<9} {'PRICE':>13} {'LIQ':>8} {'VOL24':>8} {'1H%':>8} {'AGE':>5}"
    lines.append(header)
    lines.append("-" * 100)
    for index, candidate in enumerate(shown, start=1):
        lines.append(
            f"{index:>2}  {candidate.score:>5.1f}  {candidate.symbol[:12]:<12} {candidate.chain[:9]:<9} "
            f"{_price(candidate.price_usd):>13} {_money(candidate.liquidity_usd):>8} "
            f"{_money(candidate.volume_h24):>8} {candidate.price_change_h1:>+7.1f}% {_age(candidate):>5}"
        )
        breakdown = "  ".join(f"{k}={v:.2f}" for k, v in candidate.score_breakdown.items())
        lines.append(f"      {breakdown}")
        if candidate.flags:
            lines.append(f"      flags: {'; '.join(candidate.flags)}")
        if candidate.url:
            lines.append(f"      {candidate.url}")
        lines.append("")

    lines.append("-" * 100)
    lines.append("Score is a relative ranking of this scan's candidates, not a probability of profit.")
    lines.append("Verify every token yourself before buying anything on FOMO.")
    lines.append("")
    return "\n".join(lines)


def render_positions(signals: list[SellSignal]) -> str:
    lines: list[str] = []
    lines.append("")
    lines.append(f"OPEN POSITIONS  —  {len(signals)} tracked")
    lines.append("=" * 100)
    if not signals:
        lines.append("  No positions tracked. Add one with:  coinfinder track --chain solana --pair <addr> ...")
        lines.append("")
        return "\n".join(lines)

    ordered = sorted(signals, key=lambda s: (s.verdict == HOLD, -abs(s.pnl_pct)))
    total_pnl = sum(s.pnl_usd for s in ordered if not s.stale)

    for signal in ordered:
        position = signal.position
        label = _VERDICT_LABEL.get(signal.verdict, signal.verdict)
        lines.append(
            f"{label:<15} {position.symbol[:12]:<12} {signal.pnl_pct:>+8.1f}%  "
            f"({signal.pnl_usd:>+9,.2f} USD)  held {position.hold_hours:.1f}h"
        )
        lines.append(
            f"                entry {_price(position.entry_price_usd)}  →  now {_price(signal.price_usd)}"
            f"   peak {_price(position.peak_price_usd)}   liq {signal.liquidity_change_pct:+.0f}%"
        )
        for reason in signal.reasons:
            lines.append(f"                - {reason}")
        lines.append(f"                key: {position.key}")
        lines.append("")

    lines.append("-" * 100)
    lines.append(f"Unrealized P/L across tracked positions: {total_pnl:+,.2f} USD")
    lines.append("Sell suggestions are mechanical rule output. You place every order yourself on FOMO.")
    lines.append("")
    return "\n".join(lines)


def scan_to_json(passing: list[Candidate], rejected: list[Candidate], limit: int) -> str:
    payload: dict[str, Any] = {
        "candidates": [c.to_dict() for c in passing[:limit]],
        "passed_count": len(passing),
        "rejected_count": len(rejected),
    }
    return json.dumps(payload, indent=2)


def positions_to_json(signals: list[SellSignal]) -> str:
    payload = [
        {
            "key": s.position.key,
            "symbol": s.position.symbol,
            "verdict": s.verdict,
            "reasons": s.reasons,
            "price_usd": s.price_usd,
            "pnl_pct": round(s.pnl_pct, 2),
            "pnl_usd": round(s.pnl_usd, 2),
            "drawdown_from_peak_pct": round(s.drawdown_from_peak_pct, 2),
            "liquidity_change_pct": round(s.liquidity_change_pct, 2),
            "stale": s.stale,
        }
        for s in signals
    ]
    return json.dumps(payload, indent=2)

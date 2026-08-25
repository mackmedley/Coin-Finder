from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coinfinder.config import load_config
from coinfinder.models import Candidate, Position
from coinfinder.sell import HOLD, SELL, TRIM, URGENT_SELL, evaluate
from tests.fixtures.pairs import make_pair


def config():
    return load_config()


def position(entry_price=0.0001, peak=None, entry_liquidity=80_000, hold_hours=5.0) -> Position:
    return Position(
        key="solana:PAIR1",
        chain="solana",
        pair_address="PAIR1",
        symbol="TEST",
        entry_price_usd=entry_price,
        amount_usd=1000.0,
        entry_liquidity_usd=entry_liquidity,
        opened_at=time.time() - hold_hours * 3600,
        peak_price_usd=peak if peak is not None else entry_price,
    )


def current(**kwargs) -> Candidate:
    return Candidate.from_dexscreener_pair(make_pair(**kwargs))


def test_flat_position_holds():
    signal = evaluate(position(), current(price_usd="0.0001"), config())
    assert signal.verdict == HOLD
    assert not signal.is_actionable


def test_take_profit_triggers_sell():
    signal = evaluate(position(), current(price_usd="0.00018"), config())
    assert signal.verdict == SELL
    assert any("take profit" in r for r in signal.reasons)
    assert signal.pnl_pct == 80.0
    assert signal.pnl_usd == 800.0


def test_stop_loss_triggers_sell():
    signal = evaluate(position(), current(price_usd="0.00007"), config())
    assert signal.verdict == SELL
    assert any("stop loss" in r for r in signal.reasons)


def test_trailing_stop_fires_after_a_pump_fades():
    # Entered at 0.0001, ran to 0.0005, now back to 0.0003: still +200% but
    # 40% off the peak, past the -30% trailing limit.
    signal = evaluate(position(peak=0.0005), current(price_usd="0.0003"), config())
    assert signal.verdict == SELL
    assert any("trailing stop" in r for r in signal.reasons)
    assert signal.pnl_pct > 0


def test_liquidity_collapse_outranks_take_profit():
    signal = evaluate(
        position(entry_liquidity=100_000),
        current(price_usd="0.00018", liquidity_usd=20_000),
        config(),
    )
    assert signal.verdict == URGENT_SELL
    assert any("possible rug" in r for r in signal.reasons)


def test_volume_collapse_suggests_trim():
    signal = evaluate(
        position(hold_hours=6),
        current(price_usd="0.0001", volume_h24=480_000, volume_h1=500),
        config(),
    )
    assert signal.verdict == TRIM
    assert any("volume collapsing" in r for r in signal.reasons)


def test_fresh_position_is_not_trimmed_for_low_volume():
    signal = evaluate(
        position(hold_hours=0.2),
        current(price_usd="0.0001", volume_h24=480_000, volume_h1=500),
        config(),
    )
    assert signal.verdict == HOLD


def test_sell_side_dominance_suggests_trim():
    signal = evaluate(
        position(),
        current(price_usd="0.0001", buys_h1=10, sells_h1=90),
        config(),
    )
    assert signal.verdict == TRIM
    assert any("sellers taking over" in r for r in signal.reasons)


def test_missing_live_data_is_flagged_stale_not_sold():
    signal = evaluate(position(), None, config())
    assert signal.verdict == HOLD
    assert signal.stale
    assert any("no live price" in r for r in signal.reasons)

"""Normalized data shapes shared across the package.

`Candidate` is the flattened form of a DEX pair. Raw provider payloads have
inconsistent nesting and missing keys, so everything upstream is funneled
through `Candidate.from_dexscreener_pair` and downstream code only ever sees
plain floats.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    """Coerce provider values (str/int/None/missing) to float."""
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result or result in (float("inf"), float("-inf")):
        return default
    return result


def _nested(payload: Any, *keys: str, default: Any = None) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


@dataclass
class Candidate:
    """A single tradable pair, flattened and normalized."""

    chain: str
    dex: str
    pair_address: str
    token_address: str
    symbol: str
    name: str
    url: str

    price_usd: float = 0.0
    liquidity_usd: float = 0.0
    fdv: float = 0.0
    market_cap: float = 0.0

    volume_h24: float = 0.0
    volume_h6: float = 0.0
    volume_h1: float = 0.0
    volume_m5: float = 0.0

    price_change_m5: float = 0.0
    price_change_h1: float = 0.0
    price_change_h6: float = 0.0
    price_change_h24: float = 0.0

    buys_h1: int = 0
    sells_h1: int = 0
    buys_h24: int = 0
    sells_h24: int = 0

    pair_created_at_ms: int = 0
    socials: list[str] = field(default_factory=list)
    websites: list[str] = field(default_factory=list)
    boost_amount: float = 0.0

    # Filled in by the scoring pass.
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reject_reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @classmethod
    def from_dexscreener_pair(cls, pair: dict[str, Any]) -> "Candidate":
        base = pair.get("baseToken") or {}
        info = pair.get("info") or {}
        socials = info.get("socials") or []
        websites = info.get("websites") or []
        return cls(
            chain=str(pair.get("chainId") or "unknown"),
            dex=str(pair.get("dexId") or "unknown"),
            pair_address=str(pair.get("pairAddress") or ""),
            token_address=str(base.get("address") or ""),
            symbol=str(base.get("symbol") or "?"),
            name=str(base.get("name") or "?"),
            url=str(pair.get("url") or ""),
            price_usd=_f(pair.get("priceUsd")),
            liquidity_usd=_f(_nested(pair, "liquidity", "usd")),
            fdv=_f(pair.get("fdv")),
            market_cap=_f(pair.get("marketCap")),
            volume_h24=_f(_nested(pair, "volume", "h24")),
            volume_h6=_f(_nested(pair, "volume", "h6")),
            volume_h1=_f(_nested(pair, "volume", "h1")),
            volume_m5=_f(_nested(pair, "volume", "m5")),
            price_change_m5=_f(_nested(pair, "priceChange", "m5")),
            price_change_h1=_f(_nested(pair, "priceChange", "h1")),
            price_change_h6=_f(_nested(pair, "priceChange", "h6")),
            price_change_h24=_f(_nested(pair, "priceChange", "h24")),
            buys_h1=int(_f(_nested(pair, "txns", "h1", "buys"))),
            sells_h1=int(_f(_nested(pair, "txns", "h1", "sells"))),
            buys_h24=int(_f(_nested(pair, "txns", "h24", "buys"))),
            sells_h24=int(_f(_nested(pair, "txns", "h24", "sells"))),
            pair_created_at_ms=int(_f(pair.get("pairCreatedAt"))),
            socials=[str(s.get("type") or s.get("platform") or "") for s in socials if isinstance(s, dict)],
            websites=[str(w.get("url") or "") for w in websites if isinstance(w, dict)],
        )

    @property
    def key(self) -> str:
        return f"{self.chain}:{self.pair_address}"

    @property
    def age_minutes(self) -> float:
        if self.pair_created_at_ms <= 0:
            return 0.0
        return max(0.0, (time.time() * 1000 - self.pair_created_at_ms) / 60000)

    @property
    def age_hours(self) -> float:
        return self.age_minutes / 60

    @property
    def buy_ratio_h1(self) -> float:
        """Share of last-hour trades that were buys. 0.5 is neutral."""
        total = self.buys_h1 + self.sells_h1
        return 0.5 if total == 0 else self.buys_h1 / total

    @property
    def turnover_ratio(self) -> float:
        """24h volume relative to pool depth. High = real trading, not a ghost pool."""
        return 0.0 if self.liquidity_usd <= 0 else self.volume_h24 / self.liquidity_usd

    @property
    def fdv_to_liquidity(self) -> float:
        return 0.0 if self.liquidity_usd <= 0 else self.fdv / self.liquidity_usd

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    """An open manual position the user entered on FOMO."""

    key: str
    chain: str
    pair_address: str
    symbol: str
    entry_price_usd: float
    amount_usd: float
    entry_liquidity_usd: float
    opened_at: float
    peak_price_usd: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Position":
        return cls(
            key=str(payload["key"]),
            chain=str(payload.get("chain", "")),
            pair_address=str(payload.get("pair_address", "")),
            symbol=str(payload.get("symbol", "?")),
            entry_price_usd=_f(payload.get("entry_price_usd")),
            amount_usd=_f(payload.get("amount_usd")),
            entry_liquidity_usd=_f(payload.get("entry_liquidity_usd")),
            opened_at=_f(payload.get("opened_at")),
            peak_price_usd=_f(payload.get("peak_price_usd")),
            note=str(payload.get("note", "")),
        )

    @property
    def hold_hours(self) -> float:
        return max(0.0, (time.time() - self.opened_at) / 3600)

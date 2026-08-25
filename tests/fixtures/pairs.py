"""Synthetic DexScreener pair payloads shaped like the real API responses."""

from __future__ import annotations

import time


def _ms_ago(hours: float) -> int:
    return int((time.time() - hours * 3600) * 1000)


def make_pair(
    *,
    symbol: str = "TEST",
    chain: str = "solana",
    pair_address: str = "PAIR1",
    price_usd: str = "0.00012",
    liquidity_usd: float = 80_000,
    volume_h24: float = 400_000,
    volume_h1: float = 30_000,
    price_change_h1: float = 12.0,
    price_change_h6: float = 25.0,
    buys_h1: int = 180,
    sells_h1: int = 120,
    buys_h24: int = 2000,
    sells_h24: int = 1500,
    fdv: float = 900_000,
    age_hours: float = 20,
    socials: bool = True,
) -> dict:
    return {
        "chainId": chain,
        "dexId": "raydium",
        "url": f"https://dexscreener.com/{chain}/{pair_address}",
        "pairAddress": pair_address,
        "baseToken": {"address": f"TOKEN-{symbol}", "name": f"{symbol} Coin", "symbol": symbol},
        "quoteToken": {"address": "So111", "name": "Wrapped SOL", "symbol": "SOL"},
        "priceUsd": price_usd,
        "txns": {
            "m5": {"buys": 10, "sells": 8},
            "h1": {"buys": buys_h1, "sells": sells_h1},
            "h6": {"buys": 900, "sells": 700},
            "h24": {"buys": buys_h24, "sells": sells_h24},
        },
        "volume": {"h24": volume_h24, "h6": volume_h24 / 4, "h1": volume_h1, "m5": volume_h1 / 12},
        "priceChange": {"m5": 1.2, "h1": price_change_h1, "h6": price_change_h6, "h24": 40.0},
        "liquidity": {"usd": liquidity_usd, "base": 1000, "quote": 50},
        "fdv": fdv,
        "marketCap": fdv,
        "pairCreatedAt": _ms_ago(age_hours),
        "info": {
            "socials": [{"type": "twitter", "url": "https://x.com/x"}] if socials else [],
            "websites": [{"url": "https://example.com"}] if socials else [],
        },
    }

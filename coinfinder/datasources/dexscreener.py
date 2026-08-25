"""DexScreener client.

Free, no API key. Two discovery paths are combined:

* token boosts — paid promotion feed, a decent proxy for "what is being pushed
  right now", which is where meme coin flow actually originates;
* search — keyword queries, to catch pairs that aren't paying for boosts.

Boost/profile endpoints are limited to 60 req/min and search/pairs to 300, so
the two groups get separate limiters.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from ..models import Candidate
from .http import HttpClient

log = logging.getLogger(__name__)

BASE = "https://api.dexscreener.com"


class DexScreenerClient:
    def __init__(self, timeout: float = 12.0, user_agent: str = "coinfinder/0.1") -> None:
        self._fast = HttpClient(timeout=timeout, user_agent=user_agent, calls_per_minute=240)
        self._slow = HttpClient(timeout=timeout, user_agent=user_agent, calls_per_minute=50)

    def close(self) -> None:
        self._fast.close()
        self._slow.close()

    def __enter__(self) -> "DexScreenerClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def boosted_tokens(self) -> list[dict[str, Any]]:
        """Recently boosted tokens: [{chainId, tokenAddress, totalAmount, ...}]."""
        out: list[dict[str, Any]] = []
        for path in ("/token-boosts/latest/v1", "/token-boosts/top/v1"):
            payload = self._slow.get_json(f"{BASE}{path}")
            if isinstance(payload, list):
                out.extend(item for item in payload if isinstance(item, dict))
            elif payload is not None:
                log.warning("unexpected payload shape from %s", path)
        return out

    def pairs_for_tokens(self, chain: str, token_addresses: Iterable[str]) -> list[dict[str, Any]]:
        """Look up every pair trading the given tokens. Batched 30 per request."""
        addresses = [a for a in dict.fromkeys(token_addresses) if a]
        pairs: list[dict[str, Any]] = []
        for start in range(0, len(addresses), 30):
            batch = ",".join(addresses[start : start + 30])
            payload = self._fast.get_json(f"{BASE}/tokens/v1/{chain}/{batch}")
            if isinstance(payload, list):
                pairs.extend(p for p in payload if isinstance(p, dict))
            elif isinstance(payload, dict) and isinstance(payload.get("pairs"), list):
                pairs.extend(p for p in payload["pairs"] if isinstance(p, dict))
        return pairs

    def search(self, query: str) -> list[dict[str, Any]]:
        payload = self._fast.get_json(f"{BASE}/latest/dex/search", params={"q": query})
        if isinstance(payload, dict) and isinstance(payload.get("pairs"), list):
            return [p for p in payload["pairs"] if isinstance(p, dict)]
        return []

    def get_pair(self, chain: str, pair_address: str) -> dict[str, Any] | None:
        """Fetch one pair's current state. Used to re-price open positions.

        This endpoint has two response shapes in the wild: a `pairs` list, and a
        singular `pair` object (with `pairs` sometimes null alongside it). Accept
        both — getting this wrong silently reports every position as stale.
        """
        payload = self._fast.get_json(f"{BASE}/latest/dex/pairs/{chain}/{pair_address}")
        if not isinstance(payload, dict):
            return None
        pairs = payload.get("pairs")
        if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
            return pairs[0]
        single = payload.get("pair")
        return single if isinstance(single, dict) else None


def discover(client: DexScreenerClient, config: dict[str, Any]) -> list[Candidate]:
    """Collect candidate pairs from boosts + keyword search, deduped by pair."""
    discovery = config.get("discovery", {})
    chains = {str(c).lower() for c in discovery.get("chains", [])}
    raw_pairs: list[dict[str, Any]] = []

    boosts_by_chain: dict[str, list[str]] = {}
    boost_amounts: dict[str, float] = {}
    for boost in client.boosted_tokens():
        chain = str(boost.get("chainId") or "").lower()
        token = str(boost.get("tokenAddress") or "")
        if not token or (chains and chain not in chains):
            continue
        boosts_by_chain.setdefault(chain, []).append(token)
        amount = boost.get("totalAmount") or boost.get("amount") or 0
        try:
            boost_amounts[f"{chain}:{token.lower()}"] = float(amount)
        except (TypeError, ValueError):
            pass

    for chain, tokens in boosts_by_chain.items():
        raw_pairs.extend(client.pairs_for_tokens(chain, tokens))

    for term in discovery.get("search_terms", []):
        raw_pairs.extend(client.search(str(term)))

    seen: set[str] = set()
    candidates: list[Candidate] = []
    for pair in raw_pairs:
        candidate = Candidate.from_dexscreener_pair(pair)
        if chains and candidate.chain.lower() not in chains:
            continue
        if not candidate.pair_address or candidate.key in seen:
            continue
        seen.add(candidate.key)
        candidate.boost_amount = boost_amounts.get(
            f"{candidate.chain.lower()}:{candidate.token_address.lower()}", 0.0
        )
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.volume_h24, reverse=True)
    max_candidates = int(discovery.get("max_candidates", 150))
    return candidates[:max_candidates]

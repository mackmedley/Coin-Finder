"""Provider-shape tests.

These cover the response-parsing seams that only surface against the live API:
inconsistent payload shapes, chain filtering, and dedup across the two
discovery feeds.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coinfinder.config import load_config
from coinfinder.datasources.dexscreener import DexScreenerClient, discover
from tests.fixtures.pairs import make_pair


class StubHttp:
    """Stands in for HttpClient, returning canned payloads by URL substring."""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get_json(self, url: str, params: dict | None = None) -> object:
        self.calls.append(url)
        for fragment, payload in self.routes.items():
            if fragment in url:
                return payload
        return None

    def close(self) -> None:
        pass


def client_with(fast: StubHttp, slow: StubHttp | None = None) -> DexScreenerClient:
    client = DexScreenerClient.__new__(DexScreenerClient)
    client._fast = fast
    client._slow = slow or StubHttp({})
    return client


def test_get_pair_reads_pairs_list_shape():
    pair = make_pair(symbol="AAA", pair_address="P1")
    client = client_with(StubHttp({"/latest/dex/pairs/": {"pairs": [pair]}}))
    assert client.get_pair("solana", "P1")["baseToken"]["symbol"] == "AAA"


def test_get_pair_reads_singular_pair_shape():
    # The shape that would otherwise report every position as stale.
    pair = make_pair(symbol="BBB", pair_address="P2")
    client = client_with(StubHttp({"/latest/dex/pairs/": {"pair": pair, "pairs": None}}))
    assert client.get_pair("solana", "P2")["baseToken"]["symbol"] == "BBB"


def test_get_pair_returns_none_when_pair_is_missing():
    client = client_with(StubHttp({"/latest/dex/pairs/": {"pairs": [], "pair": None}}))
    assert client.get_pair("solana", "NOPE") is None


def test_get_pair_survives_a_failed_request():
    client = client_with(StubHttp({}))
    assert client.get_pair("solana", "P1") is None


def test_pairs_for_tokens_accepts_bare_list_and_wrapped_shapes():
    bare = client_with(StubHttp({"/tokens/v1/": [make_pair(pair_address="P1")]}))
    assert len(bare.pairs_for_tokens("solana", ["T1"])) == 1

    wrapped = client_with(StubHttp({"/tokens/v1/": {"pairs": [make_pair(pair_address="P2")]}}))
    assert len(wrapped.pairs_for_tokens("solana", ["T1"])) == 1


def test_discover_filters_off_chain_pairs_and_dedupes():
    config = load_config()
    config["discovery"]["chains"] = ["solana"]
    config["discovery"]["search_terms"] = ["meme"]

    slow = StubHttp({"/token-boosts/": [{"chainId": "solana", "tokenAddress": "TOKEN-AAA", "totalAmount": 500}]})
    fast = StubHttp(
        {
            # Same pair from both feeds — must appear once.
            "/tokens/v1/": [make_pair(symbol="AAA", pair_address="P1")],
            "/latest/dex/search": {
                "pairs": [
                    make_pair(symbol="AAA", pair_address="P1"),
                    make_pair(symbol="CCC", pair_address="P3", chain="ethereum"),
                ]
            },
        }
    )

    found = discover(client_with(fast, slow), config)
    assert [c.symbol for c in found] == ["AAA"]
    assert found[0].boost_amount == 500


def test_discover_respects_max_candidates():
    config = load_config()
    config["discovery"]["chains"] = ["solana"]
    config["discovery"]["search_terms"] = ["meme"]
    config["discovery"]["max_candidates"] = 2

    pairs = [make_pair(symbol=f"S{i}", pair_address=f"P{i}", volume_h24=1000 * i) for i in range(10)]
    fast = StubHttp({"/latest/dex/search": {"pairs": pairs}})

    found = discover(client_with(fast), config)
    assert len(found) == 2
    # Sorted by 24h volume, descending.
    assert [c.symbol for c in found] == ["S9", "S8"]

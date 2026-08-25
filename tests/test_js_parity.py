"""The browser version must score identically to the Python version.

"Coin Finder.html" carries its own JavaScript copy of scoring.py so it can run
with nothing installed. Two implementations of one rule set drift silently —
a weight tweaked in Python and forgotten in JS would leave the two halves of
this project recommending different coins.

This scores a spread of payloads with the Python engine, hands the same
payloads to the JavaScript engine lifted straight out of the HTML file, and
requires the scores, every component, the flags, and the rejection reason
strings to match.

Skipped when Node isn't installed — a contributor without it still gets the
rest of the suite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coinfinder.config import load_config
from coinfinder.models import Candidate
from coinfinder.scoring import apply_filters, score_candidate
from tests.fixtures.pairs import make_pair

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "Coin Finder.html"
CHECKER = Path(__file__).resolve().parent / "js_parity_check.js"

# Single-axis variations off the baseline, chosen so every branch of the
# scoring code is exercised: each filter rejection, negative and late-pump
# momentum, the sample-size confidence scaling, each safety deduction, and
# both age extremes.
VARIANTS = [
    ("baseline", {}),
    ("rich", dict(liquidity_usd=500_000, volume_h24=3_000_000, fdv=2_000_000)),
    ("thin_liq", dict(liquidity_usd=25_000)),
    ("below_min_liq", dict(liquidity_usd=5_000)),
    ("low_vol", dict(volume_h24=5_000)),
    ("neg_momentum", dict(price_change_h1=-20.0, price_change_h6=-35.0)),
    ("crash", dict(price_change_h1=-70.0, price_change_h6=-80.0)),
    ("late_pump", dict(price_change_h1=400.0, price_change_h6=600.0)),
    ("edge_pump", dict(price_change_h1=150.0, price_change_h6=150.0)),
    ("few_txns", dict(buys_h1=3, sells_h1=2)),
    ("no_txns", dict(buys_h1=0, sells_h1=0)),
    ("sell_heavy", dict(buys_h1=40, sells_h1=160)),
    ("h24_net_selling", dict(buys_h24=1000, sells_h24=3000)),
    ("no_socials", dict(socials=False)),
    ("high_fdv", dict(fdv=50_000_000)),
    ("extreme_fdv", dict(fdv=500_000_000)),
    ("young", dict(age_hours=1.0)),
    ("very_young", dict(age_hours=0.2)),
    ("old", dict(age_hours=600)),
    ("ancient", dict(age_hours=2000)),
    ("vol_fading", dict(volume_h1=500, volume_h24=400_000)),
    ("zero_fdv", dict(fdv=0)),
]


def build_cases() -> dict:
    pairs = {}
    for index, (name, kwargs) in enumerate(VARIANTS):
        pairs[name] = make_pair(symbol=name.upper()[:8], pair_address=f"P{index}", **kwargs)

    # Provider omitted pairCreatedAt: age unknown, not brand new.
    no_age = make_pair(symbol="NOAGE", pair_address="PX")
    no_age["pairCreatedAt"] = 0
    pairs["unknown_age"] = no_age

    # Almost every field missing, to pin down that both engines coerce alike.
    pairs["sparse"] = {"chainId": "solana", "pairAddress": "PS", "baseToken": {"symbol": "SPARSE"}}

    config = load_config()
    expected = {}
    for name, pair in pairs.items():
        candidate = Candidate.from_dexscreener_pair(pair)
        reasons = apply_filters(candidate, config)
        if reasons:
            expected[name] = {"rejected": True, "reasons": reasons}
        else:
            scored = score_candidate(candidate, config)
            expected[name] = {
                "rejected": False,
                "score": scored.score,
                "breakdown": {k: round(v, 6) for k, v in scored.score_breakdown.items()},
                "flags": scored.flags,
            }
    return {"pairs": pairs, "python": expected}


def test_javascript_scoring_matches_python(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is not installed")

    cases = build_cases()

    # A vacuous pass is the real risk here: if every case were rejected, no
    # score would ever be compared. Require both paths to be represented.
    verdicts = [entry["rejected"] for entry in cases["python"].values()]
    assert any(verdicts), "no case exercised the filter-rejection path"
    assert not all(verdicts), "no case reached scoring"

    cases_file = tmp_path / "cases.json"
    cases_file.write_text(json.dumps(cases))

    result = subprocess.run(
        ["node", str(CHECKER), str(cases_file), str(HTML)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        "The JavaScript in 'Coin Finder.html' no longer scores like the Python engine.\n"
        f"{result.stdout}\n{result.stderr}"
    )

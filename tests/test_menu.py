"""Tests for the interactive menu's input parsing.

The menu delegates all real work to cli.main(), so the only logic worth testing
here is how it reads what the user pastes in.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coinfinder.menu import parse_pair_reference

PAIR = "8sLbNZoA1cfnvMJLPfp98ZLAnFSYCFApfJKMbiXNLwxj"


def test_parses_a_standard_dexscreener_url():
    assert parse_pair_reference(f"https://dexscreener.com/solana/{PAIR}") == ("solana", PAIR)


def test_parses_url_without_scheme_or_with_extra_path():
    assert parse_pair_reference(f"dexscreener.com/base/{PAIR}") == ("base", PAIR)
    assert parse_pair_reference(f"https://dexscreener.com/solana/{PAIR}?maker=0x1") == ("solana", PAIR)


def test_url_chain_is_normalized_to_lowercase():
    assert parse_pair_reference(f"https://DexScreener.com/SOLANA/{PAIR}") == ("solana", PAIR)


def test_parses_bare_chain_and_pair():
    assert parse_pair_reference(f"solana {PAIR}") == ("solana", PAIR)
    assert parse_pair_reference(f"SOLANA:{PAIR}") == ("solana", PAIR)


def test_rejects_input_it_cannot_understand():
    assert parse_pair_reference("") is None
    assert parse_pair_reference("just some words here") is None
    assert parse_pair_reference(PAIR) is None  # a pair with no chain is ambiguous

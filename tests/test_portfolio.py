from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coinfinder.config import ConfigError, load_config
from coinfinder.portfolio import PositionStore


def store(tmp_path: Path) -> PositionStore:
    return PositionStore(tmp_path / "positions.json")


def test_open_and_reload(tmp_path: Path):
    first = store(tmp_path)
    first.open(
        chain="solana",
        pair_address="PAIR1",
        symbol="TEST",
        entry_price_usd=0.0001,
        amount_usd=500,
        entry_liquidity_usd=80_000,
    )
    reloaded = PositionStore(tmp_path / "positions.json")
    assert [p.key for p in reloaded.all()] == ["solana:PAIR1"]
    assert reloaded.get("solana:PAIR1").amount_usd == 500


def test_peak_only_ratchets_up(tmp_path: Path):
    s = store(tmp_path)
    s.open(
        chain="solana",
        pair_address="PAIR1",
        symbol="TEST",
        entry_price_usd=0.0001,
        amount_usd=500,
        entry_liquidity_usd=80_000,
    )
    s.update_peak("solana:PAIR1", 0.0005)
    s.update_peak("solana:PAIR1", 0.0002)
    assert s.get("solana:PAIR1").peak_price_usd == 0.0005


def test_close_removes_position(tmp_path: Path):
    s = store(tmp_path)
    s.open(
        chain="solana",
        pair_address="PAIR1",
        symbol="TEST",
        entry_price_usd=0.0001,
        amount_usd=500,
        entry_liquidity_usd=80_000,
    )
    assert s.close("solana:PAIR1") is not None
    assert s.all() == []
    assert s.close("solana:PAIR1") is None


def test_corrupt_positions_file_raises(tmp_path: Path):
    path = tmp_path / "positions.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        PositionStore(path)


def test_default_config_loads_and_validates():
    config = load_config()
    assert config["scoring"]["weights"]
    assert config["filters"]["min_liquidity_usd"] > 0


def test_bad_weights_rejected(tmp_path: Path):
    override = tmp_path / "bad.yaml"
    override.write_text("scoring:\n  weights:\n    liquidity: -5\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(override)


def test_override_merges_over_defaults(tmp_path: Path):
    override = tmp_path / "override.yaml"
    override.write_text("filters:\n  min_liquidity_usd: 99999\n", encoding="utf-8")
    config = load_config(override)
    assert config["filters"]["min_liquidity_usd"] == 99999
    assert config["filters"]["min_volume_h24_usd"] == 20000  # untouched default survives

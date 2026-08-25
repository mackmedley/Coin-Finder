"""JSON-backed store of open positions.

Positions are entered manually on FOMO; this file only mirrors them so the sell
engine has an entry price and a running peak to compare against.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .models import Position


class PositionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._positions: dict[str, Position] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"positions file {self.path} is unreadable: {exc}") from exc
        for item in payload.get("positions", []):
            position = Position.from_dict(item)
            self._positions[position.key] = position

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"positions": [p.to_dict() for p in self._positions.values()]}
        # Write-then-rename so an interrupted save can't truncate the file.
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def all(self) -> list[Position]:
        return sorted(self._positions.values(), key=lambda p: p.opened_at)

    def get(self, key: str) -> Position | None:
        return self._positions.get(key)

    def open(
        self,
        *,
        chain: str,
        pair_address: str,
        symbol: str,
        entry_price_usd: float,
        amount_usd: float,
        entry_liquidity_usd: float,
        note: str = "",
    ) -> Position:
        position = Position(
            key=f"{chain}:{pair_address}",
            chain=chain,
            pair_address=pair_address,
            symbol=symbol,
            entry_price_usd=entry_price_usd,
            amount_usd=amount_usd,
            entry_liquidity_usd=entry_liquidity_usd,
            opened_at=time.time(),
            peak_price_usd=entry_price_usd,
            note=note,
        )
        self._positions[position.key] = position
        self.save()
        return position

    def close(self, key: str) -> Position | None:
        position = self._positions.pop(key, None)
        if position is not None:
            self.save()
        return position

    def update_peak(self, key: str, price_usd: float) -> None:
        position = self._positions.get(key)
        if position is not None and price_usd > position.peak_price_usd:
            position.peak_price_usd = price_usd
            self.save()

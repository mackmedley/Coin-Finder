"""Command line entry point.

    coinfinder scan                 find and rank buy candidates
    coinfinder track ...            record a position you opened on FOMO
    coinfinder check                evaluate open positions for exit signals
    coinfinder untrack <key>        stop tracking a position you closed
    coinfinder positions            list tracked positions without hitting the network
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from . import report
from .config import ConfigError, load_config, resolve_path
from .datasources.dexscreener import DexScreenerClient, discover
from .models import Candidate
from .portfolio import PositionStore
from .scoring import rank
from .sell import evaluate

log = logging.getLogger("coinfinder")

DISCLAIMER = (
    "coinfinder is a research tool, not financial advice. It places no orders and "
    "holds no funds. Meme coins are extremely high risk and most go to zero."
)


def _client(config: dict) -> DexScreenerClient:
    http = config.get("http", {})
    return DexScreenerClient(
        timeout=float(http.get("timeout_seconds", 12)),
        user_agent=str(http.get("user_agent", "coinfinder/0.1")),
    )


def _archive_scan(config: dict, passing: list[Candidate]) -> None:
    try:
        directory = resolve_path(config, "scan_history_dir")
    except ConfigError:
        return
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = directory / f"scan-{stamp}.json"
    path.write_text(
        json.dumps({"scanned_at": time.time(), "candidates": [c.to_dict() for c in passing]}, indent=2),
        encoding="utf-8",
    )
    log.info("scan archived to %s", path)


def cmd_scan(args: argparse.Namespace, config: dict) -> int:
    with _client(config) as client:
        candidates = discover(client, config)
    if not candidates:
        print("No pairs returned from the data provider. Check network access and try again.")
        return 1

    passing, rejected = rank(candidates, config)
    if args.json:
        print(report.scan_to_json(passing, rejected, args.limit))
    else:
        print(report.render_scan(passing, rejected, args.limit))
    if not args.no_archive:
        _archive_scan(config, passing)
    return 0


def cmd_track(args: argparse.Namespace, config: dict) -> int:
    store = PositionStore(resolve_path(config, "positions_file"))
    with _client(config) as client:
        pair = client.get_pair(args.chain, args.pair)
    if pair is None:
        print(f"Could not find pair {args.pair} on {args.chain}.", file=sys.stderr)
        return 1

    candidate = Candidate.from_dexscreener_pair(pair)
    entry_price = args.entry_price if args.entry_price is not None else candidate.price_usd
    if entry_price <= 0:
        print("No usable entry price. Pass --entry-price explicitly.", file=sys.stderr)
        return 1

    position = store.open(
        chain=candidate.chain,
        pair_address=candidate.pair_address,
        symbol=candidate.symbol,
        entry_price_usd=entry_price,
        amount_usd=args.amount,
        entry_liquidity_usd=candidate.liquidity_usd,
        note=args.note,
    )
    print(
        f"Tracking {position.symbol} ({position.key}) — entry {entry_price:.8g} USD, "
        f"size {position.amount_usd:,.2f} USD."
    )
    return 0


def cmd_check(args: argparse.Namespace, config: dict) -> int:
    store = PositionStore(resolve_path(config, "positions_file"))
    positions = store.all()
    if not positions:
        print(report.render_positions([]))
        return 0

    signals = []
    with _client(config) as client:
        for position in positions:
            pair = client.get_pair(position.chain, position.pair_address)
            current = Candidate.from_dexscreener_pair(pair) if pair else None
            if current is not None and current.price_usd > 0:
                store.update_peak(position.key, current.price_usd)
                position = store.get(position.key) or position
            signals.append(evaluate(position, current, config))

    if args.json:
        print(report.positions_to_json(signals))
    else:
        print(report.render_positions(signals))
    return 0


def cmd_untrack(args: argparse.Namespace, config: dict) -> int:
    store = PositionStore(resolve_path(config, "positions_file"))
    position = store.close(args.key)
    if position is None:
        print(f"No tracked position with key {args.key}.", file=sys.stderr)
        return 1
    print(f"Stopped tracking {position.symbol} ({position.key}).")
    return 0


def cmd_positions(args: argparse.Namespace, config: dict) -> int:
    store = PositionStore(resolve_path(config, "positions_file"))
    positions = store.all()
    if args.json:
        print(json.dumps([p.to_dict() for p in positions], indent=2))
        return 0
    if not positions:
        print("No tracked positions.")
        return 0
    for position in positions:
        print(
            f"{position.symbol:<12} {position.key}  entry {position.entry_price_usd:.8g}  "
            f"size ${position.amount_usd:,.2f}  held {position.hold_hours:.1f}h"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coinfinder", description=DISCLAIMER)
    parser.add_argument("--config", type=Path, help="YAML file merged over config/default.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="log provider requests and retries")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="find and rank buy candidates")
    scan.add_argument("--limit", type=int, default=10, help="how many candidates to show (default 10)")
    scan.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    scan.add_argument("--no-archive", action="store_true", help="skip writing the scan to scan history")
    scan.set_defaults(func=cmd_scan)

    track = subparsers.add_parser("track", help="record a position you opened on FOMO")
    track.add_argument("--chain", required=True, help="chain id, e.g. solana")
    track.add_argument("--pair", required=True, help="pair address from the DexScreener URL")
    track.add_argument("--amount", type=float, required=True, help="position size in USD")
    track.add_argument("--entry-price", type=float, help="entry price in USD (defaults to live price)")
    track.add_argument("--note", default="", help="free-text note")
    track.set_defaults(func=cmd_track)

    check = subparsers.add_parser("check", help="evaluate open positions for exit signals")
    check.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    check.set_defaults(func=cmd_check)

    untrack = subparsers.add_parser("untrack", help="stop tracking a position")
    untrack.add_argument("key", help="position key, e.g. solana:0xabc...")
    untrack.set_defaults(func=cmd_untrack)

    positions = subparsers.add_parser("positions", help="list tracked positions (no network calls)")
    positions.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    positions.set_defaults(func=cmd_positions)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        return args.func(args, config)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

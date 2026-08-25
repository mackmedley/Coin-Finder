"""Interactive menu for people who'd rather not type commands.

This is a thin front-end over cli.main(): every option builds the same argv a
terminal user would type and hands it over. No trading logic lives here, so the
menu can't drift from what the CLI does.

Launched by the double-clickable wrappers ("Coin Finder.command" / .bat), or
directly with `python3 -m coinfinder.menu`.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from coinfinder.cli import main as cli_main

# https://dexscreener.com/solana/<pair>  ->  ("solana", "<pair>")
DEXSCREENER_URL = re.compile(
    r"dexscreener\.com/([a-z0-9-]+)/([A-Za-z0-9]+)", re.IGNORECASE
)

FAILURE_HINT = """
  That didn't return anything. The usual causes, in order:
    - No internet connection, or a network that blocks the data provider.
    - The coin's pool is too new or too small to be listed yet.
  For the full technical detail, run this from a terminal instead:
    python3 -m coinfinder.cli -v scan
"""

MENU = """
==================================================
                  COIN  FINDER
==================================================
  1  Scan for coins to buy
  2  Check my positions for exit signals
  3  List my positions
  4  Track a position I just bought
  5  Stop tracking a position
  6  Quit
==================================================
"""


def ask(prompt: str, default: str = "") -> str:
    """Prompt for a line. Returns default on empty input, "" on Ctrl+C/Ctrl+D."""
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    return answer or default


def ask_number(prompt: str, allow_blank: bool = False) -> float | None:
    """Prompt until the answer parses as a positive number (or is left blank)."""
    while True:
        raw = ask(prompt)
        if not raw:
            if allow_blank:
                return None
            return None
        try:
            value = float(raw.replace("$", "").replace(",", ""))
        except ValueError:
            print("  That isn't a number. Try something like 250")
            continue
        if value <= 0:
            print("  Enter a number greater than zero.")
            continue
        return value


def parse_pair_reference(raw: str) -> tuple[str, str] | None:
    """Accept a DexScreener URL or a bare "chain pair" / "chain:pair" string."""
    match = DEXSCREENER_URL.search(raw)
    if match:
        return match.group(1).lower(), match.group(2)
    parts = raw.replace(":", " ").split()
    if len(parts) == 2:
        return parts[0].lower(), parts[1]
    return None


def do_scan() -> int:
    limit = ask("  How many coins to show? [10] ", "10")
    argv = ["scan"]
    if limit.isdigit() and int(limit) > 0:
        argv += ["--limit", limit]
    return cli_main(argv)


def do_track() -> int:
    print("\n  Paste the DexScreener link for the coin you bought.")
    print("  (Or type the chain and pair address separated by a space.)")
    raw = ask("  Link: ")
    if not raw:
        print("  Cancelled.")
        return 0

    reference = parse_pair_reference(raw)
    if reference is None:
        print("  Couldn't read that. Expected a dexscreener.com link, or: solana <pair address>")
        return 0
    chain, pair = reference

    amount = ask_number("  How much did you put in, in dollars? ")
    if amount is None:
        print("  Cancelled — a position size is required.")
        return 0

    print("  Entry price: press Enter to use the current live price.")
    entry = ask_number("  Entry price in dollars: ", allow_blank=True)
    note = ask("  Note (optional): ")

    argv = ["track", "--chain", chain, "--pair", pair, "--amount", str(amount)]
    if entry is not None:
        argv += ["--entry-price", str(entry)]
    if note:
        argv += ["--note", note]
    return cli_main(argv)


def do_untrack() -> int:
    cli_main(["positions"])
    key = ask("\n  Position key to remove (e.g. solana:0xabc...), or Enter to cancel: ")
    if not key:
        print("  Cancelled.")
        return 0
    return cli_main(["untrack", key])


ACTIONS: dict[str, tuple[str, Callable[[], int]]] = {
    "1": ("Scan", do_scan),
    "2": ("Check positions", lambda: cli_main(["check"])),
    "3": ("List positions", lambda: cli_main(["positions"])),
    "4": ("Track a position", do_track),
    "5": ("Stop tracking", do_untrack),
}


def main() -> int:
    # The HTTP layer logs a warning per retry. Three identical stack-trace-ish
    # paragraphs are alarming and useless here — the commands already print a
    # plain-language failure line, and FAILURE_HINT covers the likely cause.
    logging.getLogger("coinfinder.datasources.http").setLevel(logging.ERROR)

    print("\n  This tool only suggests. It never places a trade or touches your money.")
    print("  You make every buy and sell yourself in FOMO.")

    while True:
        print(MENU)
        choice = ask("  Choose 1-6: ")

        if choice in ("6", "q", "quit", "exit", ""):
            print("\n  Bye.\n")
            return 0

        action = ACTIONS.get(choice)
        if action is None:
            print("  Please enter a number from 1 to 6.")
            continue

        print()
        try:
            if action[1]() not in (0, None):
                print(FAILURE_HINT)
        except KeyboardInterrupt:
            print("\n  Cancelled.")
        except Exception as exc:  # a crash here shouldn't close the whole window
            print(f"\n  Something went wrong: {exc}")
            print("  If this keeps happening, run with -v for details and send the output.")

        ask("\n  Press Enter to return to the menu... ")


if __name__ == "__main__":
    raise SystemExit(main())

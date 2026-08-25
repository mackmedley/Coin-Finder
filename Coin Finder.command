#!/usr/bin/env bash
# Double-click to open Coin Finder in your browser (macOS and Linux).
#
# Why this exists: Safari refuses to let a page opened straight off the disk
# download live price data (Chrome and Firefox allow it). Serving the same
# page over http://127.0.0.1 is allowed by every browser, so this starts a
# tiny local server and opens the app. Nothing leaves your machine — the
# server only answers this computer.
#
# Keep this window open while using the app. Close it to stop.

cd "$(dirname "$0")" || exit 1

pause_and_exit() {
    echo
    read -r -p "Press Enter to close this window... "
    exit "${1:-1}"
}

open_url() {
    if command -v open >/dev/null 2>&1; then open "$1"
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1"
    else echo "Open this in your browser:  $1"
    fi
}

if [ ! -f "Coin Finder.html" ]; then
    echo "Can't find 'Coin Finder.html' next to this file."
    echo "Keep both files together in the same folder."
    pause_and_exit 1
fi

# A usable Python (the server is from its standard library — nothing to install).
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)' 2>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo
    echo "  Python wasn't found."
    echo "  If a macOS window just offered to install 'command line developer tools',"
    echo "  click Install, wait for it to finish, then double-click this file again."
    echo "  Otherwise install Python from https://python.org/downloads and retry."
    pause_and_exit 1
fi

SERVER_PID=""
trap '[ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null' EXIT

for PORT in 8791 8792 8793 8794 8795; do
    URL="http://127.0.0.1:$PORT/Coin%20Finder.html"

    # A window from an earlier double-click may still be serving — reuse it.
    if command -v curl >/dev/null 2>&1 &&
       curl -fsS --max-time 1 "$URL" 2>/dev/null | grep -q "Coin Finder"; then
        echo "Coin Finder is already running — opening your browser."
        open_url "$URL"
        exit 0
    fi

    "$PYTHON" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
    SERVER_PID=$!
    sleep 1
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        echo
        echo "  Coin Finder is running:  $URL"
        echo "  Keep this window open while you use the app."
        echo "  Close this window (or press Ctrl+C) when you're done."
        echo
        open_url "$URL"
        wait "$SERVER_PID"
        exit 0
    fi
    SERVER_PID=""
done

echo "Couldn't start the local server (ports 8791-8795 are all in use)."
echo "Falling back to opening the file directly — use Chrome or Firefox if Safari"
echo "then says it can't load prices."
open_url "file://$(pwd)/Coin Finder.html"
pause_and_exit 1

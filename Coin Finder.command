#!/usr/bin/env bash
# Double-click this file to open Coin Finder (macOS and Linux).
#
# Double-clicking starts in the home directory, not here, so the first job is to
# move to this script's own folder. Everything else is finding a usable Python
# and making sure the two dependencies are present.

cd "$(dirname "$0")" || exit 1

pause_and_exit() {
    echo
    read -r -p "Press Enter to close this window... "
    exit "${1:-1}"
}

echo "Starting Coin Finder..."

# python3 is the norm; some systems only ship `python` as 3.x.
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo
    echo "  Python 3.10 or newer isn't installed (or isn't on the PATH)."
    echo "  Install it from https://python.org/downloads and double-click this again."
    pause_and_exit 1
fi

# Install dependencies only when something is actually missing, so the normal
# launch doesn't pay for a pip round-trip.
if ! "$PYTHON" -c 'import requests, yaml' >/dev/null 2>&1; then
    echo "First run: installing the two dependencies (requests, PyYAML)..."
    if ! "$PYTHON" -m pip install --quiet -r requirements.txt; then
        echo
        echo "  Couldn't install dependencies automatically."
        echo "  Try running this by hand:  $PYTHON -m pip install -r requirements.txt"
        pause_and_exit 1
    fi
    echo "Done."
fi

"$PYTHON" -m coinfinder.menu
status=$?

if [ $status -ne 0 ]; then
    echo
    echo "  Coin Finder exited with an error (code $status)."
    pause_and_exit $status
fi

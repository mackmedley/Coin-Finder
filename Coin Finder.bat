@echo off
REM Double-click to open Coin Finder in your browser (Windows).
REM
REM This serves the app over http://127.0.0.1 with a tiny local server (from
REM Python's standard library - nothing to install) so every browser lets it
REM fetch live prices. Nothing leaves your machine.
REM
REM Keep this window open while using the app. Close it to stop.

cd /d "%~dp0"

if not exist "Coin Finder.html" (
    echo Can't find "Coin Finder.html" next to this file.
    echo Keep both files together in the same folder.
    pause
    exit /b 1
)

set "PYTHON="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"

if not defined PYTHON (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

set "PORT=8791"
set "URL=http://127.0.0.1:%PORT%/Coin%%20Finder.html"

if not defined PYTHON (
    REM No Python: Chrome and Edge can fetch prices from a plain file, so just open it.
    echo Python wasn't found - opening the file directly instead.
    echo That works in Chrome and Edge. To make it work in every browser, install
    echo Python from https://python.org/downloads and run this again.
    start "" "Coin Finder.html"
    pause
    exit /b 0
)

echo.
echo   Coin Finder is running:  %URL%
echo   Keep this window open while you use the app.
echo   Close this window when you're done.
echo.

REM Open the browser a moment after the server starts.
start "" cmd /c "timeout /t 2 >nul & start "" "%URL%""
%PYTHON% -m http.server %PORT% --bind 127.0.0.1 >nul 2>&1

REM If the port was already busy, an earlier window is probably still serving -
REM the browser tab that just opened will simply use it.
exit /b 0

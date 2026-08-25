@echo off
REM Double-click this file to open Coin Finder (Windows).
REM
REM %~dp0 is this script's own folder - double-clicking can start elsewhere,
REM so move here first, then find a usable Python and check dependencies.

cd /d "%~dp0"

echo Starting Coin Finder...

REM The py launcher ships with the python.org installer and is the most
REM reliable way to get a modern Python; fall back to python on PATH.
set "PYTHON="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"

if not defined PYTHON (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo.
    echo   Python 3.10 or newer isn't installed, or wasn't added to your PATH.
    echo   Install it from https://python.org/downloads
    echo   IMPORTANT: tick "Add Python to PATH" during setup, then run this again.
    echo.
    pause
    exit /b 1
)

REM Only install when something is missing, so normal launches stay fast.
%PYTHON% -c "import requests, yaml" >nul 2>&1
if errorlevel 1 (
    echo First run: installing the two dependencies ^(requests, PyYAML^)...
    %PYTHON% -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   Couldn't install dependencies automatically.
        echo   Try running this by hand:  %PYTHON% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
    echo Done.
)

%PYTHON% -m coinfinder.menu
if errorlevel 1 (
    echo.
    echo   Coin Finder exited with an error.
    pause
)

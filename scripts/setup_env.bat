@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM scripts\setup_env.bat
REM Creates the virtual environment and installs all dependencies on Windows.
REM
REM Usage:
REM   scripts\setup_env.bat
REM ─────────────────────────────────────────────────────────────────────────────

echo.
echo   DFire Distance Estimator -- Environment Setup (Windows)
echo   =========================================================

REM ── Python check ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: python not found. Install Python 3.10+ from python.org
    exit /b 1
)
echo   OK  Python found

REM ── Create virtual environment ────────────────────────────────────────────────
if not exist .venv (
    echo   Creating virtual environment in .venv ...
    python -m venv .venv
)
echo   OK  Virtual environment: .venv

REM ── Activate ─────────────────────────────────────────────────────────────────
call .venv\Scripts\activate.bat

REM ── Upgrade pip + setuptools first (fixes the BackendUnavailable error) ───────
echo   Upgrading pip and setuptools ...
python -m pip install --upgrade pip setuptools wheel --quiet
echo   OK  pip and setuptools upgraded

REM ── Install project ───────────────────────────────────────────────────────────
echo   Installing dfire-estimator and dependencies ...
pip install -e ".[dev]"
if errorlevel 1 (
    echo.
    echo   ERROR: Installation failed. See error above.
    pause
    exit /b 1
)
echo   OK  Package installed

REM ── .env ─────────────────────────────────────────────────────────────────────
if not exist .env (
    copy .env.example .env >nul
    echo   OK  .env created -- edit it with your camera settings
) else (
    echo   OK  .env already exists
)

REM ── data dirs ────────────────────────────────────────────────────────────────
if not exist data\dem     mkdir data\dem
if not exist data\images  mkdir data\images
if not exist output       mkdir output
if not exist models       mkdir models

echo.
echo   =========================================================
echo   Setup complete!
echo.
echo   Next steps:
echo     1. Edit .env with your camera parameters
echo     2. Put your DEM file in data\dem\
echo     3. The environment is already active in this window
echo     4. Run:  dfire
echo.
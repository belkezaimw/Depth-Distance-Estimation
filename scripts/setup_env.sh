#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/setup_env.sh
# Creates the virtual environment, installs all dependencies,
# and copies .env.example → .env if not already present.
#
# Usage:
#   bash scripts/setup_env.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PYTHON=${PYTHON:-python3}
VENV=.venv

echo ""
echo "  DFire Distance Estimator — Environment Setup"
echo "  ─────────────────────────────────────────────"

# ── Python version check ─────────────────────────────────────────────────────
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo $PY_VER | cut -d. -f1)
PY_MINOR=$(echo $PY_VER | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "  ✗  Python 3.10+ required (found $PY_VER)"
    exit 1
fi
echo "  ✓  Python $PY_VER"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo "  Creating virtual environment in $VENV …"
    $PYTHON -m venv "$VENV"
fi
echo "  ✓  Virtual environment: $VENV"

# Activate
source "$VENV/bin/activate"

# ── Upgrade pip ───────────────────────────────────────────────────────────────
pip install --upgrade pip --quiet

# ── Install project in editable mode ─────────────────────────────────────────
echo "  Installing dfire-estimator …"
pip install -e ".[dev]" --quiet
echo "  ✓  Package installed"

# ── .env ─────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  ✓  .env created from .env.example — edit it with your camera settings"
else
    echo "  ✓  .env already exists"
fi

# ── data directories ─────────────────────────────────────────────────────────
mkdir -p data/dem data/images output models
touch data/dem/.gitkeep data/images/.gitkeep output/.gitkeep

echo ""
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your camera parameters"
echo "    2. Put your DEM file in data/dem/"
echo "    3. Activate the environment:  source $VENV/bin/activate"
echo "    4. Run:  dfire"
echo "       or:   python -m dfire.cli"
echo ""

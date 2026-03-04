#!/bin/bash
# Quick activation helper — run: source activate.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
echo "✓ Chronicle environment activated"
echo "  Python: $(python3 --version)"
echo "  Run 'cd chronicle && npm run dev' to start both servers"

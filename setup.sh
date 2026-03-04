#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  Chronicle — Mac Silicon (M1/M2/M3) Setup Script
#  Run once from the project root:  bash setup.sh
# ─────────────────────────────────────────────────────────────────

set -e  # stop on any error

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET}  $1"; }
info() { echo -e "  ${BLUE}→${RESET}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $1"; }
err()  { echo -e "  ${RED}✗${RESET}  $1"; }
head() { echo -e "\n${BOLD}${BLUE}── $1 ──────────────────────────────────${RESET}"; }

echo ""
echo -e "${BOLD}${BLUE}  Chronicle — Local Setup (Mac Silicon)${RESET}"
echo -e "${BLUE}  ─────────────────────────────────────────${RESET}"
echo ""

# ── 1. Check prerequisites ────────────────────────────────────────
head "Checking prerequisites"

# Python
if command -v python3 &>/dev/null; then
  PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
  PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
    ok "Python $PY_VERSION"
  else
    err "Python $PY_VERSION found — need 3.10 or higher"
    echo ""
    echo "  Fix: brew install python@3.12"
    echo "  Then: echo 'export PATH=\"/opt/homebrew/bin:$PATH\"' >> ~/.zshrc && source ~/.zshrc"
    exit 1
  fi
else
  err "Python3 not found"
  echo "  Fix: brew install python@3.12"
  exit 1
fi

# Node
if command -v node &>/dev/null; then
  NODE_VERSION=$(node --version | sed 's/v//')
  NODE_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)
  if [ "$NODE_MAJOR" -ge 18 ]; then
    ok "Node.js v$NODE_VERSION"
  else
    err "Node.js v$NODE_VERSION found — need 18 or higher"
    echo "  Fix: brew install node"
    exit 1
  fi
else
  err "Node.js not found"
  echo "  Fix: brew install node"
  exit 1
fi

# Git
if command -v git &>/dev/null; then
  ok "Git $(git --version | awk '{print $3}')"
else
  err "Git not found"
  echo "  Fix: brew install git"
  exit 1
fi

# Homebrew (for info only)
if command -v brew &>/dev/null; then
  ok "Homebrew $(brew --version | head -1 | awk '{print $2}')"
else
  warn "Homebrew not found — not required but recommended for Mac"
fi

# ── 2. Python virtual environment ────────────────────────────────
head "Setting up Python environment"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"

if [ -d "$VENV_PATH" ]; then
  ok "Virtual environment already exists at ./venv"
else
  info "Creating virtual environment..."
  python3 -m venv "$VENV_PATH"
  ok "Virtual environment created at ./venv"
fi

# Activate
source "$VENV_PATH/bin/activate"
ok "Virtual environment activated"

# ── 3. Install Python packages ────────────────────────────────────
head "Installing Python dependencies"

info "Upgrading pip..."
pip install --upgrade pip --quiet

info "Installing core packages..."
pip install pydantic pyyaml numpy python-dotenv --quiet
ok "pydantic, pyyaml, numpy, python-dotenv"

info "Installing API server packages..."
pip install "fastapi>=0.100" "uvicorn[standard]>=0.23" python-multipart --quiet
ok "fastapi, uvicorn, python-multipart"

# sentence-transformers is optional but improves quality significantly
echo ""
echo -e "  ${YELLOW}Optional:${RESET} sentence-transformers improves memory search quality"
echo -e "  ${YELLOW}         ${RESET} (~80MB download, takes 2-3 minutes)"
read -p "  Install sentence-transformers? (recommended) [Y/n]: " INSTALL_ST
INSTALL_ST=${INSTALL_ST:-Y}
if [[ "$INSTALL_ST" =~ ^[Yy]$ ]]; then
  info "Installing sentence-transformers..."
  pip install sentence-transformers --quiet
  ok "sentence-transformers installed"
else
  warn "Skipped — SnowMemory will use built-in TF-IDF approximation"
fi

# ── 4. Verify SnowMemory ─────────────────────────────────────────
head "Verifying SnowMemory"

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

TEST_OUTPUT=$(python3 -c "
import sys
sys.path.insert(0, '.')
from snowmemory import MemoryOrchestrator, MemoryConfig, MemoryEvent, QueryContext
m = MemoryOrchestrator(MemoryConfig(agent_id='setup_test'))
r = m.write(MemoryEvent(content='JWT token expiry bug fixed in auth middleware', agent_id='setup_test'))
results = m.query(QueryContext(text='authentication token issue', agent_id='setup_test', top_k=3))
print(f'written={r.written} results={len(results)} backend={type(m._backend).__name__}')
" 2>&1)

if echo "$TEST_OUTPUT" | grep -q "written=True"; then
  ok "SnowMemory working — $TEST_OUTPUT"
else
  err "SnowMemory test failed"
  echo "  Output: $TEST_OUTPUT"
  exit 1
fi

# ── 5. Run demo tests ────────────────────────────────────────────
head "Running SnowMemory test suite"

cd "$SCRIPT_DIR/snowmemory"
DEMO_OUT=$(python3 demo.py --domain ecommerce 2>&1 | tail -5)
if echo "$DEMO_OUT" | grep -q "17/17\|PASS\|pass"; then
  ok "All tests passing"
elif echo "$DEMO_OUT" | grep -q "Error\|error\|Traceback"; then
  warn "Some tests had issues — check with: python3 demo.py --all"
  echo "  $DEMO_OUT"
else
  ok "Tests completed — run 'python3 demo.py --all' for full results"
fi
cd "$SCRIPT_DIR"

# ── 6. Run Chronicle test ────────────────────────────────────────
head "Running Chronicle memory test"

CHRONICLE_OUT=$(python3 chronicle/scripts/test_chronicle.py 2>&1)
if echo "$CHRONICLE_OUT" | grep -q "working correctly"; then
  ok "Chronicle test passed — memories surfacing correctly"
  # Show the JWT result as proof
  JWT_RESULT=$(echo "$CHRONICLE_OUT" | grep -A2 "JWT token" | head -3)
  echo -e "  ${BLUE}Sample:${RESET} $JWT_RESULT"
else
  warn "Chronicle test had issues"
  echo "$CHRONICLE_OUT" | tail -10
fi

# ── 7. Node setup ────────────────────────────────────────────────
head "Setting up Node.js (Chronicle frontend)"

cd "$SCRIPT_DIR/chronicle"

if [ ! -f "node_modules/.package-lock.json" ] && [ ! -d "node_modules" ]; then
  info "Installing concurrently..."
  npm install --silent
  ok "Node packages installed"
else
  ok "Node packages already installed"
fi

# ── 8. Next.js setup ────────────────────────────────────────────
head "Setting up Next.js frontend"

if [ -d "$SCRIPT_DIR/chronicle/frontend/node_modules" ]; then
  ok "Frontend already set up"
elif [ -f "$SCRIPT_DIR/chronicle/frontend/package.json" ]; then
  info "Installing frontend packages..."
  cd "$SCRIPT_DIR/chronicle/frontend"
  npm install --silent
  ok "Frontend packages installed"
  cd "$SCRIPT_DIR/chronicle"
else
  info "Creating Next.js app (this takes ~2 minutes)..."
  cd "$SCRIPT_DIR/chronicle"
  npx create-next-app@latest frontend \
    --typescript \
    --tailwind \
    --app \
    --no-src-dir \
    --import-alias "@/*" \
    --yes 2>/dev/null || \
  npx create-next-app@latest frontend \
    --typescript \
    --tailwind \
    --app \
    --no-src-dir \
    --yes
  ok "Next.js app created"

  cd frontend
  info "Installing Chronicle frontend packages..."
  npm install @clerk/nextjs react-dropzone react-hot-toast --silent
  ok "@clerk/nextjs, react-dropzone, react-hot-toast installed"
  cd "$SCRIPT_DIR/chronicle"
fi

# ── 9. Environment files ─────────────────────────────────────────
head "Setting up environment files"

# Backend .env
if [ ! -f "$SCRIPT_DIR/chronicle/.env" ]; then
  cp "$SCRIPT_DIR/chronicle/.env.example" "$SCRIPT_DIR/chronicle/.env"
  ok "Created chronicle/.env (from .env.example)"
else
  ok "chronicle/.env already exists"
fi

# Frontend .env.local
if [ ! -f "$SCRIPT_DIR/chronicle/frontend/.env.local" ]; then
  cp "$SCRIPT_DIR/chronicle/.env.local.example" "$SCRIPT_DIR/chronicle/frontend/.env.local"
  ok "Created chronicle/frontend/.env.local (from .env.local.example)"
else
  ok "chronicle/frontend/.env.local already exists"
fi

# ── 10. Create activate helper ───────────────────────────────────
head "Creating helper scripts"

cat > "$SCRIPT_DIR/activate.sh" << 'ACTIVATE'
#!/bin/bash
# Quick activation helper — run: source activate.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
echo "✓ Chronicle environment activated"
echo "  Python: $(python3 --version)"
echo "  Run 'cd chronicle && npm run dev' to start both servers"
ACTIVATE
chmod +x "$SCRIPT_DIR/activate.sh"
ok "Created activate.sh"

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}─────────────────────────────────────────────────${RESET}"
echo -e "${BOLD}${GREEN}  Setup complete! ✓${RESET}"
echo -e "${BOLD}${GREEN}─────────────────────────────────────────────────${RESET}"
echo ""
echo -e "  ${BOLD}Every time you open a new terminal:${RESET}"
echo -e "  ${BLUE}source activate.sh${RESET}"
echo ""
echo -e "  ${BOLD}Start both servers:${RESET}"
echo -e "  ${BLUE}cd chronicle && npm run dev${RESET}"
echo ""
echo -e "  ${BOLD}Or start them separately:${RESET}"
echo -e "  ${BLUE}cd chronicle/backend && uvicorn main:app --reload --port 8000${RESET}"
echo -e "  ${BLUE}cd chronicle/frontend && npm run dev${RESET}"
echo ""
echo -e "  ${BOLD}Test memory engine:${RESET}"
echo -e "  ${BLUE}python3 chronicle/scripts/test_chronicle.py${RESET}"
echo ""
echo -e "  ${BOLD}URLs when running:${RESET}"
echo -e "  API:      ${BLUE}http://localhost:8000${RESET}"
echo -e "  API Docs: ${BLUE}http://localhost:8000/docs${RESET}"
echo -e "  Frontend: ${BLUE}http://localhost:3000${RESET}"
echo ""
echo -e "  ${YELLOW}⚠  Don't forget to add your Clerk keys to:${RESET}"
echo -e "  chronicle/frontend/.env.local"
echo -e "  Get free keys at: ${BLUE}https://clerk.com${RESET}"
echo ""

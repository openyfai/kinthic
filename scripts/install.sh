#!/usr/bin/env bash

# ─────────────────────────────────────────────────────────────────────────────
# OpenYF Kronos — Zero-Dependency Installer
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ── 1. Guard check for native Windows shells ──────────────────────────────────
# WSL2 is required for Windows users to prevent UAC/SmartScreen execution blocks
if [ -n "${WINDIR:-}" ] || [ -n "${COMSPEC:-}" ] || [ -d "/cygdrive" ] || [ "${OSTYPE:-}" = "msys" ]; then
    echo -e "${RED}❌ Error: This installer must be executed inside a WSL2 Linux terminal.${NC}"
    echo -e "${YELLOW}Windows detected (Command Prompt / PowerShell / Git Bash).${NC}"
    echo -e "Open Ubuntu (or your WSL distro) from the Start menu, then run:"
    echo -e "  ${GREEN}curl -fsSL https://kronos.openyf.dev/install.sh | bash${NC}"
    echo -e "Native Windows is not supported — WSL2 is required."
    exit 1
fi

# Friendly WSL banner when running inside Linux-on-Windows
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo -e "${GREEN}✓ WSL2 environment detected${NC}"
fi

echo -e "${BLUE}"
echo "  ██  ██  ██████    ██████   ███   ██   ██████    ███████ "
echo "  ██ ██   ██   ██  ██    ██  ████  ██  ██    ██  ██       "
echo "  ████    ██████   ██    ██  ██ ██ ██  ██    ██   ██████  "
echo "  ██ ██   ██  ██   ██    ██  ██  ████  ██    ██        ██ "
echo "  ██  ██  ██   ██   ██████   ██   ███   ██████   ███████  "
echo -e "${NC}"
echo -e "         ${YELLOW}[ OpenYF Kronos Local Operator Installer ]${NC}"
echo -e "──────────────────────────────────────────────────────────"

# ── 2. Environment and Architecture Detection ─────────────────────────────────
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

echo -e "Checking host environment..."
echo -e "  - OS:   ${GREEN}$OS${NC}"
echo -e "  - Arch: ${GREEN}$ARCH${NC}"

# Define UI binary suffix based on detected OS/Arch
UI_SUFFIX=""
if [ "$OS" = "linux" ]; then
    UI_SUFFIX="linux-x64"
elif [ "$OS" = "darwin" ]; then
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
        UI_SUFFIX="darwin-arm64"
    else
        UI_SUFFIX="darwin-x64"
    fi
else
    echo -e "${RED}❌ Error: Operating system '$OS' is not supported.${NC}"
    exit 1
fi

# Define path constants
KRONOS_DIR="$HOME/.kronos"
KRONOS_BIN="$KRONOS_DIR/bin"
KRONOS_VENV="$KRONOS_DIR/runtime/venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "Initializing installer paths..."
mkdir -p "$KRONOS_BIN"
mkdir -p "$KRONOS_DIR/workspace/exports"
mkdir -p "$KRONOS_DIR/workspace/backups"
mkdir -p "$KRONOS_DIR/runtime/engine_cache"
mkdir -p "$KRONOS_DIR/storage/vector_db"
mkdir -p "$KRONOS_DIR/config/plugins/model-providers"
mkdir -p "$KRONOS_DIR/skills"
mkdir -p "$KRONOS_DIR/plugins/tools"
mkdir -p "$KRONOS_DIR/plugins/skills"
mkdir -p "$KRONOS_DIR/registry"
mkdir -p "$KRONOS_DIR/logs/traces"

# ── 3. Check for core package requirements ──────────────────────────────────
PACKAGES_TO_INSTALL=()
if ! command -v python3 &>/dev/null; then
    PACKAGES_TO_INSTALL+=("python3" "python3-venv" "python3-pip")
fi
if ! command -v git &>/dev/null; then
    PACKAGES_TO_INSTALL+=("git")
fi

if [ ${#PACKAGES_TO_INSTALL[@]} -ne 0 ]; then
    echo -e "${YELLOW}⚠️ Notice: Missing required system dependencies: ${PACKAGES_TO_INSTALL[*]}${NC}"
    if command -v apt-get &>/dev/null; then
        read -rp "Would you like to install them via apt-get now? (Requires sudo) [Y/n] " prompt
        if [[ $prompt =~ ^[Yy]$ || -z $prompt ]]; then
            echo -e "${BLUE}Updating package catalogs...${NC}"
            sudo apt-get update
            echo -e "${BLUE}Installing missing dependencies...${NC}"
            sudo apt-get install -y "${PACKAGES_TO_INSTALL[@]}"
        else
            echo -e "${RED}❌ Installation cancelled: Missing required dependencies.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ Please install ${PACKAGES_TO_INSTALL[*]} manually and rerun this script.${NC}"
        exit 1
    fi
fi

# ── 4. Retrieve Standalone Assets ─────────────────────────────────────────────
echo -e "${BLUE}Downloading uv package manager...${NC}"
export INSTALL_DIR="$KRONOS_BIN"
export CARGO_DIST_FORCE_INSTALL_DIR="$KRONOS_BIN"
curl -LsSf https://astral.sh/uv/install.sh | sh

echo -e "${BLUE}Fetching latest TUI binary from GitHub Releases...${NC}"
REPO="openyfai/kronos"
LATEST_TAG=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/' || true)

if [ -n "$LATEST_TAG" ]; then
    UI_URL="https://github.com/$REPO/releases/download/$LATEST_TAG/kronos-ui-$UI_SUFFIX"
    echo -e "Downloading precompiled UI version ${GREEN}$LATEST_TAG${NC}..."
    if ! curl -L -sSf -o "$KRONOS_BIN/kronos-ui" "$UI_URL"; then
        echo -e "${YELLOW}⚠️ Release UI download failed (404?). Build locally:${NC}"
        echo -e "  cd kronos-ink-ui && npm install && npm run build"
        cat << 'EOF' > "$KRONOS_BIN/kronos-ui"
#!/usr/bin/env bash
echo "❌ Precompiled UI missing. From a dev checkout run: cd kronos-ink-ui && npm run build"
exit 1
EOF
    fi
else
    echo -e "${YELLOW}⚠️ No release tag found.${NC}"
    echo -e "  Dev fallback: cd kronos-ink-ui && npm run build"
    cat << 'EOF' > "$KRONOS_BIN/kronos-ui"
#!/usr/bin/env bash
if command -v node &>/dev/null && [ -f "$HOME/kronos/kronos-ink-ui/dist/index.js" ]; then
    exec node "$HOME/kronos/kronos-ink-ui/dist/index.js" "$@"
elif command -v npx &>/dev/null; then
    exec npx tsx "$(dirname "$0")/../../kronos-ink-ui/src/index.tsx" "$@"
else
    echo "❌ Node.js or compiled standalone UI not found."
    echo "   From a dev checkout: cd kronos-ink-ui && npm install && npm run build"
    exit 1
fi
EOF
fi

chmod +x "$KRONOS_BIN/kronos-ui"

# ── 5. Setup Python Sandboxed Virtual Environment ────────────────────────────
echo -e "${BLUE}Configuring isolated Python virtual environment...${NC}"
"$KRONOS_BIN/uv" venv "$KRONOS_VENV"

echo -e "${BLUE}Installing Silex reasoning engine backend (with MCP support)...${NC}"
if [ -f "$REPO_ROOT/pyproject.toml" ]; then
    cd "$REPO_ROOT"
    "$KRONOS_BIN/uv" pip install -e ".[mcp]" || "$KRONOS_BIN/uv" pip install -e .
else
    "$KRONOS_BIN/uv" pip install "git+https://github.com/$REPO.git" || true
    "$KRONOS_BIN/uv" pip install "openyfai-kronos[mcp]" 2>/dev/null || true
fi

# Verify kronos entrypoint
if [ ! -x "$KRONOS_VENV/bin/kronos" ]; then
    echo -e "${RED}❌ Error: kronos CLI not found after install. Check pip output above.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ kronos CLI installed${NC}"

# ── 6. Bootstrap local config & seed bundled skills ─────────────────────────────
echo -e "${BLUE}Bootstrapping ~/.kronos configuration...${NC}"

if [ ! -f "$KRONOS_DIR/.env" ]; then
    if [ -f "$REPO_ROOT/.env.example" ]; then
        cp "$REPO_ROOT/.env.example" "$KRONOS_DIR/.env"
    else
        cat > "$KRONOS_DIR/.env" << 'ENVEOF'
# Kronos runtime configuration
# Add your provider API keys here, then run: kronos onboard

GEMINI_API_KEY=
# TELEGRAM_BOT_TOKEN=
# ALLOWED_TELEGRAM_USERS=
# DISCORD_BOT_TOKEN=
# ALLOWED_DISCORD_USERS=
ENVEOF
    fi
    echo -e "  Created ${GREEN}$KRONOS_DIR/.env${NC} — run ${GREEN}kronos onboard${NC} next"
fi

# Bundled catalog fallback (offline KronosHub)
if [ -f "$REPO_ROOT/registry/catalog.yaml" ]; then
    cp "$REPO_ROOT/registry/catalog.yaml" "$KRONOS_DIR/registry/catalog.yaml"
    echo -e "  Copied bundled ${GREEN}registry/catalog.yaml${NC}"
fi

# Seed bundled skills from checkout
SKILLS_SRC="$REPO_ROOT/skills"
if [ -d "$SKILLS_SRC" ]; then
    for skill_file in "$SKILLS_SRC"/*.md; do
        [ -f "$skill_file" ] || continue
        base="$(basename "$skill_file")"
        if [ "$base" = "README.md" ]; then
            continue
        fi
        if [ ! -f "$KRONOS_DIR/skills/$base" ]; then
            cp "$skill_file" "$KRONOS_DIR/skills/$base"
        fi
        stem="${base%.md}"
        sidecar="$SKILLS_SRC/${stem}.yaml"
        if [ -f "$sidecar" ] && [ ! -f "$KRONOS_DIR/skills/${stem}.yaml" ]; then
            cp "$sidecar" "$KRONOS_DIR/skills/${stem}.yaml"
        fi
    done
    echo -e "  Seeded bundled skills into ${GREEN}$KRONOS_DIR/skills/${NC}"
fi

# Initialize KronosHub catalog (remote seed with bundled fallback)
"$KRONOS_VENV/bin/python" - << PYEOF || true
from silex.utils.config import ensure_kronos_home
from silex.plugins.registry import get_registry

ensure_kronos_home()
reg = get_registry()
if not reg.catalog_path.exists():
    reg.seed_builtin_catalog()
else:
    reg.load_catalog()
print("  KronosHub catalog ready.")
PYEOF

# Non-fatal smoke test
echo -e "${BLUE}Running install smoke check (kronos doctor)...${NC}"
"$KRONOS_VENV/bin/kronos" doctor || echo -e "${YELLOW}⚠️ doctor reported issues — run kronos onboard to fix${NC}"

# ── 7. Create Binary Command Wrapper & Link PATH ──────────────────────────────
echo -e "${BLUE}Registering CLI path endpoints...${NC}"
cat << 'EOF' > "$KRONOS_BIN/kronos"
#!/usr/bin/env bash
set -e
exec "$HOME/.kronos/runtime/venv/bin/kronos" "$@"
EOF
chmod +x "$KRONOS_BIN/kronos"

add_to_path() {
    local profile_file="$1"
    if [ -f "$profile_file" ]; then
        if ! grep -q '\.kronos/bin' "$profile_file"; then
            echo -e "\n# OpenYF Kronos path registration\nexport PATH=\"\$HOME/.kronos/bin:\$PATH\"" >> "$profile_file"
            echo -e "Registered path inside ${GREEN}$profile_file${NC}"
        fi
    fi
}

add_to_path "$HOME/.zshrc"
add_to_path "$HOME/.bashrc"
add_to_path "$HOME/.profile"

# ── 8. Done ───────────────────────────────────────────────────────────────────
echo -e "\n──────────────────────────────────────────────────────────"
echo -e "${GREEN}🎉 OpenYF Kronos Installed Successfully!${NC}"
echo -e ""
echo -e "Install method: ${YELLOW}curl -fsSL https://kronos.openyf.dev/install.sh | bash${NC}"
echo -e ""
echo -e "Reload your shell, then run the onboarding wizard:"
echo -e "  ${YELLOW}source ~/.bashrc${NC}  (or source ~/.zshrc)"
echo -e "  ${GREEN}kronos onboard${NC}"
echo -e ""
echo -e "Then start the agent:"
echo -e "  ${GREEN}kronos${NC}                  — terminal session"
echo -e "  ${GREEN}kronos telegram run${NC}   — messaging bot (after onboard)"
echo -e "  ${GREEN}kronos skills list${NC}    — installed skills"
echo -e "──────────────────────────────────────────────────────────\n"

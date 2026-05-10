#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# mac-setup.sh  —  Install dev dependencies on macOS (no sudo)
#
# Installs everything into your home directory — no admin rights needed.
#
# What gets installed:
#   - Homebrew (into ~/homebrew)
#   - AWS CLI v2
#   - Python 3 + pip
#   - Terraform
#   - jq  (JSON pretty-printer, handy for AWS CLI output)
#   - git (if not already present)
#
# Usage:
#   chmod +x mac-setup.sh
#   ./mac-setup.sh
#
# After running, open a new terminal (or run: source ~/.zshrc)
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[info]${NC}  $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
skip()    { echo -e "${YELLOW}[skip]${NC}  $*"; }
fail()    { echo -e "${RED}[fail]${NC}  $*"; exit 1; }

# ── Detect shell profile ──────────────────────────────────────
# Writes PATH exports here so they survive new terminals
detect_profile() {
  if [[ "$SHELL" == *"zsh"* ]]; then
    echo "${HOME}/.zshrc"
  elif [[ "$SHELL" == *"bash"* ]]; then
    echo "${HOME}/.bash_profile"
  else
    echo "${HOME}/.profile"
  fi
}
PROFILE=$(detect_profile)

add_to_profile() {
  local line="$1"
  if ! grep -qF "$line" "$PROFILE" 2>/dev/null; then
    echo "$line" >> "$PROFILE"
    info "Added to $PROFILE: $line"
  fi
}

echo ""
echo "=== macOS Dev Setup (no sudo) ==="
echo "Shell profile: $PROFILE"
echo ""

# ─────────────────────────────────────────────────────────────
# 1. Homebrew (installed to ~/homebrew — no sudo required)
# ─────────────────────────────────────────────────────────────
BREW_DIR="${HOME}/homebrew"
BREW="${BREW_DIR}/bin/brew"

# Locate brew — check common locations in priority order
locate_brew() {
  for candidate in \
      "${HOME}/homebrew/bin/brew" \
      "/opt/homebrew/bin/brew" \
      "/usr/local/bin/brew"; do
    if [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

install_homebrew() {
  info "Installing Homebrew into ${BREW_DIR} ..."
  mkdir -p "${BREW_DIR}"
  curl -fsSL https://github.com/Homebrew/brew/tarball/master \
    | tar xz --strip-components 1 -C "${BREW_DIR}"
  BREW="${BREW_DIR}/bin/brew"
  success "Homebrew installed at ${BREW_DIR}"
}

if BREW=$(locate_brew); then
  BREW_DIR=$(dirname "$(dirname "$BREW")")   # e.g. /opt/homebrew
  skip "Homebrew already installed at ${BREW_DIR}"
else
  install_homebrew
fi

# Always ensure the correct brew bin dir is in PATH and in the shell profile.
# Using 'brew shellenv' is the canonical way — it sets PATH, MANPATH, INFOPATH.
BREW_SHELLENV="eval \"\$(${BREW} shellenv)\""
add_to_profile "$BREW_SHELLENV"
eval "$("${BREW}" shellenv)"              # apply to current script session too

# Let Homebrew update its formulae (suppress noise)
"${BREW}" update --quiet 2>/dev/null || true

echo ""

# ─────────────────────────────────────────────────────────────
# 2. AWS CLI v2
# ─────────────────────────────────────────────────────────────
info "Checking AWS CLI..."
if command -v aws &>/dev/null; then
  AWS_VER=$(aws --version 2>&1 | awk '{print $1}')
  skip "AWS CLI already installed: $AWS_VER"
else
  info "Installing AWS CLI v2 via Homebrew..."
  "${BREW}" install awscli
  success "AWS CLI installed: $(aws --version 2>&1 | awk '{print $1}')"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 3. Python 3
# ─────────────────────────────────────────────────────────────
info "Checking Python 3..."
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version)
  skip "Python already installed: $PY_VER"
else
  info "Installing Python 3 via Homebrew..."
  "${BREW}" install python
  success "Python installed: $(python3 --version)"
fi

# pip packages (installed to user dir, no sudo needed)
info "Checking pip packages..."

install_pip_pkg() {
  local pkg="$1"
  if python3 -c "import ${pkg//-/_}" &>/dev/null 2>&1; then
    skip "pip: $pkg already installed"
  else
    info "pip install $pkg ..."
    python3 -m pip install --quiet --user "$pkg"
    success "pip: $pkg installed"
  fi
}

install_pip_pkg boto3

echo ""

# ─────────────────────────────────────────────────────────────
# 4. Terraform
# ─────────────────────────────────────────────────────────────
info "Checking Terraform..."
if command -v terraform &>/dev/null; then
  skip "Terraform already installed: $(terraform version | head -1)"
else
  info "Installing Terraform via Homebrew..."
  "${BREW}" tap hashicorp/tap 2>/dev/null || true
  "${BREW}" install hashicorp/tap/terraform
  success "Terraform installed: $(terraform version | head -1)"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 5. jq  (makes AWS CLI JSON output readable)
# ─────────────────────────────────────────────────────────────
info "Checking jq..."
if command -v jq &>/dev/null; then
  skip "jq already installed: $(jq --version)"
else
  info "Installing jq via Homebrew..."
  "${BREW}" install jq
  success "jq installed: $(jq --version)"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 6. git
# ─────────────────────────────────────────────────────────────
info "Checking git..."
if command -v git &>/dev/null; then
  skip "git already installed: $(git --version)"
else
  info "Installing git via Homebrew..."
  "${BREW}" install git
  success "git installed: $(git --version)"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 7. AWS CLI configuration
# ─────────────────────────────────────────────────────────────
info "Checking AWS credentials..."
if aws sts get-caller-identity &>/dev/null 2>&1; then
  IDENTITY=$(aws sts get-caller-identity --query "Arn" --output text 2>/dev/null)
  skip "AWS already configured: $IDENTITY"
else
  warn "AWS CLI is not configured yet."
  echo ""
  echo "  Run this to configure it:"
  echo "    aws configure"
  echo ""
  echo "  You will need:"
  echo "    AWS Access Key ID      — from IAM → Users → Security credentials"
  echo "    AWS Secret Access Key  — same place"
  echo "    Default region         — us-east-1"
  echo "    Default output format  — json"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 8. SSH key permissions
# ─────────────────────────────────────────────────────────────
KEY_PATH="${HOME}/srikar-amex.pem"
info "Checking SSH key at ${KEY_PATH}..."
if [[ -f "$KEY_PATH" ]]; then
  chmod 400 "$KEY_PATH"
  success "SSH key found and permissions set to 400."
else
  warn "SSH key not found at ${KEY_PATH}"
  echo "  Copy it from a secure location:"
  echo "    mv ~/Downloads/srikar-amex.pem ~/"
  echo "    chmod 400 ~/srikar-amex.pem"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Setup complete. Installed locations:"
echo "   Homebrew  : ${BREW_DIR}"
echo "   AWS CLI   : $(command -v aws 2>/dev/null || echo 'open new terminal')"
echo "   Python 3  : $(command -v python3 2>/dev/null || echo 'open new terminal')"
echo "   Terraform : $(command -v terraform 2>/dev/null || echo 'open new terminal')"
echo "   jq        : $(command -v jq 2>/dev/null || echo 'open new terminal')"
echo "   Profile   : ${PROFILE}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "IMPORTANT: Open a new terminal (or run the line below)"
echo "  so PATH changes take effect:"
echo ""
echo "  source ${PROFILE}"
echo ""
echo "Then verify everything works:"
echo "  aws --version"
echo "  python3 --version"
echo "  terraform version"
echo "  jq --version"
echo ""
echo "Next: run ./start-ec2.sh linux to connect to your dev instance."

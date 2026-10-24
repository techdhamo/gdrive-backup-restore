#!/usr/bin/env bash
# ==============================================================================
# 🚀 1-Click Disaster Recovery & Restore Script for macOS
# Restores /Users/dhamo/m from Google Drive via gdrive-backup-restore v2.1
# ==============================================================================
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

echo -e "\n${CYAN}════════════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  🚀  Post-Service Mac Workspace Restoration Tool (v2.1)${RESET}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════════${RESET}\n"

# 1. Check & Install Homebrew
if ! command -v brew &>/dev/null; then
    echo -e "${YELLOW}⚡ Homebrew not found. Installing Homebrew …${RESET}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [ -x "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

# 2. Check & Install rclone
if ! command -v rclone &>/dev/null; then
    echo -e "${YELLOW}⚡ Installing rclone via Homebrew …${RESET}"
    brew install rclone
fi

# 3. Check Google Drive Remote Authentication
echo -e "${CYAN}🔍 Verifying Google Drive access (remote: 'gdrive') …${RESET}"
if ! rclone lsd gdrive: &>/dev/null; then
    echo -e "${YELLOW}🔑 Google Drive remote 'gdrive' not configured or expired.${RESET}"
    echo -e "   Opening browser for Google Drive authentication …\n"
    rclone config create gdrive drive scope=drive use_trash=false
fi

# 4. Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 5. Run Strategy-Based Python Restoration
echo -e "\n${GREEN}⚡ Launching automated strategy restore …${RESET}\n"
python3 "${SCRIPT_DIR}/gdrive_restore.py"

# 6. Final verification
echo -e "\n${CYAN}🔍 Performing post-restore verification …${RESET}"
if [ -L "/Users/dhamo/m" ]; then
    echo -e "${GREEN}✓ Active symlink confirmed: /Users/dhamo/m -> $(readlink /Users/dhamo/m)${RESET}"
else
    echo -e "${RED}✗ Symlink /Users/dhamo/m missing! Recreating …${RESET}"
    mkdir -p /Users/dhamo
    ln -sfn /Users/dhamo/claude/CMS/YBL/Mobility /Users/dhamo/m
fi

echo -e "\n${GREEN}════════════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  ✅  Restoration Complete & Verified!${RESET}"
echo -e "  📂  Workspace is live at: /Users/dhamo/m"
echo -e "${GREEN}════════════════════════════════════════════════════════════════════${RESET}\n"

#!/bin/bash
# ═══════════════════════════════════════════════════════
#  Google Drive Parallel Uploader — Setup & Run
# ═══════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     Google Drive Parallel Uploader — Setup       ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Check Python 3.9+
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "✗  Python 3 not found. Install from https://python.org"
    exit 1
fi
PY_VER=$($PYTHON --version 2>&1)
echo "✔  Found: $PY_VER"

# Create virtual environment if missing
if [ ! -d "venv" ]; then
    echo "● Creating virtual environment …"
    $PYTHON -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "● Installing dependencies …"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✔  Dependencies installed"

# Check for credentials
if [ ! -f "credentials.json" ]; then
    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  ⚠  credentials.json NOT FOUND"
    echo ""
    echo "  Follow these steps:"
    echo "  1. Go to https://console.cloud.google.com/"
    echo "  2. Create a new project (or select existing)"
    echo "  3. Enable 'Google Drive API':"
    echo "     APIs & Services → Library → Search 'Drive' → Enable"
    echo "  4. Create OAuth 2.0 credentials:"
    echo "     APIs & Services → Credentials → + Create Credentials"
    echo "     → OAuth client ID → Desktop App → Download JSON"
    echo "  5. Rename the downloaded file to 'credentials.json'"
    echo "     and place it in:"
    echo "     $SCRIPT_DIR/"
    echo ""
    echo "  Then re-run this script."
    echo "══════════════════════════════════════════════════"
    exit 1
fi

echo ""
echo "✔  credentials.json found — starting upload …"
echo "   (A browser window will open for Google sign-in on first run)"
echo ""

# Run the uploader
# 12 workers tuned for 300 Mbps line (~30 MB/s theoretical throughput)
python3 gdrive_uploader.py \
    --source "/Users/dhamo/m" \
    --drive-folder "m-backup-$(date +%Y%m%d)" \
    --workers 12

echo "Done!"

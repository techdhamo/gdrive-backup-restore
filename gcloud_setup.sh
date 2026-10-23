#!/bin/bash
# Auto-setup Google Drive API via gcloud
set -e

GCLOUD=/opt/homebrew/bin/gcloud
PROJECT_ID="drive-uploader-$(date +%s | tail -c 6)"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║       Google Drive API — Auto Setup              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Check auth
echo "● Checking gcloud login status …"
if ! $GCLOUD auth application-default print-access-token --scopes=https://www.googleapis.com/auth/drive > /dev/null 2>&1; then
    echo ""
    echo "⚠  Not logged in. Opening browser for Google sign-in …"
    $GCLOUD auth application-default login \
        --scopes=https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/cloud-platform
fi
echo "✔  Authenticated"

# Create project
echo "● Creating Google Cloud project: $PROJECT_ID …"
$GCLOUD projects create "$PROJECT_ID" --name="Drive Uploader" 2>/dev/null || true
$GCLOUD config set project "$PROJECT_ID" --quiet
echo "✔  Project: $PROJECT_ID"

# Enable billing warning (Drive API is free but project needs billing)
echo ""
echo "  ℹ  Google Drive API is FREE — no charges will occur"
echo ""

# Enable Drive API
echo "● Enabling Google Drive API …"
$GCLOUD services enable drive.googleapis.com --project="$PROJECT_ID" 2>&1
echo "✔  Google Drive API enabled"

# Generate OAuth client credentials
echo "● Creating OAuth 2.0 credentials …"
$GCLOUD alpha iap oauth-clients create \
    projects/$PROJECT_ID/brands/$PROJECT_ID \
    --display_name="drive-uploader" 2>/dev/null || true

# Use ADC (Application Default Credentials) — no credentials.json needed!
echo ""
echo "✔  Application Default Credentials are set up."
echo "   Token stored at: ~/.config/gcloud/application_default_credentials.json"
echo ""
echo "══════════════════════════════════════════════════"
echo "  ✅  Setup complete! Starting upload now …"
echo "══════════════════════════════════════════════════"
echo ""

# Run the uploader using ADC
cd "$(dirname "$0")"
source venv/bin/activate
python3 gdrive_uploader.py \
    --source "/Users/dhamo/m" \
    --drive-folder "m-backup-$(date +%Y%m%d)" \
    --workers 12

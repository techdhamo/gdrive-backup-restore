# 📖 Post-Service Mac Restoration Playbook

> **Complete Disaster Recovery & Restoration Guide**  
> Use this playbook after your Mac is repaired, replaced, formatted, or wiped.

---

## ⚡ Quick Start (TL;DR)

If you just received your freshly serviced Mac, open Terminal and run these 3 commands:

```bash
# 1. Install rclone (via Homebrew)
brew install rclone

# 2. Authenticate Google Drive (opens your browser)
rclone config create gdrive drive scope=drive use_trash=false

# 3. Clone this repo & run restore
git clone https://github.com/techdhamo/gdrive-backup-restore.git ~/gdrive_restore
cd ~/gdrive_restore
python3 gdrive_restore.py
```

That's it! `gdrive_restore.py` handles manifest discovery, batch downloads, SHA-256 checksum verification, extraction, and rebuilding the `~/m` symlink automatically.

---

## 📋 Table of Contents
1. [Prerequisites & Initial Setup](#1-prerequisites--initial-setup)
2. [Google Drive Authentication](#2-google-drive-authentication)
3. [Running the Restoration](#3-running-the-restoration)
4. [How the Automated Strategy Works](#4-how-the-automated-strategy-works)
5. [Restoration Options & Advanced Flags](#5-restoration-options--advanced-flags)
6. [Post-Restore Verification Checklist](#6-post-restore-verification-checklist)
7. [Troubleshooting & FAQs](#7-troubleshooting--faqs)

---

## 1. Prerequisites & Initial Setup

If macOS was clean-installed or reformatted:

### Step 1: Install Xcode Command Line Tools
```bash
xcode-select --install
```

### Step 2: Install Homebrew (if not already present)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Ensure Homebrew is in your shell PATH:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Step 3: Install rclone
```bash
brew install rclone
```

Verify installation:
```bash
rclone version
```

---

## 2. Google Drive Authentication

### Option A: Interactive Browser Auth (Default & Recommended)
Run:
```bash
rclone config create gdrive drive scope=drive use_trash=false
```
1. Your web browser will automatically open to Google's sign-in page.
2. Sign in with the Google account where your backup was uploaded.
3. Click **"Allow"** to grant Drive access.
4. Terminal will report: `Success! Configured remote "gdrive"`.

### Option B: Verify Connection
Verify that your backup is accessible on Drive:
```bash
rclone lsd gdrive:
```
You should see:
```text
          -1 2026-10-24 07:35:00        -1 m-backup-batches
```

---

## 3. Running the Restoration

Clone the repository and launch the restore script:

```bash
git clone https://github.com/techdhamo/gdrive-backup-restore.git ~/gdrive-backup-restore
cd ~/gdrive-backup-restore
python3 gdrive_restore.py
```

### What You Will See in the Terminal:
```text
════════════════════════════════════════════════════════════════════
  🔄  Google Drive Strategy-Based Restore Tool v2.0
════════════════════════════════════════════════════════════════════
  Backup Created : 2026-10-24T02:04:41+00:00
  Drive Remote   : gdrive:m-backup-batches
  Destination    : /Users/dhamo/claude/CMS/YBL/Mobility
  Total Batches  : 7
  Total Size     : ~10.2 GB

────────────────────────────────────────────────────────────────────
  📦 Restoring Batch 1: batch_01_bobcr.tar.gz
     Contents : BOBCR
     Size     : 1.29 GB
────────────────────────────────────────────────────────────────────
  ⬇  Downloading batch_01_bobcr.tar.gz from Drive …
  ✓ Downloaded in 42.1s
  🔒 Verifying SHA-256 checksum …
  ✓ Checksum verified (0a084bb78deb52...)
  📂 Extracting into /Users/dhamo/claude/CMS/YBL/Mobility …
  ✓ Extracted in 18.4s
  🧹 Cleaning up downloaded archive to free disk space …
  ✓ Local archive removed (1.29 GB freed)
...
✓ Recreated symlink: /Users/dhamo/m → /Users/dhamo/claude/CMS/YBL/Mobility
════════════════════════════════════════════════════════════════════
  ✅  Restore completed successfully!
```

---

## 4. How the Automated Strategy Works

Behind the scenes, `gdrive_restore.py` executes a multi-layer verification protocol:

```
                  [ Google Drive: m-backup-batches ]
                                  │
                                  ▼
                     Downloads restore_strategy.json
                                  │
                                  ▼
           ┌──────────────────────┴──────────────────────┐
           ▼                                             ▼
  Reads Batch Manifest                           Parses Destination & Symlinks
  - 7 Batches                                    - Target: /Users/dhamo/claude/CMS/YBL/Mobility
  - SHA-256 Checksums                            - Link  : /Users/dhamo/m
           │
           ▼ (Iterates Each Batch)
  1. Downloads batch_XX.tar.gz into temporary staging
  2. Calculates local SHA-256 hash and compares with manifest
       ├─► MATCH   ──► Extract archive into target destination
       └─► MISMATCH ──► Abort & warn; prevents data corruption!
  3. Deletes local batch_XX.tar.gz immediately after extraction
  4. Once all batches finish: Recreates symlink /Users/dhamo/m
```

---

## 5. Restoration Options & Advanced Flags

| Command | Use Case |
|---|---|
| `python3 gdrive_restore.py --dry-run` | Preview all actions without downloading or modifying disk |
| `python3 gdrive_restore.py --dest /path/to/custom` | Restore to a custom folder instead of default |
| `python3 gdrive_restore.py --batch 1` | Restore only a single specific batch (e.g. only `BOBCR`) |
| `python3 gdrive_restore.py --list` | List all backup folders found on Google Drive |
| `python3 gdrive_restore.py --remote myremote` | Use a custom rclone remote name |

---

## 6. Post-Restore Verification Checklist

After the restoration script finishes, run these quick sanity checks:

### 1. Verify the `~/m` Symlink
```bash
ls -la /Users/dhamo/m
```
*Expected Output:*
```text
lrwxr-xr-x  1 dhamo  staff  36 Oct 24 07:45 /Users/dhamo/m -> /Users/dhamo/claude/CMS/YBL/Mobility
```

### 2. Verify Directory Contents
```bash
ls -la /Users/dhamo/m/
```
Ensure key directories are present:
- `BOBCR/`
- `repos/`
- `artifacts/`
- `Server/`
- `reference-assets/`
- `screens/`, `jenkins/`, `tools/`, `LOGS/`
- `CLAUDE.md`, `LEARNINGS.md`, `Mobility.ear`

### 3. Verify Git Repositories
```bash
cd /Users/dhamo/m/repos/IDFC && git status
cd /Users/dhamo/m/repos/Mobile && git status
```
Git history and working trees should be 100% intact.

---

## 7. Troubleshooting & FAQs

### Q: rclone says `failed to open source object: no such host`
- **Cause:** No internet connection or DNS issue.
- **Fix:** Verify Wi-Fi / Ethernet connection. Run `ping google.com`.

### Q: Checksum mismatch reported during restore
- **Cause:** Download was corrupted in transit due to an unstable network.
- **Fix:** Simply re-run `python3 gdrive_restore.py`. The tool will re-download the affected batch.

### Q: "Disk full" during restoration
- **Design Protection:** The restore tool automatically deletes each `.tar.gz` archive immediately after extraction. You only need enough free disk space for the uncompressed workspace (~30 GB) plus one archive in transit (~3 GB).

### Q: Can I restore on a different Mac username?
- Yes! If your new Mac user account is e.g. `john`, run:
  ```bash
  python3 gdrive_restore.py --dest /Users/john/claude/CMS/YBL/Mobility
  ```
  The script will extract all files to your new home directory and recreate the `~/m` symlink accordingly.

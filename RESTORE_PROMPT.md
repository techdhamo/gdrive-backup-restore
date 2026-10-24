# 🎯 AI Assistant Prompt: Post-Service Mac Workspace Restoration

> **Copy and paste the prompt below directly into Antigravity (or Claude / Gemini / Cursor)**  
> as soon as your Mac is returned from service to trigger complete, autonomous restoration.

---

## 📋 The Copy-Paste Prompt for AI Assistant

```markdown
Restore my development workspace from Google Drive back to this Mac:

1. Environment & Dependencies:
   - Check if Homebrew and rclone are installed (`brew install rclone` if missing).
   - Verify Google Drive authentication (`rclone lsd gdrive:`). If not configured, prompt me or run `rclone config create gdrive drive scope=drive use_trash=false` to complete browser auth.

2. Repository & Restore Tool:
   - Clone or update the restoration repository:
     `git clone https://github.com/techdhamo/gdrive-backup-restore.git ~/gdrive-backup-restore`
     `cd ~/gdrive-backup-restore`

3. Automated Strategy-Based Restore:
   - Execute: `python3 gdrive_restore.py`
   - Ensure it downloads `restore_strategy.json` from `gdrive:m-backup-batches`.
   - Verify that all 7 archive batches are downloaded, cryptographically verified with SHA-256, and extracted cleanly into `/Users/dhamo/claude/CMS/YBL/Mobility`.
   - Confirm each downloaded `.tar.gz` is deleted after extraction to keep disk space minimal.
   - Verify the active symlink: `/Users/dhamo/m -> /Users/dhamo/claude/CMS/YBL/Mobility`.

4. Post-Restore Integrity Checks:
   - Verify key directories exist: `ls -la /Users/dhamo/m/` (BOBCR, repos, artifacts, Server, reference-assets, screens, jenkins, tools, LOGS).
   - Test a git repository: `cd /Users/dhamo/m/repos/IDFC && git status`.
   - Report a final summary table showing restored directories and total file count.
```

---

## 💻 Alternative: 1-Click Terminal Execution

If you prefer to run it yourself directly from the macOS Terminal without opening an AI assistant:

```bash
# Option A: One-liner via curl
curl -fsSL https://raw.githubusercontent.com/techdhamo/gdrive-backup-restore/main/restore.sh | bash
```

```bash
# Option B: Clone & run
git clone https://github.com/techdhamo/gdrive-backup-restore.git ~/restore
cd ~/restore
chmod +x restore.sh
./restore.sh
```

---

## 🔍 What this Automated Restoration Executes:

```
[ Google Drive: m-backup-batches ]
        │
        ▼
Downloads `restore_strategy.json` (7 Batches, 11.77 GB)
        │
        ├── Batch 1: BOBCR (~507k files) ─────────► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        ├── Batch 2: repos (All Git repos) ───────► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        ├── Batch 3: artifacts (Builds & reports) ─► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        ├── Batch 4: Server (Runtimes) ───────────► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        ├── Batch 5: reference-assets ────────────► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        ├── Batch 6: tools & logs ────────────────► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        └── Batch 7: root files & configs ────────► Validates SHA-256 ──► Extracts to /Users/dhamo/claude/CMS/YBL/Mobility
        │
        ▼
Recreates Symlink: `/Users/dhamo/m -> /Users/dhamo/claude/CMS/YBL/Mobility`
        │
        ▼
Runs Sanity Checks & Confirms 100% Integrity
```

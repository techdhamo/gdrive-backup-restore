# 🚀 gdrive-backup-restore

> High-speed Google Drive backup & restore tool — 12 parallel streams, resumable uploads, tuned for 300 Mbps connections.

---

## Features

| Feature | Detail |
|---|---|
| ⚡ **Parallel transfers** | 12 simultaneous streams (configurable) |
| 📦 **Large chunk size** | 32 MB chunks — fewer round-trips on fast lines |
| 🔄 **Resumable** | Interrupted uploads/downloads continue where they left off |
| 🗂️ **Mirror structure** | Exact folder hierarchy preserved on Drive |
| 🔒 **Safe restore** | Skip/overwrite/backup conflict modes |
| 📋 **Full logging** | Per-run log files for audit trail |
| 🔌 **rclone powered** | Battle-tested, no API quota headaches |

---

## Prerequisites

```bash
# Install rclone (one-time)
brew install rclone

# Authenticate with Google Drive (one-time — opens browser)
rclone config create gdrive drive scope=drive use_trash=false
```

Follow the browser prompt → sign in → Allow → done.

---

## Backup (Upload to Google Drive)

### Quick start
```bash
./setup_and_run.sh
```

### Manual
```bash
rclone copy /Users/dhamo/m gdrive:m-backup \
  --transfers 12 \
  --drive-chunk-size 32M \
  --drive-upload-cutoff 32M \
  --checkers 16 \
  --exclude "gdrive_upload/**" \
  --exclude ".DS_Store" \
  --stats 10s \
  -P
```

### Options
| Flag | Default | Description |
|---|---|---|
| `--transfers` | 12 | Parallel upload streams |
| `--drive-chunk-size` | 32M | Upload chunk size |
| `--exclude` | — | Glob patterns to skip |
| `-P` | — | Show live progress |

---

## Restore (Download from Google Drive)

After Mac service, migration, or fresh install — restore everything back to the original path.

### Quick start
```bash
python3 gdrive_restore.py
```

This auto-detects the latest `m-backup` folder on Drive and downloads to `/Users/dhamo/m`.

### Options

```bash
# Preview what will be restored (no files downloaded)
python3 gdrive_restore.py --dry-run

# List all available backup folders on Drive
python3 gdrive_restore.py --list

# Restore from a specific backup
python3 gdrive_restore.py --drive-folder m-backup-20261024

# Restore to a different path
python3 gdrive_restore.py --dest /Users/dhamo/restored

# Overwrite existing files instead of skipping
python3 gdrive_restore.py --conflict overwrite

# Backup existing files before overwriting
python3 gdrive_restore.py --conflict backup

# Adjust parallel streams
python3 gdrive_restore.py --workers 8
```

### Conflict modes

| Mode | Behaviour |
|---|---|
| `skip` *(default)* | Keep existing local file — safe for partial restores |
| `overwrite` | Replace local file with the Drive version |
| `backup` | Move existing local file to a timestamped backup dir, then restore |

---

## Full Reference

### Backup script: `setup_and_run.sh`
Installs dependencies and runs rclone upload with all optimised flags.

### Python uploader: `gdrive_uploader.py`
Alternative Python-based uploader using the Google Drive API directly.
Useful if rclone is not available or you need custom upload logic.

```bash
source venv/bin/activate
python3 gdrive_uploader.py --workers 12 --drive-folder my-backup
```

### Restore script: `gdrive_restore.py`
Downloads from Google Drive back to the local machine.

```bash
python3 gdrive_restore.py --help
```

---

## Project Structure

```
gdrive_upload/
├── README.md               ← This file
├── setup_and_run.sh        ← One-click backup launcher
├── gdrive_uploader.py      ← Python Drive API uploader
├── gdrive_restore.py       ← Restore from Drive to local
├── requirements.txt        ← Python dependencies
├── .gitignore              ← Excludes credentials & logs
│
│   (generated at runtime — not committed)
├── upload_state.json       ← Resume state for Python uploader
├── upload.log              ← Python uploader log
├── restore.log             ← Restore log
└── rclone_upload.log       ← rclone upload log
```

---

## Performance Guide

| Connection | Recommended `--transfers` | Expected Speed |
|---|---|---|
| 50 Mbps | 4 | ~5 MB/s |
| 100 Mbps | 6 | ~10 MB/s |
| 300 Mbps | **12** | ~25–35 MB/s |
| 1 Gbps | 20 | ~80 MB/s |

> **Note:** Google Drive may throttle very large uploads after ~100 GB/day. If you hit rate limits, reduce `--transfers` to 6.

---

## Security

- **Never commit** `credentials.json`, `token.json`, or `rclone.conf` — all are in `.gitignore`
- rclone stores OAuth tokens in `~/.config/rclone/rclone.conf` (your home directory, not this repo)
- The Python uploader stores tokens in `token.json` locally (also git-ignored)

---

## License

MIT — free to use and modify.

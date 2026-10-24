# 🚀 gdrive-backup-restore

> **Enterprise-grade, high-speed Google Drive backup & restore toolkit.**  
> Built for large-scale engineering codebases (1.2M+ files, 30+ GB).  
> Features **Batch-Compressed Streaming with Automated Restore Strategies (v2.0)**, tuned for 300+ Mbps connections.

---

## 📚 Complete Documentation Suite

| Document | Purpose |
|---|---|
| 📖 [**RESTORATION_PLAYBOOK.md**](RESTORATION_PLAYBOOK.md) | **Step-by-step recovery guide** after your Mac returns from service or wipe |
| 🏗️ [**ARCHITECTURE.md**](ARCHITECTURE.md) | **Technical design deep-dive**, benchmarks, and manifest specification |
| 📋 [**RESTORE_STRATEGY.md**](RESTORE_STRATEGY.md) | Auto-generated batch manifest and checksum reference uploaded to Google Drive |

---

## 🌟 Architecture & Strategy (v2.0)

When backing up workspaces containing hundreds of thousands or millions of files (e.g. node_modules, svn, database dumps, build artifacts), individual file uploads encounter extreme HTTP request latency and API rate limits.

**`gdrive-backup-restore v2.0` solves this with Batch-Compression & Strategy Manifests:**

```
[ ~/m (~28.4 GB, 1.2M files) ]
       │
       ▼
 1. Discover & Group Into Batches (BOBCR, repos, artifacts, server, tools, root)
       │
       ▼ (Batch-by-Batch Sliding Window Pipeline)
 2. Compress to .tar.gz ──► 3. Compute SHA-256 ──► 4. Upload to Drive ──► 5. Delete Local Archive
                                                                             (Zero disk bloat)
       │
       ▼
 6. Generate `restore_strategy.json` & `RESTORE_STRATEGY.md`
       │
       ▼
 7. Upload Strategy Docs to Drive Root
```

```
[ After Mac Service / Restoration ]
       │
       ▼
 1. Run `python3 gdrive_restore.py`
 2. Program downloads `restore_strategy.json` from Drive
 3. Downloads archives batch-by-batch
 4. Validates SHA-256 cryptographic integrity
 5. Extracts to target directory (`/Users/dhamo/claude/CMS/YBL/Mobility`)
 6. Deletes local `.tar.gz` after extraction
 7. Reconstructs symlinks (`~/m -> /Users/dhamo/claude/CMS/YBL/Mobility`)
```

---

## ✨ Features

| Feature | Detail |
|---|---|
| ⚡ **Batch Compression** | Groups 1.2M files into 7 balanced, high-speed archives |
| 🔒 **Cryptographic Integrity** | SHA-256 checksum calculated and verified for every batch |
| 📋 **Strategy Manifest** | Auto-generates `restore_strategy.json` and human-readable `RESTORE_STRATEGY.md` |
| 🧹 **Zero Disk Waste** | Local `.tar.gz` is immediately deleted after upload/extraction (< 4.5 GB peak usage) |
| 🔄 **100% Resumable** | State file tracks uploaded batches; resumes instantly if interrupted |
| 🔗 **Symlink Preservation** | Records and restores directory symlinks accurately |
| 🔌 **High Speed** | Tuned for 300 Mbps bandwidth (64 MB chunks, multi-threaded) |

---

## 🛠️ Prerequisites

```bash
# Install rclone (one-time)
brew install rclone

# Authenticate with Google Drive (one-time — opens browser)
rclone config create gdrive drive scope=drive use_trash=false
```

---

## 🚀 Usage

### 1. Run Batch Backup (Recommended)

Compresses batch by batch, uploads, frees disk space, and uploads the restore strategy:

```bash
python3 gdrive_batch_backup.py
```

Options:
- `--folder <name>`: Drive folder (default: `m-backup-batches`)
- `--dry-run`: Preview batch division and calculations without uploading

---

### 2. Restore After Mac Service

Once your Mac is serviced or wiped:

```bash
# 1. Install & configure rclone
brew install rclone
rclone config create gdrive drive scope=drive use_trash=false

# 2. Run restore (reads strategy document automatically from Drive)
python3 gdrive_restore.py
```

*For complete step-by-step restoration procedures, verification commands, and troubleshooting, read [RESTORATION_PLAYBOOK.md](RESTORATION_PLAYBOOK.md).*

Options:
- `--dest <path>`: Custom restore path (default: `/Users/dhamo/claude/CMS/YBL/Mobility`)
- `--batch <id>`: Restore only a single batch (e.g. `--batch 1`)
- `--dry-run`: Simulate download, verification, and extraction
- `--list`: List all backup folders on Drive

---

## 📦 What Batches Are Created?

| Batch | Archive | Contents | Raw Size | Compressed |
|:---:|:---|:---|:---:|:---:|
| **1** | `batch_01_bobcr.tar.gz` | `BOBCR/` (Database scripts, comparisons, UAT/Dev dumps) | 10.2 GB | **1.29 GB** |
| **2** | `batch_02_repos.tar.gz` | `repos/` (Git repositories: IDFC, Mobile, YBL, etc.) | 12.1 GB | **~3.5 GB** |
| **3** | `batch_03_artifacts.tar.gz` | `artifacts/` (Build deliverables, mobile reports) | 4.7 GB | **~1.1 GB** |
| **4** | `batch_04_server.tar.gz` | `Server/` (Runtimes and server configs) | 1.8 GB | **~0.4 GB** |
| **5** | `batch_05_reference_assets.tar.gz` | `reference-assets/` (Documentation assets, prototypes) | 1.2 GB | **~0.3 GB** |
| **6** | `batch_06_tools_and_logs.tar.gz` | `screens/`, `jenkins/`, `tools/`, `LOGS/` | 1.4 GB | **~0.4 GB** |
| **7** | `batch_07_root_and_configs.tar.gz` | Root files, `.claude/`, markdown guides, PDFs, `Mobility.ear` | 0.4 GB | **~0.2 GB** |

---

## 🛡️ License

MIT License. Developed for enterprise-grade reliability and high performance.

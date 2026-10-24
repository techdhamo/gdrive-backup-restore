# 📋 Google Drive Restore Strategy Document

> **Last Updated:** 2026-10-24T12:06:48.269856+00:00  
> **Original Source:** `/Users/dhamo/m` → `/Users/dhamo/claude/CMS/YBL/Mobility`  
> **Target Remote Folder:** `m-backup-batches`  
> **Total Compressed Batches:** 7  
> **Total Compressed Size:** 11.77 GB  

---

## 📦 Backup Archive Batches

| Batch | Archive File | Items Included | Compressed Size | SHA-256 Checksum | Last Uploaded |
| :---: | :--- | :--- | :---: | :--- | :--- |
| **1** | `batch_01_bobcr.tar.gz` | `BOBCR` | 1.29 GB | `0a084bb78deb5216...` | 2026-10-24 02:04:41 |
| **2** | `batch_02_repos.tar.gz` | `repos` | 5.50 GB | `9f7ef17e15bfc3fe...` | 2026-10-24 11:58:52 |
| **3** | `batch_03_artifacts.tar.gz` | `artifacts` | 2.12 GB | `15bc8d35f6813dbd...` | 2026-10-24 12:05:49 |
| **4** | `batch_04_server.tar.gz` | `Server` | 1.08 GB | `1226e9938046775f...` | 2026-10-24 02:31:26 |
| **5** | `batch_05_reference_assets.tar.gz` | `reference-assets` | 516.10 MB | `9c0ab255b9ff949a...` | 2026-10-24 02:32:52 |
| **6** | `batch_06_tools_and_logs.tar.gz` | `screens`, `jenkins`, `tools`, `LOGS` | 1006.27 MB | `6750ff5786ecbee4...` | 2026-10-24 02:34:43 |
| **7** | `batch_07_root_and_configs.tar.gz` | `.backup-2026-10-01`, `.claude`, `BDTS_PlanDesign_Business_Requirment_Accessibility Compliance basis ITE at IGTB (1).docx.md`, `CBX-A11Y-001_FSD_Accessibility_Options.pdf` (+23 more) | 287.19 MB | `6520bc3d5c119a29...` | 2026-10-24 12:06:48 |

---

## 🔄 Restoration Instructions

When restoring on your newly serviced or wiped Mac:

```bash
# 1. Ensure rclone is installed & authenticated
brew install rclone
rclone config create gdrive drive scope=drive use_trash=false

# 2. Clone and run restore
git clone https://github.com/techdhamo/gdrive-backup-restore.git ~/restore
cd ~/restore
python3 gdrive_restore.py
```

### How `gdrive_restore.py` works automatically:
1. Fetches `restore_strategy.json` directly from Google Drive.
2. Downloads archives batch-by-batch into local staging.
3. Validates each archive with SHA-256 before extraction.
4. Extracts files cleanly to `/Users/dhamo/claude/CMS/YBL/Mobility`.
5. Deletes local `.tar.gz` after extraction to preserve disk space.
6. Recreates `/Users/dhamo/m` symlink pointing to the restored project.

---
*End of Strategy Document — Version 2.1*
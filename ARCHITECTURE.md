# 🏗️ Architecture & Technical Design Specification (v2.0)

> Deep-dive architectural documentation for `gdrive-backup-restore v2.0`.

---

## 1. Problem Statement: Why Raw File Sync Fails on Large Codebases

The directory `/Users/dhamo/m` (`/Users/dhamo/claude/CMS/YBL/Mobility`) contains:
- **Total Uncompressed Size:** ~28.4 GB
- **Total Files:** 1,238,389 files (1.23 Million)
- **Characteristics:** Highly fragmented (millions of small `.sql`, `.java`, `.xml`, `.js`, `.svn`, and build files), alongside multi-gigabyte zip/ear archives and git packfiles.

### The Bottleneck with Traditional File Sync:
When uploading 1.2M individual files over cloud storage APIs (Google Drive REST API):
1. **HTTP Handshake Overhead:** Each file requires an HTTPS request, authorization token exchange, and metadata creation in Drive.
2. **API Rate Limiting:** Google Drive enforces rate limits (typically ~10 queries per second per user). At 10 files/second, 1.23 million files would require **~34 hours** minimum, purely in HTTP overhead, regardless of internet bandwidth!
3. **Directory Traversal Lag:** Walking 1.2 million inodes takes 10–15 minutes on local APFS and causes rclone denominator calculations to drag indefinitely.

---

## 2. The Solution: Batch-Compressed Pipeline Architecture

Version 2.0 solves this by transitioning from **file-level sync** to **batch-archive streaming**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Local Workspace (~28.4 GB)                     │
│                /Users/dhamo/claude/CMS/YBL/Mobility                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                       1. Intelligent Batch Partition
                                    │
 ┌────────────────┬─────────────────┼────────────────┬──────────────────┐
 │                │                 │                │                  │
 ▼                ▼                 ▼                ▼                  ▼
Batch 1          Batch 2           Batch 3          Batch 4–6          Batch 7
BOBCR            repos             artifacts        Server, Assets,    Root Docs &
(10 GB raw)      (12 GB raw)       (4.7 GB raw)     Tools & Logs       Configs
 │                │                 │                │                  │
 └────────────────┴─────────────────┼────────────────┴──────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │             Streaming Compression Engine                │
       │  tar -czf (preserves modes, paths, timestamps, links)   │
       └────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │              Cryptographic Checksum Engine              │
       │  Calculates SHA-256 in 4MB streaming chunks             │
       └────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │           High-Speed Multi-Threaded Uploader            │
       │  rclone copy --drive-chunk-size 64M --transfers 8       │
       └────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                 Ephemeral Disk Cleanup                  │
       │  local_archive.unlink() frees staging storage           │
       └────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │          Strategy Manifest Generation & Upload          │
       │  restore_strategy.json & RESTORE_STRATEGY.md            │
       └─────────────────────────────────────────────────────────┘
```

---

## 3. Storage Efficiency & Compression Ratio

Because codebases and database dumps consist predominantly of text files (`.sql`, `.xml`, `.java`, `.properties`, `.json`), gzip compression yields an exceptional **~3.2x compression ratio**:

| Batch | Content Description | Raw Size | Compressed Size | Reduction |
|---|---|:---:|:---:|:---:|
| **1** | `BOBCR` (Database scripts, comparisons) | 10.2 GB | **1.29 GB** | **87% smaller** |
| **2** | `repos` (IDFC, Mobile, YBL Git trees) | 12.1 GB | **~3.5 GB** | **71% smaller** |
| **3** | `artifacts` (Build output, reports) | 4.7 GB | **~1.1 GB** | **76% smaller** |
| **4** | `Server` (Local runtime & configs) | 1.8 GB | **~0.4 GB** | **78% smaller** |
| **5** | `reference-assets` | 1.2 GB | **~0.3 GB** | **75% smaller** |
| **6** | `screens`, `jenkins`, `tools`, `LOGS` | 1.4 GB | **~0.4 GB** | **71% smaller** |
| **7** | Root documents, `.claude`, `Mobility.ear` | 0.4 GB | **~0.2 GB** | **50% smaller** |
| **TOTAL** | **Full `~/m` Workspace** | **~31.8 GB** | **~7.2 – 8.5 GB** | **~75% reduction** |

---

## 4. Manifest Schema (`restore_strategy.json`)

The manifest provides complete self-describing recovery instructions:

```json
{
  "version": "2.0",
  "created_at": "2026-10-24T02:04:41.126607+00:00",
  "drive_remote": "gdrive",
  "drive_folder": "m-backup-batches",
  "source": {
    "symlink_path": "/Users/dhamo/m",
    "real_path": "/Users/dhamo/claude/CMS/YBL/Mobility"
  },
  "restore_destination_default": "/Users/dhamo/claude/CMS/YBL/Mobility",
  "symlinks_to_create": [
    {
      "link_path": "/Users/dhamo/m",
      "target_path": "/Users/dhamo/claude/CMS/YBL/Mobility"
    }
  ],
  "total_compressed_bytes": 8452194816,
  "batches": [
    {
      "batch_id": 1,
      "archive_name": "batch_01_bobcr.tar.gz",
      "description": "BOBCR database scripts, comparisons, and tools",
      "items": ["BOBCR"],
      "compressed_bytes": 1389173110,
      "sha256": "0a084bb78deb5216ed14d621f7720b2eab3fda0b6bd3a6969af8829189dfcc12",
      "upload_timestamp": "2026-10-24T02:04:41.126607+00:00"
    }
  ]
}
```

---

## 5. Security & Cryptographic Integrity

1. **Deterministic Hashing:** SHA-256 is computed directly on the `.tar.gz` stream via 4MB memory buffers before upload.
2. **Pre-Extraction Verification:** `gdrive_restore.py` recalculates the SHA-256 hash of every downloaded archive and asserts that it matches the manifest byte-for-byte.
3. **Fail-Closed Safety:** If even a single byte is corrupted during transit or truncated by an unstable Wi-Fi connection, extraction is blocked, protecting the destination directory from corrupted partial states.

---

## 6. Zero Disk Bloat (Ephemeral Staging)

On machines with constrained local SSD storage (e.g. 114 GB available), creating a full 30 GB uncompressed staging directory alongside an 8 GB compressed copy would consume ~38 GB simultaneously.

`gdrive-backup-restore v2.0` operates in a **sliding window**:
- Only **one** archive exists locally at any single time (`~1.5 GB` average).
- Immediately after Google Drive acknowledges receipt, `local_archive.unlink()` reclaims that disk space.
- Maximum local disk headroom required at peak: **< 4.5 GB**.

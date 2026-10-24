#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║        Google Drive Batch-Compressed Backup Tool v2.0                ║
║  Compress Batch-by-Batch, Upload, Generate & Upload Restore Strategy ║
╚══════════════════════════════════════════════════════════════════════╝

Strategy:
  1. Divides ~/m into logical archive batches (BOBCR, repos, artifacts, etc.)
  2. Compresses batch-by-batch into .tar.gz (tar streaming)
  3. Computes SHA-256 hash & metrics
  4. Uploads immediately to Google Drive (rclone high-speed chunked stream)
  5. Deletes local archive immediately after upload (zero disk bloat)
  6. Generates restore_strategy.json + RESTORE_STRATEGY.md
  7. Uploads strategy documents to Google Drive for automated restore
"""

import os
import sys
import json
import time
import shutil
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, _):
            return ""
    Fore = Style = DummyColor()

RCLONE = shutil.which("rclone") or "/opt/homebrew/bin/rclone"
SOURCE_LINK = Path("/Users/dhamo/m")
SOURCE_REAL = SOURCE_LINK.resolve()
DEFAULT_REMOTE = "gdrive"
DEFAULT_FOLDER = "m-backup-batches"
STAGING_DIR = Path(__file__).parent / "staging"
STATE_FILE = Path(__file__).parent / "batch_backup_state.json"


def check_rclone():
    if not Path(RCLONE).exists() and not shutil.which("rclone"):
        print(f"{Fore.RED}✗ rclone not found. Please install: brew install rclone{Style.RESET_ALL}")
        sys.exit(1)


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024 * 4):  # 4MB chunks
            h.update(chunk)
    return h.hexdigest()


def format_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


def discover_batches(source_dir: Path):
    """
    Scans source directory and groups items into logical batches.
    """
    excluded = {"gdrive_upload", ".DS_Store", ".git"}
    all_entries = sorted([e for e in os.listdir(source_dir) if e not in excluded and not e.startswith("._")])
    
    batches = []
    batch_num = 1
    
    # 1. Major folders get their own batches for isolation & parallel speed
    priority_dirs = [
        ("BOBCR", "batch_01_bobcr.tar.gz", "BOBCR database scripts, comparisons, and tools"),
        ("repos", "batch_02_repos.tar.gz", "Git & code repositories (IDFC, Mobile, YBL, etc.)"),
        ("artifacts", "batch_03_artifacts.tar.gz", "Project artifacts, builds, and deliverables"),
        ("Server", "batch_04_server.tar.gz", "Server runtimes and local configurations"),
        ("reference-assets", "batch_05_reference_assets.tar.gz", "Reference assets and mobile documentation"),
    ]
    
    consumed = set()
    for dirname, archive_name, desc in priority_dirs:
        if dirname in all_entries:
            batches.append({
                "batch_id": batch_num,
                "archive_name": archive_name,
                "description": desc,
                "items": [dirname],
            })
            consumed.add(dirname)
            batch_num += 1
            
    # Secondary folders group
    tools_dirs = ["screens", "jenkins", "tools", "LOGS"]
    tools_items = [d for d in tools_dirs if d in all_entries]
    if tools_items:
        batches.append({
            "batch_id": batch_num,
            "archive_name": f"batch_{batch_num:02d}_tools_and_logs.tar.gz",
            "description": "Screens, Jenkins configs, tooling, and development logs",
            "items": tools_items,
        })
        for d in tools_items:
            consumed.add(d)
        batch_num += 1

    # Remaining items (root files, markdown docs, .claude, etc.)
    remaining = [e for e in all_entries if e not in consumed]
    if remaining:
        batches.append({
            "batch_id": batch_num,
            "archive_name": f"batch_{batch_num:02d}_root_and_configs.tar.gz",
            "description": "Project configs, documentation, PDFs, and root assets",
            "items": remaining,
        })
        
    return batches


def rclone_file_exists(remote: str, drive_path: str, filename: str) -> bool:
    cmd = [RCLONE, "lsf", f"{remote}:{drive_path}/{filename}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0 and filename in res.stdout


def upload_file_rclone(local_path: Path, remote: str, drive_path: str, max_workers: int = 8):
    cmd = [
        RCLONE, "copy",
        str(local_path),
        f"{remote}:{drive_path}",
        "--transfers", str(max_workers),
        "--drive-chunk-size", "64M",
        "--drive-upload-cutoff", "64M",
        "-P",
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"rclone upload failed with code {res.returncode}")


def generate_restore_strategy_md(strategy: dict) -> str:
    lines = [
        "# 📋 Google Drive Restore Strategy Document",
        "",
        f"> **Generated at:** {strategy['created_at']}  ",
        f"> **Original Source:** `{strategy['source']['symlink_path']}` → `{strategy['source']['real_path']}`  ",
        f"> **Target Remote Folder:** `{strategy['drive_folder']}`  ",
        f"> **Total Compressed Batches:** {len(strategy['batches'])}  ",
        f"> **Total Compressed Size:** {format_bytes(strategy['total_compressed_bytes'])}  ",
        "",
        "---",
        "",
        "## 📦 Backup Archive Batches",
        "",
        "| Batch | Archive File | Items Included | Compressed Size | SHA-256 Checksum |",
        "| :---: | :--- | :--- | :---: | :--- |",
    ]
    for b in strategy["batches"]:
        items_str = ", ".join(f"`{i}`" for i in b["items"][:4])
        if len(b["items"]) > 4:
            items_str += f" (+{len(b['items'])-4} more)"
        lines.append(
            f"| **{b['batch_id']}** | `{b['archive_name']}` | {items_str} | {format_bytes(b['compressed_bytes'])} | `{b['sha256'][:16]}...` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 🔄 Restoration Instructions",
        "",
        "When restoring on your newly serviced or wiped Mac:",
        "",
        "```bash",
        "# 1. Ensure rclone is installed & authenticated",
        "brew install rclone",
        "rclone config create gdrive drive scope=drive use_trash=false",
        "",
        "# 2. Clone or run gdrive_restore.py",
        "python3 gdrive_restore.py",
        "```",
        "",
        "### How `gdrive_restore.py` works automatically:",
        "1. Fetches `restore_strategy.json` directly from Google Drive.",
        "2. Downloads archives batch-by-batch into local staging.",
        "3. Validates each archive with SHA-256 before extraction.",
        "4. Extracts files cleanly to `/Users/dhamo/claude/CMS/YBL/Mobility`.",
        "5. Deletes local `.tar.gz` after extraction to preserve disk space.",
        "6. Recreates `/Users/dhamo/m` symlink pointing to the restored project.",
        "",
        "---",
        f"*End of Strategy Document — Version {strategy['version']}*",
    ])
    return "\n".join(lines)


def run_batch_backup(remote: str, drive_folder: str, dry_run: bool = False):
    print(f"\n{Fore.CYAN}{'═'*68}")
    print(f"  🚀  Batch-Compressed Google Drive Backup & Strategy Generator")
    print(f"{'═'*68}{Style.RESET_ALL}")
    print(f"  Source (Link): {SOURCE_LINK}")
    print(f"  Source (Real): {SOURCE_REAL}")
    print(f"  Drive Remote : {remote}:{drive_folder}")
    print(f"  Staging Dir  : {STAGING_DIR}")
    if dry_run:
        print(f"  {Fore.YELLOW}⚠  DRY RUN MODE — no archives will be created or uploaded{Style.RESET_ALL}")
    print()

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    batches = discover_batches(SOURCE_REAL)

    # Load state if resuming
    state = {}
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        except Exception:
            state = {}

    completed_batches = state.get("completed_batches", {})
    strategy_batches = []
    total_compressed = 0

    print(f"{Fore.GREEN}Plan: Discovered {len(batches)} archive batches:{Style.RESET_ALL}")
    for b in batches:
        print(f"  • Batch {b['batch_id']}: {b['archive_name']} ({b['description']})")
    print()

    for idx, b in enumerate(batches, 1):
        archive_name = b["archive_name"]
        print(f"{Fore.YELLOW}{'─'*68}")
        print(f"  📦 Processing Batch {idx}/{len(batches)}: {archive_name}")
        print(f"     Items: {', '.join(b['items'][:6])}")
        print(f"{'─'*68}{Style.RESET_ALL}")

        # Check if already completed and in Drive
        if archive_name in completed_batches:
            meta = completed_batches[archive_name]
            print(f"{Fore.GREEN}✓  Already uploaded according to state: {format_bytes(meta['compressed_bytes'])} (SHA: {meta['sha256'][:12]}...){Style.RESET_ALL}")
            strategy_batches.append(meta)
            total_compressed += meta["compressed_bytes"]
            continue

        if dry_run:
            print(f"  [Dry Run] Would compress {b['items']} -> {archive_name} and upload to Drive")
            strategy_batches.append({
                "batch_id": b["batch_id"],
                "archive_name": archive_name,
                "description": b["description"],
                "items": b["items"],
                "compressed_bytes": 0,
                "sha256": "dry-run-hash",
            })
            continue

        local_archive = STAGING_DIR / archive_name

        # 1. Compress batch
        print(f"  ⚡ Compressing batch into {archive_name} …")
        t0 = time.time()
        tar_cmd = ["tar", "-czf", str(local_archive), "-C", str(SOURCE_REAL)] + b["items"]
        res = subprocess.run(tar_cmd)
        if res.returncode != 0:
            print(f"{Fore.RED}✗ Failed to create archive for batch {b['batch_id']}{Style.RESET_ALL}")
            sys.exit(1)
        
        comp_dur = time.time() - t0
        arch_size = local_archive.stat().st_size
        print(f"  ✓ Compressed in {comp_dur:.1f}s | Size: {Fore.GREEN}{format_bytes(arch_size)}{Style.RESET_ALL}")

        # 2. Compute SHA-256
        print(f"  🔒 Calculating SHA-256 checksum …")
        sha = sha256_file(local_archive)
        print(f"     SHA-256: {Fore.CYAN}{sha}{Style.RESET_ALL}")

        # 3. Upload to Google Drive
        print(f"  ☁ Uploading {archive_name} to {remote}:{drive_folder}/archives/ …")
        t_up0 = time.time()
        upload_file_rclone(local_archive, remote, f"{drive_folder}/archives")
        up_dur = time.time() - t_up0
        speed_mbps = (arch_size * 8 / (1024 * 1024)) / max(up_dur, 0.1)
        print(f"  ✓ Uploaded in {up_dur:.1f}s | Average Speed: {speed_mbps:.1f} Mbps")

        # 4. Immediate local cleanup
        print(f"  🧹 Cleaning up local archive {archive_name} to free disk space …")
        local_archive.unlink(missing_ok=True)
        print(f"  ✓ Freed {format_bytes(arch_size)} local disk space")

        batch_meta = {
            "batch_id": b["batch_id"],
            "archive_name": archive_name,
            "description": b["description"],
            "items": b["items"],
            "compressed_bytes": arch_size,
            "sha256": sha,
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        completed_batches[archive_name] = batch_meta
        strategy_batches.append(batch_meta)
        total_compressed += arch_size

        # Save checkpoint
        with open(STATE_FILE, "w") as f:
            json.dump({"completed_batches": completed_batches}, f, indent=2)

    # 5. Build Restore Strategy Document
    strategy = {
        "version": "2.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "drive_remote": remote,
        "drive_folder": drive_folder,
        "source": {
            "symlink_path": str(SOURCE_LINK),
            "real_path": str(SOURCE_REAL),
        },
        "restore_destination_default": str(SOURCE_REAL),
        "symlinks_to_create": [
            {
                "link_path": str(SOURCE_LINK),
                "target_path": str(SOURCE_REAL),
            }
        ],
        "total_compressed_bytes": total_compressed,
        "batches": strategy_batches,
    }

    strategy_json_path = Path(__file__).parent / "restore_strategy.json"
    strategy_md_path = Path(__file__).parent / "RESTORE_STRATEGY.md"

    with open(strategy_json_path, "w", encoding="utf-8") as f:
        json.dump(strategy, f, indent=2)

    with open(strategy_md_path, "w", encoding="utf-8") as f:
        f.write(generate_restore_strategy_md(strategy))

    print(f"\n{Fore.GREEN}{'═'*68}")
    print(f"  🎉 All batches compressed & uploaded successfully!")
    print(f"  Total Compressed Size: {format_bytes(total_compressed)}")
    print(f"{'═'*68}{Style.RESET_ALL}\n")

    if not dry_run:
        print(f"{Fore.CYAN}Uploading restore strategy documents to {remote}:{drive_folder}/ …{Style.RESET_ALL}")
        upload_file_rclone(strategy_json_path, remote, drive_folder)
        upload_file_rclone(strategy_md_path, remote, drive_folder)
        print(f"{Fore.GREEN}✓ restore_strategy.json and RESTORE_STRATEGY.md live on Google Drive!{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Backup complete! Restore tool is ready to use:{Style.RESET_ALL}")
    print(f"  python3 gdrive_restore.py\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Drive Batch-Compressed Backup Tool")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help="rclone remote name")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="Drive destination folder")
    parser.add_argument("--dry-run", action="store_true", help="Preview batches without uploading")
    args = parser.parse_args()

    check_rclone()
    run_batch_backup(args.remote, args.folder, dry_run=args.dry_run)

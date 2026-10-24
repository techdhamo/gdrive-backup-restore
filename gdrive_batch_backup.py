#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║        Google Drive Batch-Compressed Backup Tool v2.1                ║
║  Smart Incremental Replacement: Detects Modified Batches & Uploads   ║
╚══════════════════════════════════════════════════════════════════════╝

Features:
  1. Detects modified files inside batches since last backup (fast early exit).
  2. If content modified: re-compresses, re-hashes with SHA-256, and replaces
     the archive on Google Drive.
  3. If content unchanged: retains existing verified Drive archive (saves bandwidth & time).
  4. Ephemeral local staging: deletes each local archive immediately after upload.
  5. Updates restore_strategy.json & RESTORE_STRATEGY.md and uploads them to Drive.
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


def check_batch_modified(source_real: Path, items: list[str], last_upload_iso: str | None) -> tuple[bool, str]:
    """
    Checks if any file inside the batch items was modified after last_upload_iso.
    Returns (True, reason) if modified, or (False, "unchanged") if clean.
    """
    if not last_upload_iso:
        return True, "No previous backup record found"
    
    try:
        cutoff = datetime.fromisoformat(last_upload_iso).timestamp()
    except Exception:
        return True, "Invalid timestamp in state"
    
    for item in items:
        p = source_real / item
        if not p.exists():
            continue
        try:
            if p.is_symlink():
                continue
            if p.is_file():
                if p.stat().st_mtime > cutoff:
                    return True, f"Modified file: {item}"
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            if not os.path.islink(fp) and os.path.getmtime(fp) > cutoff:
                                rel = os.path.relpath(fp, source_real)
                                return True, f"Modified file: {rel}"
                        except Exception:
                            pass
        except Exception:
            pass

    return False, "All files clean (no modifications)"


def discover_batches(source_dir: Path):
    """
    Scans source directory and groups items into logical batches.
    """
    excluded = {"gdrive_upload", ".DS_Store", ".git"}
    all_entries = sorted([e for e in os.listdir(source_dir) if e not in excluded and not e.startswith("._")])
    
    batches = []
    batch_num = 1
    
    # 1. Major folders get their own batches
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


def upload_file_rclone(local_path: Path, remote: str, drive_path: str, max_workers: int = 8):
    """Uploads file using rclone, overwriting remote target if it exists."""
    cmd = [
        RCLONE, "copyto",
        str(local_path),
        f"{remote}:{drive_path}/{local_path.name}",
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
        f"> **Last Updated:** {strategy['created_at']}  ",
        f"> **Original Source:** `{strategy['source']['symlink_path']}` → `{strategy['source']['real_path']}`  ",
        f"> **Target Remote Folder:** `{strategy['drive_folder']}`  ",
        f"> **Total Compressed Batches:** {len(strategy['batches'])}  ",
        f"> **Total Compressed Size:** {format_bytes(strategy['total_compressed_bytes'])}  ",
        "",
        "---",
        "",
        "## 📦 Backup Archive Batches",
        "",
        "| Batch | Archive File | Items Included | Compressed Size | SHA-256 Checksum | Last Uploaded |",
        "| :---: | :--- | :--- | :---: | :--- | :--- |",
    ]
    for b in strategy["batches"]:
        items_str = ", ".join(f"`{i}`" for i in b["items"][:4])
        if len(b["items"]) > 4:
            items_str += f" (+{len(b['items'])-4} more)"
        ts = b.get("upload_timestamp", "")[:19].replace("T", " ")
        lines.append(
            f"| **{b['batch_id']}** | `{b['archive_name']}` | {items_str} | {format_bytes(b['compressed_bytes'])} | `{b['sha256'][:16]}...` | {ts} |"
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
        "# 2. Clone and run restore",
        "git clone https://github.com/techdhamo/gdrive-backup-restore.git ~/restore",
        "cd ~/restore",
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


def run_batch_backup(remote: str, drive_folder: str, dry_run: bool = False, force: bool = False):
    print(f"\n{Fore.CYAN}{'═'*68}")
    print(f"  🚀  Batch-Compressed Google Drive Backup & Smart Sync v2.1")
    print(f"{'═'*68}{Style.RESET_ALL}")
    print(f"  Source (Link): {SOURCE_LINK}")
    print(f"  Source (Real): {SOURCE_REAL}")
    print(f"  Drive Remote : {remote}:{drive_folder}")
    print(f"  Staging Dir  : {STAGING_DIR}")
    if force:
        print(f"  {Fore.YELLOW}⚡ FORCE MODE — Re-compressing and replacing ALL batches{Style.RESET_ALL}")
    if dry_run:
        print(f"  {Fore.YELLOW}⚠  DRY RUN MODE — no archives will be uploaded{Style.RESET_ALL}")
    print()

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    batches = discover_batches(SOURCE_REAL)

    # Load state if exists
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
    modified_batches_count = 0

    print(f"{Fore.GREEN}Plan: Discovered {len(batches)} archive batches:{Style.RESET_ALL}")
    for b in batches:
        print(f"  • Batch {b['batch_id']}: {b['archive_name']} ({b['description']})")
    print()

    for idx, b in enumerate(batches, 1):
        archive_name = b["archive_name"]
        print(f"{Fore.YELLOW}{'─'*68}")
        print(f"  📦 Checking Batch {idx}/{len(batches)}: {archive_name}")
        print(f"     Items: {', '.join(b['items'][:6])}")
        print(f"{'─'*68}{Style.RESET_ALL}")

        prev_meta = completed_batches.get(archive_name)
        last_ts = prev_meta.get("upload_timestamp") if prev_meta else None

        # Check if content has been modified
        if force:
            is_modified = True
            reason = "Forced replacement (--force specified)"
        else:
            is_modified, reason = check_batch_modified(SOURCE_REAL, b["items"], last_ts)

        if not is_modified and prev_meta:
            print(f"  {Fore.GREEN}✓ No modifications detected.{Style.RESET_ALL}")
            print(f"    Keeping verified archive on Drive: {format_bytes(prev_meta['compressed_bytes'])} (SHA: {prev_meta['sha256'][:12]}...)")
            strategy_batches.append(prev_meta)
            total_compressed += prev_meta["compressed_bytes"]
            continue

        print(f"  {Fore.MAGENTA}⚡ Modifications detected: {reason}{Style.RESET_ALL}")
        print(f"     Re-compressing & replacing {archive_name} on Google Drive …")
        modified_batches_count += 1

        if dry_run:
            print(f"  [Dry Run] Would compress {b['items']} -> {archive_name} and replace on Drive")
            strategy_batches.append({
                "batch_id": b["batch_id"],
                "archive_name": archive_name,
                "description": b["description"],
                "items": b["items"],
                "compressed_bytes": prev_meta.get("compressed_bytes", 0) if prev_meta else 0,
                "sha256": "dry-run-hash",
                "upload_timestamp": datetime.now(timezone.utc).isoformat(),
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
        print(f"  🔒 Calculating new SHA-256 checksum …")
        sha = sha256_file(local_archive)
        print(f"     New SHA-256: {Fore.CYAN}{sha}{Style.RESET_ALL}")

        # 3. Upload and replace on Google Drive
        print(f"  ☁ Uploading & replacing {archive_name} at {remote}:{drive_folder}/archives/ …")
        t_up0 = time.time()
        upload_file_rclone(local_archive, remote, f"{drive_folder}/archives")
        up_dur = time.time() - t_up0
        speed_mbps = (arch_size * 8 / (1024 * 1024)) / max(up_dur, 0.1)
        print(f"  ✓ Replaced on Drive in {up_dur:.1f}s | Speed: {speed_mbps:.1f} Mbps")

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
        "version": "2.1",
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
    print(f"  🎉 Sync complete! Modified batches replaced: {modified_batches_count}/{len(batches)}")
    print(f"  Total Backup Size: {format_bytes(total_compressed)}")
    print(f"{'═'*68}{Style.RESET_ALL}\n")

    if not dry_run and modified_batches_count > 0:
        print(f"{Fore.CYAN}Uploading updated restore strategy documents to {remote}:{drive_folder}/ …{Style.RESET_ALL}")
        upload_file_rclone(strategy_json_path, remote, drive_folder)
        upload_file_rclone(strategy_md_path, remote, drive_folder)
        print(f"{Fore.GREEN}✓ Updated restore_strategy.json and RESTORE_STRATEGY.md live on Google Drive!{Style.RESET_ALL}")
    elif modified_batches_count == 0:
        print(f"{Fore.GREEN}✓ All archives on Drive were already up to date.{Style.RESET_ALL}")

    print(f"\n{Fore.CYAN}Restore tool is ready to use:{Style.RESET_ALL}")
    print(f"  python3 gdrive_restore.py\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Drive Batch-Compressed Backup Tool v2.1")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help="rclone remote name")
    parser.add_argument("--folder", default=DEFAULT_FOLDER, help="Drive destination folder")
    parser.add_argument("--dry-run", action="store_true", help="Preview batches without uploading")
    parser.add_argument("--force", action="store_true", help="Force re-compress and replace all batches regardless of mtime")
    args = parser.parse_args()

    check_rclone()
    run_batch_backup(args.remote, args.folder, dry_run=args.dry_run, force=args.force)

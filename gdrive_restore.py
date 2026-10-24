#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║        Google Drive Restore Tool v2.0                                ║
║  Strategy-Aware Automated Restore from Google Drive to Original Path ║
╚══════════════════════════════════════════════════════════════════════╝

Features:
  - Automatically fetches `restore_strategy.json` from Google Drive
  - Downloads archives batch-by-batch
  - Validates SHA-256 checksums before extracting
  - Extracts directly to original folder structure
  - Deletes downloaded archives after extraction to preserve local disk space
  - Reconstructs symlinks (e.g. ~/m -> /Users/dhamo/claude/CMS/YBL/Mobility)
  - Backward compatible with raw rclone folder backups
"""

import os
import sys
import json
import time
import shutil
import hashlib
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, _):
            return ""
    Fore = Style = DummyColor()

RCLONE = shutil.which("rclone") or "/opt/homebrew/bin/rclone"
LOG_FILE = Path(__file__).parent / "restore.log"
STAGING_DIR = Path(__file__).parent / "restore_staging"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger(__name__)


def check_rclone():
    if not Path(RCLONE).exists() and not shutil.which("rclone"):
        print(f"{Fore.RED}✗ rclone not found.{Style.RESET_ALL}")
        print("  Install with:  brew install rclone")
        print("  Then run:      rclone config  (choose gdrive remote)")
        sys.exit(1)


def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024 * 4):
            h.update(chunk)
    return h.hexdigest()


def format_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


def fetch_strategy_doc(remote: str, drive_folder: str) -> dict | None:
    """Download and parse restore_strategy.json from Drive if available."""
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    local_strategy = STAGING_DIR / "restore_strategy.json"
    
    cmd = [
        RCLONE, "copyto",
        f"{remote}:{drive_folder}/restore_strategy.json",
        str(local_strategy),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and local_strategy.exists():
        try:
            with open(local_strategy, "r", encoding="utf-8") as f:
                strategy = json.load(f)
                return strategy
        except Exception as e:
            log.warning(f"Failed to parse downloaded strategy: {e}")
    return None


def list_backups(remote: str):
    """List available backup folders on Drive."""
    result = subprocess.run(
        [RCLONE, "lsd", f"{remote}:", "--max-depth", "1"],
        capture_output=True, text=True
    )
    folders = []
    for line in result.stdout.strip().splitlines():
        parts = line.strip().split()
        if parts:
            folders.append(parts[-1])
    return folders


def restore_with_strategy(
    strategy: dict,
    remote: str,
    drive_folder: str,
    dest: Path,
    dry_run: bool = False,
    selected_batch: int | None = None,
):
    print(f"\n{Fore.CYAN}{'═'*68}")
    print(f"  🔄  Google Drive Strategy-Based Restore Tool v2.0")
    print(f"{'═'*68}{Style.RESET_ALL}")
    print(f"  Backup Created : {strategy.get('created_at', 'Unknown')}")
    print(f"  Drive Remote   : {remote}:{drive_folder}")
    print(f"  Destination    : {dest}")
    print(f"  Total Batches  : {len(strategy.get('batches', []))}")
    print(f"  Total Size     : {format_bytes(strategy.get('total_compressed_bytes', 0))}")
    if dry_run:
        print(f"  {Fore.YELLOW}⚠  DRY RUN MODE — no files will be downloaded or extracted{Style.RESET_ALL}")
    print()

    dest.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    batches = strategy.get("batches", [])
    if selected_batch is not None:
        batches = [b for b in batches if b.get("batch_id") == selected_batch]
        if not batches:
            print(f"{Fore.RED}✗ Batch ID {selected_batch} not found in strategy.{Style.RESET_ALL}")
            return

    for idx, b in enumerate(batches, 1):
        archive_name = b["archive_name"]
        expected_sha = b.get("sha256")
        expected_size = b.get("compressed_bytes", 0)
        items = b.get("items", [])

        print(f"{Fore.YELLOW}{'─'*68}")
        print(f"  📦 Restoring Batch {b.get('batch_id', idx)}: {archive_name}")
        print(f"     Contents : {', '.join(items[:5])}")
        print(f"     Size     : {format_bytes(expected_size)}")
        print(f"{'─'*68}{Style.RESET_ALL}")

        if dry_run:
            print(f"  [Dry Run] Would download {archive_name}, verify SHA-256, and extract to {dest}")
            continue

        local_archive = STAGING_DIR / archive_name

        # 1. Download archive from Drive
        print(f"  ⬇  Downloading {archive_name} from Drive …")
        t0 = time.time()
        cmd_dl = [
            RCLONE, "copyto",
            f"{remote}:{drive_folder}/archives/{archive_name}",
            str(local_archive),
            "--drive-chunk-size", "64M",
            "-P",
        ]
        res_dl = subprocess.run(cmd_dl)
        if res_dl.returncode != 0 or not local_archive.exists():
            print(f"{Fore.RED}✗ Download failed for {archive_name}{Style.RESET_ALL}")
            log.error(f"Download failed for {archive_name}")
            sys.exit(1)
        
        dl_dur = time.time() - t0
        print(f"  ✓ Downloaded in {dl_dur:.1f}s")

        # 2. Checksum validation
        print(f"  🔒 Verifying SHA-256 checksum …")
        actual_sha = sha256_file(local_archive)
        if expected_sha and actual_sha != expected_sha:
            print(f"{Fore.RED}✗ Checksum mismatch for {archive_name}!{Style.RESET_ALL}")
            print(f"   Expected: {expected_sha}")
            print(f"   Actual:   {actual_sha}")
            log.error(f"Checksum mismatch for {archive_name}")
            sys.exit(1)
        print(f"  ✓ Checksum verified ({actual_sha[:16]}...)")

        # 3. Extraction
        print(f"  📂 Extracting into {dest} …")
        t_ex0 = time.time()
        cmd_ex = ["tar", "-xzf", str(local_archive), "-C", str(dest)]
        res_ex = subprocess.run(cmd_ex)
        if res_ex.returncode != 0:
            print(f"{Fore.RED}✗ Extraction failed for {archive_name}{Style.RESET_ALL}")
            log.error(f"Extraction failed for {archive_name}")
            sys.exit(1)
        ex_dur = time.time() - t_ex0
        print(f"  ✓ Extracted in {ex_dur:.1f}s")

        # 4. Cleanup downloaded archive to save disk space
        print(f"  🧹 Cleaning up downloaded archive to free disk space …")
        local_archive.unlink(missing_ok=True)
        print(f"  ✓ Local archive removed ({format_bytes(expected_size)} freed)")

    # 5. Recreate symlinks specified in strategy
    symlinks = strategy.get("symlinks_to_create", [])
    for sym in symlinks:
        link_path = Path(sym["link_path"])
        target_path = Path(sym.get("target_path", str(dest)))
        if not dry_run:
            try:
                if link_path.is_symlink() or link_path.exists():
                    link_path.unlink()
                link_path.parent.mkdir(parents=True, exist_ok=True)
                link_path.symlink_to(target_path)
                print(f"{Fore.GREEN}✓ Recreated symlink: {link_path} → {target_path}{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}⚠ Could not recreate symlink {link_path}: {e}{Style.RESET_ALL}")

    print(f"\n{Fore.GREEN}{'═'*68}")
    print(f"  ✅  Restore completed successfully!")
    print(f"  📂  Restored files location: {dest}")
    print(f"  🔗  Active symlink         : /Users/dhamo/m")
    print(f"  📋  Restore log            : {LOG_FILE}")
    print(f"{'═'*68}{Style.RESET_ALL}\n")


def restore_raw_folder(remote: str, drive_folder: str, dest: Path, workers: int, dry_run: bool):
    """Fallback restore for raw folder backups."""
    print(f"\n{Fore.YELLOW}ℹ  No restore_strategy.json found; falling back to direct rclone folder mirror.{Style.RESET_ALL}")
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        RCLONE, "copy",
        f"{remote}:{drive_folder}",
        str(dest),
        "--transfers", str(workers),
        "--drive-chunk-size", "32M",
        "--checkers", "16",
        "-P",
    ]
    if dry_run:
        cmd.append("--dry-run")
    subprocess.run(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Drive Restore Tool")
    parser.add_argument("--remote", default="gdrive", help="rclone remote name")
    parser.add_argument("--drive-folder", default=None, help="Drive folder to restore from (default: auto-detect)")
    parser.add_argument("--dest", default=None, help="Local restore path (default from strategy)")
    parser.add_argument("--batch", type=int, default=None, help="Restore only a single specific batch ID")
    parser.add_argument("--workers", type=int, default=12, help="Worker threads for fallback mode")
    parser.add_argument("--dry-run", action="store_true", help="Preview restore without downloading")
    parser.add_argument("--list", action="store_true", help="List backup folders on Drive")
    args = parser.parse_args()

    check_rclone()

    if args.list:
        print(f"\n{Fore.CYAN}Available backup folders on {args.remote}:{Style.RESET_ALL}")
        for f in list_backups(args.remote):
            print(f"  • {f}")
        print()
        sys.exit(0)

    drive_folder = args.drive_folder
    if not drive_folder:
        backups = list_backups(args.remote)
        # Check for m-backup-batches first, then m-backup
        if "m-backup-batches" in backups:
            drive_folder = "m-backup-batches"
        else:
            candidates = [f for f in backups if "backup" in f]
            drive_folder = sorted(candidates)[-1] if candidates else "m-backup-batches"

    print(f"{Fore.CYAN}ℹ  Selected Drive backup folder: {drive_folder}{Style.RESET_ALL}")

    strategy = fetch_strategy_doc(args.remote, drive_folder)
    if strategy:
        dest_path = Path(args.dest) if args.dest else Path(strategy.get("restore_destination_default", "/Users/dhamo/claude/CMS/YBL/Mobility"))
        restore_with_strategy(
            strategy=strategy,
            remote=args.remote,
            drive_folder=drive_folder,
            dest=dest_path,
            dry_run=args.dry_run,
            selected_batch=args.batch,
        )
    else:
        dest_path = Path(args.dest) if args.dest else Path("/Users/dhamo/claude/CMS/YBL/Mobility")
        restore_raw_folder(args.remote, drive_folder, dest_path, args.workers, args.dry_run)

#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║        Google Drive Restore Tool v1.0                ║
║  Restore files from Google Drive to original path    ║
╚══════════════════════════════════════════════════════╝

Restores /Users/<user>/m from Google Drive back to its
original path after a Mac service, wipe, or migration.

Features:
  - Mirrors Drive folder structure exactly to local path
  - 12 parallel download streams (tuned for 300 Mbps)
  - Skip existing files by default (safe re-run)
  - Dry-run mode to preview without downloading
  - Detailed progress + log file
  - Conflict modes: skip | overwrite | backup
"""

import subprocess
import sys
import os
import argparse
import shutil
import logging
from pathlib import Path
from datetime import datetime
from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

RCLONE = shutil.which("rclone") or "/opt/homebrew/bin/rclone"
LOG_FILE = Path(__file__).parent / "restore.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger(__name__)


def check_rclone():
    if not Path(RCLONE).exists():
        print(f"{Fore.RED}✗  rclone not found.{Style.RESET_ALL}")
        print("  Install with:  brew install rclone")
        print("  Then run:      rclone config  (choose gdrive remote)")
        sys.exit(1)


def check_remote(remote: str):
    """Verify the rclone remote + Drive folder exists."""
    result = subprocess.run(
        [RCLONE, "lsd", f"{remote}:", "--max-depth", "1"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"{Fore.RED}✗  Cannot access remote '{remote}'.{Style.RESET_ALL}")
        print("  Run:  rclone config  — to set up Google Drive access")
        sys.exit(1)


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


def run_restore(
    remote: str,
    drive_folder: str,
    dest: Path,
    workers: int,
    dry_run: bool,
    conflict: str,
):
    print(f"\n{Fore.CYAN}{'═'*58}")
    print(f"  🔄  Google Drive Restore Tool  v1.0")
    print(f"{'═'*58}{Style.RESET_ALL}")
    print(f"  Source  : {remote}:{drive_folder}")
    print(f"  Dest    : {dest}")
    print(f"  Workers : {workers} parallel streams")
    print(f"  Conflict: {conflict}")
    if dry_run:
        print(f"  {Fore.YELLOW}⚠  DRY RUN — no files will be downloaded{Style.RESET_ALL}")
    print()

    # Ensure destination exists
    dest.mkdir(parents=True, exist_ok=True)

    cmd = [
        RCLONE, "copy",
        f"{remote}:{drive_folder}",
        str(dest),
        "--transfers", str(workers),
        "--drive-chunk-size", "32M",
        "--checkers", "16",
        "--log-level", "INFO",
        "--log-file", str(LOG_FILE),
        "--stats", "10s",
        "--stats-log-level", "NOTICE",
        "-P",
    ]

    if dry_run:
        cmd.append("--dry-run")

    # Conflict handling
    if conflict == "skip":
        cmd += ["--ignore-existing"]
    elif conflict == "backup":
        cmd += ["--backup-dir", str(dest.parent / f"restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")]

    print(f"{Fore.YELLOW}● Starting restore …{Style.RESET_ALL}")
    log.info(f"Restore started: {remote}:{drive_folder} → {dest}")

    try:
        result = subprocess.run(cmd)
        if result.returncode == 0:
            print(f"\n{Fore.GREEN}{'═'*58}")
            print(f"  ✅  Restore complete!")
            if dry_run:
                print(f"  ℹ  Dry run — re-run without --dry-run to actually download")
            print(f"  📂  Restored to: {dest}")
            print(f"  📋  Log: {LOG_FILE}")
            print(f"{'═'*58}{Style.RESET_ALL}\n")
            log.info("Restore completed successfully")
        else:
            print(f"\n{Fore.RED}✗  Restore finished with errors. Check log:{Style.RESET_ALL}")
            print(f"   {LOG_FILE}")
            log.error(f"Restore finished with exit code {result.returncode}")
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠  Restore interrupted. Re-run to resume.{Style.RESET_ALL}")


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Restore files from Google Drive to original local path",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--remote", default="gdrive",
                        help="rclone remote name (run 'rclone config' to set up)")
    parser.add_argument("--drive-folder", default=None,
                        help="Drive folder to restore from (auto-detects latest m-backup if not set)")
    parser.add_argument("--dest", default="/Users/dhamo/m",
                        help="Local destination path to restore files to")
    parser.add_argument("--workers", type=int, default=12,
                        help="Parallel download streams (12 = tuned for 300 Mbps)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be restored without downloading")
    parser.add_argument("--conflict", choices=["skip", "overwrite", "backup"],
                        default="skip",
                        help="How to handle files that already exist locally:\n"
                             "  skip      = keep existing local file (default, safe)\n"
                             "  overwrite = replace local file with Drive version\n"
                             "  backup    = move existing local file to a backup dir first")
    parser.add_argument("--list", action="store_true",
                        help="List available backup folders on Drive and exit")

    args = parser.parse_args()

    check_rclone()
    check_remote(args.remote)

    if args.list:
        print(f"\n{Fore.CYAN}Available backup folders on {args.remote}:{Style.RESET_ALL}")
        for f in list_backups(args.remote):
            print(f"  • {f}")
        print()
        sys.exit(0)

    # Auto-detect latest backup folder
    drive_folder = args.drive_folder
    if not drive_folder:
        backups = [f for f in list_backups(args.remote) if f.startswith("m-backup")]
        if not backups:
            print(f"{Fore.RED}✗  No m-backup* folders found on Drive.{Style.RESET_ALL}")
            print(f"  Run with --list to see all available folders.")
            sys.exit(1)
        drive_folder = sorted(backups)[-1]  # Latest by name
        print(f"{Fore.CYAN}ℹ  Auto-selected backup: {drive_folder}{Style.RESET_ALL}")

    run_restore(
        remote=args.remote,
        drive_folder=drive_folder,
        dest=Path(args.dest),
        workers=args.workers,
        dry_run=args.dry_run,
        conflict=args.conflict,
    )

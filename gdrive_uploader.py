#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║        Google Drive Parallel Uploader v2.0           ║
║  Tuned for 300 Mbps — 12 workers, 32 MB chunks       ║
╚══════════════════════════════════════════════════════╝

Features:
  - Parallel uploads (configurable worker threads)
  - Resumable uploads (survives network drops)
  - Progress bar per file + overall progress
  - Upload state saved to disk (restart-safe)
  - Skips already-uploaded files automatically
  - Rate-limit aware with exponential back-off
  - Mirrors full folder structure on Drive
"""

import os
import sys
import json
import time
import mimetypes
import threading
import argparse
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from colorama import Fore, Style, init as colorama_init
from tqdm import tqdm

import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request as AuthRequest

# ─── Configuration ──────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_FILE = Path(__file__).parent / "token.json"
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
STATE_FILE = Path(__file__).parent / "upload_state.json"
LOG_FILE = Path(__file__).parent / "upload.log"

DEFAULT_WORKERS = 12            # Parallel upload threads (tuned for 300 Mbps)
CHUNK_SIZE = 32 * 1024 * 1024  # 32 MB chunks — fewer round-trips on fast lines
MAX_RETRIES = 7                # Max retries per file
RETRY_BASE_DELAY = 2           # Seconds (exponential back-off base)
RATE_LIMIT_SLEEP = 30          # Seconds to wait on 429/403 rate errors

# ADC scopes needed
ADC_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Files/directories to skip
SKIP_NAMES = {".DS_Store", "__pycache__", ".git", "node_modules", "gdrive_upload"}

# ─── Logging setup ──────────────────────────────────────────────────────────
colorama_init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger(__name__)

# Thread-local Drive service (one connection per thread)
_thread_local = threading.local()
_creds_lock = threading.Lock()
_creds_cache = None


# ─── Auth (Application Default Credentials via gcloud) ─────────────────────
def get_credentials():
    """Use gcloud Application Default Credentials — no credentials.json needed."""
    global _creds_cache
    with _creds_lock:
        if _creds_cache and _creds_cache.valid:
            return _creds_cache
        try:
            creds, _ = google.auth.default(scopes=ADC_SCOPES)
        except google.auth.exceptions.DefaultCredentialsError:
            print(f"\n{Fore.RED}✗  Not authenticated with gcloud!{Style.RESET_ALL}")
            print("  Run this command first:")
            print(f"  {Fore.CYAN}/opt/homebrew/bin/gcloud auth application-default login "
                  f"--scopes=https://www.googleapis.com/auth/drive{Style.RESET_ALL}")
            sys.exit(1)
        # Refresh if needed
        if hasattr(creds, 'expired') and creds.expired:
            creds.refresh(AuthRequest())
        _creds_cache = creds
        return creds


def get_drive_service():
    """Return a Drive service instance; one per thread."""
    if not hasattr(_thread_local, "service"):
        _thread_local.service = build(
            "drive", "v3",
            credentials=get_credentials(),
            cache_discovery=False,
        )
    return _thread_local.service


# ─── State management (resume support) ──────────────────────────────────────
class UploadState:
    def __init__(self, state_file):
        self.path = state_file
        self._lock = threading.Lock()
        self.data = {"uploaded": {}, "folder_map": {}, "started_at": str(datetime.now())}
        if state_file.exists():
            try:
                self.data = json.loads(state_file.read_text())
                count = len(self.data.get("uploaded", {}))
                if count:
                    print(f"{Fore.CYAN}↩  Resuming — {count} files already uploaded{Style.RESET_ALL}")
            except Exception:
                pass

    def is_uploaded(self, local_path):
        return local_path in self.data["uploaded"]

    def mark_uploaded(self, local_path, drive_id):
        with self._lock:
            self.data["uploaded"][local_path] = drive_id
            self._save()

    def set_folder(self, key, drive_id):
        with self._lock:
            self.data["folder_map"][key] = drive_id
            self._save()

    def get_folder(self, key):
        return self.data["folder_map"].get(key)

    def _save(self):
        self.path.write_text(json.dumps(self.data, indent=2))


# ─── Drive folder helpers ────────────────────────────────────────────────────
_folder_lock = threading.Lock()


def get_or_create_folder(service, name, parent_id):
    """Find or create a Drive folder by name under parent_id."""
    # Escape single quotes in name
    safe_name = name.replace("'", "\\'")
    query = (
        f"name='{safe_name}' and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents and trashed=false"
    )
    result = service.files().list(q=query, fields="files(id,name)").execute()
    files = result.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def ensure_drive_path(service, relative_parts, root_id, state):
    """Walk/create the full folder path on Drive; return leaf folder ID."""
    current_id = root_id
    cumulative = ""
    for part in relative_parts:
        cumulative = os.path.join(cumulative, part)
        cached = state.get_folder(cumulative)
        if cached:
            current_id = cached
            continue
        with _folder_lock:
            cached = state.get_folder(cumulative)
            if cached:
                current_id = cached
                continue
            current_id = get_or_create_folder(service, part, current_id)
            state.set_folder(cumulative, current_id)
    return current_id


# ─── File upload (with retry + resumable) ───────────────────────────────────
def upload_file(local_path, drive_folder_id, state, pbar_global):
    """Upload a single file with exponential back-off retries."""
    service = get_drive_service()
    file_size = local_path.stat().st_size
    mime_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    metadata = {"name": local_path.name, "parents": [drive_folder_id]}

    for attempt in range(MAX_RETRIES):
        try:
            media = MediaFileUpload(
                str(local_path),
                mimetype=mime_type,
                chunksize=CHUNK_SIZE,
                resumable=True,
            )
            request = service.files().create(body=metadata, media_body=media, fields="id")

            uploaded_bytes = 0
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status and pbar_global:
                    chunk = status.resumable_progress - uploaded_bytes
                    uploaded_bytes = status.resumable_progress
                    pbar_global.update(chunk)

            # Account for final chunk
            remaining = file_size - uploaded_bytes
            if remaining > 0 and pbar_global:
                pbar_global.update(remaining)

            file_id = response.get("id")
            state.mark_uploaded(str(local_path), file_id)
            log.info(f"UPLOADED  {local_path}  id={file_id}")
            return True

        except HttpError as e:
            code = e.resp.status
            if code in (429, 403):
                sleep = RATE_LIMIT_SLEEP * (attempt + 1)
                log.warning(f"Rate limited ({code}). Sleeping {sleep}s [{local_path.name}]")
                time.sleep(sleep)
            elif code in (500, 502, 503, 504):
                delay = RETRY_BASE_DELAY ** attempt
                log.warning(f"Server error ({code}). Retry in {delay}s [{local_path.name}]")
                time.sleep(delay)
            else:
                log.error(f"HTTP {code} uploading {local_path}: {e}")
                return False
        except Exception as e:
            delay = RETRY_BASE_DELAY ** attempt
            log.warning(f"Attempt {attempt+1}/{MAX_RETRIES} failed for {local_path.name}: {e}")
            time.sleep(delay)

    log.error(f"FAILED after {MAX_RETRIES} attempts: {local_path}")
    return False


# ─── Directory walker ────────────────────────────────────────────────────────
def collect_files(source_dir):
    """Recursively collect all uploadable files."""
    files = []
    for root, dirs, filenames in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_NAMES and not d.startswith("._")]
        for fname in filenames:
            if fname in SKIP_NAMES or fname.startswith("._"):
                continue
            files.append(Path(root) / fname)
    return files


# ─── Main upload orchestrator ────────────────────────────────────────────────
def run_upload(source_dir, drive_root_name, workers):
    print(f"\n{Fore.CYAN}{'═'*58}")
    print(f"  🚀  Google Drive Parallel Uploader  v1.0")
    print(f"{'═'*58}{Style.RESET_ALL}")
    print(f"  Source   : {source_dir}")
    print(f"  Target   : My Drive / {drive_root_name}")
    print(f"  Workers  : {workers} parallel threads")
    print(f"  Chunks   : {CHUNK_SIZE // (1024*1024)} MB each (resumable)")
    print()

    # Auth
    print(f"{Fore.YELLOW}● Authenticating with Google …{Style.RESET_ALL}", end=" ", flush=True)
    service = get_drive_service()
    print(f"{Fore.GREEN}✔{Style.RESET_ALL}")

    # State
    state = UploadState(STATE_FILE)

    # Root Drive folder
    print(f"{Fore.YELLOW}● Setting up Drive root folder …{Style.RESET_ALL}", end=" ", flush=True)
    root_id = state.get_folder("__root__")
    if not root_id:
        root_id = get_or_create_folder(service, drive_root_name, "root")
        state.set_folder("__root__", root_id)
    print(f"{Fore.GREEN}✔  id={root_id}{Style.RESET_ALL}")

    # Collect files
    print(f"{Fore.YELLOW}● Scanning source directory …{Style.RESET_ALL}", end=" ", flush=True)
    all_files = collect_files(source_dir)
    print(f"{Fore.GREEN}✔  {len(all_files)} files found{Style.RESET_ALL}")

    # Filter already uploaded
    pending = [f for f in all_files if not state.is_uploaded(str(f))]
    already_done = len(all_files) - len(pending)
    if already_done:
        print(f"  {Fore.CYAN}↩  {already_done} already uploaded — skipping{Style.RESET_ALL}")

    if not pending:
        print(f"\n{Fore.GREEN}🎉  All files already uploaded!{Style.RESET_ALL}\n")
        return

    total_bytes = sum(f.stat().st_size for f in pending)
    total_gb = total_bytes / (1024 ** 3)
    print(f"  {Fore.YELLOW}To upload: {total_gb:.2f} GB across {len(pending)} files{Style.RESET_ALL}")

    est_mins = total_gb * 1024 / (5 * workers)  # ~5 MB/s per thread estimate
    print(f"  ⏱  Estimated time: ~{est_mins:.0f} min at ~{5*workers} MB/s")
    print()

    # ── Upload loop ──────────────────────────────────────────────────────────
    failed = []
    uploaded_count = 0
    lock = threading.Lock()

    with tqdm(
        total=total_bytes,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc="Overall",
        colour="green",
        dynamic_ncols=True,
    ) as pbar_global:

        def process_file(local_path):
            nonlocal uploaded_count
            rel = local_path.relative_to(source_dir)
            parts = list(rel.parts[:-1])
            try:
                folder_id = ensure_drive_path(service, parts, root_id, state)
            except Exception as e:
                log.error(f"Folder creation failed for {local_path}: {e}")
                with lock:
                    failed.append(local_path)
                return local_path, False

            success = upload_file(local_path, folder_id, state, pbar_global)
            with lock:
                if success:
                    uploaded_count += 1
                else:
                    failed.append(local_path)
            return local_path, success

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_file, f): f for f in pending}
            try:
                for future in as_completed(futures):
                    path, ok = future.result()
                    icon = f"{Fore.GREEN}✔{Style.RESET_ALL}" if ok else f"{Fore.RED}✗{Style.RESET_ALL}"
                    pbar_global.write(f"  {icon}  {path.name}")
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}⚠  Interrupted — progress saved. Re-run to resume.{Style.RESET_ALL}")
                executor.shutdown(wait=False, cancel_futures=True)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{Fore.CYAN}{'═'*58}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✔  Uploaded : {uploaded_count} files{Style.RESET_ALL}")
    if failed:
        print(f"  {Fore.RED}✗  Failed   : {len(failed)} files{Style.RESET_ALL}")
        for f in failed:
            print(f"      • {f}")
    print(f"\n  📂  Drive: https://drive.google.com/drive/folders/{root_id}")
    print(f"  📋  Log  : {LOG_FILE}")
    print(f"{Fore.CYAN}{'═'*58}{Style.RESET_ALL}\n")


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="High-speed parallel Google Drive uploader",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", default="/Users/dhamo/m",
                        help="Local directory to upload")
    parser.add_argument("--drive-folder", default="m-backup",
                        help="Root folder name to create on Google Drive")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="Parallel upload threads (12 = tuned for 300 Mbps)")
    parser.add_argument("--reset", action="store_true",
                        help="Ignore saved state and re-upload everything")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print(f"{Fore.YELLOW}⚠  State reset — will re-upload all files{Style.RESET_ALL}")

    source = Path(args.source)
    if not source.is_dir():
        print(f"{Fore.RED}✗  Source directory not found: {source}{Style.RESET_ALL}")
        sys.exit(1)

    run_upload(source, args.drive_folder, args.workers)

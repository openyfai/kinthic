import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from silex.utils.config import KINTHIC_BACKUPS, KINTHIC_HOME, SILEX_DB, SILEX_VECTOR_DB

log = logging.getLogger("kinthic.backup")

# How long to wait to acquire the fence lock before giving up and falling
# back to a best-effort backup without it.
_FENCE_LOCK_TIMEOUT_SECONDS = 30.0

_REQUIRED_DB_ARCNAME = "storage/silex.db"
_SKIP_RESTORE_NAMES = {"secrets.json"}
_SKIP_RESTORE_PARTS = {"__pycache__"}
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def _snapshot_sqlite_db(src_path: Path, dest_path: Path) -> None:
    """Copy a live SQLite database to dest_path using the online-backup API.

    This produces a single, self-contained, transactionally-consistent file
    (folding in any outstanding WAL content) that is safe to copy even while
    the source is open elsewhere. A raw file copy of the .db/-wal/-shm triple
    is not: a copy racing an in-flight checkpoint or write can capture a torn,
    inconsistent snapshot.
    """
    src_conn = sqlite3.connect(str(src_path), timeout=_FENCE_LOCK_TIMEOUT_SECONDS)
    try:
        dest_conn = sqlite3.connect(str(dest_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def export_backup(output_filename: str) -> None:
    """
    Exports a crash-consistent snapshot of the ~/.kinthic directory to a zip file.
    Specifically excludes secrets.json to prevent credential leakage.

    The SQLite memory database and the ChromaDB vector store are dual-written
    (SQLite commits first, then the Chroma upsert — see MemoryStore.add), so a
    naive concurrent file copy of both stores can capture them at different
    points in time and silently reintroduce the split-brain drift that
    reconcile_vector_index() exists to repair. To avoid that, this backup:

      1. Acquires SQLite's own write lock (BEGIN IMMEDIATE) directly on the
         live database file. This is a real OS/file-level lock — it also
         blocks a separately-running `kinthic daemon` process from committing
         any further writes for the duration of the backup, not just writers
         in this process.
      2. While that lock is held, no *new* Chroma writes can land either,
         because the write path always commits SQLite before touching Chroma
         (the a3-atomic invariant) — so holding the SQLite writer lock
         transitively fences the vector store too, giving both stores a
         consistent snapshot fence without needing a separate Chroma-side lock.
      3. Copies the SQLite DB via the online-backup API (safe for a live,
         WAL-mode database) and copies the Chroma persist directory verbatim
         while still fenced.
      4. Releases the lock and zips everything else from ~/.kinthic normally.
    """
    kinthic_dir = Path(KINTHIC_HOME)
    out_path = Path(output_filename).absolute()

    if not kinthic_dir.exists():
        print(f"Error: Kinthic directory {kinthic_dir} does not exist.")
        return

    excluded_files = {"secrets.json"}
    # These raw store paths are handled specially via the fenced snapshot
    # below instead of a plain copy, so skip them in the generic file walk.
    excluded_paths = {
        Path(str(SILEX_DB)).resolve(),
        Path(str(SILEX_DB) + "-wal").resolve(),
        Path(str(SILEX_DB) + "-shm").resolve(),
        Path(str(SILEX_DB) + "-journal").resolve(),
    }
    vector_db_dir = SILEX_VECTOR_DB.resolve()

    print(f"Starting crash-consistent backup of {kinthic_dir} to {out_path}...")

    with tempfile.TemporaryDirectory(prefix="kinthic-backup-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        snapshot_db = tmp_path / "silex.db"
        snapshot_vector_dir = tmp_path / "vector_db"

        fence_conn = None
        if SILEX_DB.exists():
            try:
                fence_conn = sqlite3.connect(str(SILEX_DB), timeout=_FENCE_LOCK_TIMEOUT_SECONDS)
                fence_conn.execute("BEGIN IMMEDIATE")
                print("Acquired write-lock fence on the memory database...")
            except sqlite3.OperationalError as e:
                log.warning(f"Could not acquire backup fence lock, proceeding without it: {e}")
                if fence_conn is not None:
                    fence_conn.close()
                fence_conn = None

        try:
            if SILEX_DB.exists():
                _snapshot_sqlite_db(SILEX_DB, snapshot_db)
            if vector_db_dir.exists():
                shutil.copytree(vector_db_dir, snapshot_vector_dir)
        finally:
            if fence_conn is not None:
                # No writes were made on this connection; just release the lock.
                fence_conn.rollback()
                fence_conn.close()
                print("Released backup fence lock.")

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            if snapshot_db.exists():
                zipf.write(snapshot_db, str(Path("storage") / "silex.db"))
            if snapshot_vector_dir.exists():
                for file_path in snapshot_vector_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = Path("storage") / "vector_db" / file_path.relative_to(snapshot_vector_dir)
                        zipf.write(file_path, str(arcname))

            for root, dirs, files in os.walk(kinthic_dir):
                # Skip python cache dirs
                if "__pycache__" in dirs:
                    dirs.remove("__pycache__")

                root_path = Path(root).resolve()
                if root_path == vector_db_dir:
                    # Already captured via the fenced snapshot above.
                    dirs[:] = []
                    continue

                for file in files:
                    if file in excluded_files:
                        print(f"Skipping {file} (security exclusion)")
                        continue

                    file_path = Path(root) / file
                    if file_path.resolve() in excluded_paths:
                        continue
                    # Skip the output file itself if it's being written into the kinthic dir
                    if file_path.absolute() == out_path:
                        continue

                    arcname = file_path.relative_to(kinthic_dir)
                    zipf.write(file_path, arcname)

    print(f"Backup successfully exported to {out_path}")


def _normalize_arcname(name: str) -> str:
    return name.replace("\\", "/")


def _is_safe_arcname(name: str) -> bool:
    normalized = _normalize_arcname(name)
    if not normalized or normalized.startswith("/"):
        return False
    parts = PurePosixPath(normalized).parts
    return ".." not in parts


def _should_skip_restore(arcname: str) -> bool:
    normalized = _normalize_arcname(arcname)
    parts = PurePosixPath(normalized).parts
    if any(part in _SKIP_RESTORE_PARTS for part in parts):
        return True
    if parts and parts[-1] in _SKIP_RESTORE_NAMES:
        return True
    if normalized.endswith(_SQLITE_SIDECAR_SUFFIXES):
        return True
    return False


def daemon_is_running() -> bool:
    """Return True when the Kinthic daemon lock exists and its PID is alive."""
    from silex.utils.config import KINTHIC_DAEMON_LOCK

    if not KINTHIC_DAEMON_LOCK.exists():
        return False
    try:
        lock_data = json.loads(KINTHIC_DAEMON_LOCK.read_text(encoding="utf-8").strip())
        pid = lock_data.get("pid")
        if not pid:
            return False
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def inspect_backup(archive_path: str | Path) -> dict:
    """Validate a backup zip and return a restore preview summary."""
    path = Path(archive_path).expanduser()
    summary: dict = {
        "archive": str(path.resolve()),
        "valid": False,
        "file_count": 0,
        "has_memory_db": False,
        "has_vector_db": False,
        "skipped_entries": [],
        "warnings": [],
        "errors": [],
        "sample_files": [],
    }

    if not path.exists():
        summary["errors"].append(f"Archive not found: {path}")
        return summary
    if not zipfile.is_zipfile(path):
        summary["errors"].append(f"Not a zip archive: {path}")
        return summary

    restore_files: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as zipf:
            for info in zipf.infolist():
                if info.is_dir():
                    continue
                arcname = _normalize_arcname(info.filename)
                if not _is_safe_arcname(arcname):
                    summary["errors"].append(f"Unsafe archive path: {arcname}")
                    continue
                summary["file_count"] += 1
                if arcname == _REQUIRED_DB_ARCNAME:
                    summary["has_memory_db"] = True
                if arcname.startswith("storage/vector_db/"):
                    summary["has_vector_db"] = True
                if _should_skip_restore(arcname):
                    summary["skipped_entries"].append(arcname)
                    continue
                restore_files.append(arcname)
    except zipfile.BadZipFile as exc:
        summary["errors"].append(f"Corrupt zip archive: {exc}")
        return summary

    if not summary["has_memory_db"]:
        summary["errors"].append(f"Missing required entry: {_REQUIRED_DB_ARCNAME}")
    if not summary["has_vector_db"]:
        summary["warnings"].append(
            "No storage/vector_db/ in archive — semantic recall may be degraded until reconciliation."
        )

    summary["restore_file_count"] = len(restore_files)
    summary["sample_files"] = restore_files[:12]
    summary["valid"] = not summary["errors"]
    return summary


def _remove_sqlite_sidecars(db_path: Path) -> None:
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def restore_backup(
    archive_path: str | Path,
    *,
    apply: bool = False,
    pre_backup: bool = True,
) -> dict:
    """Restore ~/.kinthic from a backup zip produced by export_backup."""
    path = Path(archive_path).expanduser()
    summary = inspect_backup(path)
    summary["applied"] = False
    summary["pre_backup_path"] = None
    summary["restored_files"] = []
    summary["restored_count"] = 0

    if not summary["valid"]:
        return summary

    if daemon_is_running():
        summary["errors"].append(
            "Kinthic daemon is running. Stop it first with: kinthic stop"
        )
        summary["valid"] = False
        return summary

    kinthic_dir = Path(KINTHIC_HOME)
    kinthic_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path, "r") as zipf:
        restore_entries = []
        for info in zipf.infolist():
            if info.is_dir():
                continue
            arcname = _normalize_arcname(info.filename)
            if not _is_safe_arcname(arcname) or _should_skip_restore(arcname):
                continue
            restore_entries.append((arcname, info))

        if not apply:
            summary["restore_file_count"] = len(restore_entries)
            summary["sample_files"] = [name for name, _ in restore_entries[:12]]
            return summary

        if pre_backup:
            KINTHIC_BACKUPS.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            pre_path = KINTHIC_BACKUPS / f"pre-restore-{stamp}.zip"
            print(f"Creating pre-restore safety backup at {pre_path}...")
            export_backup(str(pre_path))
            summary["pre_backup_path"] = str(pre_path.resolve())

        with tempfile.TemporaryDirectory(prefix="kinthic-restore-") as tmp_dir:
            tmp_path = Path(tmp_dir)

            for arcname, info in restore_entries:
                rel = PurePosixPath(arcname)
                extracted = tmp_path.joinpath(*rel.parts)
                extracted.parent.mkdir(parents=True, exist_ok=True)
                with zipf.open(info) as src, open(extracted, "wb") as dest:
                    shutil.copyfileobj(src, dest)

            # Replace storage/vector_db as a tree when present in the archive.
            extracted_vector = tmp_path / "storage" / "vector_db"
            if extracted_vector.exists():
                _copy_tree(extracted_vector, SILEX_VECTOR_DB)

            for arcname, _info in restore_entries:
                rel = PurePosixPath(arcname)
                if len(rel.parts) >= 2 and rel.parts[0] == "storage" and rel.parts[1] == "vector_db":
                    continue

                src = tmp_path.joinpath(*rel.parts)
                if not src.is_file():
                    continue
                dest = kinthic_dir.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest.unlink()
                shutil.copy2(src, dest)
                summary["restored_files"].append(arcname)
                summary["restored_count"] += 1

            if (tmp_path / "storage" / "silex.db").exists():
                _remove_sqlite_sidecars(SILEX_DB)

    summary["applied"] = True
    return summary


def print_restore_summary(summary: dict, *, apply: bool) -> None:
    """Human-readable restore preview or result."""
    if summary.get("errors"):
        print("Restore failed:")
        for err in summary["errors"]:
            print(f"  - {err}")
        return

    mode = "APPLY" if apply else "DRY RUN"
    print(f"Restore plan ({mode})")
    print(f"  Archive: {summary.get('archive')}")
    print(f"  Files in archive: {summary.get('file_count', 0)}")
    print(f"  Files to restore: {summary.get('restore_file_count', 0)}")
    if summary.get("skipped_entries"):
        print(f"  Skipped (security/cache): {len(summary['skipped_entries'])}")
    for warning in summary.get("warnings", []):
        print(f"  Warning: {warning}")
    if summary.get("sample_files"):
        print("  Sample paths:")
        for sample in summary["sample_files"]:
            print(f"    - {sample}")

    if apply:
        if summary.get("pre_backup_path"):
            print(f"  Pre-restore backup: {summary['pre_backup_path']}")
        print(f"  Restored files: {summary.get('restored_count', 0)}")
        print("Restore complete. Start the daemon with: kinthic start")
    else:
        print("No changes made. Re-run with --apply to execute.")

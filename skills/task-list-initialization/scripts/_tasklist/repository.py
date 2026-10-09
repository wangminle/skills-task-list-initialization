"""Atomic, crash-safe file writes for task-list maintenance commands.

REQ-13: every file mutation must be atomic and recoverable. A plain ``path.write_text``
overwrites the destination in place — if the process is interrupted mid-write (signal,
disk full, OS error) the file is left truncated or empty. This module replaces all
``write_text`` call sites in the package so that:

- A single-file write goes through a same-directory temp file → flush → fsync →
  ``os.replace`` (atomic rename on POSIX). On any failure the temp is removed and the
  target's bytes are untouched.
- A multi-file operation (e.g. ``archive`` writes the archive file then the main file,
  ``install-maintenance`` writes agent file + hook script + settings.json) goes through
  ``commit_all``: all content is generated up front, each file is committed via
  ``atomic_write`` in order, and if any single commit fails the already-committed files
  are restored from in-memory backups — so the operation either fully takes effect or
  leaves the project exactly as it was, never half-installed.
"""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
import time
from pathlib import Path

__all__ = [
    "atomic_write",
    "backup",
    "commit_all",
    "file_lock",
    "LockCreateError",
    "LockTimeout",
]


class LockTimeout(TimeoutError):
    """Raised when the task-list write lock is not acquired within the timeout.

    Carries the lock path and the waited seconds so the CLI layer can render a
    localized message without re-deriving them.
    """

    def __init__(self, lock_path: Path, waited: float):
        super().__init__(f"timed out acquiring {lock_path}")
        self.lock_path = lock_path
        self.waited = waited


class LockCreateError(OSError):
    """Raised when the lock sidecar cannot be created or opened (BUG-099).

    Wraps the underlying OSError raised by the sidecar's mkdir/open (read-only
    directory, path component is a file, ...) so the CLI can render a localized
    message naming the LEDGER path instead of leaking a raw traceback. It is a
    distinct type on purpose: a plain ``except OSError`` around the whole lock
    scope would also swallow ordinary I/O errors from the guarded command itself.
    """

    def __init__(self, lock_path: Path, target: Path, reason: OSError):
        super().__init__(f"cannot create lock {lock_path}: {reason}")
        self.lock_path = lock_path
        self.target = target
        self.reason = reason


def _lock_fd_once(fd: int) -> bool:
    """One non-blocking acquire attempt. True on success, False when held elsewhere."""
    if os.name == "nt":
        import msvcrt

        try:
            # Lock one byte at the start of the file; LK_NBLCK returns immediately.
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_fd(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextlib.contextmanager
def file_lock(path: Path, timeout: float = 10.0):
    """Cross-process advisory lock guarding one task-list's read-modify-write cycle.

    Two sessions running ``add`` on the same file otherwise race: both read, both
    compute the same next ID, both write — duplicate IDs that check only finds after
    the fact. All mutating commands hold this lock from first read to final write, so
    the second session waits (or times out) instead of interleaving.

    The lock lives in a sidecar ``<name>.lock`` file and is an OS-level lock
    (flock / msvcrt), so it is released automatically if the holder crashes — no
    stale-lock cleanup. The sidecar file itself is never deleted (harmless, and
    deleting it would reintroduce a race). Raises LockTimeout after *timeout* seconds.
    """
    lock_path = path.with_name(path.name + ".lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        raise LockCreateError(lock_path, path, exc) from exc
    try:
        deadline = time.monotonic() + timeout
        while True:
            if _lock_fd_once(fd):
                break
            if time.monotonic() >= deadline:
                raise LockTimeout(lock_path, timeout)
            time.sleep(0.1)
        try:
            yield
        finally:
            _unlock_fd(fd)
    finally:
        os.close(fd)



def atomic_write(path: Path, text: str) -> None:
    """Atomically write *text* to *path* (UTF-8, LF line endings, byte-faithful).

    Writes to a temporary file in the same directory, flushes + fsyncs it, then
    ``os.replace``s it onto the target. Because the temp lives in the same directory,
    the rename is guaranteed atomic on POSIX (same filesystem). On any error the temp
    file is cleaned up and the target file is left byte-for-byte unchanged.

    The parent directory is created on demand (mirrors the previous ``write_text`` call
    sites which relied on ``parent.mkdir`` or the file already existing).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the target's mode when replacing an existing file. NamedTemporaryFile
    # defaults to 0o600, and os.replace keeps the temp's mode — that turned every
    # rewrite into a 0600 chmod (BUG-068). New files use 0o644.
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    # delete=False: we rename it ourselves via os.replace; unlink on failure.
    # newline="": write \n verbatim instead of translating to os.linesep. The
    # default turned every Windows install into CRLF — fine for Markdown, fatal
    # for the bash hook script, where "fi\r" is not "fi" and the Stop hook died
    # at parse time (BUG-105). Deterministic LF also agrees with the byte-faithful
    # rollback twin _atomic_write_bytes (BUG-090), so commit/rollback round-trips
    # stay stable across OSes.
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.chmod(tmp.name, existing_mode)
        os.replace(tmp.name, path)
    except BaseException:
        # Close the handle if still open, then remove the temp file. Swallow cleanup
        # errors so the original exception propagates unmasked.
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def backup(path: Path) -> bytes | None:
    """Read the current bytes of *path* into memory for later restoration.

    Returns ``None`` when the file does not exist (nothing to restore). Used by
    ``commit_all`` to snapshot pre-write state so a partial multi-file commit can be
    rolled back to the original bytes.
    """
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write raw *data* to *path* — byte-faithful, no newline translation.

    Text-mode writes translate ``\\n`` to ``os.linesep`` on Windows, so restoring a
    snapshot through ``atomic_write`` (decode → text write) corrupts CRLF files:
    every rollback doubles ``\\r`` (``\\r\\n`` → ``\\r\\r\\n``). Rollbacks must
    reproduce the pre-transaction bytes exactly, hence this binary twin.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.chmod(tmp.name, existing_mode)
        os.replace(tmp.name, path)
    except BaseException:
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def _restore(path: Path, snapshot: bytes | None) -> None:
    """Restore *path* to its pre-commit bytes (or delete it if it didn't exist)."""
    if snapshot is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _atomic_write_bytes(path, snapshot)


def commit_all(plans: list[tuple[Path, str]]) -> None:
    """Commit several file writes as one all-or-nothing transaction.

    Each entry in *plans* is ``(path, text)``. Files are committed in order via
    ``atomic_write``. If any commit fails, every file that was already committed in
    this call is restored from a backup taken before its write, so the project is left
    in its pre-transaction state. The triggering exception then propagates.

    All intended content must already be generated by the caller — this function does
    no validation, only atomic dispatch + rollback. That keeps the "decide everything
    first, then commit" boundary clean.
    """
    snapshots: list[tuple[Path, bytes | None]] = []
    committed: list[tuple[Path, bytes | None]] = []
    for path, _text in plans:
        snapshots.append((path, backup(path)))
    try:
        for (path, text), (_snap_path, snap) in zip(plans, snapshots):
            atomic_write(path, text)
            committed.append((path, snap))
    except BaseException:
        # Roll back every file committed so far, in reverse order, to its pre-transaction
        # bytes. Swallow restore errors so the original exception is not masked.
        for path, snap in reversed(committed):
            try:
                _restore(path, snap)
            except Exception:
                pass
        raise

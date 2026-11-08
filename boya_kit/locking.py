from __future__ import annotations

import hashlib
import os
import time
import uuid
import ctypes
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from autoboya.storage import AutoBoyaStore


class LockUnavailable(RuntimeError):
    """Another process currently owns the requested lock."""


@contextmanager
def file_lock(
    store: AutoBoyaStore,
    relative: str,
    *,
    timeout: float = 0.0,
    stale_after: float = 300.0,
) -> Iterator[None]:
    path = store.path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}:{time.time():.6f}:{uuid.uuid4().hex}"
    deadline = time.monotonic() + max(0.0, timeout)

    while True:
        try:
            descriptor = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            if _remove_stale_lock(path, stale_after):
                continue
            if time.monotonic() >= deadline:
                raise LockUnavailable(f"lock is busy: {relative}")
            time.sleep(0.1)
            continue
        try:
            os.write(descriptor, token.encode("ascii"))
        finally:
            os.close(descriptor)
        break

    try:
        yield
    finally:
        try:
            if path.read_text(encoding="ascii", errors="ignore") == token:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def account_login_lock(
    store: AutoBoyaStore,
    username: str,
    *,
    timeout: float = 0.0,
) -> Iterator[None]:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:20]
    return file_lock(
        store,
        f"run/account-login-{digest}.lock",
        timeout=timeout,
        stale_after=300.0,
    )


def _remove_stale_lock(path: Path, stale_after: float) -> bool:
    try:
        token = path.read_text(encoding="ascii", errors="ignore")
        owner_pid = int(token.split(":", 1)[0])
        age = time.time() - path.stat().st_mtime
        if not _pid_is_running(owner_pid) or (
            stale_after > 0 and age > stale_after
        ):
            path.unlink(missing_ok=True)
            return True
    except (OSError, ValueError):
        pass
    return False


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(
            handle,
            ctypes.byref(exit_code),
        ):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)

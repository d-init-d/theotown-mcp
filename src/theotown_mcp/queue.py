"""Durable, process-safe JSON mailbox used by the Python and Lua bridges."""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from theotown_mcp.bridge_io import atomic_write_text

PROTOCOL_VERSION = 2
MAX_MAILBOX_BYTES = 1_048_576
MAX_JOBS = 64


@contextmanager
def mailbox_lock(lock_path: Path, timeout: float = 5.0) -> Iterator[None]:
    """Acquire an advisory lock shared by bridge processes on this machine."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for mailbox lock: {lock_path}")
                time.sleep(0.02)
        yield
    finally:
        with contextlib.suppress(OSError):
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def empty_mailbox() -> dict[str, Any]:
    return {"protocol": PROTOCOL_VERSION, "revision": 0, "jobs": {}}


def read_mailbox(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_mailbox()
    raw = path.read_bytes()
    if len(raw) > MAX_MAILBOX_BYTES:
        raise ValueError("Mailbox exceeds the 1 MiB safety limit")
    if not raw.strip():
        return empty_mailbox()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("protocol") != PROTOCOL_VERSION:
        raise ValueError("Unsupported or malformed mailbox protocol")
    jobs = data.get("jobs")
    if not isinstance(jobs, dict):
        raise TypeError("Mailbox jobs must be an object")
    if len(jobs) > MAX_JOBS:
        raise ValueError(f"Mailbox contains more than {MAX_JOBS} jobs")
    return data


def write_mailbox(path: Path, mailbox: dict[str, Any]) -> None:
    payload = json.dumps(mailbox, ensure_ascii=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_MAILBOX_BYTES:
        raise ValueError("Mailbox exceeds the 1 MiB safety limit")
    atomic_write_text(path, payload)

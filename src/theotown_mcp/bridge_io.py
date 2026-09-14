"""Small filesystem primitives shared by the bridge and queue modules."""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path


def atomic_write_text(
    target_file: Path,
    content: str,
    max_retries: int = 5,
    base_delay: float = 0.02,
) -> None:
    """Durably replace a UTF-8 text file without exposing partial contents."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=target_file.parent,
        prefix=f".{target_file.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, mode="w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(max_retries):
            try:
                os.replace(temp_path, target_file)
                return
            except (PermissionError, OSError):
                if attempt == max_retries - 1:
                    raise
                time.sleep(base_delay * (2**attempt))
    except Exception:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise

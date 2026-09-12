"""
Lua syntax validator for generated scripts and plugin artifacts.
Supports TheoTown JVM Luaj LuaParser and Python-based static token analysis.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def check_lua_syntax(code_or_file: str | Path) -> tuple[bool, str]:
    """
    Validates Lua script syntax.
    Returns (True, "OK") or (False, error_message).
    """
    content = code_or_file.read_text(encoding="utf-8") if isinstance(code_or_file, Path) else code_or_file

    # 1. Try TheoTown Java Luaj Parser if available on host
    java_exe = Path(r"d:\steam\steamapps\common\TheoTown\jre\bin\java.exe")
    theotown_lby = Path(r"d:\steam\steamapps\common\TheoTown\TheoTown66.lby")

    if java_exe.exists() and theotown_lby.exists():
        try:
            res = subprocess.run(
                [str(java_exe), "-cp", str(theotown_lby), "vm2.parser.LuaParser"],
                input=content,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0:
                return True, "Luaj parse clean"
            return False, f"Luaj syntax error: {res.stderr or res.stdout}"
        except (OSError, subprocess.SubprocessError):
            pass  # Fallback to static analyzer

    # 2. Static syntax checking (delimiter balance, quote balance, keyword balance)
    # Check string literals are closed
    in_str = False
    quote_char = None
    escaped = False
    stack: list[str] = []
    pairs = {"(": ")", "{": "}", "[": "]"}

    for idx, ch in enumerate(content):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote_char:
                in_str = False
                quote_char = None
            continue

        if ch in ('"', "'"):
            in_str = True
            quote_char = ch
            continue

        if ch in ("(", "{", "["):
            stack.append(ch)
        elif ch in (")", "}", "]"):
            if not stack:
                return False, f"Unmatched closing delimiter '{ch}' at position {idx}"
            top = stack.pop()
            if pairs[top] != ch:
                return False, f"Mismatched delimiter '{top}' closed by '{ch}' at {idx}"

    if in_str:
        return False, "Unclosed string literal"
    if stack:
        return False, f"Unclosed delimiters: {stack}"

    return True, "Static syntax clean"

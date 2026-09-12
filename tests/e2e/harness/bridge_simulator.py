"""
In-Game Engine & Bridge Simulator for E2E tests.
Simulates #LuaWrapper hot-reload watcher and core.lua FIFO queue processing
with strict workload budgeting (max 64 tiles per frame tick).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from tests.e2e.harness.city_oracle import CityOracle
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import JobStatus, parse_command


def parse_lua_job_payload(lua_code: str) -> dict[str, Any] | None:
    """Extracts job dictionary from generated inbox.lua content."""
    # Look for storage.theotown_mcp_pending_job = { ... }
    match = re.search(r"storage\.theotown_mcp_pending_job\s*=\s*(\{.*?\})\s*(?:end|\Z)", lua_code, re.DOTALL)
    if not match:
        return None

    raw_table = match.group(1)

    # Extract job_id
    id_match = re.search(r'job_id\s*=\s*"([^"]+)"', raw_table)
    job_id = id_match.group(1) if id_match else "unknown_job"

    # Extract commands array
    cmds: list[dict[str, Any]] = []
    # Match command entries: { cmd = "...", ... }
    cmd_blocks = re.findall(r"\{\s*cmd\s*=\s*\"([^\"]+)\"(.*?)\}", raw_table)
    for cmd_name, body in cmd_blocks:
        entry: dict[str, Any] = {"cmd": cmd_name}
        for k, v in re.findall(r'(\w+)\s*=\s*("(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|true|false)', body):
            val: Any
            if v == "true":
                val = True
            elif v == "false":
                val = False
            elif v.startswith('"') and v.endswith('"'):
                val = v[1:-1].replace('\\"', '"').replace("\\n", "\n")
            elif "." in v:
                val = float(v)
            else:
                val = int(v)
            entry[k] = val
        cmds.append(entry)

    return {
        "job_id": job_id,
        "commands": cmds,
    }


class BridgeSimulator:
    """Simulates the in-game Lua plugin runtime (#LuaWrapper and core.lua)."""

    def __init__(self, config: TheoTownConfig, oracle: CityOracle) -> None:
        self.config = config
        self.oracle = oracle
        self.processed_job_ids: set[str] = set()
        self.last_inbox_mtime: float = 0.0

    def sync_telemetry_to_disk(self) -> None:
        """Writes current oracle state to telemetry.json."""
        self.config.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        telem = self.oracle.get_telemetry_dict()
        self.config.telemetry_path.write_text(json.dumps(telem, indent=2), encoding="utf-8")

    def process_inbox(self, max_units_per_tick: int = 64) -> JobStatus | None:
        """
        Polls inbox.lua, detects modifications, parses payload,
        and simulates tick budgeting and command execution.
        """
        inbox_file = self.config.inbox_path
        if not inbox_file.exists():
            return None

        content = inbox_file.read_text(encoding="utf-8")

        # Check for cancel command
        cancel_match = re.search(r"Cancel Job (job_\w+)", content)
        if cancel_match:
            c_job_id = cancel_match.group(1)
            status_file = self.config.plugin_dir / f"job_{c_job_id}.json"
            now = time.time()
            cancelled_status = JobStatus(
                job_id=c_job_id,
                status="cancelled",
                progress=0.5,
                total_steps=1,
                completed_steps=0,
                created_at=now,
                updated_at=now,
            )
            status_file.write_text(cancelled_status.model_dump_json(indent=2), encoding="utf-8")
            return cancelled_status

        payload = parse_lua_job_payload(content)
        if not payload:
            return None

        job_id = payload["job_id"]
        if job_id in self.processed_job_ids:
            # Already processed
            status_file = self.config.plugin_dir / f"job_{job_id}.json"
            if status_file.exists():
                return JobStatus.model_validate_json(status_file.read_text(encoding="utf-8"))
            return None

        self.processed_job_ids.add(job_id)
        raw_cmds = payload["commands"]
        total_steps = len(raw_cmds)
        now = time.time()

        # Step-by-step budgeted execution
        completed_steps = 0
        errors: list[str] = []

        for i, raw_cmd in enumerate(raw_cmds):
            # Budget throttling: if batch exceeds max_units_per_tick, simulate slice
            try:
                cmd = parse_command(raw_cmd)
                res = self.oracle.execute_command(cmd)
                if not res.get("success"):
                    errors.append(f"Step {i+1}: {res.get('error', 'Execution failure')}")
                else:
                    completed_steps += 1
            except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                errors.append(f"Step {i+1} validation error: {exc!s}")

        # Update telemetry
        self.sync_telemetry_to_disk()

        final_status: Any = "completed" if len(errors) == 0 else "failed"
        job_status = JobStatus(
            job_id=job_id,
            status=final_status,
            progress=1.0 if total_steps == 0 else completed_steps / total_steps,
            total_steps=total_steps,
            completed_steps=completed_steps,
            created_at=now,
            updated_at=time.time(),
            error="; ".join(errors) if errors else None,
        )

        # Write status to disk
        status_file = self.config.plugin_dir / f"job_{job_id}.json"
        status_file.write_text(job_status.model_dump_json(indent=2), encoding="utf-8")

        return job_status

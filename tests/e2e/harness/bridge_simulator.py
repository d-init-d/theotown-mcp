"""In-game protocol-v2 bridge simulator for end-to-end tests."""

from __future__ import annotations

import json
import time
from typing import Any

from tests.e2e.harness.city_oracle import CityOracle
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import JobStatus, parse_command
from theotown_mcp.queue import read_mailbox


class BridgeSimulator:
    """Simulates the in-game Lua plugin runtime (#LuaWrapper and core.lua)."""

    def __init__(self, config: TheoTownConfig, oracle: CityOracle) -> None:
        self.config = config
        self.oracle = oracle
        self.processed_job_ids: set[str] = set()
        self.last_inbox_mtime: float = 0.0
        self.last_result: JobStatus | None = None

    def sync_telemetry_to_disk(self) -> None:
        """Writes current oracle state to telemetry.json."""
        self.config.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        telem = self.oracle.get_telemetry_dict()
        self.config.telemetry_path.write_text(json.dumps(telem, indent=2), encoding="utf-8")

    def process_inbox(self, max_units_per_tick: int = 64) -> JobStatus | None:
        """
        Polls requests.txt, selects the first unprocessed job,
        and simulates tick budgeting and command execution.
        """
        if not self.config.requests_path.exists():
            return None
        mailbox = read_mailbox(self.config.requests_path)
        payload = next((item for item in mailbox["jobs"].values()
                        if item.get("job_id") not in self.processed_job_ids), None)
        if payload is None:
            return self.last_result

        job_id = payload["job_id"]
        if payload.get("cancel_requested") is True:
            self.processed_job_ids.add(job_id)
            now = time.time()
            cancelled_status = JobStatus(
                job_id=job_id,
                session_id=str(payload.get("session_id", "")),
                status="cancelled",
                progress=0.0,
                total_steps=len(payload.get("commands", [])),
                created_at=float(payload.get("created_at", now)),
                updated_at=now,
            )
            status_file = self.config.plugin_dir / f"job_{job_id}.txt"
            status_file.write_text(cancelled_status.model_dump_json(indent=2), encoding="utf-8")
            self.last_result = cancelled_status
            return cancelled_status
        if job_id in self.processed_job_ids:
            # Already processed
            status_file = self.config.plugin_dir / f"job_{job_id}.txt"
            if status_file.exists():
                return JobStatus.model_validate_json(status_file.read_text(encoding="utf-8"))
            return None

        self.processed_job_ids.add(job_id)
        raw_cmds = [payload["commands"][key] for key in sorted(payload["commands"], key=int)]
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
            session_id=str(payload.get("session_id", "")),
            status=final_status,
            progress=1.0 if total_steps == 0 else completed_steps / total_steps,
            total_steps=total_steps,
            completed_steps=completed_steps,
            created_at=float(payload.get("created_at", now)),
            updated_at=time.time(),
            error="; ".join(errors) if errors else None,
        )

        # Write status to disk
        status_file = self.config.plugin_dir / f"job_{job_id}.txt"
        status_file.write_text(job_status.model_dump_json(indent=2), encoding="utf-8")
        self.last_result = job_status
        return job_status

"""Safe filesystem IPC bridge between MCP and the TheoTown Lua plugin."""

from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from theotown_mcp.bridge_io import atomic_write_text
from theotown_mcp.catalog import DraftCatalog, get_catalog
from theotown_mcp.config import TheoTownConfig, get_config
from theotown_mcp.models import (
    BuildRoadCmd,
    BuildUtilityCmd,
    CityTelemetry,
    JobStatus,
    PlanCommand,
    PlanValidationResult,
    parse_commands,
    validate_job_id,
)
from theotown_mcp.queue import MAX_JOBS, mailbox_lock, read_mailbox, write_mailbox

TERMINAL_STATES = {"completed", "failed", "cancelled"}
HEARTBEAT_PROTOCOL = 2
MAX_JOB_ERROR_DETAILS = 64
MAX_JOB_ERROR_TEXT = 4096


def _ordered_error_counts(messages: Sequence[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in messages:
        message = str(value).strip()
        if message:
            counts[message] = counts.get(message, 0) + 1
    return counts


def _compact_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Bound verbose game errors while preserving totals and representative details."""
    compact = dict(payload)
    raw_result = compact.get("result")
    if not isinstance(raw_result, dict):
        raw_error = compact.get("error")
        if isinstance(raw_error, str) and len(raw_error) > MAX_JOB_ERROR_TEXT:
            compact["error"] = raw_error[: MAX_JOB_ERROR_TEXT - 3] + "..."
        return compact

    result = dict(raw_result)
    raw_details = result.get("errors", [])
    if isinstance(raw_details, dict):
        detail_items = list(raw_details.items())
        detail_messages = [value for _, value in detail_items]
        result["errors"] = dict(detail_items[:MAX_JOB_ERROR_DETAILS])
    elif isinstance(raw_details, list):
        detail_items = list(enumerate(raw_details))
        detail_messages = raw_details
        result["errors"] = raw_details[:MAX_JOB_ERROR_DETAILS]
    else:
        detail_items = []
        detail_messages = []
        result["errors"] = []

    existing_counts = result.get("error_counts")
    if isinstance(existing_counts, dict):
        counts: dict[str, int] = {}
        for message, count in existing_counts.items():
            try:
                amount = int(count)
            except (TypeError, ValueError):
                continue
            if amount > 0:
                counts[str(message)] = amount
    else:
        counts = _ordered_error_counts(detail_messages)
    result["error_counts"] = counts
    omitted = max(0, len(detail_items) - MAX_JOB_ERROR_DETAILS)
    result["omitted_error_details"] = int(result.get("omitted_error_details", 0)) + omitted

    if counts:
        summary = "; ".join(
            f"{count}x {message}" if count > 1 else message
            for message, count in counts.items()
        )
        compact["error"] = summary[:MAX_JOB_ERROR_TEXT]
    elif isinstance(compact.get("error"), str) and len(compact["error"]) > MAX_JOB_ERROR_TEXT:
        compact["error"] = compact["error"][: MAX_JOB_ERROR_TEXT - 3] + "..."
    compact["result"] = result
    return compact


def serialize_to_lua(obj: Any) -> str:
    """Serialize plain Python values for legacy callers without executing them live."""
    if obj is None:
        return "nil"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        if isinstance(obj, float) and not math.isfinite(obj):
            raise ValueError("Lua serialization rejects non-finite numbers")
        return str(obj)
    if isinstance(obj, str):
        escaped = (obj.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                   .replace("\r", "\\r").replace("\t", "\\t").replace("\0", "\\0"))
        return f'"{escaped}"'
    if isinstance(obj, (list, tuple)):
        return "{ " + ", ".join(serialize_to_lua(value) for value in obj) + " }"
    if isinstance(obj, dict):
        entries = []
        for key, value in obj.items():
            key_text = str(key)
            lhs = key_text if key_text.isidentifier() else f"[{serialize_to_lua(key_text)}]"
            entries.append(f"{lhs} = {serialize_to_lua(value)}")
        return "{ " + ", ".join(entries) + " }"
    if hasattr(obj, "model_dump"):
        return serialize_to_lua(obj.model_dump())
    raise TypeError(f"Cannot serialize type {type(obj)} to Lua")


def write_atomic_lua(target_file: Path, lua_content: str, max_retries: int = 5, base_delay: float = 0.02) -> None:
    """Backward-compatible name for the atomic UTF-8 writer."""
    atomic_write_text(target_file, lua_content, max_retries=max_retries, base_delay=base_delay)


def generate_job_lua(job_id: str, commands: Sequence[PlanCommand | dict[str, Any]], timestamp: float | None = None,
                     batch_jobs: list[dict[str, Any]] | None = None) -> str:
    """Generate an inert compatibility fixture; production IPC uses requests.txt."""
    validate_job_id(job_id)
    created_at = time.time() if timestamp is None else timestamp
    jobs = batch_jobs or [{"job_id": job_id, "created_at": created_at,
                           "commands": [item.model_dump() for item in parse_commands(commands)]}]
    return (f"-- Job ID: {job_id}\n"
            "-- Compatibility fixture only; core.lua consumes requests.txt\nreturn "
            + serialize_to_lua(jobs) + "\n")


class TheoTownBridge:
    """Coordinates a durable, acknowledged command queue with the running game."""

    def __init__(self, config: TheoTownConfig | None = None, catalog: DraftCatalog | None = None) -> None:
        self.config = config or get_config()
        self.catalog = catalog or get_catalog(self.config)
        self.jobs: dict[str, JobStatus] = {}

    def read_telemetry(self, max_stale_seconds: float = 10.0) -> CityTelemetry:
        """Read a protocol-v2 heartbeat and reject stale or explicitly offline data."""
        path = self.config.telemetry_path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise TypeError("Telemetry root is not an object")
            timestamp = float(data.get("last_updated", data.get("last_update", 0.0)))
            fresh = 0.0 <= time.time() - timestamp <= max_stale_seconds
            connected = (data.get("protocol") == HEARTBEAT_PROTOCOL
                         and isinstance(data.get("session_id"), str) and bool(data.get("session_id"))
                         and data.get("connected") is True and fresh)
            data["connected"] = connected
            data["last_update"] = timestamp
            if not connected and not data.get("reason"):
                data["reason"] = "TheoTown heartbeat is missing, stale, offline, or uses an unsupported protocol"
            return CityTelemetry.model_validate(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return CityTelemetry(connected=False, last_update=0.0,
                                 reason="No valid TheoTown protocol-v2 heartbeat was found")

    def validate_plan(self, commands: Sequence[PlanCommand | dict[str, Any]], dry_run: bool = True) -> PlanValidationResult:
        from theotown_mcp.models import MAX_AFFECTED_TILES, MAX_COMMANDS_PER_PLAN

        del dry_run
        errors: list[str] = []
        warnings: list[str] = []
        try:
            parsed = parse_commands(commands)
        except (ValueError, TypeError, KeyError) as exc:
            return PlanValidationResult(valid=False, errors=[f"Schema validation error: {exc}"], command_count=len(commands))
        if len(parsed) > MAX_COMMANDS_PER_PLAN:
            errors.append(f"Plan command count ({len(parsed)}) exceeds maximum allowed ({MAX_COMMANDS_PER_PLAN})")

        telemetry = self.read_telemetry()
        width, height = (telemetry.width, telemetry.height) if telemetry.connected else (128, 128)
        if not telemetry.connected:
            warnings.append("City telemetry is offline or stale; validation uses a 128x128 fallback grid")
        affected = 0
        for index, command in enumerate(parsed, 1):
            errors.extend(f"Command #{index} ({command.cmd}): {message}" for message in command.check_bounds(width, height))
            affected += getattr(command, "tile_length", getattr(command, "tile_count", 1))
            if isinstance(command, (BuildRoadCmd, BuildUtilityCmd)) and command.x0 != command.x1 and command.y0 != command.y1:
                errors.append(f"Command #{index} ({command.cmd}): only horizontal or vertical lines are supported")
        if affected > MAX_AFFECTED_TILES:
            errors.append(f"Plan affected tiles ({affected}) exceeds maximum allowed ({MAX_AFFECTED_TILES})")
        estimated_cost = self.catalog.estimate_total_cost(parsed)
        if telemetry.connected and telemetry.money < estimated_cost:
            warnings.append(f"Estimated cost ({estimated_cost}) exceeds active treasury ({telemetry.money})")
        return PlanValidationResult(valid=not errors, errors=errors, warnings=warnings,
                                    estimated_cost=estimated_cost, command_count=len(parsed), affected_tiles=affected)

    def _append_job(self, job: dict[str, Any]) -> None:
        with mailbox_lock(self.config.mailbox_lock_path):
            mailbox = read_mailbox(self.config.requests_path)
            jobs = mailbox["jobs"]
            retained: dict[str, Any] = {}
            for prior_id, item in jobs.items():
                prior_path = self.config.plugin_dir / f"job_{prior_id}.txt"
                try:
                    prior = json.loads(prior_path.read_text(encoding="utf-8"))
                    if prior.get("status") in TERMINAL_STATES:
                        continue
                except (OSError, json.JSONDecodeError, AttributeError):
                    pass
                retained[prior_id] = item
            jobs.clear()
            jobs.update(retained)
            jobs.pop(job["job_id"], None)
            if len(jobs) >= MAX_JOBS:
                raise RuntimeError(f"TheoTown mailbox is full ({MAX_JOBS} jobs)")
            jobs[job["job_id"]] = job
            mailbox["revision"] = int(mailbox.get("revision", 0)) + 1
            write_mailbox(self.config.requests_path, mailbox)

    def execute_plan(self, commands: Sequence[PlanCommand | dict[str, Any]],
                     max_stale_seconds: float = 10.0) -> JobStatus:
        parsed = parse_commands(commands)
        validation = self.validate_plan(parsed, dry_run=False)
        if not validation.valid:
            raise ValueError(f"Plan validation failed: {'; '.join(validation.errors)}")
        telemetry = self.read_telemetry(max_stale_seconds=max_stale_seconds)
        if not telemetry.connected:
            raise ConnectionError(telemetry.reason or "TheoTown is not connected")
        now = time.time()
        job_id = f"job_{uuid.uuid4().hex}"
        status = JobStatus(job_id=job_id, session_id=telemetry.session_id, status="pending",
                           progress=0.0, total_steps=len(parsed), completed_steps=0,
                           attempted_steps=0, failed_steps=0, created_at=now, updated_at=now)
        self._append_job({"job_id": job_id, "session_id": telemetry.session_id, "created_at": now,
                          "cancel_requested": False,
                          "commands": {str(index): command.model_dump() for index, command in enumerate(parsed, 1)}})
        self.jobs[job_id] = status
        return status

    def get_job_status(self, job_id: str) -> JobStatus:
        validate_job_id(job_id)
        for suffix in ("txt", "json"):
            path = self.config.plugin_dir / f"job_{job_id}.{suffix}"
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise TypeError("Job status root is not an object")
                status = JobStatus.model_validate(_compact_job_payload(payload))
                self.jobs[job_id] = status
                return status
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        if job_id in self.jobs:
            return self.jobs[job_id]
        try:
            mailbox = read_mailbox(self.config.requests_path)
            item = mailbox["jobs"].get(job_id)
            if isinstance(item, dict):
                created_at = float(item.get("created_at", time.time()))
                commands = item.get("commands") if isinstance(item.get("commands"), dict) else {}
                return JobStatus(
                    job_id=job_id,
                    session_id=str(item.get("session_id", "")),
                    status="cancel_requested" if item.get("cancel_requested") is True else "pending",
                    total_steps=len(commands),
                    created_at=created_at,
                    updated_at=created_at,
                )
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        now = time.time()
        return JobStatus(job_id=job_id, status="failed", created_at=now, updated_at=now,
                         error=f"Job '{job_id}' not found")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        validate_job_id(job_id)
        current = self.get_job_status(job_id)
        if current.status in TERMINAL_STATES:
            return {"job_id": job_id, "status": current.status,
                    "error": f"Cannot cancel job in state '{current.status}'"}
        found = False
        with mailbox_lock(self.config.mailbox_lock_path):
            mailbox = read_mailbox(self.config.requests_path)
            item = mailbox["jobs"].get(job_id)
            if isinstance(item, dict):
                item["cancel_requested"] = True
                found = True
            if found:
                mailbox["revision"] = int(mailbox.get("revision", 0)) + 1
                write_mailbox(self.config.requests_path, mailbox)
        if not found:
            return {"job_id": job_id, "status": current.status,
                    "error": "Job is no longer present in the command mailbox"}
        if job_id in self.jobs:
            self.jobs[job_id].status = "cancel_requested"
            self.jobs[job_id].updated_at = time.time()
        return {"job_id": job_id, "status": "cancel_requested"}

    def set_speed(self, speed: int, max_stale_seconds: float = 10.0) -> dict[str, Any]:
        if speed not in (0, 1, 2, 3, 4):
            raise ValueError("Speed must be an integer between 0 and 4")
        telemetry = self.read_telemetry(max_stale_seconds=max_stale_seconds)
        if not telemetry.connected:
            raise ConnectionError(telemetry.reason or "TheoTown is not connected")
        now = time.time()
        job_id = f"job_{uuid.uuid4().hex}"
        self._append_job({"job_id": job_id, "session_id": telemetry.session_id, "created_at": now,
                          "cancel_requested": False, "commands": {"1": {"cmd": "set_speed", "speed": speed}}})
        return {"status": "pending", "speed": speed, "job_id": job_id}


_global_bridge: TheoTownBridge | None = None


def get_bridge(config: TheoTownConfig | None = None, catalog: DraftCatalog | None = None,
               refresh: bool = False) -> TheoTownBridge:
    global _global_bridge
    if config is not None or catalog is not None:
        return TheoTownBridge(config=config, catalog=catalog)
    if _global_bridge is None or refresh:
        _global_bridge = TheoTownBridge()
    return _global_bridge


def reset_bridge() -> None:
    global _global_bridge
    _global_bridge = None

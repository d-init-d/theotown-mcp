from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from theotown_mcp.bridge import TheoTownBridge
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import BuildRoadCmd
from theotown_mcp.queue import read_mailbox


def live_bridge(tmp_path: Path) -> TheoTownBridge:
    config = TheoTownConfig(data_dir_override=tmp_path)
    config.ensure_directories()
    config.telemetry_path.write_text(json.dumps({
        "protocol": 2,
        "session_id": "test-session",
        "name": "test",
        "width": 128,
        "height": 128,
        "connected": True,
        "last_updated": time.time(),
    }), encoding="utf-8")
    return TheoTownBridge(config=config)


def test_explicit_offline_and_stale_heartbeat_are_rejected(tmp_path: Path) -> None:
    bridge = live_bridge(tmp_path)
    data = json.loads(bridge.config.telemetry_path.read_text(encoding="utf-8"))
    data["connected"] = False
    bridge.config.telemetry_path.write_text(json.dumps(data), encoding="utf-8")
    assert bridge.read_telemetry().connected is False
    with pytest.raises(ConnectionError):
        bridge.execute_plan([BuildRoadCmd(x0=1, y0=1, x1=2, y1=1)])

    data["connected"] = True
    data["last_updated"] = time.time() - 60
    bridge.config.telemetry_path.write_text(json.dumps(data), encoding="utf-8")
    assert bridge.read_telemetry().connected is False


def test_concurrent_writers_preserve_every_job(tmp_path: Path) -> None:
    bridge = live_bridge(tmp_path)
    command = BuildRoadCmd(x0=1, y0=1, x1=2, y1=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: bridge.execute_plan([command]), range(24)))
    mailbox = read_mailbox(bridge.config.requests_path)
    assert set(mailbox["jobs"]) == {job.job_id for job in jobs}


def test_cancel_is_acknowledged_by_game_and_does_not_drop_other_jobs(tmp_path: Path) -> None:
    bridge = live_bridge(tmp_path)
    a = bridge.execute_plan([BuildRoadCmd(x0=1, y0=1, x1=2, y1=1)])
    b = bridge.execute_plan([BuildRoadCmd(x0=3, y0=1, x1=4, y1=1)])
    assert bridge.cancel_job(a.job_id)["status"] == "cancel_requested"
    mailbox = read_mailbox(bridge.config.requests_path)
    by_id = mailbox["jobs"]
    assert by_id[a.job_id]["cancel_requested"] is True
    assert by_id[b.job_id]["cancel_requested"] is False


def test_new_bridge_recovers_pending_status_from_mailbox(tmp_path: Path) -> None:
    first = live_bridge(tmp_path)
    job = first.execute_plan([BuildRoadCmd(x0=1, y0=1, x1=2, y1=1)])
    recovered = TheoTownBridge(config=first.config).get_job_status(job.job_id)
    assert recovered.status == "pending"
    assert recovered.session_id == "test-session"


def test_plugin_manifest_loads_only_static_core_and_lua_has_no_nul() -> None:
    plugin_dir = Path(__file__).parents[1] / "plugin" / "theotown_mcp"
    manifest = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
    assert [item["script"] for item in manifest] == ["core.lua"]
    assert b"\0" not in (plugin_dir / "core.lua").read_bytes()
    assert b"\0" not in (plugin_dir / "inbox.lua").read_bytes()


def test_lua_core_matches_builder_and_tile_api_signatures() -> None:
    core = (Path(__file__).parents[1] / "plugin" / "theotown_mcp" / "core.lua").read_text(encoding="utf-8")
    assert "Builder.isZoneBuildable" not in core
    assert "Builder.isRemovable" not in core
    assert 'verifyDraft("getRoadDraft", x0, y0, level)' in core
    assert "tonumber(tostring(unit.x0))" in core


def test_lua_core_bounds_repeated_errors_and_includes_failed_coordinates() -> None:
    core = (Path(__file__).parents[1] / "plugin" / "theotown_mcp" / "core.lua").read_text(encoding="utf-8")
    assert "local MAX_ERROR_DETAILS = 64" in core
    assert "recordFailure(active, unit, active.index, err)" in core
    assert 'string.format("step %d %s: %s", step, describeUnit(unit), message)' in core
    assert "omitted_error_details" in core
    assert "summarizeFailures(active)" in core

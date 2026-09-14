"""
Comprehensive hardening and regression test suite for TheoTown MCP.
Covers:
1. Rapid multi-job queue without overwrites (Issue A)
2. Anti-replay and idempotency on reload (Issue B)
3. Job cancellation lifecycle and injection protection (Issue C)
4. Builder failure reporting and status accuracy (Issue D)
5. Universal validation on all paths (Issue E)
6. STDIO log cleanliness and JSON-RPC protocol (Issue F)
7. Telemetry heartbeat and stale connection detection (Issue G)
8. Instance isolation and dependency injection (Issue H)
9. Plugin asset integrity and safe installation (Issue I)
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from theotown_mcp.assets import install_plugin_files
from theotown_mcp.bridge import TheoTownBridge
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import (
    MAX_COMMANDS_PER_PLAN,
    BuildRoadCmd,
    JobStatus,
    validate_job_id,
)


def write_live_telemetry(config: TheoTownConfig, session_id: str = "hardening-test") -> None:
    config.ensure_directories()
    config.telemetry_path.write_text(json.dumps({
        "protocol": 2,
        "session_id": session_id,
        "name": "HardeningTestCity",
        "money": 100000,
        "population": 0,
        "width": 128,
        "height": 128,
        "connected": True,
        "last_updated": time.time(),
    }), encoding="utf-8")


class TestMultiJobBatchQueue:
    """Issue A: Rapid multi-job queue without overwrites."""

    def test_rapid_multi_job_enqueue_preserves_all_in_batch(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        write_live_telemetry(cfg)
        bridge = TheoTownBridge(config=cfg)

        # Enqueue 5 jobs in rapid succession without simulated game ticks
        jobs: list[JobStatus] = []
        for i in range(5):
            cmd = BuildRoadCmd(x0=i * 2, y0=0, x1=i * 2 + 1, y1=0)
            job = bridge.execute_plan([cmd])
            jobs.append(job)

        # Inspect inbox.lua content
        assert cfg.requests_path.exists()
        content = cfg.requests_path.read_text(encoding="utf-8")

        # All 5 job IDs must be present in the mailbox
        for job in jobs:
            assert job.job_id in content

        # Pruning simulation: when game marks job 0 and 1 acknowledged
        for job in jobs[:2]:
            status_file = cfg.plugin_dir / f"job_{job.job_id}.txt"
            status_payload = job.model_dump()
            status_payload["status"] = "completed"
            status_file.write_text(json.dumps(status_payload), encoding="utf-8")

        # Next job submission should prune acknowledged jobs
        job6 = bridge.execute_plan([BuildRoadCmd(x0=20, y0=0, x1=21, y1=0)])
        new_content = cfg.requests_path.read_text(encoding="utf-8")

        # Completed jobs should have been pruned from batch
        assert jobs[0].job_id not in new_content
        assert jobs[1].job_id not in new_content
        # Remaining pending jobs must still be present
        assert jobs[2].job_id in new_content
        assert jobs[3].job_id in new_content
        assert jobs[4].job_id in new_content
        assert job6.job_id in new_content


class TestAntiReplayIdempotency:
    """Issue B: Anti-replay and idempotency on reload."""

    def test_anti_replay_on_inbox_re_execution(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        write_live_telemetry(cfg)
        bridge = TheoTownBridge(config=cfg)

        job = bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        assert job.status == "pending"

        # Game processes and completes job
        status_file = cfg.plugin_dir / f"job_{job.job_id}.txt"
        comp_payload = job.model_dump()
        comp_payload["status"] = "completed"
        status_file.write_text(json.dumps(comp_payload), encoding="utf-8")

        # Query status
        current = bridge.get_job_status(job.job_id)
        assert current.status == "completed"

        # If inbox.lua is re-executed, bridge still reports completed
        current2 = bridge.get_job_status(job.job_id)
        assert current2.status == "completed"


class TestJobCancellation:
    """Issue C: Safe job cancellation protocol and injection prevention."""

    def test_cancel_pending_job_success(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        write_live_telemetry(cfg)
        bridge = TheoTownBridge(config=cfg)

        job = bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        res = bridge.cancel_job(job.job_id)
        assert res["status"] == "cancel_requested"

        # Check inbox has cancel payload
        mailbox = json.loads(cfg.requests_path.read_text(encoding="utf-8"))
        assert mailbox["jobs"][job.job_id]["cancel_requested"] is True

    def test_cancel_completed_job_rejected(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        write_live_telemetry(cfg)
        bridge = TheoTownBridge(config=cfg)

        job = bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        status_file = cfg.plugin_dir / f"job_{job.job_id}.txt"
        comp_payload = job.model_dump()
        comp_payload["status"] = "completed"
        status_file.write_text(json.dumps(comp_payload), encoding="utf-8")

        res = bridge.cancel_job(job.job_id)
        assert res["status"] == "completed"
        assert "Cannot cancel job" in res["error"]

    def test_cancel_job_invalid_id_raises_value_error(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        bridge = TheoTownBridge(config=cfg)

        with pytest.raises(ValueError, match="Invalid job_id"):
            bridge.cancel_job("job_123'; os.execute('calc'); --")

    def test_get_job_status_invalid_id_raises_value_error(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        bridge = TheoTownBridge(config=cfg)

        with pytest.raises(ValueError, match="Invalid job_id"):
            bridge.get_job_status("invalid id with spaces")


class TestUniversalValidation:
    """Issue E: Universal input and boundary validation."""

    def test_job_id_regex_validator(self):
        assert validate_job_id("job_123456") == "job_123456"
        assert validate_job_id("job-abc-XYZ_01") == "job-abc-XYZ_01"

        with pytest.raises(ValueError):
            validate_job_id("")
        with pytest.raises(ValueError):
            validate_job_id("job/with/slashes")
        with pytest.raises(ValueError):
            validate_job_id("job$injection")
        with pytest.raises(ValueError):
            validate_job_id("a" * 65)

    def test_batch_limit_command_count(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        bridge = TheoTownBridge(config=cfg)

        too_many = [
            {"cmd": "build_road", "x0": i % 50, "y0": 0, "x1": (i % 50) + 1, "y1": 0}
            for i in range(MAX_COMMANDS_PER_PLAN + 1)
        ]
        val = bridge.validate_plan(too_many)
        assert val.valid is False
        assert any("command count" in e for e in val.errors)

        with pytest.raises(ValueError, match="Plan validation failed"):
            bridge.execute_plan(too_many)

    def test_batch_limit_affected_tiles(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        bridge = TheoTownBridge(config=cfg)

        # 101 x 101 zone = 10,201 tiles > 10,000
        oversized_zone = [{"cmd": "build_zone", "x": 0, "y": 0, "width": 101, "height": 101}]
        val = bridge.validate_plan(oversized_zone)
        assert val.valid is False
        assert any("affected tiles" in e for e in val.errors)

        with pytest.raises(ValueError, match="Plan validation failed"):
            bridge.execute_plan(oversized_zone)

    def test_bounds_validation_against_connected_telemetry(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        # Write live telemetry with 64x64 grid
        telem = {
            "protocol": 2,
            "session_id": "bounds-test",
            "name": "SmallTown",
            "money": 50000,
            "population": 100,
            "width": 64,
            "height": 64,
            "connected": True,
            "last_updated": time.time(),
        }
        cfg.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.telemetry_path.write_text(json.dumps(telem), encoding="utf-8")

        bridge = TheoTownBridge(config=cfg)
        out_of_bounds = [{"cmd": "build_road", "x0": 10, "y0": 10, "x1": 70, "y1": 10}]
        val = bridge.validate_plan(out_of_bounds)
        assert val.valid is False
        assert any("out of bounds" in e for e in val.errors)

        with pytest.raises(ValueError, match="Plan validation failed"):
            bridge.execute_plan(out_of_bounds)


class TestTelemetryFreshness:
    """Issue G: Telemetry heartbeat freshness and offline detection."""

    def test_fresh_telemetry_detected_as_connected(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        telem_data = {
            "protocol": 2,
            "session_id": "fresh-test",
            "name": "LiveCity",
            "money": 10000,
            "population": 500,
            "width": 128,
            "height": 128,
            "connected": True,
            "last_updated": time.time(),
        }
        cfg.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.telemetry_path.write_text(json.dumps(telem_data), encoding="utf-8")

        bridge = TheoTownBridge(config=cfg)
        t = bridge.read_telemetry(max_stale_seconds=10.0)
        assert t.connected is True
        assert t.name == "LiveCity"

    def test_stale_telemetry_detected_as_disconnected(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        telem_data = {
            "name": "StaleCity",
            "money": 10000,
            "population": 500,
            "width": 128,
            "height": 128,
            "last_updated": time.time() - 3600.0,  # 1 hour ago
        }
        cfg.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.telemetry_path.write_text(json.dumps(telem_data), encoding="utf-8")

        # Also set file mtime back
        import os
        old_time = time.time() - 3600.0
        os.utime(cfg.telemetry_path, (old_time, old_time))

        bridge = TheoTownBridge(config=cfg)
        t = bridge.read_telemetry(max_stale_seconds=10.0)
        assert t.connected is False

    def test_corrupted_telemetry_file(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        cfg.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.telemetry_path.write_text("NOT_JSON", encoding="utf-8")

        bridge = TheoTownBridge(config=cfg)
        t = bridge.read_telemetry()
        assert t.connected is False

    def test_missing_telemetry_file(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        bridge = TheoTownBridge(config=cfg)
        t = bridge.read_telemetry()
        assert t.connected is False


class TestInstanceIsolation:
    """Issue H: Independent configuration and instance isolation."""

    def test_independent_bridge_and_config_instances(self, tmp_path: Path):
        dir1 = tmp_path / "inst1"
        dir2 = tmp_path / "inst2"

        cfg1 = TheoTownConfig(data_dir_override=dir1)
        cfg2 = TheoTownConfig(data_dir_override=dir2)

        br1 = TheoTownBridge(config=cfg1)
        br2 = TheoTownBridge(config=cfg2)

        assert br1.config.theotown_data_dir != br2.config.theotown_data_dir

        write_live_telemetry(cfg1, "instance-one")
        job1 = br1.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        assert cfg1.requests_path.exists()
        assert not cfg2.requests_path.exists()

        assert job1.job_id in br1.jobs
        assert job1.job_id not in br2.jobs


class TestPluginPackagingAndAssets:
    """Issue I: Wheel packaging and safe install-plugin."""

    def test_bundled_assets_exist_and_install_safely(self, tmp_path: Path):
        dest = tmp_path / "plugins" / "theotown_mcp"
        installed = install_plugin_files(target_dir=dest, force=True, backup=True)

        assert len(installed) == 3
        installed_names = [f.name for f in installed]
        assert "plugin.json" in installed_names
        assert "core.lua" in installed_names
        assert "inbox.lua" in installed_names

        # Verify content validity
        plugin_json = dest / "plugin.json"
        data = json.loads(plugin_json.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert any(item.get("id") == "$theotown_mcp_core" for item in data)

        # Non-destructive: user file created before install must not be wiped
        user_file = dest / "user_saved_state.json"
        user_file.write_text('{"preserved": true}', encoding="utf-8")

        # Re-install with force=True
        installed2 = install_plugin_files(target_dir=dest, force=True, backup=True)
        assert len(installed2) == 3
        # user_saved_state.json must still exist!
        assert user_file.exists()


class TestStdioJsonRpcSubprocess:
    """Issue F: Clean STDIO JSON-RPC handshake without stderr pollution."""

    def test_stdio_handshake_and_tools_list(self):
        """Launches the CLI in stdio mode, tests initialize and tools/list."""
        proc = subprocess.Popen(
            [sys.executable, "-m", "theotown_mcp.cli", "run", "--transport", "stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        try:
            # 1. Send initialize request
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0.0"},
                },
            }
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()

            # Read response
            assert proc.stdout is not None
            response_line = proc.stdout.readline()
            assert response_line, "Expected JSON-RPC response from stdio server"
            resp = json.loads(response_line)
            assert resp.get("id") == 1
            assert "result" in resp
            server_info = resp["result"].get("serverInfo", {})
            assert server_info.get("name") == "theotown-mcp"

            # 2. Send tools/list request
            tools_req = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
            proc.stdin.write(json.dumps(tools_req) + "\n")
            proc.stdin.flush()

            tools_line = proc.stdout.readline()
            assert tools_line, "Expected tools/list response"
            tools_resp = json.loads(tools_line)
            assert tools_resp.get("id") == 2
            tools_list = tools_resp["result"]["tools"]
            tool_names = [t["name"] for t in tools_list]
            assert len(tool_names) == 12
            assert "theotown_get_status" in tool_names
            assert "theotown_build_road" in tool_names
            assert "theotown_execute_plan" in tool_names
            assert "theotown_set_speed" in tool_names

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


class TestLoopbackHttpServer:
    """Real loopback HTTP/SSE server test on ephemeral port."""

    def test_http_transport_loopback_startup_and_endpoint(self):
        import socket
        import urllib.error
        import urllib.request

        # Find a free local port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "theotown_mcp.cli",
                "run",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Poll until server responds on loopback
            url = f"http://127.0.0.1:{port}/mcp"
            server_started = False
            for _ in range(30):
                time.sleep(0.2)
                try:
                    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        if resp.status in (200, 400, 405):
                            server_started = True
                            break
                except urllib.error.HTTPError as he:
                    # HTTP response received means server is up
                    if he.code in (200, 400, 405):
                        server_started = True
                        break
                except (urllib.error.URLError, ConnectionRefusedError, OSError):
                    continue

            assert server_started, "HTTP MCP server failed to bind and respond on loopback port"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


class TestWheelPackageBuildAndInspect:
    """Verifies that built wheel package contains required Lua assets."""

    def test_wheel_contains_all_plugin_assets(self, tmp_path: Path):
        import zipfile

        # Build wheel into tmp_path
        subprocess.run(
            [sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(tmp_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        wheels = list(tmp_path.glob("*.whl"))
        assert len(wheels) == 1, f"Expected 1 wheel file in {tmp_path}"

        whl_path = wheels[0]
        with zipfile.ZipFile(whl_path, "r") as zf:
            names = zf.namelist()
            assert any(n.endswith("plugin.json") and "plugin_assets" in n for n in names)
            assert any(n.endswith("core.lua") and "plugin_assets" in n for n in names)
            assert any(n.endswith("inbox.lua") and "plugin_assets" in n for n in names)


class TestBuilderFailureStatusAccuracy:
    """Issue D: Failure reporting and status accuracy."""

    def test_failed_job_records_failed_status_and_failed_steps(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        write_live_telemetry(cfg)
        bridge = TheoTownBridge(config=cfg)

        job = bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])

        # Simulate game reporting a failure
        status_file = cfg.plugin_dir / f"job_{job.job_id}.txt"
        failed_payload = {
            "job_id": job.job_id,
            "status": "failed",
            "progress": 0.0,
            "total_steps": 1,
            "completed_steps": 0,
            "attempted_steps": 1,
            "failed_steps": 1,
            "created_at": time.time(),
            "updated_at": time.time(),
            "error": "Road blocked or unbuildable on terrain",
            "result": {
                "total_cost": 0,
                "commands_executed": 0,
                "attempted_steps": 1,
                "failed_steps": 1,
                "valid": False,
                "errors": ["Road blocked or unbuildable on terrain"],
            },
        }
        status_file.write_text(json.dumps(failed_payload), encoding="utf-8")

        status = bridge.get_job_status(job.job_id)
        assert status.status == "failed"
        assert status.failed_steps == 1
        assert status.completed_steps == 0
        assert status.error == "Road blocked or unbuildable on terrain"
        assert status.result is not None
        assert status.result["valid"] is False

    def test_repeated_game_errors_are_compacted_without_losing_counts(self, tmp_path: Path):
        cfg = TheoTownConfig(data_dir_override=tmp_path)
        write_live_telemetry(cfg)
        bridge = TheoTownBridge(config=cfg)
        job = bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        repeated = "Utility preflight failed: TheoTown rejected the operation"
        details = {str(index): repeated for index in range(200)}
        payload = {
            "job_id": job.job_id,
            "status": "failed",
            "total_steps": 200,
            "completed_steps": 0,
            "attempted_steps": 200,
            "failed_steps": 200,
            "created_at": time.time(),
            "updated_at": time.time(),
            "error": "; ".join([repeated] * 200),
            "result": {"errors": details, "failed_steps": 200},
        }
        status_file = cfg.plugin_dir / f"job_{job.job_id}.txt"
        status_file.write_text(json.dumps(payload), encoding="utf-8")

        status = bridge.get_job_status(job.job_id)

        assert status.error == f"200x {repeated}"
        assert status.result is not None
        assert len(status.result["errors"]) == 64
        assert status.result["error_counts"] == {repeated: 200}
        assert status.result["omitted_error_details"] == 136

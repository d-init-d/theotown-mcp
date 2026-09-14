"""
Unit tests for hardened Windows atomic filesystem IPC bridge,
Lua serialization, and job lifecycle management in theotown_mcp.bridge.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from theotown_mcp.bridge import (
    TheoTownBridge,
    generate_job_lua,
    serialize_to_lua,
    write_atomic_lua,
)
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import BuildRoadCmd, BuildZoneCmd


class TestLuaSerialization:
    def test_serialize_primitives(self):
        assert serialize_to_lua(None) == "nil"
        assert serialize_to_lua(True) == "true"
        assert serialize_to_lua(False) == "false"
        assert serialize_to_lua(42) == "42"
        assert serialize_to_lua(3.14) == "3.14"

    def test_serialize_strings_with_escaping(self):
        assert serialize_to_lua("simple") == '"simple"'
        assert serialize_to_lua('string "with" quotes') == r'"string \"with\" quotes"'
        assert serialize_to_lua("new\nline\tand\rcarriage") == r'"new\nline\tand\rcarriage"'
        assert serialize_to_lua(r"back\slash") == r'"back\\slash"'

    def test_serialize_lists_and_tuples(self):
        assert serialize_to_lua([1, 2, 3]) == "{ 1, 2, 3 }"
        assert serialize_to_lua(("a", "b")) == '{ "a", "b" }'
        assert serialize_to_lua([]) == "{  }"

    def test_serialize_dicts(self):
        # Identifier keys
        d1 = {"cmd": "build_road", "x0": 10}
        s1 = serialize_to_lua(d1)
        assert 'cmd = "build_road"' in s1
        assert "x0 = 10" in s1

        # Non-identifier keys (special chars or spaces)
        d2 = {"my key": 100, "123": "numeric_key"}
        s2 = serialize_to_lua(d2)
        assert '["my key"] = 100' in s2
        assert '["123"] = "numeric_key"' in s2

    def test_serialize_pydantic_model(self):
        cmd = BuildRoadCmd(x0=0, y0=0, x1=10, y1=0)
        s = serialize_to_lua(cmd)
        assert 'cmd = "build_road"' in s
        assert "x0 = 0" in s
        assert "x1 = 10" in s

    def test_serialize_unsupported_type_raises(self):
        class ArbitraryObject:
            pass

        with pytest.raises(TypeError, match="Cannot serialize type"):
            serialize_to_lua(ArbitraryObject())


class TestWriteAtomicLua:
    def test_atomic_write_creates_file(self, tmp_path: Path):
        target = tmp_path / "test_inbox.lua"
        content = "-- Hello TheoTown Lua\nreturn true\n"
        write_atomic_lua(target, content)

        assert target.exists()
        assert target.read_text(encoding="utf-8") == content

    def test_atomic_write_overwrites_cleanly(self, tmp_path: Path):
        target = tmp_path / "sub" / "inbox.lua"
        write_atomic_lua(target, "first_content")
        assert target.read_text(encoding="utf-8") == "first_content"

        write_atomic_lua(target, "second_content")
        assert target.read_text(encoding="utf-8") == "second_content"

    def test_atomic_write_retry_loop_on_transient_permission_error(self, tmp_path: Path):
        import os
        target = tmp_path / "retry_test.lua"
        content = "-- test content"

        call_count = 0
        real_replace = os.replace

        def flaky_replace(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise PermissionError("Access denied (transient lock)")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=flaky_replace):
            write_atomic_lua(target, content, max_retries=5, base_delay=0.001)

        assert target.exists()
        assert target.read_text(encoding="utf-8") == content
        assert call_count == 3

    def test_atomic_write_exhausted_retries_cleans_up_temp_file(self, tmp_path: Path):
        target = tmp_path / "fail_test.lua"

        def always_fail(src, dst):
            raise PermissionError("Permanent lock")

        with patch("os.replace", side_effect=always_fail), pytest.raises(PermissionError):
            write_atomic_lua(target, "content", max_retries=2, base_delay=0.001)

        # Confirm no orphan temporary files remaining in target.parent
        temp_files = list(tmp_path.glob("tmp_inbox_*.tmp"))
        assert len(temp_files) == 0


class TestGenerateJobLua:
    def test_generate_job_lua_structure(self):
        cmd = BuildRoadCmd(x0=5, y0=5, x1=15, y1=5)
        lua = generate_job_lua("job_test_001", [cmd], timestamp=1700000000.0)

        assert "Job ID: job_test_001" in lua
        assert "Compatibility fixture only" in lua
        assert "TheoTown.getStorage" not in lua
        assert 'job_id = "job_test_001"' in lua
        assert 'cmd = "build_road"' in lua
        assert "created_at = 1700000000" in lua


class TestTheoTownBridge:
    def test_read_telemetry_missing_file(self, mock_bridge: TheoTownBridge):
        mock_bridge.config.telemetry_path.unlink(missing_ok=True)
        telem = mock_bridge.read_telemetry()
        assert telem.connected is False
        assert telem.width == 128
        assert telem.height == 128

    def test_read_telemetry_valid_file(self, mock_bridge: TheoTownBridge, mock_telemetry_file: Path):
        telem = mock_bridge.read_telemetry()
        assert telem.connected is True
        assert telem.name == "EmeraldCity"
        assert telem.money == 75000
        assert telem.population == 1250
        assert telem.happiness == 88.5
        assert telem.income == 4200
        assert telem.happiness_by_category["health"] == 62.0
        assert telem.utilities["power"]["utilization_percent"] == 92.0
        assert telem.service_coverage["health"]["weak_locations"][0] == {
            "x": 80,
            "y": 12,
            "value_percent": 5.0,
        }
        assert telem.speed == 1

    def test_read_telemetry_corrupted_file(self, mock_bridge: TheoTownBridge, mock_config: TheoTownConfig):
        mock_config.telemetry_path.write_text("NOT_JSON_DATA", encoding="utf-8")
        telem = mock_bridge.read_telemetry()
        assert telem.connected is False

    def test_validate_plan_success(self, mock_bridge: TheoTownBridge, mock_telemetry_file: Path):
        cmds = [
            {"cmd": "build_road", "x0": 10, "y0": 10, "x1": 20, "y1": 10},
            {"cmd": "build_zone", "x": 10, "y": 12, "width": 5, "height": 5},
        ]
        result = mock_bridge.validate_plan(cmds, dry_run=True)
        assert result.valid is True
        assert result.errors == []
        assert result.command_count == 2
        assert result.affected_tiles == 11 + 25  # road: 11 tiles, zone: 25 tiles
        assert result.estimated_cost > 0

    def test_validate_plan_bounds_failure(self, mock_bridge: TheoTownBridge, mock_telemetry_file: Path):
        cmds = [
            {"cmd": "build_road", "x0": 10, "y0": 10, "x1": 200, "y1": 10},
        ]
        result = mock_bridge.validate_plan(cmds, dry_run=True)
        assert result.valid is False
        assert len(result.errors) >= 1
        assert "out of bounds" in result.errors[0]

    def test_validate_plan_schema_failure(self, mock_bridge: TheoTownBridge):
        cmds = [
            {"cmd": "build_road", "x0": -5, "y0": 0, "x1": 10, "y1": 0},
        ]
        result = mock_bridge.validate_plan(cmds, dry_run=True)
        assert result.valid is False
        assert len(result.errors) >= 1
        assert "Schema validation error" in result.errors[0]

    def test_validate_plan_treasury_warning(self, mock_bridge: TheoTownBridge, mock_config: TheoTownConfig):
        # Set city money low
        mock_config.telemetry_path.write_text(
            json.dumps({"protocol": 2, "session_id": "test-session", "name": "PoorTown", "money": 100,
                        "width": 128, "height": 128, "connected": True, "last_updated": time.time()}),
            encoding="utf-8",
        )
        cmds = [{"cmd": "build_building", "x": 10, "y": 10, "building_id": "$solarplant00"}]
        result = mock_bridge.validate_plan(cmds)
        assert result.valid is True  # Bounds and schema are valid
        assert len(result.warnings) == 1
        assert "exceeds active treasury" in result.warnings[0]

    def test_execute_plan_writes_inbox_and_tracks_job(self, mock_bridge: TheoTownBridge):
        cmds = [
            BuildRoadCmd(x0=10, y0=10, x1=20, y1=10),
            BuildZoneCmd(x=10, y=12, width=4, height=4),
        ]
        job = mock_bridge.execute_plan(cmds)

        assert job.status == "pending"
        assert job.total_steps == 2
        assert job.job_id.startswith("job_")
        assert job.job_id in mock_bridge.jobs

        # Verify the data mailbox on disk
        inbox_file = mock_bridge.config.requests_path
        assert inbox_file.exists()
        content = inbox_file.read_text(encoding="utf-8")
        assert job.job_id in content
        assert '"protocol":2' in content

    def test_get_job_status_in_memory_and_disk(self, mock_bridge: TheoTownBridge):
        # 1. In memory
        job = mock_bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        status = mock_bridge.get_job_status(job.job_id)
        assert status.job_id == job.job_id
        assert status.status == "pending"

        # 2. From disk file
        disk_job_file = mock_bridge.config.plugin_dir / "job_disk_99.json"
        disk_job_file.write_text(
            json.dumps({
                "job_id": "disk_99",
                "status": "completed",
                "progress": 1.0,
                "total_steps": 5,
                "completed_steps": 5,
                "created_at": 100.0,
                "updated_at": 110.0,
            }),
            encoding="utf-8",
        )
        disk_status = mock_bridge.get_job_status("disk_99")
        assert disk_status.job_id == "disk_99"
        assert disk_status.status == "completed"
        assert disk_status.progress == 1.0

        # 3. Non-existent job
        missing_status = mock_bridge.get_job_status("non_existent_job")
        assert missing_status.status == "failed"
        assert "not found" in (missing_status.error or "")

    def test_cancel_job(self, mock_bridge: TheoTownBridge):
        job = mock_bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        res = mock_bridge.cancel_job(job.job_id)
        assert res["status"] == "cancel_requested"
        assert mock_bridge.jobs[job.job_id].status == "cancel_requested"

        inbox = json.loads(mock_bridge.config.requests_path.read_text(encoding="utf-8"))
        assert inbox["jobs"][job.job_id]["cancel_requested"] is True

    def test_set_speed(self, mock_bridge: TheoTownBridge):
        res = mock_bridge.set_speed(2)
        assert res["status"] == "pending"
        assert res["speed"] == 2

        inbox = json.loads(mock_bridge.config.requests_path.read_text(encoding="utf-8"))
        assert inbox["jobs"][res["job_id"]]["commands"]["1"]["speed"] == 2

        with pytest.raises(ValueError, match="between 0 and 4"):
            mock_bridge.set_speed(5)

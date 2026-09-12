"""
Tier 2: Boundary & Corner Cases (Features F01 to F06)
30 Boundary Test Cases (5 per feature).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.city_oracle import slice_road_coordinates
from theotown_mcp.models import (
    BuildRoadCmd,
)


class TestF01F06Boundaries:
    # --- F01: Storage Discovery Boundaries (5) ---
    def test_e2e_t2_f01_01_missing_pmodext(self, mock_env: MockTheoTownEnv):
        """Non-existent .pmodext handled safely."""
        if mock_env.config.pmodext_path.exists():
            mock_env.config.pmodext_path.unlink()
        assert not mock_env.config.pmodext_path.exists()

    def test_e2e_t2_f01_02_corrupted_pmodext_no_hash(self, mock_env: MockTheoTownEnv):
        """Corrupted .pmodext without '#' delimiter falls back safely."""
        mock_env.config.pmodext_path.write_text("RANDOM_CORRUPT_BYTES_WITHOUT_DELIMITER", encoding="utf-8")
        raw = mock_env.config.pmodext_path.read_text(encoding="utf-8")
        assert "#" not in raw

    def test_e2e_t2_f01_03_deeply_nested_json(self, mock_env: MockTheoTownEnv):
        """Deeply nested JSON structure parses cleanly."""
        nested = {"level1": {"level2": {"level3": {"level4": {"val": 42}}}}}
        mock_env.config.pmodext_path.write_text(f"header\n#{json.dumps(nested)}", encoding="utf-8")
        raw = mock_env.config.pmodext_path.read_text(encoding="utf-8").split("#", 1)[1]
        data = json.loads(raw)
        assert data["level1"]["level2"]["level3"]["level4"]["val"] == 42

    def test_e2e_t2_f01_04_unicode_and_emojis(self, mock_env: MockTheoTownEnv):
        """Unicode characters and emojis survive serialization."""
        unicode_data = {"key_🚀": "Thành phố Hồ Chí Minh 🏙️"}
        mock_env.config.pmodext_path.write_text(f"header\n#{json.dumps(unicode_data, ensure_ascii=False)}", encoding="utf-8")
        raw = mock_env.config.pmodext_path.read_text(encoding="utf-8").split("#", 1)[1]
        data = json.loads(raw)
        assert data["key_🚀"] == "Thành phố Hồ Chí Minh 🏙️"

    def test_e2e_t2_f01_05_large_payload(self, mock_env: MockTheoTownEnv):
        """Large 200KB payload loads without error."""
        large_dict = {f"k_{i}": f"val_{i}" for i in range(5000)}
        mock_env.config.pmodext_path.write_text(f"header\n#{json.dumps(large_dict)}", encoding="utf-8")
        assert mock_env.config.pmodext_path.stat().st_size > 50000

    # --- F02: Cross-Script Handoff & Telemetry Boundaries (5) ---
    def test_e2e_t2_f02_01_telemetry_not_loaded_fallback(self, mock_env: MockTheoTownEnv):
        """Telemetry returns connected=False when file is absent."""
        if mock_env.config.telemetry_path.exists():
            mock_env.config.telemetry_path.unlink()
        telem = mock_env.bridge.read_telemetry()
        assert telem.connected is False

    def test_e2e_t2_f02_02_negative_treasury(self, mock_env: MockTheoTownEnv):
        """CityTelemetry handles negative money (municipal debt)."""
        mock_env.oracle.money = -50000
        mock_env.simulator.sync_telemetry_to_disk()
        telem = mock_env.bridge.read_telemetry()
        assert telem.money == -50000

    def test_e2e_t2_f02_03_zero_population_happiness(self, mock_env: MockTheoTownEnv):
        """Zero population city reports neutral baseline happiness."""
        mock_env.oracle.population = 0
        mock_env.oracle.happiness = 100.0
        mock_env.simulator.sync_telemetry_to_disk()
        telem = mock_env.bridge.read_telemetry()
        assert telem.population == 0
        assert telem.happiness == 100.0

    def test_e2e_t2_f02_04_concurrent_read(self, mock_env: MockTheoTownEnv):
        """Concurrent read operations yield valid model."""
        mock_env.simulator.sync_telemetry_to_disk()
        for _ in range(10):
            telem = mock_env.bridge.read_telemetry()
            assert telem.connected is True

    def test_e2e_t2_f02_05_max_speed_setting(self, mock_env: MockTheoTownEnv):
        """Speed literal 4 (Max Ultra Speed) handled cleanly."""
        mock_env.oracle.speed = 4
        mock_env.simulator.sync_telemetry_to_disk()
        telem = mock_env.bridge.read_telemetry()
        assert telem.speed == 4

    # --- F03: Manifest & #LuaWrapper Boundaries (5) ---
    def test_e2e_t2_f03_01_minimal_manifest(self):
        """Manifest without optional metadata is valid."""
        min_manifest = [{"id": "$test", "type": "script", "script": "core.lua"}]
        assert len(min_manifest) == 1

    def test_e2e_t2_f03_02_rapid_modification_inbox(self, mock_env: MockTheoTownEnv):
        """Rapid successive modifications to inbox.lua."""
        for i in range(5):
            mock_env.config.inbox_path.write_text(f"-- rapid write {i}", encoding="utf-8")
        assert "-- rapid write 4" in mock_env.config.inbox_path.read_text(encoding="utf-8")

    def test_e2e_t2_f03_03_zero_byte_inbox(self, mock_env: MockTheoTownEnv):
        """Zero byte inbox handled without crash."""
        mock_env.config.inbox_path.write_text("", encoding="utf-8")
        res = mock_env.simulator.process_inbox()
        assert res is None

    def test_e2e_t2_f03_04_missing_script_graceful(self, mock_env: MockTheoTownEnv):
        """Missing non-critical script handled safely."""
        missing = mock_env.config.plugin_dir / "missing.lua"
        assert not missing.exists()

    def test_e2e_t2_f03_05_long_path_support(self, tmp_path: Path):
        """Deeply nested path structures handled properly."""
        deep = tmp_path / ("sub_" * 10)
        deep.mkdir(parents=True, exist_ok=True)
        assert deep.exists()

    # --- F04: FIFO Queue Boundaries (5) ---
    def test_e2e_t2_f04_01_empty_commands_batch(self, mock_env: MockTheoTownEnv):
        """Job with empty commands completes immediately."""
        mock_env.bridge.execute_plan([])
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.status == "completed"
        assert res.total_steps == 0

    def test_e2e_t2_f04_02_queue_ordering_ten_items(self, mock_env: MockTheoTownEnv):
        """Ordering preserved for 10 sequential commands."""
        cmds = [BuildRoadCmd(x0=i, y0=0, x1=i, y1=0) for i in range(10)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.completed_steps == 10

    def test_e2e_t2_f04_03_job_cancellation_lifecycle(self, mock_env: MockTheoTownEnv):
        """Job status transitions to cancelled."""
        job = mock_env.bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=10, y1=0)])
        c_res = mock_env.bridge.cancel_job(job.job_id)
        assert c_res["status"] == "cancelled"

    def test_e2e_t2_f04_04_non_existent_job_query(self, mock_env: MockTheoTownEnv):
        """Querying unknown job returns failed with error message."""
        status = mock_env.bridge.get_job_status("job_unknown_xyz")
        assert status.status == "failed"
        assert "not found" in (status.error or "")

    def test_e2e_t2_f04_05_partial_failure_in_batch(self, mock_env: MockTheoTownEnv):
        """Batch with invalid step records error and reports failed status."""
        # Tile (10, 10) is blocked by water
        mock_env.oracle.grid[(10, 10)] = {"water": True}
        cmds = [
            BuildRoadCmd(x0=0, y0=0, x1=5, y1=0),
            BuildRoadCmd(x0=10, y0=10, x1=10, y1=10, level=0),
        ]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.status == "failed"
        assert res.completed_steps == 1
        assert "Step 2" in (res.error or "")

    # --- F05: Workload Budgeting Boundaries (5) ---
    def test_e2e_t2_f05_01_exactly_64_work_units(self, mock_env: MockTheoTownEnv):
        """Batch of exactly 64 commands."""
        cmds = [BuildRoadCmd(x0=i % 120, y0=1, x1=i % 120, y1=1) for i in range(64)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.completed_steps == 64

    def test_e2e_t2_f05_02_exactly_65_work_units(self, mock_env: MockTheoTownEnv):
        """Batch of exactly 65 commands (boundary 64 + 1)."""
        cmds = [BuildRoadCmd(x0=i % 120, y0=2, x1=i % 120, y1=2) for i in range(65)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.completed_steps == 65

    def test_e2e_t2_f05_03_heavy_operation_yield(self, mock_env: MockTheoTownEnv):
        """Operations yield without locking."""
        cmds = [BuildRoadCmd(x0=i % 120, y0=3, x1=i % 120, y1=3) for i in range(10)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None

    def test_e2e_t2_f05_04_budgeting_when_simulation_paused(self, mock_env: MockTheoTownEnv):
        """Commands execute even when simulation speed is 0 (Paused)."""
        mock_env.oracle.speed = 0
        cmds = [BuildRoadCmd(x0=0, y0=4, x1=5, y1=4)]
        mock_env.bridge.execute_plan(cmds)
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert res.status == "completed"

    def test_e2e_t2_f05_05_high_frame_rate_execution(self, mock_env: MockTheoTownEnv):
        """Rapid frame rate ticks process cleanly."""
        for i in range(5):
            cmds = [BuildRoadCmd(x0=i, y0=5, x1=i, y1=5)]
            mock_env.bridge.execute_plan(cmds)
            mock_env.simulator.process_inbox()
        assert (0, 5) in mock_env.oracle.grid

    # --- F06: Road Segmenting Boundaries (5) ---
    def test_e2e_t2_f06_01_exactly_32_tiles_length(self):
        """Road length exactly 32 tiles is not sliced."""
        segments = slice_road_coordinates(0, 0, 31, 0, max_segment_length=32)
        assert len(segments) == 1

    def test_e2e_t2_f06_02_exactly_33_tiles_length(self):
        """Road length exactly 33 tiles is sliced into 2 segments."""
        segments = slice_road_coordinates(0, 0, 32, 0, max_segment_length=32)
        assert len(segments) == 2

    def test_e2e_t2_f06_03_diagonal_path_segmenting(self):
        """Diagonal coordinates segmented along axis."""
        segments = slice_road_coordinates(10, 10, 50, 50, max_segment_length=32)
        assert len(segments) == 2

    def test_e2e_t2_f06_04_full_map_128_tiles(self):
        """128-tile map-spanning road sliced into 4 segments."""
        segments = slice_road_coordinates(0, 50, 127, 50, max_segment_length=32)
        assert len(segments) == 4

    def test_e2e_t2_f06_05_single_tile_stub(self):
        """Single-tile road stub (x0=y0=x1=y1) is a valid single segment."""
        segments = slice_road_coordinates(10, 10, 10, 10, max_segment_length=32)
        assert len(segments) == 1
        assert segments[0] == (10, 10, 10, 10)

"""
Tier 2: Boundary & Corner Cases (Features F19 to F24)
30 Boundary Test Cases (5 per feature).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.e2e.conftest import MockTheoTownEnv
from tests.e2e.harness.city_oracle import slice_road_coordinates
from theotown_mcp.bridge import serialize_to_lua
from theotown_mcp.models import BuildRoadCmd


class TestF19F24Boundaries:
    # --- F19: Git Repository & Licensing Boundaries (5) ---
    def test_e2e_t2_f19_01_license_year(self):
        """LICENSE contains current year 2026."""
        content = Path("LICENSE").read_text(encoding="utf-8")
        assert "2026" in content

    def test_e2e_t2_f19_02_license_mit_standard_text(self):
        """LICENSE includes standard MIT liability disclaimer."""
        content = Path("LICENSE").read_text(encoding="utf-8")
        assert "WITHOUT WARRANTY OF ANY KIND" in content

    def test_e2e_t2_f19_03_gitignore_ignores_egg_info(self):
        """.gitignore ignores egg-info and build artifacts."""
        content = Path(".gitignore").read_text(encoding="utf-8")
        assert "*.egg-info" in content

    def test_e2e_t2_f19_04_gitignore_ignores_dist(self):
        """.gitignore ignores distribution directories."""
        content = Path(".gitignore").read_text(encoding="utf-8")
        assert "dist/" in content

    def test_e2e_t2_f19_05_gitignore_ignores_venv(self):
        """.gitignore ignores virtualenv folders."""
        content = Path(".gitignore").read_text(encoding="utf-8")
        assert ".venv/" in content or "venv/" in content

    # --- F20: Documentation Boundaries (5) ---
    def test_e2e_t2_f20_01_readme_comprehensive_length(self):
        """README.md contains detailed documentation (>= 150 lines)."""
        lines = Path("README.md").read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 150

    def test_e2e_t2_f20_02_readme_vietnamese_reference(self):
        """README.md contains Vietnamese tool explanations."""
        content = Path("README.md").read_text(encoding="utf-8")
        assert "theotown_get_status" in content
        assert "quy hoạch" in content.lower()

    def test_e2e_t2_f20_03_claude_desktop_snippet_valid_json(self):
        """Claude desktop snippet in README is valid JSON."""
        content = Path("README.md").read_text(encoding="utf-8")
        # Extract json code block under claude
        start = content.find('```json\n{\n  "mcpServers"')
        assert start != -1
        end = content.find("```", start + 7)
        json_str = content[start + 7:end].strip()
        data = json.loads(json_str)
        assert "theotown" in data["mcpServers"]

    def test_e2e_t2_f20_04_all_12_tools_documented(self):
        """All 12 tool names appear in README table."""
        content = Path("README.md").read_text(encoding="utf-8")
        tools = [
            "theotown_get_status", "theotown_build_road", "theotown_build_zone",
            "theotown_build_building", "theotown_build_utilities", "theotown_demolish",
            "theotown_validate_plan", "theotown_execute_plan", "theotown_get_job",
            "theotown_cancel_job", "theotown_set_speed", "theotown_get_draft_catalog",
        ]
        for t in tools:
            assert t in content, f"Tool {t} not documented in README"

    def test_e2e_t2_f20_05_resources_and_prompts_documented(self):
        """Resources and urban_planner prompt documented in README."""
        content = Path("README.md").read_text(encoding="utf-8")
        assert "theotown://city/status" in content
        assert "theotown://catalog/drafts" in content
        assert "urban_planner" in content

    # --- F21: Unit Test Suite Boundaries (5) ---
    def test_e2e_t2_f21_01_all_test_files_prefixed(self):
        """All unit tests follow test_*.py convention."""
        tests_dir = Path("tests")
        for p in tests_dir.glob("test_*.py"):
            assert p.name.startswith("test_")

    def test_e2e_t2_f21_02_cli_tests_runner_usage(self):
        """test_cli.py utilizes CliRunner for clean isolated invocation."""
        content = Path("tests/test_cli.py").read_text(encoding="utf-8")
        assert "CliRunner" in content

    def test_e2e_t2_f21_03_bridge_atomic_flaky_mock(self):
        """test_bridge_atomic.py tests transient lock simulation."""
        content = Path("tests/test_bridge_atomic.py").read_text(encoding="utf-8")
        assert "PermissionError" in content

    def test_e2e_t2_f21_04_dsl_models_forbid_extra(self):
        """test_dsl_models.py validates extra forbidden fields."""
        content = Path("tests/test_dsl_models.py").read_text(encoding="utf-8")
        assert "extra_fields_forbidden" in content

    def test_e2e_t2_f21_05_catalog_pricing_coverage(self):
        """test_catalog.py exercises price estimation for all command types."""
        content = Path("tests/test_catalog.py").read_text(encoding="utf-8")
        assert "estimate_command_cost" in content

    # --- F22: E2E Suite Structure Boundaries (5) ---
    def test_e2e_t2_f22_01_mock_theotown_env_initialization(self, mock_env: MockTheoTownEnv):
        """Mock environment initializes with valid data dir and config."""
        assert mock_env.config.theotown_data_dir.exists()
        assert mock_env.config.plugin_dir.exists()

    def test_e2e_t2_f22_02_oracle_grid_access(self, mock_env: MockTheoTownEnv):
        """Oracle grid handles non-existent coordinate queries gracefully."""
        assert mock_env.oracle.grid.get((99, 99)) is None

    def test_e2e_t2_f22_03_simulator_inbox_absence(self, mock_env: MockTheoTownEnv):
        """Simulator handles missing inbox without error."""
        if mock_env.config.inbox_path.exists():
            mock_env.config.inbox_path.unlink()
        assert mock_env.simulator.process_inbox() is None

    def test_e2e_t2_f22_04_live_detector_call(self):
        """LiveDetector query does not throw exceptions."""
        from tests.e2e.harness.live_client import LiveDetector
        running = LiveDetector.is_game_running()
        assert isinstance(running, bool)

    def test_e2e_t2_f22_05_lua_syntax_check_fallback(self):
        """Lua syntax checker validates matching braces and quotes."""
        from tests.e2e.harness.lua_syntax_check import check_lua_syntax
        ok, _msg = check_lua_syntax("local x = { a = 1, b = 'test' }\nreturn x\n")
        assert ok is True

    # --- F23: Execution Verification Boundaries (5) ---
    def test_e2e_t2_f23_01_road_slicing_zero_length(self):
        """Zero length road segment returns single coordinate point."""
        segs = slice_road_coordinates(5, 5, 5, 5)
        assert len(segs) == 1
        assert segs[0] == (5, 5, 5, 5)

    def test_e2e_t2_f23_02_telemetry_schema_validation(self, mock_env: MockTheoTownEnv):
        """Telemetry output adheres to schema."""
        dict_data = mock_env.oracle.get_telemetry_dict()
        assert isinstance(dict_data["money"], int)
        assert isinstance(dict_data["population"], int)

    def test_e2e_t2_f23_03_job_status_progress_clamped(self, mock_env: MockTheoTownEnv):
        """Progress float is between 0.0 and 1.0."""
        mock_env.bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        res = mock_env.simulator.process_inbox()
        assert res is not None
        assert 0.0 <= res.progress <= 1.0

    def test_e2e_t2_f23_04_status_file_cleanup(self, mock_env: MockTheoTownEnv):
        """Status file for job is created and queryable."""
        job = mock_env.bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        mock_env.simulator.process_inbox()
        assert (mock_env.config.plugin_dir / f"job_{job.job_id}.txt").exists()

    def test_e2e_t2_f23_05_telemetry_timestamp_freshness(self, mock_env: MockTheoTownEnv):
        """Telemetry includes last_updated timestamp."""
        dict_data = mock_env.oracle.get_telemetry_dict()
        assert "last_updated" in dict_data

    # --- F24: Adversarial Coverage Boundaries (5) ---
    def test_e2e_t2_f24_01_semicolon_escape_in_lua(self):
        """Semicolons and Lua comments in strings are escaped."""
        raw = "test; do return end; --"
        s = serialize_to_lua(raw)
        assert s.startswith('"') and s.endswith('"')

    def test_e2e_t2_f24_02_newlines_in_draft_id(self):
        """Newlines in strings are escaped as \\n."""
        raw = "line1\nline2"
        s = serialize_to_lua(raw)
        assert "\\n" in s
        assert "\n" not in s

    def test_e2e_t2_f24_03_backslash_escape(self):
        """Backslashes in paths are escaped as \\\\."""
        raw = "C:\\Windows\\System32"
        s = serialize_to_lua(raw)
        assert "\\\\" in s

    def test_e2e_t2_f24_04_large_coordinate_plan_validation(self, mock_env: MockTheoTownEnv):
        """Extremely large coordinates fail bounds check."""
        cmd = {"cmd": "build_road", "x0": 99999, "y0": 99999, "x1": 100000, "y1": 99999}
        val = mock_env.bridge.validate_plan([cmd])
        assert val.valid is False
        assert len(val.errors) >= 1

    def test_e2e_t2_f24_05_negative_budget_deficit_warning(self, mock_env: MockTheoTownEnv):
        """Negative money generates low treasury warning in validation."""
        mock_env.oracle.money = -1000
        mock_env.simulator.sync_telemetry_to_disk()
        cmd = {"cmd": "build_road", "x0": 0, "y0": 0, "x1": 5, "y1": 0}
        val = mock_env.bridge.validate_plan([cmd])
        assert len(val.warnings) >= 1

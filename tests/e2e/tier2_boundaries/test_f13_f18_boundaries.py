"""
Tier 2: Boundary & Corner Cases (Features F13 to F18)
30 Boundary Test Cases (5 per feature).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click import unstyle
from typer.testing import CliRunner

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.cli import app
from theotown_mcp.config import TheoTownConfig
from theotown_mcp.models import BuildRoadCmd, DemolishCmd


class TestF13F18Boundaries:
    # --- F13: Auto-Config Boundaries (5) ---
    def test_e2e_t2_f13_01_trailing_slashes(self):
        """Path with trailing slashes is normalized cleanly."""
        cfg = TheoTownConfig(data_dir_override=Path("C:/TheoTownData///"))
        assert cfg.theotown_data_dir == Path("C:/TheoTownData")

    def test_e2e_t2_f13_02_drive_root(self):
        """Drive root path handled safely."""
        cfg = TheoTownConfig(data_dir_override=Path("D:/"))
        assert cfg.plugin_dir == Path("D:/plugins/theotown_mcp")

    def test_e2e_t2_f13_03_relative_path(self):
        """Relative path resolution."""
        cfg = TheoTownConfig(data_dir_override=Path("./local_theotown"))
        assert cfg.theotown_data_dir == Path("./local_theotown")

    def test_e2e_t2_f13_04_ensure_directories_idempotent(self, tmp_path: Path):
        """ensure_directories can be called repeatedly without error."""
        cfg = TheoTownConfig(data_dir_override=tmp_path / "TT")
        cfg.ensure_directories()
        cfg.ensure_directories()
        assert cfg.plugin_dir.exists()

    def test_e2e_t2_f13_05_path_properties_memoization(self):
        """Path properties evaluate consistently."""
        cfg = TheoTownConfig(data_dir_override=Path("C:/Test"))
        assert cfg.inbox_path == cfg.inbox_path

    # --- F14: Draft Catalog Boundaries (5) ---
    def test_e2e_t2_f14_01_alias_mixed_case(self, mock_env: MockTheoTownEnv):
        """Mixed-case alias resolution."""
        assert mock_env.catalog.resolve_draft_id("Two_Lane_Road") == "$road00"

    def test_e2e_t2_f14_02_alias_leading_trailing_spaces(self, mock_env: MockTheoTownEnv):
        """Spaces in alias cleaned before lookup."""
        assert mock_env.catalog.resolve_draft_id("  solar  ") == "$solarplant00"

    def test_e2e_t2_f14_03_unknown_alias_returns_raw(self, mock_env: MockTheoTownEnv):
        """Unregistered identifier returned as-is."""
        assert mock_env.catalog.resolve_draft_id("custom_road_99") == "custom_road_99"

    def test_e2e_t2_f14_04_demolish_price_boundary(self, mock_env: MockTheoTownEnv):
        """1x1 demolish cost equals 5."""
        cmd = DemolishCmd(x=0, y=0, width=1, height=1)
        assert mock_env.catalog.estimate_command_cost(cmd) == 5

    def test_e2e_t2_f14_05_search_special_characters(self, mock_env: MockTheoTownEnv):
        """Search query with regex special chars ($ or .) handled safely."""
        res = mock_env.catalog.search_drafts(query="$road")
        assert len(res) >= 4

    # --- F15: Hardened Atomic Bridge Boundaries (5) ---
    def test_e2e_t2_f15_01_empty_string_write(self, tmp_path: Path):
        """Writing empty string payload."""
        from theotown_mcp.bridge import write_atomic_lua
        target = tmp_path / "inbox.lua"
        write_atomic_lua(target, "")
        assert target.exists()
        assert target.read_text(encoding="utf-8") == ""

    def test_e2e_t2_f15_02_unicode_payload_write(self, tmp_path: Path):
        """Writing UTF-8 Unicode characters atomically."""
        from theotown_mcp.bridge import write_atomic_lua
        target = tmp_path / "inbox.lua"
        write_atomic_lua(target, "-- Tiếng Việt: Thành phố xanh\n")
        assert "Thành phố xanh" in target.read_text(encoding="utf-8")

    def test_e2e_t2_f15_03_high_retry_configuration(self, tmp_path: Path):
        """Configuring high retry count (max_retries=10)."""
        from theotown_mcp.bridge import write_atomic_lua
        target = tmp_path / "inbox.lua"
        write_atomic_lua(target, "-- high retry", max_retries=10, base_delay=0.001)
        assert target.exists()

    def test_e2e_t2_f15_04_creates_missing_parent_directories(self, tmp_path: Path):
        """Atomic write creates missing deep parent directories automatically."""
        from theotown_mcp.bridge import write_atomic_lua
        target = tmp_path / "deep" / "nested" / "inbox.lua"
        write_atomic_lua(target, "-- nested")
        assert target.exists()

    def test_e2e_t2_f15_05_no_temp_file_leakage(self, tmp_path: Path):
        """Zero temporary files remain after successful write."""
        from theotown_mcp.bridge import write_atomic_lua
        target = tmp_path / "inbox.lua"
        write_atomic_lua(target, "-- test clean")
        temps = list(tmp_path.glob("tmp_inbox_*.tmp"))
        assert len(temps) == 0

    # --- F16: MCP Tools Boundaries (5) ---
    @pytest.mark.anyio
    async def test_e2e_t2_f16_01_max_coordinates_tool(self, mock_env: MockTheoTownEnv):
        """Tool handles coordinates up to map boundary."""
        res = await mock_env.server.call_tool("theotown_build_road", {"x0": 126, "y0": 10, "x1": 127, "y1": 10})
        assert res.is_error is False

    @pytest.mark.anyio
    async def test_e2e_t2_f16_02_negative_coords_tool_rejected(self, mock_env: MockTheoTownEnv):
        """Tool call with negative coords raises error or validation failure."""
        from mcp.server.mcpserver.exceptions import UnexpectedToolError
        with pytest.raises(UnexpectedToolError):
            await mock_env.server.call_tool("theotown_build_road", {"x0": -1, "y0": 0, "x1": 5, "y1": 0})

    @pytest.mark.anyio
    async def test_e2e_t2_f16_03_cancel_completed_job_safe(self, mock_env: MockTheoTownEnv):
        """Cancelling an already completed job handled safely."""
        job = mock_env.bridge.execute_plan([BuildRoadCmd(x0=0, y0=0, x1=5, y1=0)])
        mock_env.simulator.process_inbox()
        res = await mock_env.server.call_tool("theotown_cancel_job", {"job_id": job.job_id})
        assert res.is_error is False

    @pytest.mark.anyio
    async def test_e2e_t2_f16_04_speed_bounds_tool(self, mock_env: MockTheoTownEnv):
        """Tool accepts speed 0 and speed 4."""
        res0 = await mock_env.server.call_tool("theotown_set_speed", {"speed": 0})
        assert res0.structured_content["speed"] == 0
        res4 = await mock_env.server.call_tool("theotown_set_speed", {"speed": 4})
        assert res4.structured_content["speed"] == 4

    @pytest.mark.anyio
    async def test_e2e_t2_f16_05_unknown_tool_rejection(self, mock_env: MockTheoTownEnv):
        """Calling unregistered tool raises ToolError."""
        from mcp.server.mcpserver.exceptions import ToolError
        with pytest.raises(ToolError):
            await mock_env.server.call_tool("theotown_nuclear_strike", {})

    # --- F17: MCP Resources & Prompts Boundaries (5) ---
    @pytest.mark.anyio
    async def test_e2e_t2_f17_01_unknown_resource_uri(self, mock_env: MockTheoTownEnv):
        """Unknown resource URI raises ResourceNotFoundError."""
        from mcp.server.mcpserver.exceptions import ResourceNotFoundError
        with pytest.raises(ResourceNotFoundError):
            await mock_env.server.read_resource("theotown://unknown/endpoint")

    @pytest.mark.anyio
    async def test_e2e_t2_f17_02_unknown_prompt_name(self, mock_env: MockTheoTownEnv):
        """Unknown prompt name raises ValueError."""
        with pytest.raises(ValueError):
            await mock_env.server.get_prompt("unknown_prompt_xyz", {})

    @pytest.mark.anyio
    async def test_e2e_t2_f17_03_prompt_with_empty_arguments(self, mock_env: MockTheoTownEnv):
        """Prompt call with empty dict succeeds."""
        res = await mock_env.server.get_prompt("urban_planner", {})
        assert len(res.messages) == 1

    @pytest.mark.anyio
    async def test_e2e_t2_f17_04_resource_mime_types(self, mock_env: MockTheoTownEnv):
        """Both resources return application/json mime type."""
        c1 = await mock_env.server.read_resource("theotown://city/status")
        c2 = await mock_env.server.read_resource("theotown://catalog/drafts")
        assert c1[0].mime_type == "application/json"
        assert c2[0].mime_type == "application/json"

    def test_e2e_t2_f17_05_prompt_instructions_content(self, mock_env: MockTheoTownEnv):
        """Urban planner prompt contains core planning rules."""
        from theotown_mcp.server import URBAN_PLANNER_PROMPT
        assert "Road Hierarchy" in URBAN_PLANNER_PROMPT
        assert "Budget Discipline" in URBAN_PLANNER_PROMPT

    # --- F18: Typer CLI Boundaries (5) ---
    def test_e2e_t2_f18_01_unknown_cli_command(self):
        """Unknown CLI subcommand raises error."""
        runner = CliRunner()
        res = runner.invoke(app, ["nonexistent-command"])
        assert res.exit_code != 0

    def test_e2e_t2_f18_02_probe_ipc_help(self):
        """probe-ipc --help outputs options."""
        runner = CliRunner()
        res = runner.invoke(app, ["probe-ipc", "--help"])
        assert res.exit_code == 0
        assert "--data-dir" in unstyle(res.output)

    def test_e2e_t2_f18_03_install_plugin_help(self):
        """install-plugin --help outputs options."""
        runner = CliRunner()
        res = runner.invoke(app, ["install-plugin", "--help"])
        assert res.exit_code == 0
        assert "--force" in unstyle(res.output)

    def test_e2e_t2_f18_04_run_help(self):
        """run --help outputs options."""
        runner = CliRunner()
        res = runner.invoke(app, ["run", "--help"])
        assert res.exit_code == 0
        output = unstyle(res.output)
        assert "--transport" in output
        assert "--port" in output

    def test_e2e_t2_f18_05_probe_ipc_non_existent_data_dir(self, tmp_path: Path):
        """probe-ipc against missing directory reports warning but does not crash."""
        runner = CliRunner()
        missing = tmp_path / "NonExistentTheoTown"
        res = runner.invoke(app, ["probe-ipc", "--data-dir", str(missing)])
        assert res.exit_code == 0
        assert "Data directory not found" in res.output

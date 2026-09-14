"""
Unit tests for Typer CLI subcommands in theotown_mcp.cli.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from theotown_mcp.cli import app

runner = CliRunner()


class TestCliCommands:
    def test_cli_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "probe-ipc" in result.output
        assert "install-plugin" in result.output
        assert "run" in result.output

    def test_module_entrypoint_does_not_import_cli_twice(self):
        result = subprocess.run(
            [sys.executable, "-m", "theotown_mcp.cli", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "RuntimeWarning" not in result.stderr

    def test_cli_probe_ipc_success(self, tmp_path: Path):
        mock_data = tmp_path / "TheoTown"
        mock_data.mkdir(parents=True, exist_ok=True)
        # Create .pmodext
        pmodext = mock_data / ".pmodext"
        pmodext.write_text("Last played: 123456\n#{\"test\": true}", encoding="utf-8")
        # Create prefs
        prefs = tmp_path / ".prefs" / "theotown"
        prefs.mkdir(parents=True, exist_ok=True)
        (prefs / "pref1.xml").write_text("<map></map>", encoding="utf-8")

        with patch.dict("os.environ", {"USERPROFILE": str(tmp_path)}):
            result = runner.invoke(app, ["probe-ipc", "--data-dir", str(mock_data)])
            assert result.exit_code == 0
            assert "Probing TheoTown installation" in result.output
            assert "Data directory exists" in result.output
            assert ".pmodext found" in result.output
            assert "Atomic filesystem write test: PASS" in result.output
            assert "Probe IPC diagnostics completed successfully" in result.output

    def test_cli_install_plugin(self, tmp_path: Path):
        mock_target_data = tmp_path / "TheoTownTarget"
        result = runner.invoke(
            app,
            ["install-plugin", "--data-dir", str(mock_target_data), "--force"],
        )
        assert result.exit_code == 0
        assert "Successfully installed plugin" in result.output

        plugin_dest = mock_target_data / "plugins" / "theotown_mcp"
        assert plugin_dest.exists()
        assert (plugin_dest / "plugin.json").exists()
        assert (plugin_dest / "core.lua").exists()
        assert (plugin_dest / "inbox.lua").exists()

    def test_cli_run_invalid_transport_rejected(self):
        result = runner.invoke(app, ["run", "--transport", "graphql"])
        assert result.exit_code == 1
        assert "Unknown transport 'graphql'" in result.output

    def test_cli_run_valid_transports(self):
        mock_srv = MagicMock()
        with patch("theotown_mcp.cli.create_server", return_value=mock_srv):
            # Test stdio invocation
            res_stdio = runner.invoke(app, ["run", "--transport", "stdio"])
            assert res_stdio.exit_code == 0
            mock_srv.run.assert_called_with(transport="stdio")

            # Test streamable http invocation
            res_http = runner.invoke(app, ["run", "--transport", "http", "--port", "9090", "--host", "0.0.0.0"])
            assert res_http.exit_code == 0
            mock_srv.run.assert_called_with(transport="streamable-http", host="0.0.0.0", port=9090)

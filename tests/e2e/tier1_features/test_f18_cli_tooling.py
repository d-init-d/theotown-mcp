"""
Tier 1: Feature F18 — Typer CLI Tooling
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from theotown_mcp.cli import app


class TestFeatureF18CLITooling:
    def test_e2e_t1_f18_01_cli_help(self):
        """CLI --help flag displays all subcommands."""
        runner = CliRunner()
        res = runner.invoke(app, ["--help"])
        assert res.exit_code == 0
        assert "probe-ipc" in res.output
        assert "install-plugin" in res.output
        assert "run" in res.output

    def test_e2e_t1_f18_02_cli_install_plugin(self, tmp_path: Path):
        """CLI install-plugin copies files into target directory."""
        runner = CliRunner()
        target = tmp_path / "TargetTheoTown"
        res = runner.invoke(app, ["install-plugin", "--data-dir", str(target), "--force"])
        assert res.exit_code == 0
        dest = target / "plugins" / "theotown_mcp"
        assert dest.exists()
        assert (dest / "plugin.json").exists()

    def test_e2e_t1_f18_03_cli_run_stdio(self):
        """CLI run with stdio transport."""
        runner = CliRunner()
        mock_srv = MagicMock()
        with patch("theotown_mcp.cli.create_server", return_value=mock_srv):
            res = runner.invoke(app, ["run", "--transport", "stdio"])
            assert res.exit_code == 0
            mock_srv.run.assert_called_with(transport="stdio")

    def test_e2e_t1_f18_04_cli_run_http(self):
        """CLI run with streamable-http transport."""
        runner = CliRunner()
        mock_srv = MagicMock()
        with patch("theotown_mcp.cli.create_server", return_value=mock_srv):
            res = runner.invoke(app, ["run", "--transport", "http", "--port", "8080"])
            assert res.exit_code == 0
            mock_srv.run.assert_called_with(transport="streamable-http", host="127.0.0.1", port=8080)

    def test_e2e_t1_f18_05_cli_invalid_transport(self):
        """CLI rejects invalid transport with code 1."""
        runner = CliRunner()
        res = runner.invoke(app, ["run", "--transport", "zmq"])
        assert res.exit_code == 1
        assert "Unknown transport" in res.output

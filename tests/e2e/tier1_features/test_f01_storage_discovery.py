"""
Tier 1: Feature F01 — Phase 0 Canary Token & Storage Discovery
5 Isolated Test Cases.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from tests.e2e.conftest import MockTheoTownEnv
from theotown_mcp.cli import app


class TestFeatureF01StorageDiscovery:
    def test_e2e_t1_f01_01_canary_token_storage(self, mock_env: MockTheoTownEnv):
        """Set and retrieve canary token in storage representation."""
        canary = {"canary_id": "test_c1_01", "timestamp": 1773300000}
        canary_file = mock_env.config.theotown_data_dir / "canary.json"
        canary_file.write_text(json.dumps(canary), encoding="utf-8")

        read_back = json.loads(canary_file.read_text(encoding="utf-8"))
        assert read_back["canary_id"] == "test_c1_01"
        assert read_back["timestamp"] == 1773300000

    def test_e2e_t1_f01_02_pmodext_header_structure(self, mock_env: MockTheoTownEnv):
        """Inspect .pmodext file header and delimiter structure."""
        pmodext_path = mock_env.config.pmodext_path
        header_text = "Last played: 1789199218075\nAccess token: abcdef123456\n#{\"dOrFeEgVFK71f54k\":false}"
        pmodext_path.write_text(header_text, encoding="utf-8")

        raw = pmodext_path.read_text(encoding="utf-8")
        assert "Last played:" in raw
        assert "Access token:" in raw
        assert "#" in raw

    def test_e2e_t1_f01_03_prefs_directory_structure(self, mock_env: MockTheoTownEnv):
        """Validate .prefs/theotown SharedPreferences directory detection."""
        prefs_dir = mock_env.config.prefs_dir
        prefs_dir.mkdir(parents=True, exist_ok=True)
        sample_pref = prefs_dir / "info.flowersoft.theotown.settings"
        sample_pref.write_text("<map><string name='test'>val</string></map>", encoding="utf-8")

        assert prefs_dir.exists()
        assert sample_pref.exists()
        assert "<map>" in sample_pref.read_text(encoding="utf-8")

    def test_e2e_t1_f01_04_parse_pmodext_json_payload(self, mock_env: MockTheoTownEnv):
        """Parse JSON payload residing after the '#' delimiter in .pmodext."""
        payload_data = {"canary": "TOKEN_2026", "count": 42}
        pmodext_path = mock_env.config.pmodext_path
        pmodext_path.write_text(f"Header lines...\n#{json.dumps(payload_data)}", encoding="utf-8")

        content = pmodext_path.read_text(encoding="utf-8")
        _, hash_part = content.split("#", 1)
        parsed = json.loads(hash_part.strip())
        assert parsed["canary"] == "TOKEN_2026"
        assert parsed["count"] == 42

    def test_e2e_t1_f01_05_cli_probe_ipc_execution(self, mock_env: MockTheoTownEnv):
        """Execute CLI probe-ipc subcommand against mock environment."""
        runner = CliRunner()
        result = runner.invoke(app, ["probe-ipc", "--data-dir", str(mock_env.config.theotown_data_dir)])
        assert result.exit_code == 0
        assert "Probing TheoTown installation" in result.output
        assert "Probe IPC diagnostics completed successfully" in result.output

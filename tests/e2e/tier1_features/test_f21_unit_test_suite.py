"""
Tier 1: Feature F21 — Automated Unit & Integration Tests
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path


class TestFeatureF21UnitTestSuite:
    def test_e2e_t1_f21_01_unit_test_files_exist(self):
        """Verify all 5 core unit test modules exist under tests/."""
        tests_dir = Path("tests")
        assert (tests_dir / "test_dsl_models.py").exists()
        assert (tests_dir / "test_bridge_atomic.py").exists()
        assert (tests_dir / "test_catalog.py").exists()
        assert (tests_dir / "test_mcp_server.py").exists()
        assert (tests_dir / "test_cli.py").exists()

    def test_e2e_t1_f21_02_conftest_exists(self):
        """tests/conftest.py exists and provides shared fixtures."""
        assert Path("tests/conftest.py").exists()
        content = Path("tests/conftest.py").read_text(encoding="utf-8")
        assert "mock_bridge" in content
        assert "mock_config" in content

    def test_e2e_t1_f21_03_dsl_models_suite_coverage(self):
        """Verify test_dsl_models.py has all command classes covered."""
        content = Path("tests/test_dsl_models.py").read_text(encoding="utf-8")
        assert "TestBuildRoadCmd" in content
        assert "TestBuildZoneCmd" in content
        assert "TestBuildBuildingCmd" in content
        assert "TestBuildUtilityCmd" in content
        assert "TestDemolishCmd" in content

    def test_e2e_t1_f21_04_bridge_atomic_suite_coverage(self):
        """Verify test_bridge_atomic.py covers serialization and file replacement."""
        content = Path("tests/test_bridge_atomic.py").read_text(encoding="utf-8")
        assert "TestLuaSerialization" in content
        assert "TestWriteAtomicLua" in content
        assert "TestTheoTownBridge" in content

    def test_e2e_t1_f21_05_mcp_server_suite_coverage(self):
        """Verify test_mcp_server.py covers tools, resources, and prompts."""
        content = Path("tests/test_mcp_server.py").read_text(encoding="utf-8")
        assert "TestMCPServerRegistration" in content
        assert "TestMCPServerToolCalls" in content
        assert "TestMCPServerResourcesAndPrompts" in content

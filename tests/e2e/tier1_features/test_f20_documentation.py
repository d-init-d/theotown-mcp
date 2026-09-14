"""
Tier 1: Feature F20 — Bilingual Documentation
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path


class TestFeatureF20Documentation:
    def test_e2e_t1_f20_01_bilingual_sections(self):
        """README.md contains English and Vietnamese sections."""
        readme = Path("README.md")
        assert readme.exists()
        content = readme.read_text(encoding="utf-8")
        assert "English Documentation" in content
        assert "Tiếng Việt" in content

    def test_e2e_t1_f20_02_claude_desktop_config_block(self):
        """README.md contains Claude Desktop config JSON snippet."""
        content = Path("README.md").read_text(encoding="utf-8")
        assert "claude_desktop_config.json" in content
        assert '"theotown"' in content
        assert "theotown-mcp.exe" in content

    def test_e2e_t1_f20_03_cursor_config_block(self):
        """README.md contains Cursor config snippet."""
        content = Path("README.md").read_text(encoding="utf-8")
        assert "Cursor" in content
        assert "mcp.json" in content

    def test_e2e_t1_f20_04_hermes_config_block(self):
        """README.md contains Hermes Agent config snippet."""
        content = Path("README.md").read_text(encoding="utf-8")
        assert "Hermes" in content

    def test_e2e_t1_f20_05_architecture_diagram(self):
        """README.md includes architecture diagrams."""
        content = Path("README.md").read_text(encoding="utf-8")
        assert "AI AGENT RUNTIME" in content
        assert "PYTHON MCP SERVER" in content
        assert "THEOTOWN SIMULATION WORLD" in content

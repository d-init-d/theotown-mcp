"""
Tier 1: Feature F11 — Python Modern Packaging
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path

import tomllib


class TestFeatureF11Packaging:
    def test_e2e_t1_f11_01_pep517_build_config(self):
        """pyproject.toml declares hatchling backend."""
        pyproj = Path("pyproject.toml")
        assert pyproj.exists()
        with open(pyproj, "rb") as f:
            data = tomllib.load(f)
        assert data["build-system"]["build-backend"] == "hatchling.build"

    def test_e2e_t1_f11_02_dependency_pins(self):
        """pyproject.toml includes mcp, pydantic, and typer pins."""
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        deps = data["project"]["dependencies"]
        assert any("mcp>=2.0.0" in d for d in deps)
        assert any("pydantic>=2.7.0" in d for d in deps)
        assert any("typer>=0.12.0" in d for d in deps)

    def test_e2e_t1_f11_03_package_metadata(self):
        """Package metadata specifies name, version, and license."""
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        proj = data["project"]
        assert proj["name"] == "theotown-mcp"
        assert proj["version"] == "0.2.0"
        assert proj["license"]["text"] == "MIT"

    def test_e2e_t1_f11_04_cli_entrypoint_registered(self):
        """Scripts table registers theotown-mcp entry point."""
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        scripts = data["project"]["scripts"]
        assert scripts.get("theotown-mcp") == "theotown_mcp.cli:app"

    def test_e2e_t1_f11_05_package_importability(self):
        """theotown_mcp package and modules can be imported cleanly."""
        import theotown_mcp
        import theotown_mcp.bridge
        import theotown_mcp.catalog
        import theotown_mcp.cli
        import theotown_mcp.config
        import theotown_mcp.models
        import theotown_mcp.server

        assert theotown_mcp.__version__ == "0.2.0"

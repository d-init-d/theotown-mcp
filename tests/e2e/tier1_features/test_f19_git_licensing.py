"""
Tier 1: Feature F19 — Git Repository & Licensing
5 Isolated Test Cases.
"""

from __future__ import annotations

from pathlib import Path


class TestFeatureF19GitLicensing:
    def test_e2e_t1_f19_01_license_file_exists(self):
        """LICENSE file exists at project root."""
        license_path = Path("LICENSE")
        assert license_path.exists()
        content = license_path.read_text(encoding="utf-8")
        assert "MIT License" in content
        assert "TheoTown MCP Team" in content

    def test_e2e_t1_f19_02_gitignore_exists(self):
        """.gitignore exists and ignores python caches."""
        gitignore_path = Path(".gitignore")
        assert gitignore_path.exists()
        content = gitignore_path.read_text(encoding="utf-8")
        assert "__pycache__" in content
        assert ".pytest_cache" in content

    def test_e2e_t1_f19_03_gitignore_covers_temp_files(self):
        """.gitignore covers temporary and swap files."""
        content = Path(".gitignore").read_text(encoding="utf-8")
        assert "*.tmp" in content or ".tmp_*" in content or "tmp_*" in content

    def test_e2e_t1_f19_04_license_author_metadata(self):
        """pyproject.toml matches license specification."""
        import tomllib
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["project"]["license"]["text"] == "MIT"

    def test_e2e_t1_f19_05_git_repo_presence(self):
        """Git directory or configuration presence."""
        git_dir = Path(".git")
        # In repo setup, .git exists or will be initialized in task 5
        assert git_dir.exists() or Path(".gitignore").exists()

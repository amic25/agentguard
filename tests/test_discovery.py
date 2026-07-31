"""Source discovery and language mapping tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.config import Config
from agentguard.scanner import LANGUAGES, Scanner


@pytest.mark.parametrize("extension", [".mts", ".cts"])
def test_discovers_modern_typescript_extension(project: Path, extension: str) -> None:
    (project / f"agent{extension}").write_text("execSync(command)", encoding="utf-8")
    result = Scanner().scan(project)
    assert result.files_scanned == 1
    assert "AG002" in {finding.rule_id for finding in result.findings}


@pytest.mark.parametrize("extension", [".mts", ".cts"])
def test_modern_typescript_extension_maps_to_typescript(extension: str) -> None:
    assert LANGUAGES[extension] == "typescript"


@pytest.mark.parametrize("extension", [".mts", ".cts"])
def test_excludes_vendor_directory_for_modern_typescript(project: Path, extension: str) -> None:
    vendor = project / "node_modules"
    vendor.mkdir()
    (vendor / f"bad{extension}").write_text("execSync(command)", encoding="utf-8")
    result = Scanner().scan(project)
    assert result.files_scanned == 0
    assert result.findings == []


@pytest.mark.parametrize("extension", [".mts", ".cts"])
def test_skips_oversized_modern_typescript_file(project: Path, extension: str) -> None:
    (project / f"large{extension}").write_text("x" * 2000, encoding="utf-8")
    result = Scanner(Config(max_file_size_kb=1)).scan(project)
    assert result.skipped_files == 1

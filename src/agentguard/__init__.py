"""AgentGuard public package API."""

from importlib.metadata import PackageNotFoundError, version

from agentguard.models import Finding, ScanResult, Severity
from agentguard.scanner import Scanner

__all__ = ["Finding", "ScanResult", "Scanner", "Severity"]

try:
    #: Read from installed metadata so `pyproject.toml` is the only place a version number
    #: is written. It used to be hardcoded here as well, and this value - not the one in
    #: `pyproject.toml` - is what `--version`, the JSON report's `tool.version`, and the
    #: SARIF driver version all report. Bumping one and not the other would have published
    #: a package declaring one version while every report it emitted claimed another.
    __version__ = version("agentguard")
except PackageNotFoundError:  # pragma: no cover - source tree with no install
    __version__ = "0.0.0+unknown"

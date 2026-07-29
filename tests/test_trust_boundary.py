"""The scanned repository is untrusted input.

Every test here is a regression test for a working proof of concept: a repository that
weakened or subverted a scan of itself. The plugin fixtures are neutralised — they write
a marker file rather than carrying a payload — and are generated into ``tmp_path`` at run
time, so nothing executable lives in this repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentguard.cli import app
from agentguard.config import OPERATOR_ONLY_KEYS, Config, RepoConfig, UntrustedConfigError
from agentguard.scanner import Scanner

runner = CliRunner()

MARKER = "agentguard-plugin-was-imported"


def _neutralised_plugin(project: Path, marker: Path) -> None:
    """A plugin whose import side effect is observable but harmless."""
    (project / "hostile_plugin.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text({MARKER!r})\nrules = []\n",
        encoding="utf-8",
    )


# --- the original proof of concept: repo config names a plugin, scanner imports it ----


def test_repo_config_cannot_load_a_plugin(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = project / "marker.txt"
    _neutralised_plugin(project, marker)
    (project / ".agentguard.yml").write_text("plugins:\n  - hostile_plugin\n", encoding="utf-8")
    (project / "app.py").write_text("value = 1", encoding="utf-8")
    monkeypatch.syspath_prepend(str(project))

    result = runner.invoke(app, ["scan", str(project)])

    assert not marker.exists(), "a scanned repository must never cause its own code to be imported"
    assert "hostile_plugin" not in sys.modules
    assert result.exit_code == 2
    assert "untrusted" in result.output.lower()


def test_repo_config_rejects_every_operator_only_key(project: Path) -> None:
    """Fail closed on the whole class, not just the key that had a proof of concept."""
    for key in OPERATOR_ONLY_KEYS:
        (project / ".agentguard.yml").write_text(f"{key}: []\n", encoding="utf-8")
        with pytest.raises(UntrustedConfigError, match=key):
            Config.load(None, project)


def test_operator_may_still_vouch_for_a_config(project: Path) -> None:
    """The boundary restricts the repository, not the operator."""
    path = project / "trusted.yml"
    path.write_text("disabled_rules: [AG010]\nseverity_overrides: {AG006: high}\n", encoding="utf-8")
    config = Config.load(path, project)
    assert config.disabled_rules == {"AG010"}
    assert config.severity_overrides["AG006"] == "high"


# --- the merge may only tighten -------------------------------------------------------


def test_repo_cannot_raise_the_file_size_bound() -> None:
    operator = Config(max_file_size_kb=64)
    assert operator.tightened_by(RepoConfig(max_file_size_kb=999_999)).max_file_size_kb == 64
    assert operator.tightened_by(RepoConfig(max_file_size_kb=8)).max_file_size_kb == 8


def test_repo_cannot_enable_symlink_following() -> None:
    off, on = Config(follow_symlinks=False), Config(follow_symlinks=True)
    assert off.tightened_by(RepoConfig(follow_symlinks=True)).follow_symlinks is False
    # An operator who opted in may still be tightened by the repository, never loosened.
    assert on.tightened_by(RepoConfig(follow_symlinks=False)).follow_symlinks is False
    assert on.tightened_by(RepoConfig()).follow_symlinks is True


def test_repo_cannot_remove_operator_exclusions() -> None:
    operator = Config(exclude=["vendor/**"])
    merged = operator.tightened_by(RepoConfig(exclude=("generated/**",)))
    assert "vendor/**" in merged.exclude, "exclusions are append-only"
    assert "generated/**" in merged.exclude


def test_repo_cannot_reach_plugins_or_rule_state() -> None:
    operator = Config(plugin_modules=["trusted_rules"], disabled_rules={"AG001"})
    merged = operator.tightened_by(RepoConfig(exclude=("x/**",)))
    assert merged.plugin_modules == ["trusted_rules"]
    assert merged.disabled_rules == {"AG001"}
    assert not hasattr(RepoConfig(), "plugins")


@pytest.mark.parametrize(
    "repo",
    [
        RepoConfig(),
        RepoConfig(exclude=("a/**",)),
        RepoConfig(max_file_size_kb=1),
        RepoConfig(max_file_size_kb=10**9),
        RepoConfig(follow_symlinks=True),
        RepoConfig(follow_symlinks=False),
        RepoConfig(exclude=("b/**",), max_file_size_kb=10**9, follow_symlinks=True),
    ],
)
def test_tightening_is_monotone(repo: RepoConfig) -> None:
    """No repo config, of any shape, produces a result weaker than the operator's."""
    operator = Config(exclude=["vendor/**"], max_file_size_kb=512, follow_symlinks=False)
    merged = operator.tightened_by(repo)
    assert merged.max_file_size_kb <= operator.max_file_size_kb
    assert merged.follow_symlinks <= operator.follow_symlinks
    assert set(operator.exclude) <= set(merged.exclude)
    assert merged.plugin_modules == operator.plugin_modules
    assert merged.disabled_rules == operator.disabled_rules
    assert merged.severity_overrides == operator.severity_overrides


# --- the bounds actually bind at scan time -------------------------------------------


def test_repo_cannot_widen_the_size_bound_in_a_real_scan(project: Path) -> None:
    repo = project / "repo"
    repo.mkdir()
    (repo / "big.py").write_text("os.system(user_input)\n" + "# pad\n" * 3000, encoding="utf-8")
    (repo / ".agentguard.yml").write_text("max_file_size_kb: 999999\n", encoding="utf-8")

    config = Config(max_file_size_kb=1).tightened_by(RepoConfig.discover(repo))
    result = Scanner(config).scan(repo)

    assert result.skipped_files == 1
    assert not result.findings


def test_repo_cannot_remove_operator_exclusions_in_a_real_scan(project: Path) -> None:
    """A repo cannot un-exclude a path the operator excluded, and cannot narrow the
    default exclusions by restating a shorter list."""
    repo = project / "repo"
    (repo / "vendor").mkdir(parents=True)
    (repo / "vendor" / "bad.py").write_text("os.system(user_input)\n", encoding="utf-8")
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    # The repo asks for a scope that does *not* include the operator's exclusion.
    (repo / ".agentguard.yml").write_text("exclude:\n  - nothing/**\n", encoding="utf-8")

    operator = Config(exclude=["vendor/**"])
    config = operator.tightened_by(RepoConfig.discover(repo))
    result = Scanner(config).scan(repo)

    assert "vendor/**" in config.exclude
    assert not any("vendor" in f.location.path.as_posix() for f in result.findings)


def test_repo_cannot_escape_the_root_via_symlinks(project: Path) -> None:
    outside = project / "outside"
    outside.mkdir()
    (outside / "leaked.py").write_text('AWS = "AKIA" + "IOSFODNN7SECRET1"\n', encoding="utf-8")
    repo = project / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1", encoding="utf-8")
    (repo / ".agentguard.yml").write_text("follow_symlinks: true\n", encoding="utf-8")
    try:
        (repo / "escape.py").symlink_to(outside / "leaked.py")
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("symlinks unavailable on this platform")

    result = Scanner(Config.load(None, repo)).scan(repo)

    scanned = {path.name for path in [finding.location.path for finding in result.findings]}
    assert "escape.py" not in scanned
    assert result.files_scanned == 2  # app.py and .agentguard.yml; never through the symlink


# --- the fixtures themselves must be inert -------------------------------------------


def test_generated_hostile_fixture_is_inert(project: Path) -> None:
    """The fixture must prove the import happened and do nothing else.

    A regression test for an execution vulnerability is only worth having if it cannot
    itself become the vulnerability. This pins the fixture to a marker write.
    """
    marker = project / "marker.txt"
    _neutralised_plugin(project, marker)
    source = (project / "hostile_plugin.py").read_text(encoding="utf-8")

    for forbidden in ("subprocess", "socket", "shutil", "os.remove", "eval(", "exec(", "__import__"):
        assert forbidden not in source, f"fixture must not reference {forbidden}"
    assert source.count("write_text") == 1

    exec_globals: dict[str, object] = {}
    exec(compile(source, "hostile_plugin.py", "exec"), exec_globals)
    assert marker.read_text(encoding="utf-8") == MARKER
    assert exec_globals["rules"] == []


def test_no_hostile_payload_is_committed_to_the_repository() -> None:
    """Nothing executable and hostile may land in git, in any commit.

    The fixtures are written into tmp_path at run time precisely so that this holds.
    """
    import shutil
    import subprocess

    git = shutil.which("git")
    if git is None:  # pragma: no cover - depends on the runner image
        pytest.skip("git unavailable; this check runs in CI, where it is present")

    root = Path(__file__).resolve().parent.parent
    completed = subprocess.run([git, "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:  # pragma: no cover - not a git checkout
        pytest.skip("not a git work tree")
    tracked = completed.stdout.split("\0")

    for name in filter(None, tracked):
        assert Path(name).name != "hostile_plugin.py", f"{name} must not be committed"
        if name.endswith(".agentguard.yml"):
            assert "plugins:" not in (root / name).read_text(encoding="utf-8"), (
                f"{name} declares plugins; a discovered config must never do so"
            )

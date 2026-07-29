"""The corpus must stay consistent with its manifest, and recall must not regress.

Precision is expected to move — improving it is the point of the work that follows — so
it is measured by `make bench` and reviewed as a delta rather than asserted here. Recall
and corpus consistency are different: a rule that stops firing on a file labelled as a
true positive, or a corpus file that drifts away from its label, is a defect either way.
"""

from __future__ import annotations

import pytest
from tools.bench import CORPUS, load_manifest, measure


def test_manifest_and_disk_agree() -> None:
    """load_manifest exits 2 on drift, so reaching the assertions means it is consistent."""
    labels = load_manifest()
    assert labels, "corpus is empty"
    assert (CORPUS / "manifest.yml").exists()


def test_every_label_has_a_reason() -> None:
    import yaml

    raw = yaml.safe_load((CORPUS / "manifest.yml").read_text(encoding="utf-8"))
    for section in ("true_positives", "true_negatives"):
        for name, entry in raw[section].items():
            assert entry.get("why", "").strip(), f"{section}/{name} has no `why`"


def test_recall_is_total() -> None:
    """Every rule labelled as firing on a true positive still fires on it."""
    tallies, _, _ = measure(load_manifest())
    missed = {rule_id: tally.fn_locations for rule_id, tally in tallies.items() if tally.false_negatives}
    assert not missed, f"rules stopped detecting labelled true positives: {missed}"


def test_measurement_is_not_degraded_by_scan_errors() -> None:
    """A benchmark computed from a partial scan is not a benchmark."""
    _, scan_errors, _ = measure(load_manifest())
    assert not scan_errors, f"corpus scan produced errors: {scan_errors}"


def test_undiscovered_files_are_reported_not_silently_passed() -> None:
    """A file discovery never opens proves nothing; the harness must say so.

    `.env.example` is currently in this state, which also means a real `.env` would be
    missed. If discovery is extended to cover it, this test should be updated to assert
    the new coverage rather than deleted.
    """
    _, _, undiscovered = measure(load_manifest())
    assert undiscovered == ["true_negatives/.env.example"], (
        "the set of files AgentGuard cannot see has changed; update this test deliberately"
    )


@pytest.mark.parametrize("section", ["true_positives", "true_negatives"])
def test_corpus_sections_are_populated(section: str) -> None:
    files = [path for path in (CORPUS / section).rglob("*") if path.is_file()]
    assert len(files) >= 10, f"{section} has only {len(files)} files"

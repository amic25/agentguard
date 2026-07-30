"""The corpus must stay consistent with its manifest, and recall must not regress.

Precision is expected to move — improving it is the point of the work that follows — so
it is measured by `make bench` and reviewed as a delta rather than asserted here. Recall
and corpus consistency are different: a rule that stops firing on a file labelled as a
true positive, or a corpus file that drifts away from its label, is a defect either way.
"""

from __future__ import annotations

import pytest
from tools.bench import CORPUS, ORIGINS, load_manifest, measure


def test_manifest_and_disk_agree() -> None:
    """load_manifest exits 2 on drift, so reaching the assertions means it is consistent."""
    labels, _ = load_manifest()
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
    tallies, _, _, _ = measure(load_manifest()[0])
    missed = {rule_id: tally.fn_locations for rule_id, tally in tallies.items() if tally.false_negatives}
    assert not missed, f"rules stopped detecting labelled true positives: {missed}"


def test_measurement_is_not_degraded_by_scan_errors() -> None:
    """A benchmark computed from a partial scan is not a benchmark."""
    _, scan_errors, _, _ = measure(load_manifest()[0])
    assert not scan_errors, f"corpus scan produced errors: {scan_errors}"


def test_every_corpus_file_is_discovered() -> None:
    """A file discovery never opens proves nothing; the harness must say so.

    `.env.example` used to be in this state, and so did every real `.env` — a secrets
    scanner that could not read the canonical secrets file. Discovery now covers them, so
    the expected set is empty. If this grows, something stopped being scanned.
    """
    _, _, undiscovered, _ = measure(load_manifest()[0])
    assert undiscovered == [], (
        f"corpus files AgentGuard cannot see: {undiscovered}. Either discovery regressed, "
        "or a file shape was added that nothing scans."
    )


@pytest.mark.parametrize("section", ["true_positives", "true_negatives"])
def test_corpus_sections_are_populated(section: str) -> None:
    files = [path for path in (CORPUS / section).rglob("*") if path.is_file()]
    assert len(files) >= 10, f"{section} has only {len(files)} files"


def test_every_case_declares_its_origin() -> None:
    """`origin` separates cases drawn from real projects from cases someone composed.

    Enforced rather than inferred: it was previously read by sniffing the prose in `why`,
    which miscounted the moment an entry said "field finding" instead of "measured". A
    corpus whose negatives were all selected from observed failures is biased towards
    passing, so the split has to be reliable enough to score separately.
    """
    _, origins = load_manifest()
    assert origins, "corpus is empty"
    assert set(origins.values()) <= ORIGINS
    field = sum(1 for value in origins.values() if value == "field")
    assert field, "no case is marked as field-derived; the split has stopped meaning anything"


def test_field_only_scoring_is_a_strict_subset() -> None:
    labels, origins = load_manifest()
    field_only = {p: e for p, e in labels.items() if origins[p] == "field"}
    assert 0 < len(field_only) < len(labels)


def test_directory_matches_expectation() -> None:
    """`true_positives/` expects findings; `true_negatives/` expects none.

    One file used to sit in `true_negatives/` while expecting AG001 — its assertion was
    about severity, not silence. That made the corpus report 14 true positives across 13
    positive files, and the README prose then had to explain a number that only looked
    wrong because the layout was inconsistent. The directory is the claim; keep it true.
    """
    import yaml

    raw = yaml.safe_load((CORPUS / "manifest.yml").read_text(encoding="utf-8"))
    misfiled = [
        f"true_positives/{name}" for name, entry in raw["true_positives"].items() if not entry["expect"]
    ] + [f"true_negatives/{name}" for name, entry in raw["true_negatives"].items() if entry["expect"]]
    assert not misfiled, f"expectation contradicts the directory: {misfiled}"

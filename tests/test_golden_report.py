"""The JSON report is a contract and the text report is what a reader sees.

Both were previously covered only incidentally. The JSON schema string was written and never
asserted, and ``render/text.py`` had no test at all -- which matters because "explanation
overshoot" (prose claiming more than the structure supports) is a failure mode this project
names, and the renderer is the only thing standing between the two.

A golden file that recorded every value would break every time a protocol's wording changed,
so what is pinned is what a consumer actually depends on:

* the key order at every level, because a reordering is a silent contract change;
* the enum values, because a renamed status is a breaking change;
* the uncertainty: which evidence is missing, which checks were unknown, whether expert review
  was requested. These are the parts most likely to be lost in rendering, and losing them is
  how a report starts overclaiming.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.evidence import EvidenceType
from qcjudge.domain.validation import ValidationStatus
from qcjudge.render import report_to_text, to_json
from qcjudge.render.json_report import SCHEMA, report_to_dict
from tests.golden import build_report, build_report_with_boundary

GOLDEN_DIR = Path(__file__).resolve().parent / "data"
SHAPE_FILE = GOLDEN_DIR / "audit_report_shape.json"
PLAIN_TEXT = GOLDEN_DIR / "report_task.txt"
BOUNDARY_TEXT = GOLDEN_DIR / "report_expert_boundary.txt"


def shape(value: Any) -> Any:
    """The structure of a JSON value: keys in order, and the shape of each value.

    Lists collapse to the shape of their first element, because a report's lists vary in
    length while their element shape is the contract.
    """
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


@pytest.fixture()
def report(tmp_path: Path):
    return build_report(tmp_path)


# -- the golden file itself ------------------------------------------------------------------


@pytest.mark.skipif(not SHAPE_FILE.exists(), reason="golden shape not generated")
def test_the_json_report_matches_the_golden_shape(report) -> None:
    """A key added, removed, renamed or reordered is a change to the published contract."""
    committed = json.loads(SHAPE_FILE.read_text(encoding="utf-8"))

    assert shape(report_to_dict(report)) == committed


@pytest.mark.skipif(not PLAIN_TEXT.exists(), reason="golden text not generated")
def test_the_text_report_matches_its_golden_file(report) -> None:
    """A byte comparison, because the rendering is what a reader is shown."""
    committed = PLAIN_TEXT.read_text(encoding="utf-8")

    assert report_to_text(report) == committed


@pytest.mark.skipif(not BOUNDARY_TEXT.exists(), reason="golden text not generated")
def test_requesting_expert_review_survives_both_renderings(tmp_path: Path) -> None:
    """The status must reach the reader, not be flattened into a plain verdict."""
    report = build_report_with_boundary(tmp_path)

    assert report_to_text(report) == BOUNDARY_TEXT.read_text(encoding="utf-8")
    document = report_to_dict(report)
    assert document["evidence"]["overall_status"] == "requires_expert_review"
    requirements = [
        requirement
        for hypothesis in document["evidence"]["hypotheses"]
        for claim in hypothesis["claims"]
        for requirement in claim["requirements"]
    ]
    flagged = [item for item in requirements if item["expert_review_required"]]
    assert len(flagged) == 1
    assert flagged[0]["requirement_id"] == "ts.mode_identity"


# -- properties the golden file alone would not explain ---------------------------------------


def test_the_schema_string_is_pinned(report) -> None:
    """A consumer keys off this; changing it is a breaking change, not a detail."""
    assert SCHEMA == "qcjudge.audit_report/1"
    assert report_to_dict(report)["schema"] == SCHEMA


def test_key_order_is_stable_at_the_top_level(report) -> None:
    assert list(report_to_dict(report)) == [
        "schema",
        "tool_version",
        "generated_at",
        "protocol",
        "question",
        "execution",
        "structure",
        "methodology",
        "evidence",
        "recommendations",
        "trace",
        "inventory",
        "disclaimer",
    ]


def test_the_json_is_byte_identical_across_builds(tmp_path: Path) -> None:
    """Anything varying would make the golden file unmaintainable."""
    first = build_report(tmp_path / "one")
    second = build_report(tmp_path / "two")

    assert to_json(first) == to_json(second)


def test_the_generated_at_stamp_is_the_only_thing_a_caller_must_ignore(tmp_path: Path) -> None:
    first = to_json(build_report(tmp_path / "one"))
    stamp = datetime(2026, 1, 1, 12, 0).isoformat()

    assert stamp in first
    assert first.count("2026-01-01T12:00:00") >= 1


# -- uncertainty must survive rendering ------------------------------------------------------


def test_every_status_in_the_report_is_a_registered_enum_member(report) -> None:
    """A free string here would mean a status nobody can branch on."""
    document = report_to_dict(report)

    for axis in ("execution", "structure", "methodology"):
        assert document[axis]["status"] in {member.value for member in ValidationStatus}
    assert document["evidence"]["overall_status"] in {
        member.value for member in AssessmentStatus
    }


def test_missing_evidence_types_survive_into_the_json(report) -> None:
    """What is *missing* is the most useful thing in the report and the easiest to drop."""
    document = report_to_dict(report)
    missing = [
        kind
        for hypothesis in document["evidence"]["hypotheses"]
        for claim in hypothesis["claims"]
        for requirement in claim["requirements"]
        for kind in requirement["missing_evidence_types"]
    ]

    assert missing, "the fixture must leave something missing for this to mean anything"
    assert set(missing) <= {member.value for member in EvidenceType}


def test_unavailable_inputs_survive_into_the_json(report) -> None:
    """A reader must be able to see what could not be read, and why."""
    unavailable = report_to_dict(report)["inventory"]["unavailable"]

    assert unavailable
    for absent in unavailable:
        assert absent["key"]
        assert absent["reason"]


def test_the_text_report_never_drops_the_disclaimer(report) -> None:
    text = report_to_text(report)

    assert report.disclaimer in text


def test_the_text_report_names_every_axis_it_reports_on(report) -> None:
    """A silently omitted axis would read as "nothing to report" rather than "not examined"."""
    text = report_to_text(report)

    for heading in ("Execution validity", "Structural validation", "Methodological checks"):
        assert heading in text


def test_the_text_report_states_that_no_methodology_check_ran(report) -> None:
    """TS declares none, and an unexamined axis must not read as a passed one."""
    text = report_to_text(report)

    assert report.methodology_status is ValidationStatus.UNKNOWN
    assert "no methodology check was declared" in text


def test_facts_keep_their_provenance_in_the_json(report) -> None:
    """A number without a source is not evidence."""
    facts = report_to_dict(report)["inventory"]["facts"]

    assert facts
    for fact in facts:
        assert fact["provenance"]["source_file"]
        assert fact["provenance"]["producer"]
        assert fact["provenance"]["extracted_at"]

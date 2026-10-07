"""A requirement's declared insufficiency conditions must reach the report.

``insufficiency_conditions`` states what a requirement would have accepted -- "the imaginary
frequency is known but its mode was never inspected". Nothing read the field, so six
requirements declared conditions that appeared in no report, and a reader was left with the
engine's terse "no evidence of an accepted type was supplied" when the protocol's own account of
the gap was more precise.

Which condition a given gap matches is not machine-decidable, because the conditions are prose,
so all of them are restated rather than one being guessed at.
"""

from __future__ import annotations

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.evidence import EvidenceRequirement, FactKey
from qcjudge.domain.question import QuestionFamily
from qcjudge.evidence.matching import _with_conditions
from tests.support import (
    TADF,
    TS,
    ct_question,
    fact,
    inventory,
    tadf_facts,
    tadf_gap_evidence,
    tadf_question,
    ts_evidence,
    ts_facts,
    ts_irc_evidence,
    ts_question,
)


def _requirement(**overrides: object) -> EvidenceRequirement:
    defaults: dict[str, object] = {
        "id": "synthetic",
        "claim_id": "claim",
        "description": "Synthetic.",
        "level": "required",
        "accepted_evidence_types": ("irc",),
    }
    defaults.update(overrides)
    return EvidenceRequirement(**defaults)  # type: ignore[arg-type]


def _rationales(report) -> dict[str, str]:
    return {
        assessment.requirement_id: assessment.rationale
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for assessment in claim.requirement_assessments
    }


# -- the helper -------------------------------------------------------------------------------


def test_a_requirement_with_no_declared_conditions_is_unchanged() -> None:
    """Most requirements declare none, and their rationale must not acquire a dangling clause."""
    assert _with_conditions(_requirement(), "Base rationale.") == "Base rationale."


def test_declared_conditions_are_restated_after_the_rationale() -> None:
    requirement = _requirement(
        insufficiency_conditions=("No frequency calculation was provided.", "Second.")
    )

    text = _with_conditions(requirement, "Base rationale.")

    assert text.startswith("Base rationale.")
    assert "No frequency calculation was provided." in text
    assert "Second." in text


def test_the_conditions_are_enumerated_so_they_read_as_a_list() -> None:
    """Bare sentences run together would be unreadable once there are two of them."""
    requirement = _requirement(insufficiency_conditions=("First.", "Second."))

    text = _with_conditions(requirement, "Base.")

    assert "(1) First." in text
    assert "(2) Second." in text


# -- the built-in protocols -------------------------------------------------------------------


def test_every_declared_condition_belongs_to_a_requirement_that_can_use_it() -> None:
    """The field exists to explain a gap, so it belongs on a requirement that has one."""
    for family in QuestionFamily:
        protocol = _protocol(family)
        for requirement in protocol.requirements:
            if requirement.insufficiency_conditions:
                assert requirement.accepted_evidence_types


def test_a_failing_requirement_restates_its_declared_conditions() -> None:
    """The mode-identity case: the frequency exists, the inspection does not.

    The premise has to be established first -- a requirement whose prerequisite is missing is
    ``NOT_ASSESSABLE``, which is not a coverage gap and has nothing to explain.
    """
    report = audit(
        ts_question(),
        inventory(*ts_facts(1), evidence_items=(ts_evidence(),)),
    )

    assert _status_of(report, "ts.mode_identity") is AssessmentStatus.INSUFFICIENT
    assert "its mode was never inspected" in _rationales(report)["ts.mode_identity"]


def test_the_conditions_survive_into_the_json_contract() -> None:
    """The contractual rendering must carry them too, not only the human one."""
    from qcjudge.render.json_report import report_to_dict

    report = audit(
        tadf_question(),
        inventory(*tadf_facts(), evidence_items=(tadf_gap_evidence(),)),
    )
    document = report_to_dict(report)
    rationales = {
        requirement["requirement_id"]: requirement["rationale"]
        for hypothesis in document["evidence"]["hypotheses"]
        for claim in hypothesis["claims"]
        for requirement in claim["requirements"]
    }

    assert _status_of(report, "tadf.risc_coupling") is AssessmentStatus.INSUFFICIENT
    assert "Only a singlet-triplet gap was provided." in rationales["tadf.risc_coupling"]


def test_a_supported_requirement_does_not_restate_them() -> None:
    """There is no gap to explain once the requirement is met."""
    report = audit(
        ts_question(),
        inventory(*ts_facts(1), evidence_items=(ts_evidence(), ts_irc_evidence())),
    )

    assert _status_of(report, "ts.pathway_connection") is AssessmentStatus.SUPPORTED
    assert "declares as insufficient" not in _rationales(report)["ts.pathway_connection"]


def test_a_contradicted_requirement_does_not_restate_them() -> None:
    """``CONTRADICTED`` is not a coverage gap, so the coverage conditions do not apply."""
    report = audit(
        ts_question(),
        inventory(
            fact(FactKey.SCF_CONVERGED, True),
            fact(FactKey.GEOMETRY_CONVERGED, True),
            fact(FactKey.FREQUENCY_OBSERVED_MODE_COUNT, 18, unit="modes"),
            fact(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, 18, unit="modes"),
            fact(FactKey.FREQUENCY_IMAGINARY_COUNT, 0, unit="modes"),
            evidence_items=(ts_evidence(),),
        ),
    )

    assert _status_of(report, "ts.stationary_point") is AssessmentStatus.CONTRADICTED
    assert "declares as insufficient" not in _rationales(report)["ts.stationary_point"]


def _status_of(report, requirement_id: str) -> AssessmentStatus:
    for hypothesis in report.hypothesis_assessments:
        for claim in hypothesis.claim_assessments:
            for assessment in claim.requirement_assessments:
                if assessment.requirement_id == requirement_id:
                    return assessment.status
    raise AssertionError(f"{requirement_id} is not in the report")


def _protocol(family: QuestionFamily):
    from qcjudge.protocols import get_protocol

    return get_protocol(family)


def test_the_three_families_are_the_ones_these_tests_cover() -> None:
    """Guards the family constants imported above against a rename."""
    assert {TS, TADF} <= set(QuestionFamily)
    assert ct_question().family is QuestionFamily.CHARGE_TRANSFER_EXCITATION

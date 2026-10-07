"""The defining invariant, stated as a truth table over the real engine.

Execution validity and evidence adequacy are computed on different axes, and the structural
result is a third. These tests fail if any change lets one axis leak into another.
"""

from __future__ import annotations

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.common import UnavailableReason
from qcjudge.domain.evidence import EvidenceStrength, EvidenceType, FactKey
from qcjudge.domain.question import QuestionFamily
from qcjudge.domain.validation import ValidationStatus
from tests.support import (
    CT,
    TS,
    converged_calculation,
    ct_question,
    ct_state_count,
    evidence,
    excited_state_evidence,
    fact,
    hole_electron_evidence,
    inventory,
    ts_evidence,
    ts_facts,
    ts_question,
    unavailable,
)


def _complete_ct_report():
    return audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(excited_state_evidence(), hole_electron_evidence()),
        ),
    )


def _unsupported_ct_report():
    return audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(excited_state_evidence(),),
        ),
    )


def test_technical_success_does_not_imply_scientific_sufficiency() -> None:
    """Execution PASS with evidence INSUFFICIENT is the expected outcome, not an anomaly."""
    report = _unsupported_ct_report()
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


def test_execution_failure_is_never_relabelled_as_a_contradicted_claim() -> None:
    report = audit(
        ct_question(),
        inventory(
            fact(FactKey.SCF_CONVERGED, False),
            ct_state_count(),
            evidence_items=(excited_state_evidence(),),
        ),
    )
    assert report.execution_status is ValidationStatus.FAIL
    assert report.overall_evidence_status is not AssessmentStatus.CONTRADICTED


def test_structural_result_does_not_disturb_execution_validity() -> None:
    """A converged minimum is a successful calculation that is not a saddle point."""
    report = audit(ts_question(), inventory(*ts_facts(0), evidence_items=(ts_evidence(),)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.structure_status is ValidationStatus.FAIL
    assert report.overall_evidence_status is AssessmentStatus.CONTRADICTED


def test_unknown_input_never_becomes_false() -> None:
    report = audit(ct_question(), inventory())
    assert report.execution_status is ValidationStatus.UNKNOWN
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


def test_recorded_absence_reason_decides_between_coverage_and_access() -> None:
    """A missing calculation is a coverage gap; an unreadable file is not."""
    coverage = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            unavailable_items=(
                unavailable(FactKey.EXCITED_STATE_COUNT, UnavailableReason.NOT_PROVIDED),
            ),
        ),
    )
    access = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            unavailable_items=(
                unavailable(FactKey.EXCITED_STATE_COUNT, UnavailableReason.FILE_TRUNCATED),
            ),
        ),
    )
    assert coverage.execution_status is ValidationStatus.PASS
    assert coverage.overall_evidence_status is AssessmentStatus.INSUFFICIENT
    assert access.execution_status is ValidationStatus.PASS
    assert access.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


def test_weak_evidence_is_recorded_but_cannot_satisfy_a_direct_requirement() -> None:
    weakened = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(excited_state_evidence(), hole_electron_evidence()),
        ),
    )
    alone = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(
                excited_state_evidence(),
                evidence(
                    "ev-weak",
                    EvidenceType.HOLE_ELECTRON_ANALYSIS,
                    strength=EvidenceStrength.WEAK,
                ),
            ),
        ),
    )
    assert weakened.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert alone.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


def test_supplied_but_weak_evidence_is_not_reported_as_missing() -> None:
    """The gap must be described accurately: present-but-insufficient is not absent."""
    report = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(
                excited_state_evidence(),
                evidence(
                    "ev-weak",
                    EvidenceType.HOLE_ELECTRON_ANALYSIS,
                    strength=EvidenceStrength.WEAK,
                ),
            ),
        ),
    )
    spatial = next(
        item
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for item in claim.requirement_assessments
        if item.requirement_id == "ct.spatial_redistribution"
    )
    assert spatial.status is AssessmentStatus.PARTIALLY_SUPPORTED
    assert EvidenceType.HOLE_ELECTRON_ANALYSIS not in spatial.missing_evidence_types
    assert EvidenceType.NTO_ANALYSIS in spatial.missing_evidence_types


def test_every_supported_assessment_cites_evidence() -> None:
    report = _complete_ct_report()
    for hypothesis in report.hypothesis_assessments:
        for claim in hypothesis.claim_assessments:
            for item in claim.requirement_assessments:
                if item.status is AssessmentStatus.SUPPORTED:
                    assert item.evidence_ids


def test_trace_reaches_back_to_the_source_file() -> None:
    report = _complete_ct_report()
    targets = {edge.target_id for edge in report.trace}
    sources = {edge.source_id for edge in report.trace}
    assert "synthetic/case.out" in targets
    assert f"question:{CT.value}" in sources


def test_report_is_self_contained() -> None:
    """The report must carry what "inspect why" needs, without re-reading anything."""
    report = _complete_ct_report()
    assert report.question.family is CT
    assert report.inventory.facts
    assert report.inventory.evidence
    assert report.trace
    assert report.disclaimer
    assert report.protocol_version


def test_reports_are_reproducible_for_identical_inputs() -> None:
    from qcjudge.render import to_json

    first = _complete_ct_report()
    second = _complete_ct_report()
    assert to_json(first).replace(
        first.generated_at.isoformat(), ""
    ) == to_json(second).replace(second.generated_at.isoformat(), "")


def test_fixtures_match_the_identifiers_asserted_above() -> None:
    assert CT is QuestionFamily.CHARGE_TRANSFER_EXCITATION
    assert TS is QuestionFamily.TRANSITION_STATE_VALIDATION

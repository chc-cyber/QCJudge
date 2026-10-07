"""The acceptance corpus.

`TECHNICALLY_SUCCESSFUL != SCIENTIFICALLY_SUFFICIENT` must hold for every row. Each case
runs through the real engine against a hand-built inventory, so a green suite means the
reasoning is right rather than that a fixture was shaped to fit it.
"""

from __future__ import annotations

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.common import UnavailableReason
from qcjudge.domain.evidence import (
    EvidenceDirectness,
    EvidenceStrength,
    EvidenceType,
    FactKey,
)
from qcjudge.domain.question import QuestionFamily
from qcjudge.domain.validation import ValidationStatus
from tests.support import (
    CT,
    TADF,
    TS,
    converged_calculation,
    ct_question,
    ct_state_count,
    evidence,
    excited_state_evidence,
    fact,
    hole_electron_evidence,
    inventory,
    tadf_facts,
    tadf_gap_evidence,
    tadf_question,
    tadf_soc_evidence,
    ts_evidence,
    ts_facts,
    ts_irc_evidence,
    ts_question,
    unavailable,
)

# --------------------------------------------------------------------------------------
# Charge transfer
# --------------------------------------------------------------------------------------


def _ct_complete():
    return inventory(
        *converged_calculation(),
        ct_state_count(),
        evidence_items=(excited_state_evidence(), hole_electron_evidence()),
    )


def test_ct_with_spatial_descriptor_is_supported() -> None:
    report = audit(ct_question(), _ct_complete())
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED


def test_ct_with_energies_only_is_insufficient_despite_passing_execution() -> None:
    report = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(excited_state_evidence(),),
        ),
    )
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


def test_ct_without_state_assignment_is_insufficient() -> None:
    report = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            unavailable_items=(
                unavailable(FactKey.EXCITED_STATE_COUNT, UnavailableReason.NOT_PROVIDED),
            ),
        ),
    )
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


def test_a_user_assertion_is_recorded_but_does_not_satisfy_a_direct_requirement() -> None:
    """Decision Q2: admissible, capped, and never a substitute for verified evidence."""
    asserted = evidence(
        "assertion-1",
        EvidenceType.HOLE_ELECTRON_ANALYSIS,
        strength=EvidenceStrength.WEAK,
        directness=EvidenceDirectness.INDIRECT,
    )
    report = audit(
        ct_question(),
        inventory(
            *converged_calculation(),
            ct_state_count(),
            evidence_items=(excited_state_evidence(), asserted),
        ),
    )
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


def test_methodology_warning_does_not_change_evidence_status() -> None:
    """The axes are orthogonal: a methodology warning never blocks a supported claim."""
    report = audit(ct_question(), _ct_complete())
    assert report.methodology_status is ValidationStatus.WARNING
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED


# --------------------------------------------------------------------------------------
# TADF potential
# --------------------------------------------------------------------------------------


def test_tadf_with_gap_only_caps_at_partially_supported() -> None:
    """Decision Q6: energetics alone can never reach SUPPORTED, however small the gap."""
    report = audit(
        tadf_question(),
        inventory(*tadf_facts(), evidence_items=(tadf_gap_evidence(),)),
    )
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


def test_the_hypothesis_level_never_contradicts_the_overall_status() -> None:
    """A report that says "unassessable" up top and "partially supported" below is broken."""
    report = audit(
        tadf_question(),
        inventory(*tadf_facts(), evidence_items=(tadf_gap_evidence(),)),
    )
    hypothesis_statuses = {
        item.status for item in report.hypothesis_assessments
    }
    assert hypothesis_statuses == {report.overall_evidence_status}


def test_tadf_with_gap_and_spin_orbit_coupling_is_supported() -> None:
    report = audit(
        tadf_question(),
        inventory(*tadf_facts(), evidence_items=(tadf_gap_evidence(), tadf_soc_evidence())),
    )
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED


def test_tadf_with_inconsistent_methods_requires_expert_review() -> None:
    report = audit(
        tadf_question(),
        inventory(
            *tadf_facts(),
            fact(
                FactKey.METHOD_NAME, "M06-2X", calculation_id="calc-2",
                source_calculation_id="calc-1",
            ),
            evidence_items=(tadf_gap_evidence(), tadf_soc_evidence()),
        ),
    )
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.REQUIRES_EXPERT_REVIEW


# --------------------------------------------------------------------------------------
# Transition state
# --------------------------------------------------------------------------------------


def test_ts_with_one_imaginary_frequency_only_is_partially_supported() -> None:
    report = audit(ts_question(), inventory(*ts_facts(1), evidence_items=(ts_evidence(),)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


def test_ts_with_no_imaginary_frequency_is_contradicted_not_failed() -> None:
    """A converged minimum is a successful calculation and a contradicted claim."""
    report = audit(ts_question(), inventory(*ts_facts(0), evidence_items=(ts_evidence(),)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.structure_status is ValidationStatus.FAIL
    assert report.overall_evidence_status is AssessmentStatus.CONTRADICTED


def test_ts_with_multiple_imaginary_frequencies_is_contradicted() -> None:
    report = audit(ts_question(), inventory(*ts_facts(3), evidence_items=(ts_evidence(),)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.CONTRADICTED


def test_ts_with_path_evidence_is_supported_via_the_alternative() -> None:
    report = audit(
        ts_question(),
        inventory(*ts_facts(1), evidence_items=(ts_evidence(), ts_irc_evidence())),
    )
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    modes = [
        item
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for item in claim.requirement_assessments
        if item.requirement_id == "ts.mode_identity"
    ]
    assert modes and modes[0].met_via_alternative == "ts.pathway_connection"


# --------------------------------------------------------------------------------------
# Execution failure and unreadable input
# --------------------------------------------------------------------------------------


def test_unconverged_scf_is_not_assessable_and_not_a_verdict() -> None:
    report = audit(
        ct_question(),
        inventory(
            fact(FactKey.SCF_CONVERGED, False),
            ct_state_count(),
            evidence_items=(excited_state_evidence(),),
        ),
    )
    assert report.execution_status is ValidationStatus.FAIL
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


def test_unconverged_optimization_is_not_assessable() -> None:
    report = audit(
        ts_question(),
        inventory(
            fact(FactKey.SCF_CONVERGED, True),
            fact(FactKey.GEOMETRY_CONVERGED, False),
            fact(FactKey.FREQUENCY_OBSERVED_MODE_COUNT, 54, unit="modes"),
            fact(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, 54, unit="modes"),
            fact(FactKey.FREQUENCY_IMAGINARY_COUNT, 1, unit="modes"),
            evidence_items=(ts_evidence(),),
        ),
    )
    assert report.execution_status is ValidationStatus.FAIL
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


def test_absent_convergence_markers_stay_unknown() -> None:
    report = audit(ct_question(), inventory(ct_state_count()))
    assert report.execution_status is ValidationStatus.UNKNOWN
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


def test_truncated_mode_list_refuses_to_count_frequencies() -> None:
    """An incomplete Hessian is not a zero-imaginary-frequency result."""
    report = audit(
        ts_question(),
        inventory(*ts_facts(1, observed=12, expected=54), evidence_items=(ts_evidence(),)),
    )
    check = next(
        result
        for result in report.validation_results
        if result.rule_id == "struct.frequency_count"
    )
    assert check.status is ValidationStatus.UNKNOWN
    assert report.overall_evidence_status is not AssessmentStatus.CONTRADICTED


def test_absent_frequency_calculation_is_a_coverage_gap() -> None:
    """Not running the calculation is a gap, not an unanswerable question."""
    report = audit(
        ts_question(),
        inventory(
            fact(FactKey.SCF_CONVERGED, True),
            fact(FactKey.GEOMETRY_CONVERGED, True),
            unavailable_items=(
                unavailable(
                    FactKey.FREQUENCY_IMAGINARY_COUNT, UnavailableReason.NOT_PROVIDED
                ),
            ),
        ),
    )
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


def test_every_declared_rule_resolves() -> None:
    """A protocol naming a rule nobody implements must fail, not silently skip the check."""
    from qcjudge.protocols import get_protocol
    from qcjudge.validators import registered_keys

    for family in (CT, TADF, TS):
        for spec in get_protocol(family).validation_rules:
            assert spec.implementation_key in registered_keys()


def test_only_the_three_initial_families_are_registered() -> None:
    from qcjudge.protocols import PROTOCOLS

    assert set(PROTOCOLS) == set(QuestionFamily)

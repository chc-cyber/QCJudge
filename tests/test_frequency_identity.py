"""Hessian completeness belongs to a calculation, regardless of fact input order."""

from __future__ import annotations

from dataclasses import replace

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.calculation import Observation
from qcjudge.domain.evidence import EvidenceInventory, FactKey
from qcjudge.domain.validation import ValidationStatus
from tests.property_support import (
    common_observations,
    project,
    reader_result,
    scientific_signature,
)
from tests.support import TS, question


def _two_hessians(*, complete: bool) -> EvidenceInventory:
    results = tuple(reader_result(calculation_id, (
        *common_observations(), Observation(FactKey.GEOMETRY_CONVERGED, True),
        Observation(FactKey.FREQUENCY_CM1, (-300.0, *((100.0,) * (observed - 1)))),
        Observation(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, expected),
        Observation(FactKey.IRC_CONNECTS_TWO_MINIMA, True),
    ), source="root" if calculation_id == "child" else None)
        for calculation_id, observed, expected in (
            ("root", 2, 2 if complete else 3), ("child", 3, 3 if complete else 2),
        ))
    return project(results)


def _reverse_expected_facts(inventory: EvidenceInventory) -> EvidenceInventory:
    expected = [
        item for item in inventory.facts if item.key is FactKey.FREQUENCY_EXPECTED_MODE_COUNT
    ]
    expected.reverse()
    reordered = tuple(
        expected.pop(0) if item.key is FactKey.FREQUENCY_EXPECTED_MODE_COUNT else item
        for item in inventory.facts
    )
    return replace(inventory, facts=reordered)


def test_complete_hessians_remain_complete_when_expected_facts_are_reordered() -> None:
    inventory = _two_hessians(complete=True)
    q = question(TS, molecule="molecule", calculation_id="root")
    before = audit(q, inventory)
    after = audit(q, _reverse_expected_facts(inventory))
    assert before.structure_status is after.structure_status is ValidationStatus.PASS
    assert before.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert after.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert scientific_signature(after) == scientific_signature(before)


def test_incomplete_hessians_cannot_be_repaired_by_cross_pairing_expected_counts() -> None:
    inventory = _two_hessians(complete=False)
    q = question(TS, molecule="molecule", calculation_id="root")
    before = audit(q, inventory)
    after = audit(q, _reverse_expected_facts(inventory))
    assert before.structure_status is after.structure_status is ValidationStatus.UNKNOWN
    assert before.overall_evidence_status is not AssessmentStatus.SUPPORTED
    assert scientific_signature(after) == scientific_signature(before)


def test_expected_counts_from_a_linked_analysis_do_not_complete_a_different_hessian() -> None:
    root = reader_result("root", (
        *common_observations(), Observation(FactKey.GEOMETRY_CONVERGED, True),
        Observation(FactKey.FREQUENCY_CM1, (-300.0, 100.0, 200.0)),
        Observation(FactKey.IRC_CONNECTS_TWO_MINIMA, True),
    ))
    child = reader_result("child", (Observation(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, 3),),
                          source="root")
    report = audit(question(TS, molecule="molecule", calculation_id="root"), project((root, child)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.structure_status is ValidationStatus.UNKNOWN
    assert report.overall_evidence_status is not AssessmentStatus.SUPPORTED

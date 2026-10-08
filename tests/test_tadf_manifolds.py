"""TADF manifold evidence requires actual energy lists, not merely present fact keys."""

from __future__ import annotations

from dataclasses import replace

import pytest

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.calculation import Observation
from qcjudge.domain.evidence import (
    EvidenceType,
    FactKey,
    FactPredicate,
    FactPredicateOperator,
    ScalarValue,
)
from qcjudge.domain.validation import ValidationStatus
from tests.property_support import common_observations, project, reader_result
from tests.support import TADF, question

MANIFOLD_PREDICATE = FactPredicate(
    FactKey.SINGLET_STATE_ENERGY_EV, FactPredicateOperator.NONEMPTY_FINITE_NUMERIC_TUPLE,
)


@pytest.mark.parametrize("value", [
    None, False, True, (), "unknown", 0, 2.85, (False,), (True, 2.0), ("2.85",),
    (float("nan"),), (float("inf"),), (float("-inf"),),
])
def test_manifold_predicate_rejects_missing_or_non_numeric_energy_lists(
    value: ScalarValue | tuple[ScalarValue, ...] | None,
) -> None:
    assert not MANIFOLD_PREDICATE.accepts(value)


@pytest.mark.parametrize("value", [(0,), (-1.0,), (2.85,), (-2.0, 0, 2.85), (10**1000,)])
def test_manifold_predicate_accepts_finite_ints_and_floats_without_sign_thresholds(
    value: tuple[int | float, ...],
) -> None:
    assert MANIFOLD_PREDICATE.accepts(value)


@pytest.mark.parametrize("value", [None, False, (), "unknown", (False,)])
@pytest.mark.parametrize("invalid", ["singlet", "triplet", "both"])
def test_public_projection_does_not_treat_invalid_energy_manifolds_as_tadf_evidence(
    value: ScalarValue | tuple[ScalarValue, ...] | None, invalid: str,
) -> None:
    observations = (
        *common_observations(),
        Observation(FactKey.SINGLET_STATE_ENERGY_EV, (2.85,)),
        Observation(FactKey.TRIPLET_STATE_ENERGY_EV, (2.77,)),
        Observation(FactKey.SPIN_ORBIT_COUPLING_CM1, 12.4),
    )
    invalid_keys = {
        "singlet": {FactKey.SINGLET_STATE_ENERGY_EV},
        "triplet": {FactKey.TRIPLET_STATE_ENERGY_EV},
        "both": {FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV},
    }[invalid]
    result = reader_result("root", tuple(
        replace(item, value=value) if item.key in invalid_keys else item for item in observations
    ))
    report = audit(question(TADF, molecule="molecule"), project((result,)))
    assert report.execution_status is ValidationStatus.PASS
    assert not report.inventory.evidence_by_type(EvidenceType.SINGLET_TRIPLET_GAP)
    assert report.inventory.evidence_by_type(EvidenceType.SPIN_ORBIT_COUPLING)
    assert report.overall_evidence_status is not AssessmentStatus.SUPPORTED
    for key in invalid_keys:
        assert report.inventory.facts_by_key(key)[0].value == value


@pytest.mark.parametrize("singlet,triplet", [
    ((2.85,), (2.77,)), ((-1,), (-2.0,)), ((0, 1.5), (0.0, 1)),
])
def test_public_projection_retains_support_for_nonempty_finite_energy_lists(
    singlet: tuple[int | float, ...], triplet: tuple[int | float, ...],
) -> None:
    result = reader_result("root", (
        *common_observations(),
        Observation(FactKey.SINGLET_STATE_ENERGY_EV, singlet),
        Observation(FactKey.TRIPLET_STATE_ENERGY_EV, triplet),
        Observation(FactKey.SPIN_ORBIT_COUPLING_CM1, 12.4),
    ))
    report = audit(question(TADF, molecule="molecule"), project((result,)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.inventory.evidence_by_type(EvidenceType.SINGLET_TRIPLET_GAP)
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED

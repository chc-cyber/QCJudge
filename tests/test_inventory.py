"""Referential integrity and the epistemic guards that make provenance non-negotiable."""

from __future__ import annotations

from dataclasses import replace

import pytest

from qcjudge.domain.assessment import AssessmentStatus, EvidenceAssessment
from qcjudge.domain.common import EpistemicKind, Provenance, UnavailableReason
from qcjudge.domain.evidence import (
    Evidence,
    EvidenceDirectness,
    EvidenceInventory,
    EvidenceOrigin,
    EvidenceStrength,
    EvidenceType,
    ExtractedFact,
    FactKey,
    FactPredicate,
    FactPredicateOperator,
    ScalarValue,
    Subject,
)
from qcjudge.errors import InventoryError
from tests.support import (
    CALCULATION_ID,
    SOURCE_FILE,
    STAMP,
    ct_state_count,
    evidence,
    fact,
    inventory,
    provenance,
    unavailable,
)


def _raw_evidence(
    evidence_id: str, *, origin: EvidenceOrigin, strength: EvidenceStrength, **overrides: object
) -> Evidence:
    defaults: dict[str, object] = {
        "id": evidence_id,
        "evidence_type": EvidenceType.IRC,
        "description": "Synthetic.",
        "fact_ids": (),
        "strength": strength,
        "directness": EvidenceDirectness.DIRECT,
        "origin": origin,
        "provenance": provenance() if origin is not EvidenceOrigin.USER_ASSERTION else None,
    }
    defaults.update(overrides)
    return Evidence(**defaults)  # type: ignore[arg-type]


def test_duplicate_fact_ids_are_rejected() -> None:
    with pytest.raises(InventoryError, match="Fact IDs must be unique"):
        inventory(fact(FactKey.SCF_CONVERGED, True), fact(FactKey.SCF_CONVERGED, False))


@pytest.mark.parametrize("value", [0, 1])
def test_duplicate_calculation_fact_keys_are_rejected_even_with_distinct_ids(value: int) -> None:
    first = fact(FactKey.EXCITED_STATE_COUNT, 1)
    second = replace(first, id="another-source", value=value)
    with pytest.raises(InventoryError, match="unique per calculation and fact key"):
        inventory(first, second)


def test_the_same_fact_key_is_allowed_for_distinct_calculations() -> None:
    first = fact(FactKey.EXCITED_STATE_COUNT, 1, calculation_id="first")
    second = fact(FactKey.EXCITED_STATE_COUNT, 2, calculation_id="second")
    assert inventory(first, second).facts == (first, second)


def test_multiple_state_values_remain_one_list_fact() -> None:
    states = replace(fact(FactKey.SINGLET_STATE_ENERGY_EV, 0), value=(2.1, 2.4, 3.0))
    assert inventory(states).facts[0].value == (2.1, 2.4, 3.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("as_list", [False, True])
def test_nonfinite_float_facts_are_rejected(value: float, as_list: bool) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        replace(fact(FactKey.SINGLET_STATE_ENERGY_EV, 0), value=(2.0, value) if as_list else value)


def test_explicit_none_remains_a_fact_without_a_numeric_value() -> None:
    absent_value = replace(fact(FactKey.SINGLET_TRIPLET_GAP_EV, 0), value=None)
    assert inventory(absent_value).facts[0].value is None


@pytest.mark.parametrize("operator", [
    FactPredicateOperator.NONNEGATIVE_FINITE, FactPredicateOperator.UNIT_INTERVAL,
])
@pytest.mark.parametrize("value", [None, False, True, "0.5", -0.1, float("nan"), float("inf")])
def test_numeric_domain_predicates_refuse_invalid_values(
    operator: FactPredicateOperator, value: ScalarValue | None,
) -> None:
    assert not FactPredicate(FactKey.HOLE_ELECTRON_SR_INDEX, operator).accepts(value)


@pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0])
def test_numeric_domain_predicates_preserve_closed_interval_endpoints(value: ScalarValue) -> None:
    for operator in (FactPredicateOperator.NONNEGATIVE_FINITE, FactPredicateOperator.UNIT_INTERVAL):
        assert FactPredicate(FactKey.HOLE_ELECTRON_SR_INDEX, operator).accepts(value)


def test_nonnegative_distance_predicate_has_no_universal_upper_threshold() -> None:
    assert FactPredicate(
        FactKey.HOLE_ELECTRON_D_INDEX, FactPredicateOperator.NONNEGATIVE_FINITE,
    ).accepts(10**1000)
    assert not FactPredicate(
        FactKey.HOLE_ELECTRON_SR_INDEX, FactPredicateOperator.UNIT_INTERVAL,
    ).accepts(1.01)


def test_duplicate_evidence_ids_are_rejected() -> None:
    with pytest.raises(InventoryError, match="Evidence IDs must be unique"):
        inventory(
            ct_state_count(),
            evidence_items=(evidence("ev", EvidenceType.IRC), evidence("ev", EvidenceType.IRC)),
        )


def test_evidence_citing_an_unknown_fact_is_rejected() -> None:
    with pytest.raises(InventoryError, match="cites unknown facts"):
        inventory(
            ct_state_count(),
            evidence_items=(evidence("ev", EvidenceType.IRC, fact_ids=("ghost",)),),
        )


def test_a_fact_cannot_be_both_present_and_unavailable() -> None:
    with pytest.raises(InventoryError, match="both present and marked unavailable"):
        inventory(
            ct_state_count(),
            unavailable_items=(
                unavailable(FactKey.EXCITED_STATE_COUNT, UnavailableReason.NOT_PROVIDED),
            ),
        )


def test_user_asserted_evidence_may_not_carry_provenance() -> None:
    with pytest.raises(ValueError, match="no file provenance"):
        _raw_evidence(
            "assertion",
            origin=EvidenceOrigin.USER_ASSERTION,
            strength=EvidenceStrength.WEAK,
            directness=EvidenceDirectness.INDIRECT,
            provenance=provenance(),
        )


def test_user_asserted_evidence_is_capped_at_weak_and_indirect() -> None:
    with pytest.raises(ValueError, match="capped at WEAK and INDIRECT"):
        _raw_evidence(
            "assertion", origin=EvidenceOrigin.USER_ASSERTION, strength=EvidenceStrength.STRONG
        )


def test_parsed_evidence_must_carry_provenance() -> None:
    with pytest.raises(ValueError, match="must carry provenance"):
        _raw_evidence(
            "parsed",
            origin=EvidenceOrigin.PARSED,
            strength=EvidenceStrength.STRONG,
            provenance=None,
        )


def test_parsed_evidence_must_cite_a_fact() -> None:
    with pytest.raises(ValueError, match="must cite at least one fact"):
        _raw_evidence(
            "parsed", origin=EvidenceOrigin.PARSED, strength=EvidenceStrength.STRONG
        )


def test_a_supported_assessment_without_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="must cite evidence"):
        EvidenceAssessment("requirement", AssessmentStatus.SUPPORTED, "Synthetic.")


def test_facts_may_only_be_observations_or_computed_facts() -> None:
    with pytest.raises(ValueError, match="observations or computed facts"):
        ExtractedFact(
            id="bad",
            key=FactKey.SCF_CONVERGED,
            value=True,
            unit=None,
            subject=Subject(CALCULATION_ID),
            provenance=provenance(),
            epistemic_kind=EpistemicKind.CLAIM,
        )


def test_provenance_requires_an_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Provenance(
            source_file=SOURCE_FILE,
            producer="tests.support",
            producer_version="0.0.0",
            extracted_at=STAMP.replace(tzinfo=None),
        )


def test_absence_lookup_prefers_an_access_failure() -> None:
    """If any source says we could not read a value, that beats an omission."""
    mixed = EvidenceInventory(
        unavailable=(
            unavailable(FactKey.SCF_CONVERGED, UnavailableReason.NOT_PROVIDED),
            unavailable(FactKey.SCF_CONVERGED, UnavailableReason.AMBIGUOUS_MATCH),
        )
    )
    omitted = EvidenceInventory(
        unavailable=(unavailable(FactKey.SCF_CONVERGED, UnavailableReason.NOT_PROVIDED),)
    )
    assert mixed.unavailable_reason(FactKey.SCF_CONVERGED) is UnavailableReason.AMBIGUOUS_MATCH
    assert omitted.unavailable_reason(FactKey.SCF_CONVERGED) is UnavailableReason.NOT_PROVIDED
    assert omitted.unavailable_reason(FactKey.BASIS_NAME) is None


def test_only_access_failures_are_access_failures() -> None:
    assert not UnavailableReason.NOT_PROVIDED.is_access_failure
    assert UnavailableReason.FILE_TRUNCATED.is_access_failure
    assert UnavailableReason.UNSUPPORTED_CONSTRUCT.is_access_failure
    assert UnavailableReason.AMBIGUOUS_MATCH.is_access_failure


def test_inventory_lookup_helpers() -> None:
    value: ScalarValue = 3
    filled = inventory(
        fact(FactKey.EXCITED_STATE_COUNT, value, unit="states"),
        evidence_items=(evidence("ev", EvidenceType.IRC),),
    )
    assert len(filled.facts_by_key(FactKey.EXCITED_STATE_COUNT)) == 1
    assert len(filled.facts_by_key(FactKey.BASIS_NAME)) == 0
    assert filled.evidence_by_type(EvidenceType.IRC)[0].id == "ev"

"""Derivation: where evidence strength is decided, and by whom.

The parser must not decide how strong a piece of evidence is. These tests hold that line:
strength comes from the protocol declaration, a derivation fires only on a complete set of
facts from one calculation, and nothing is scaled down or guessed in between.
"""

from __future__ import annotations

import pytest

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.evidence import (
    EvidenceDerivation,
    EvidenceDirectness,
    EvidenceOrigin,
    EvidenceStrength,
    EvidenceType,
    FactKey,
)
from qcjudge.domain.protocol import ScientificProtocol
from qcjudge.domain.question import QuestionFamily
from qcjudge.errors import ProtocolError
from qcjudge.evidence import derive_evidence, with_derived_evidence
from qcjudge.protocols import get_protocol
from tests.support import (
    CT,
    TADF,
    TS,
    converged_calculation,
    ct_question,
    fact,
    inventory,
    tadf_facts,
    tadf_question,
    ts_facts,
    ts_question,
)


def _ct_protocol() -> ScientificProtocol:
    return get_protocol(CT)


def test_a_derivation_fires_only_when_every_required_fact_is_present() -> None:
    protocol = _ct_protocol()
    complete = inventory(*converged_calculation(), fact(FactKey.EXCITED_STATE_COUNT, 5))
    partial = inventory(*converged_calculation())
    assert derive_evidence(protocol, complete)
    assert derive_evidence(protocol, partial) == ()


def test_derived_strength_comes_from_the_protocol_not_from_code() -> None:
    protocol = _ct_protocol()
    derived = derive_evidence(
        protocol, inventory(*converged_calculation(), fact(FactKey.EXCITED_STATE_COUNT, 5))
    )
    declared = protocol.derivations[0]
    assert declared.strength is EvidenceStrength.MODERATE
    assert derived[0].strength is declared.strength
    assert derived[0].directness is declared.directness
    assert derived[0].evidence_type is declared.evidence_type


def test_derived_evidence_cites_the_facts_it_came_from() -> None:
    protocol = _ct_protocol()
    derived = derive_evidence(
        protocol, inventory(*converged_calculation(), fact(FactKey.EXCITED_STATE_COUNT, 5))
    )
    assert derived[0].fact_ids == ("calc-1:tddft.state_count",)
    assert derived[0].provenance is not None
    assert derived[0].origin is EvidenceOrigin.PARSED


def test_facts_from_different_calculations_do_not_combine() -> None:
    """A gap assembled from two different jobs is not one derivation."""
    protocol = get_protocol(TADF)
    together = inventory(
        fact(FactKey.SINGLET_STATE_ENERGY_EV, (2.85,), calculation_id="calc-1"),
        fact(FactKey.TRIPLET_STATE_ENERGY_EV, (2.77,), calculation_id="calc-1"),
    )
    split = inventory(
        fact(FactKey.SINGLET_STATE_ENERGY_EV, (2.85,), calculation_id="calc-1"),
        fact(FactKey.TRIPLET_STATE_ENERGY_EV, (2.77,), calculation_id="calc-2"),
    )
    assert derive_evidence(protocol, together)
    assert derive_evidence(protocol, split) == ()


def test_a_partial_match_is_not_scaled_down_into_weaker_evidence() -> None:
    """Inventing a weaker derivation would be a judgement nobody declared."""
    protocol = get_protocol(TADF)
    one_of_two = inventory(fact(FactKey.SINGLET_STATE_ENERGY_EV, (2.85,)))
    assert derive_evidence(protocol, one_of_two) == ()


def test_derived_evidence_is_added_to_the_inventory_without_duplicating() -> None:
    protocol = _ct_protocol()
    base = inventory(*converged_calculation(), fact(FactKey.EXCITED_STATE_COUNT, 5))
    once = with_derived_evidence(protocol, base)
    twice = with_derived_evidence(protocol, once)
    assert len(once.evidence) == 1
    assert once.evidence == twice.evidence


def test_every_built_in_protocol_derives_from_registered_keys() -> None:
    for family in (CT, TADF, TS):
        protocol = get_protocol(family)
        for derivation in protocol.derivations:
            for key in derivation.required_fact_keys:
                assert key in FactKey
            assert derivation.description.strip()


def test_a_protocol_deriving_something_nobody_accepts_is_rejected() -> None:
    """A derivation no requirement can consume is a declaration mistake, not a no-op."""
    protocol = _ct_protocol()
    with pytest.raises(ProtocolError, match="which no requirement accepts"):
        ScientificProtocol(
            id=protocol.id,
            version=protocol.version,
            question_family=protocol.question_family,
            hypotheses=protocol.hypotheses,
            claims=protocol.claims,
            requirements=protocol.requirements,
            validation_rules=protocol.validation_rules,
            derivations=(
                *protocol.derivations,
                EvidenceDerivation(
                    id="orphan",
                    evidence_type=EvidenceType.IRC,
                    required_fact_keys=(FactKey.CHARGE,),
                    description="Nothing consumes this.",
                    strength=EvidenceStrength.STRONG,
                    directness=EvidenceDirectness.DIRECT,
                ),
            ),
        )


def test_a_derivation_must_depend_on_at_least_one_fact() -> None:
    with pytest.raises(ValueError, match="at least one fact"):
        EvidenceDerivation(
            id="empty",
            evidence_type=EvidenceType.IRC,
            required_fact_keys=(),
            description="Depends on nothing.",
            strength=EvidenceStrength.WEAK,
            directness=EvidenceDirectness.DIRECT,
        )


def test_the_engine_applies_derivations_without_the_caller_asking() -> None:
    report = audit(ts_question(), inventory(*ts_facts(1)))
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED
    derived = [item for item in report.inventory.evidence if item.id.startswith("derived:")]
    assert derived
    assert derived[0].origin is EvidenceOrigin.PARSED


def test_a_tadf_gap_statement_alone_still_reaches_the_cap() -> None:
    """The derived gap evidence is MODERATE, so it satisfies the gap but never the RISC."""
    report = audit(tadf_question(), inventory(*tadf_facts()))
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


def test_a_ct_report_without_a_descriptor_stays_insufficient_with_derivation() -> None:
    report = audit(
        ct_question(),
        inventory(*converged_calculation(), fact(FactKey.EXCITED_STATE_COUNT, 5)),
    )
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


def test_question_family_dispatch_uses_the_matching_protocol() -> None:
    report = audit(ts_question(), inventory(*ts_facts(1)))
    assert report.protocol_id == get_protocol(QuestionFamily.TRANSITION_STATE_VALIDATION).id

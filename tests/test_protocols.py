"""Protocol declarations must be internally consistent, and never silently incomplete."""

from __future__ import annotations

import re

import pytest

from qcjudge.audit.trace import build_trace
from qcjudge.domain.evidence import (
    EvidenceDerivation,
    EvidenceDirectness,
    EvidenceGroup,
    EvidenceInventory,
    EvidenceRequirement,
    EvidenceStrength,
    EvidenceType,
    FactKey,
    RequirementLevel,
)
from qcjudge.domain.protocol import ScientificProtocol
from qcjudge.domain.question import Claim, Hypothesis, QuestionFamily, ResearchQuestion
from qcjudge.domain.validation import ValidationRuleSpec, ValidationScope
from qcjudge.errors import ProtocolError
from qcjudge.protocols import PROTOCOLS, get_protocol
from qcjudge.validators import registered_keys

# Placeholders a protocol's claim templates expect the question to bind.
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def _claim(claim_id: str = "claim", hypothesis_id: str = "hypothesis") -> Claim:
    return Claim(claim_id, hypothesis_id, "A synthetic checkable statement.")


def _requirement(requirement_id: str = "requirement", **overrides: object):
    defaults: dict[str, object] = {
        "id": requirement_id,
        "claim_id": "claim",
        "description": "Synthetic requirement.",
        "level": RequirementLevel.REQUIRED,
        "accepted_evidence_types": (EvidenceType.IRC,),
    }
    defaults.update(overrides)
    return EvidenceRequirement(**defaults)  # type: ignore[arg-type]


def _protocol(**overrides: object) -> ScientificProtocol:
    defaults: dict[str, object] = {
        "id": "synthetic",
        "version": "1.0.0",
        "question_family": QuestionFamily.CHARGE_TRANSFER_EXCITATION,
        "hypotheses": (Hypothesis("hypothesis", "A synthetic hypothesis."),),
        "claims": (_claim(),),
        "requirements": (_requirement(),),
        "validation_rules": (),
    }
    defaults.update(overrides)
    return ScientificProtocol(**defaults)  # type: ignore[arg-type]


def _bound_question(protocol: ScientificProtocol) -> ResearchQuestion:
    """A question whose context satisfies every placeholder the protocol uses."""
    keys = sorted(
        {
            match.group(1)
            for claim in protocol.claims
            for match in _PLACEHOLDER.finditer(claim.statement)
        }
    )
    return ResearchQuestion(
        family=protocol.question_family,
        text="A synthetic question.",
        hypotheses=tuple(
            Hypothesis(item.id, item.statement) for item in protocol.hypotheses
        ),
        context=tuple((key, "value") for key in keys),
    )


def test_exactly_three_initial_question_families_are_registered() -> None:
    assert set(PROTOCOLS) == set(QuestionFamily)


def test_every_declared_rule_is_implemented() -> None:
    for protocol in PROTOCOLS.values():
        for spec in protocol.validation_rules:
            assert spec.implementation_key in registered_keys()


def test_protocol_rejects_requirement_for_unknown_claim() -> None:
    with pytest.raises(ProtocolError, match="Unknown claim ID"):
        _protocol(requirements=(_requirement(claim_id="missing"),))


def test_protocol_rejects_claim_for_unknown_hypothesis() -> None:
    with pytest.raises(ProtocolError, match="unknown hypothesis"):
        _protocol(claims=(_claim(hypothesis_id="missing"),))


def test_protocol_rejects_unknown_requirement_dependency() -> None:
    with pytest.raises(ProtocolError, match="Unknown requirement IDs"):
        _protocol(requirements=(_requirement(dependencies=("absent",)),))


def test_protocol_rejects_cyclic_dependencies() -> None:
    with pytest.raises(ProtocolError, match="Cyclic requirement dependencies"):
        _protocol(
            requirements=(
                _requirement("a", dependencies=("b",)),
                _requirement("b", dependencies=("a",)),
            )
        )


def test_protocol_rejects_group_with_unknown_member() -> None:
    with pytest.raises(ProtocolError, match="unknown requirements"):
        _protocol(
            requirements=(
                _requirement("a", group_id="pair"),
                _requirement("b", group_id="pair"),
            ),
            groups=(EvidenceGroup("pair", ("a", "ghost")),),
        )


def test_protocol_rejects_requirement_naming_an_unknown_rule() -> None:
    with pytest.raises(ProtocolError, match="unknown rules"):
        _protocol(requirements=(_requirement(gating_rules=("nope",)),))


def test_protocol_rejects_duplicate_ids() -> None:
    with pytest.raises(ProtocolError, match="must be unique"):
        _protocol(requirements=(_requirement("a"), _requirement("a")))


def test_group_needs_at_least_two_members() -> None:
    with pytest.raises(ValueError, match="at least two members"):
        EvidenceGroup("solo", ("a",))


def test_requirement_needs_an_accepted_evidence_type() -> None:
    with pytest.raises(ValueError, match="at least one evidence type"):
        _requirement(accepted_evidence_types=())


def test_requirement_cannot_depend_on_itself() -> None:
    with pytest.raises(ValueError, match="cannot depend on itself"):
        _requirement("a", dependencies=("a",))


def test_declared_rule_scopes_are_known() -> None:
    scopes = {scope for protocol in PROTOCOLS.values() for scope in
              (rule.scope for rule in protocol.validation_rules)}
    assert scopes <= set(ValidationScope)


def test_transition_state_declares_the_structural_rule_outside_execution() -> None:
    """Zero imaginary frequencies is a structural finding, not a failed calculation."""
    protocol = get_protocol(QuestionFamily.TRANSITION_STATE_VALIDATION)
    scopes = {rule.id: rule.scope for rule in protocol.validation_rules}
    assert scopes["struct.frequency_count"] is ValidationScope.STRUCTURE
    assert scopes["exec.optimization"] is ValidationScope.EXECUTION


def test_ct_spatial_requirement_accepts_only_quantitative_descriptors() -> None:
    protocol = get_protocol(QuestionFamily.CHARGE_TRANSFER_EXCITATION)
    spatial = next(
        item for item in protocol.requirements if item.id == "ct.spatial_redistribution"
    )
    assert EvidenceType.EXCITED_STATE_ASSIGNMENT not in spatial.accepted_evidence_types
    assert EvidenceType.HOLE_ELECTRON_ANALYSIS in spatial.accepted_evidence_types


def test_tadf_gap_requirement_does_not_accept_coupling_evidence() -> None:
    """The gap and the RISC channel are separate requirements on purpose."""
    protocol = get_protocol(QuestionFamily.TADF_POTENTIAL)
    gap = next(
        item for item in protocol.requirements if item.id == "tadf.singlet_triplet_states"
    )
    assert gap.accepted_evidence_types == (EvidenceType.SINGLET_TRIPLET_GAP,)
    assert FactKey.SINGLET_STATE_ENERGY_EV in gap.required_facts
    assert FactKey.TRIPLET_STATE_ENERGY_EV in gap.required_facts


def test_evidence_strength_is_declared_by_the_protocol_not_the_parser() -> None:
    """Every derivation states its own strength; none is applied implicitly in code."""
    for protocol in PROTOCOLS.values():
        assert protocol.derivations
        for derivation in protocol.derivations:
            assert derivation.strength in set(EvidenceStrength)
            assert derivation.directness in set(EvidenceDirectness)
            assert derivation.description.strip()


def test_a_derivation_must_be_consumed_by_some_requirement() -> None:
    """A derivation nobody can accept is a declaration mistake, caught at construction."""
    with pytest.raises(ProtocolError, match="which no requirement accepts"):
        _protocol(
            derivations=(
                EvidenceDerivation(
                    id="orphan",
                    evidence_type=EvidenceType.NTO_ANALYSIS,
                    required_fact_keys=(FactKey.CHARGE,),
                    description="Nothing consumes this.",
                    strength=EvidenceStrength.STRONG,
                    directness=EvidenceDirectness.DIRECT,
                ),
            )
        )


def test_every_protocol_declares_a_maximum_defensible_strength() -> None:
    for protocol in PROTOCOLS.values():
        assert protocol.max_defensible_claim_strength


def test_rule_spec_requires_an_implementation_key() -> None:
    spec = ValidationRuleSpec(
        "synthetic.rule", ValidationScope.EXECUTION, "Synthetic.", "scf_converged"
    )
    assert spec.implementation_key == "scf_converged"


# -- id namespaces -----------------------------------------------------------------------


def test_protocol_rejects_a_claim_and_requirement_sharing_an_id() -> None:
    """One id meaning two things makes every trace edge nameless."""
    with pytest.raises(ProtocolError, match="claim and requirement namespaces"):
        _protocol(requirements=(_requirement(requirement_id="claim"),))


def test_no_builtin_protocol_reuses_an_id_across_namespaces() -> None:
    """Trace edges are strings, so ids must be unambiguous before an edge is built."""
    for protocol in PROTOCOLS.values():
        claim_ids = {claim.id for claim in protocol.claims}
        requirement_ids = {requirement.id for requirement in protocol.requirements}
        assert not (claim_ids & requirement_ids), protocol.id


def test_no_builtin_protocol_trace_contains_a_self_loop() -> None:
    """A requirement sharing its claim's id produced a self-referential edge."""
    for family, protocol in PROTOCOLS.items():
        edges = build_trace(
            _bound_question(protocol),
            protocol,
            EvidenceInventory(),
            (),
        )
        loops = [edge for edge in edges if edge.source_id == edge.target_id]
        assert not loops, f"{family.value}: {[(e.source_id, e.relation) for e in loops]}"

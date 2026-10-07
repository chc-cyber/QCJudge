"""Versioned, typed scientific protocol schema.

Protocols are typed Python data rather than YAML: construction-time validation, refactoring
safety, and direct testability, with no runtime schema dependency. Serialisation can be
added at the boundary later without making serialised data authoritative.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from qcjudge.domain.evidence import (
    EvidenceDerivation,
    EvidenceGroup,
    EvidenceRequirement,
    RequirementLevel,
)
from qcjudge.domain.question import Claim, Hypothesis, Interpretation, QuestionFamily
from qcjudge.domain.validation import ValidationRuleSpec
from qcjudge.errors import ProtocolError


def order_requirements(
    requirements: Sequence[EvidenceRequirement],
) -> tuple[EvidenceRequirement, ...]:
    """Return requirements in dependency order, refusing a cyclic graph.

    The engine evaluates premises before the requirements that depend on them, so the order
    is a correctness property rather than a presentation detail.
    """
    remaining = {requirement.id: requirement for requirement in requirements}
    ordered: list[EvidenceRequirement] = []
    resolved: set[str] = set()
    while remaining:
        ready = [
            requirement
            for requirement in remaining.values()
            if set(requirement.dependencies) <= resolved
        ]
        if not ready:
            raise ProtocolError(
                f"Cyclic requirement dependencies among {sorted(remaining)}"
            )
        for requirement in ready:
            ordered.append(requirement)
            resolved.add(requirement.id)
            del remaining[requirement.id]
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class RecommendationSpec:
    id: str
    when_requirement_id: str
    action: str
    rationale: str


@dataclass(frozen=True, slots=True)
class ScientificProtocol:
    """A versioned, inspectable declaration of what a question family needs."""

    id: str
    version: str
    question_family: QuestionFamily
    hypotheses: tuple[Hypothesis, ...]
    claims: tuple[Claim, ...]
    requirements: tuple[EvidenceRequirement, ...]
    validation_rules: tuple[ValidationRuleSpec, ...]
    recommendations: tuple[RecommendationSpec, ...] = ()
    groups: tuple[EvidenceGroup, ...] = ()
    derivations: tuple[EvidenceDerivation, ...] = ()
    background: tuple[Interpretation, ...] = ()
    limitations: tuple[str, ...] = ()
    max_defensible_claim_strength: str | None = None

    def __post_init__(self) -> None:
        self._check_unique_ids()
        self._check_id_namespaces_are_disjoint()
        hypothesis_ids = {hypothesis.id for hypothesis in self.hypotheses}
        for claim in self.claims:
            if claim.hypothesis_id not in hypothesis_ids:
                raise ProtocolError(f"Claim {claim.id!r} names unknown hypothesis")
        claim_ids = {claim.id for claim in self.claims}
        requirement_ids = {requirement.id for requirement in self.requirements}
        rule_ids = {rule.id for rule in self.validation_rules}
        group_ids = {group.id for group in self.groups}
        for requirement in self.requirements:
            if requirement.claim_id not in claim_ids:
                raise ProtocolError(f"Unknown claim ID: {requirement.claim_id}")
            referenced = set(requirement.dependencies)
            unknown = sorted(referenced - requirement_ids)
            if unknown:
                raise ProtocolError(f"Unknown requirement IDs: {unknown}")
            if requirement.group_id is not None and requirement.group_id not in group_ids:
                raise ProtocolError(
                    f"Requirement {requirement.id!r} names unknown group "
                    f"{requirement.group_id!r}"
                )
            unknown_rules = sorted(
                (set(requirement.gating_rules) | set(requirement.contradicting_rules))
                - rule_ids
            )
            if unknown_rules:
                raise ProtocolError(
                    f"Requirement {requirement.id!r} references unknown rules: {unknown_rules}"
                )
        for group in self.groups:
            unknown_members = sorted(set(group.member_ids) - requirement_ids)
            if unknown_members:
                raise ProtocolError(
                    f"Group {group.id!r} names unknown requirements: {unknown_members}"
                )
        for recommendation in self.recommendations:
            if recommendation.when_requirement_id not in requirement_ids:
                raise ProtocolError(
                    f"Recommendation {recommendation.id!r} references unknown requirement "
                    f"{recommendation.when_requirement_id!r}"
                )
        accepted_types = {
            kind
            for requirement in self.requirements
            for kind in requirement.accepted_evidence_types
        }
        for derivation in self.derivations:
            if derivation.evidence_type not in accepted_types:
                raise ProtocolError(
                    f"Derivation {derivation.id!r} produces "
                    f"{derivation.evidence_type.value!r}, which no requirement accepts"
                )
        # Checked last: a dependency on an unknown id would otherwise be misreported as a
        # cycle, since an unresolvable dependency never becomes ready.
        order_requirements(self.requirements)

    def _check_unique_ids(self) -> None:
        for label, values in (
            ("Hypothesis", [hypothesis.id for hypothesis in self.hypotheses]),
            ("Claim", [claim.id for claim in self.claims]),
            ("Requirement", [requirement.id for requirement in self.requirements]),
            ("Validation rule", [rule.id for rule in self.validation_rules]),
            ("Recommendation", [item.id for item in self.recommendations]),
            ("Group", [group.id for group in self.groups]),
            ("Derivation", [derivation.id for derivation in self.derivations]),
            ("Background", [item.id for item in self.background]),
        ):
            if len(set(values)) != len(values):
                raise ProtocolError(f"{label} IDs must be unique within a protocol")

    def _check_id_namespaces_are_disjoint(self) -> None:
        """A claim and a requirement must never share an id.

        Trace edges are plain strings, so one id meaning two things makes a relation
        unreadable: a requirement that happens to share its claim's id produces a
        self-referential edge that no longer says what it claims to say.
        """
        namespaces = {
            "hypothesis": {hypothesis.id for hypothesis in self.hypotheses},
            "claim": {claim.id for claim in self.claims},
            "requirement": {requirement.id for requirement in self.requirements},
            "validation rule": {rule.id for rule in self.validation_rules},
        }
        labels = sorted(namespaces)
        for index, first in enumerate(labels):
            for second in labels[index + 1 :]:
                shared = sorted(namespaces[first] & namespaces[second])
                if shared:
                    raise ProtocolError(
                        f"IDs shared between the {first} and {second} namespaces: {shared}"
                    )

    @property
    def required_requirements(self) -> tuple[EvidenceRequirement, ...]:
        return tuple(
            requirement
            for requirement in self.requirements
            if requirement.level is RequirementLevel.REQUIRED
        )

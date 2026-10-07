"""Fold requirement assessments into claim, hypothesis, and overall conclusions.

The fold is deterministic and contains no scientific branching: it only combines statuses
that the matcher and the validators already produced. Its one substantive rule is that
prerequisite requirements cannot manufacture support -- only substantive requirements can
lift a claim from unsupported to partially supported.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from qcjudge.domain.assessment import (
    AssessmentStatus,
    ClaimAssessment,
    EvidenceAssessment,
    HypothesisAssessment,
)
from qcjudge.domain.evidence import EvidenceRequirement, RequirementLevel, RequirementRole
from qcjudge.domain.protocol import ScientificProtocol
from qcjudge.domain.question import bind


@dataclass(frozen=True, slots=True)
class _Signal:
    status: AssessmentStatus
    role: RequirementRole
    expert_review_required: bool


def combine(statuses: Sequence[AssessmentStatus]) -> AssessmentStatus:
    """Reduce claim statuses to a hypothesis status, on the same rule as the overall one.

    Using a different rule here would let one report contradict itself: a hypothesis
    reported as unassessable while the audit as a whole is partially supported.
    """
    if not statuses:
        return AssessmentStatus.NOT_ASSESSABLE
    if any(status is AssessmentStatus.CONTRADICTED for status in statuses):
        return AssessmentStatus.CONTRADICTED
    if any(status is AssessmentStatus.NOT_ASSESSABLE for status in statuses):
        return AssessmentStatus.NOT_ASSESSABLE
    if any(status is AssessmentStatus.REQUIRES_EXPERT_REVIEW for status in statuses):
        return AssessmentStatus.REQUIRES_EXPERT_REVIEW
    if all(status is AssessmentStatus.SUPPORTED for status in statuses):
        return AssessmentStatus.SUPPORTED
    if any(status is AssessmentStatus.SUPPORTED for status in statuses):
        return AssessmentStatus.PARTIALLY_SUPPORTED
    return AssessmentStatus.INSUFFICIENT


def reduce_required(signals: Sequence[_Signal]) -> AssessmentStatus:
    """Status implied by the required requirements of one claim, or all of a protocol."""
    if not signals:
        return AssessmentStatus.NOT_ASSESSABLE
    if any(signal.status is AssessmentStatus.CONTRADICTED for signal in signals):
        return AssessmentStatus.CONTRADICTED
    if any(signal.status is AssessmentStatus.NOT_ASSESSABLE for signal in signals):
        return AssessmentStatus.NOT_ASSESSABLE
    if any(signal.expert_review_required for signal in signals):
        return AssessmentStatus.REQUIRES_EXPERT_REVIEW
    if all(signal.status is AssessmentStatus.SUPPORTED for signal in signals):
        return AssessmentStatus.SUPPORTED
    supported_substantive = any(
        signal.role is RequirementRole.SUBSTANTIVE
        and signal.status
        in {AssessmentStatus.SUPPORTED, AssessmentStatus.PARTIALLY_SUPPORTED}
        for signal in signals
    )
    if supported_substantive:
        return AssessmentStatus.PARTIALLY_SUPPORTED
    return AssessmentStatus.INSUFFICIENT


def _signal(requirement: EvidenceRequirement, assessment: EvidenceAssessment) -> _Signal:
    return _Signal(
        status=assessment.status,
        role=requirement.role,
        expert_review_required=assessment.expert_review_required,
    )


def _rationale(status: AssessmentStatus, subject: str) -> str:
    return {
        AssessmentStatus.SUPPORTED: f"Every required evidence item for {subject} is covered.",
        AssessmentStatus.PARTIALLY_SUPPORTED: (
            f"Some substantive evidence for {subject} is present, but the claim is not "
            "fully covered."
        ),
        AssessmentStatus.INSUFFICIENT: (
            f"No substantive evidence for {subject} was established."
        ),
        AssessmentStatus.CONTRADICTED: (
            f"Available evidence contradicts a required condition for {subject}."
        ),
        AssessmentStatus.NOT_ASSESSABLE: (
            f"The inputs needed to judge {subject} are unavailable or unusable."
        ),
        AssessmentStatus.REQUIRES_EXPERT_REVIEW: (
            f"A declared expert boundary was reached for {subject}."
        ),
    }[status]


def build_assessments(
    protocol: ScientificProtocol,
    bindings: Mapping[str, str],
    requirement_assessments: Sequence[EvidenceAssessment],
) -> tuple[tuple[HypothesisAssessment, ...], AssessmentStatus]:
    """Build the claim, hypothesis, and overall levels from requirement results."""
    by_id: dict[str, EvidenceAssessment] = {
        assessment.requirement_id: assessment for assessment in requirement_assessments
    }
    requirements_by_claim: dict[str, list[EvidenceRequirement]] = {}
    for requirement in protocol.requirements:
        requirements_by_claim.setdefault(requirement.claim_id, []).append(requirement)

    claim_assessments: list[ClaimAssessment] = []
    for claim in protocol.claims:
        owned = [
            requirement
            for requirement in requirements_by_claim.get(claim.id, ())
            if requirement.id in by_id
        ]
        required = [
            requirement
            for requirement in owned
            if requirement.level is RequirementLevel.REQUIRED
        ]
        # A claim whose evidence is only recommended is still a claim: judging it by nothing
        # would report it as unassessable rather than as unevidenced.
        judged = required or owned
        status = reduce_required([_signal(item, by_id[item.id]) for item in judged])
        statement = bind(claim.statement, bindings)
        claim_assessments.append(
            ClaimAssessment(
                claim_id=claim.id,
                hypothesis_id=claim.hypothesis_id,
                statement=statement,
                status=status,
                rationale=_rationale(status, "this claim"),
                requirement_assessments=tuple(by_id[item.id] for item in owned),
            )
        )

    hypothesis_assessments: list[HypothesisAssessment] = []
    for hypothesis in protocol.hypotheses:
        mine = [
            claim for claim in claim_assessments if claim.hypothesis_id == hypothesis.id
        ]
        status = combine([claim.status for claim in mine])
        hypothesis_assessments.append(
            HypothesisAssessment(
                hypothesis_id=hypothesis.id,
                statement=hypothesis.statement,
                status=status,
                rationale=_rationale(status, "the hypothesis"),
                claim_assessments=tuple(mine),
            )
        )

    required_signals = [
        _signal(
            requirement,
            by_id[requirement.id],
        )
        for requirement in protocol.requirements
        if requirement.level is RequirementLevel.REQUIRED and requirement.id in by_id
    ]
    return tuple(hypothesis_assessments), reduce_required(required_signals)

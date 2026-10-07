"""Evidence coverage assessments; intentionally not a scalar score.

Statuses are defined so that "we could not read the input" and "the input was never
produced" stay distinguishable, and so that a partly covered claim is not reported as
supported.
"""

from dataclasses import dataclass
from enum import StrEnum

from qcjudge.domain.evidence import EvidenceType


class AssessmentStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INSUFFICIENT = "insufficient"
    CONTRADICTED = "contradicted"
    NOT_ASSESSABLE = "not_assessable"
    REQUIRES_EXPERT_REVIEW = "requires_expert_review"


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """Coverage of one requirement, with the evidence that carried it."""

    requirement_id: str
    status: AssessmentStatus
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    missing_evidence_types: tuple[EvidenceType, ...] = ()
    blocked_by: tuple[str, ...] = ()
    expert_review_required: bool = False
    met_via_alternative: str | None = None

    def __post_init__(self) -> None:
        if self.status is AssessmentStatus.SUPPORTED and not self.evidence_ids:
            raise ValueError("A supported assessment must cite evidence")


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    claim_id: str
    hypothesis_id: str
    statement: str
    status: AssessmentStatus
    rationale: str
    requirement_assessments: tuple[EvidenceAssessment, ...]


@dataclass(frozen=True, slots=True)
class HypothesisAssessment:
    """The level at which a broad proposition is declared established or not."""

    hypothesis_id: str
    statement: str
    status: AssessmentStatus
    rationale: str
    claim_assessments: tuple[ClaimAssessment, ...]

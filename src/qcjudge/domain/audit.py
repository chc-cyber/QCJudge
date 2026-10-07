"""The audit report: a self-contained, inspectable record of one audit.

The report carries the question, the inventory it was judged against, the validation
results, assessments at all three levels, the trace edges, and the versions involved. That
is what makes "why did it say that" answerable from the report alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qcjudge.domain.assessment import AssessmentStatus, HypothesisAssessment
from qcjudge.domain.context import ExpertReviewFlag
from qcjudge.domain.evidence import EvidenceInventory
from qcjudge.domain.question import ResearchQuestion
from qcjudge.domain.validation import ValidationResult, ValidationScope, ValidationStatus

DISCLAIMER = (
    "This report evaluates evidence adequacy. It does not determine scientific truth."
)


@dataclass(frozen=True, slots=True)
class TraceEdge:
    """One edge of the reasoning graph, so the report can show why a status was produced."""

    source_id: str
    relation: str
    target_id: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    id: str
    action: str
    rationale: str
    addresses_requirement_ids: tuple[str, ...]
    priority: int = 0


@dataclass(frozen=True, slots=True)
class AuditReport:
    question: ResearchQuestion
    protocol_id: str
    protocol_version: str
    inventory: EvidenceInventory
    validation_results: tuple[ValidationResult, ...]
    hypothesis_assessments: tuple[HypothesisAssessment, ...]
    overall_evidence_status: AssessmentStatus
    generated_at: datetime
    trace: tuple[TraceEdge, ...] = ()
    recommendations: tuple[Recommendation, ...] = ()
    limitations: tuple[str, ...] = ()
    background: tuple[str, ...] = ()
    max_defensible_claim: str | None = None
    tool_version: str = "0.1.0.dev1"
    disclaimer: str = DISCLAIMER
    selected_calculation_ids: tuple[str, ...] = ()
    association_issue: str | None = None
    conditions: tuple[tuple[str, str], ...] = ()
    expert_reviews: tuple[ExpertReviewFlag, ...] = ()

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")

    def results_in(self, scope: ValidationScope) -> tuple[ValidationResult, ...]:
        return tuple(
            result for result in self.validation_results if result.scope is scope
        )

    @property
    def execution_status(self) -> ValidationStatus:
        """Did the calculation finish? Never folded into evidence adequacy."""
        statuses = tuple(
            result.status for result in self.results_in(ValidationScope.EXECUTION)
        )
        if not statuses or ValidationStatus.UNKNOWN in statuses:
            return ValidationStatus.UNKNOWN
        if ValidationStatus.FAIL in statuses:
            return ValidationStatus.FAIL
        if ValidationStatus.WARNING in statuses:
            return ValidationStatus.WARNING
        return ValidationStatus.PASS

    @property
    def structure_status(self) -> ValidationStatus:
        """What is the computed object, independently of whether it is what was wanted?"""
        statuses = tuple(
            result.status for result in self.results_in(ValidationScope.STRUCTURE)
        )
        if not statuses:
            return ValidationStatus.UNKNOWN
        if ValidationStatus.UNKNOWN in statuses:
            return ValidationStatus.UNKNOWN
        if ValidationStatus.FAIL in statuses:
            return ValidationStatus.FAIL
        if ValidationStatus.WARNING in statuses:
            return ValidationStatus.WARNING
        return ValidationStatus.PASS

    @property
    def methodology_status(self) -> ValidationStatus:
        """Are the inputs mutually consistent?

        With no methodology check declared there is nothing to report, so the answer is
        ``UNKNOWN`` -- not ``PASS``. A scope that was never examined must not be indistinguishable
        from one that was examined and found consistent, or "technically successful" would read
        as "scientifically checked".
        """
        statuses = tuple(
            result.status for result in self.results_in(ValidationScope.METHODOLOGY)
        )
        if not statuses:
            return ValidationStatus.UNKNOWN
        if ValidationStatus.REQUIRES_EXPERT_REVIEW in statuses:
            return ValidationStatus.REQUIRES_EXPERT_REVIEW
        if ValidationStatus.UNKNOWN in statuses:
            return ValidationStatus.UNKNOWN
        if ValidationStatus.WARNING in statuses:
            return ValidationStatus.WARNING
        return ValidationStatus.PASS

"""The audit engine: orchestration only.

This module deliberately contains **no** scientific branching. It does not know which
requirement is which, or which rule means what. It resolves the protocol's declared rules
through the registry, hands them the context, passes the results to the matcher, and folds
the outcome. All science lives in ``protocols/``, ``validators/``, and ``evidence/``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from qcjudge.audit.aggregation import build_assessments
from qcjudge.audit.trace import build_trace
from qcjudge.domain.assessment import AssessmentStatus, EvidenceAssessment
from qcjudge.domain.audit import AuditReport, Recommendation
from qcjudge.domain.context import AuditContext, ExpertReviewFlag
from qcjudge.domain.evidence import EvidenceInventory, EvidenceRequirement, RequirementLevel
from qcjudge.domain.protocol import ScientificProtocol
from qcjudge.domain.question import ResearchQuestion
from qcjudge.domain.validation import ValidationResult
from qcjudge.evidence import with_derived_evidence
from qcjudge.evidence.matching import assess_all
from qcjudge.evidence.selection import select_inventory
from qcjudge.protocols import get_protocol
from qcjudge.validators import resolve

TOOL_VERSION = "0.1.0.dev2"


def run_validation_rules(
    protocol: ScientificProtocol, ctx: AuditContext
) -> tuple[ValidationResult, ...]:
    """Run every rule the protocol declares, resolving it by ``implementation_key``.

    Resolution happens before anything else, so a protocol naming a rule nobody implements
    fails immediately instead of silently skipping that check.
    """
    results: list[ValidationResult] = []
    for spec in protocol.validation_rules:
        outcome = resolve(spec.implementation_key)(ctx)
        results.append(
            ValidationResult(
                rule_id=spec.id,
                scope=spec.scope,
                status=outcome.status,
                message=outcome.message,
                fact_ids=outcome.fact_ids,
            )
        )
    return tuple(results)


def audit(
    question: ResearchQuestion,
    inventory: EvidenceInventory,
    *,
    generated_at: datetime | None = None,
    conditions: Mapping[str, str] | None = None,
    expert_reviews: Sequence[ExpertReviewFlag] = (),
) -> AuditReport:
    """Audit an evidence inventory against the protocol for a question family.

    Evidence the protocol declares as derivable from facts is added before matching, so a
    caller supplies facts plus whatever evidence it already has, and never has to remember
    which derivations apply.

    ``conditions`` carries what a researcher reports about their own calculation -- the
    partition they chose, the character they assigned -- which no parser can observe. A
    protocol may name one by key to have an expert boundary tested rather than guessed.
    ``expert_reviews`` records a boundary reached directly.
    """
    protocol = get_protocol(question.family)
    effective = with_derived_evidence(protocol, inventory)
    selection = select_inventory(question, effective)
    ctx = AuditContext(
        question=question,
        protocol=protocol,
        inventory=selection.inventory,
        conditions=dict(conditions or {}),
        expert_reviews=tuple(expert_reviews),
        association_issue=selection.issue,
    )
    validations = run_validation_rules(protocol, ctx)
    rule_results = {result.rule_id: result for result in validations}
    requirement_assessments = assess_all(ctx, rule_results)
    hypotheses, overall = build_assessments(
        protocol, question.bindings, requirement_assessments
    )
    return AuditReport(
        question=question,
        protocol_id=protocol.id,
        protocol_version=protocol.version,
        inventory=effective,
        validation_results=validations,
        hypothesis_assessments=hypotheses,
        overall_evidence_status=overall,
        generated_at=generated_at or datetime.now(UTC),
        trace=build_trace(question, protocol, effective, requirement_assessments),
        recommendations=_recommendations(protocol, requirement_assessments),
        limitations=protocol.limitations,
        background=tuple(item.statement for item in protocol.background),
        max_defensible_claim=protocol.max_defensible_claim_strength,
        tool_version=TOOL_VERSION,
        selected_calculation_ids=selection.calculation_ids,
        association_issue=selection.issue,
        conditions=tuple(sorted((conditions or {}).items())),
        expert_reviews=tuple(expert_reviews),
    )


def _dependency_weight(protocol: ScientificProtocol, requirement_id: str) -> int:
    return sum(
        1
        for requirement in protocol.requirements
        if requirement_id in requirement.dependencies
    )


def _priority(
    protocol: ScientificProtocol,
    requirement: EvidenceRequirement,
    assessments: Mapping[str, EvidenceAssessment],
) -> int:
    """Higher means "closes more of the gap first"."""
    score = 10 if requirement.level is RequirementLevel.REQUIRED else 0
    score += _dependency_weight(protocol, requirement.id)
    blocked = assessments.get(requirement.id)
    if blocked is not None and blocked.blocked_by:
        score -= 1
    return score


def _recommendations(
    protocol: ScientificProtocol, assessments: Sequence[EvidenceAssessment]
) -> tuple[Recommendation, ...]:
    by_id = {assessment.requirement_id: assessment for assessment in assessments}
    by_requirement = {requirement.id: requirement for requirement in protocol.requirements}
    recommendations: list[Recommendation] = []
    for spec in protocol.recommendations:
        assessment = by_id.get(spec.when_requirement_id)
        if assessment is None or assessment.status is AssessmentStatus.SUPPORTED:
            continue
        requirement = by_requirement[spec.when_requirement_id]
        recommendations.append(
            Recommendation(
                id=spec.id,
                action=spec.action,
                rationale=spec.rationale,
                addresses_requirement_ids=(spec.when_requirement_id,),
                priority=_priority(protocol, requirement, by_id),
            )
        )
    recommendations.sort(key=lambda item: (-item.priority, item.id))
    return tuple(recommendations)

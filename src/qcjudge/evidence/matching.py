"""Map evidence onto requirements, honouring gates, dependencies, and alternatives.

All of the reasoning that decides *whether* a requirement is met lives here, so the audit
engine can stay pure orchestration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from qcjudge.domain.assessment import AssessmentStatus, EvidenceAssessment
from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import (
    EvidenceInventory,
    EvidenceRequirement,
    EvidenceType,
    GroupSatisfaction,
)
from qcjudge.domain.protocol import ScientificProtocol, order_requirements
from qcjudge.domain.validation import ValidationResult, ValidationStatus

_GATING_FAILURES = frozenset({ValidationStatus.FAIL, ValidationStatus.UNKNOWN})
_PREMISE_UNAVAILABLE = frozenset(
    {AssessmentStatus.NOT_ASSESSABLE, AssessmentStatus.CONTRADICTED}
)


def admissible_evidence_ids(
    inventory: EvidenceInventory, requirement: EvidenceRequirement
) -> tuple[str, ...]:
    """Evidence of an accepted type that is also strong and direct enough.

    User-asserted evidence is already capped at WEAK/INDIRECT when it is constructed, so a
    requirement demanding more cannot be satisfied by an assertion.
    """
    admitted: list[str] = []
    for item in inventory.evidence:
        if item.evidence_type not in requirement.accepted_evidence_types:
            continue
        if item.strength.rank < requirement.minimum_strength.rank:
            continue
        if item.directness.rank < requirement.minimum_directness.rank:
            continue
        admitted.append(item.id)
    return tuple(admitted)


def candidate_evidence_ids(
    inventory: EvidenceInventory, requirement: EvidenceRequirement
) -> tuple[str, ...]:
    """Evidence of an accepted type, regardless of strength or directness."""
    return tuple(
        item.id
        for item in inventory.evidence
        if item.evidence_type in requirement.accepted_evidence_types
    )


def provided_evidence_types(
    inventory: EvidenceInventory, requirement: EvidenceRequirement
) -> tuple[EvidenceType, ...]:
    """Accepted types for which *some* evidence exists, at any strength."""
    provided = {
        item.evidence_type
        for item in inventory.evidence
        if item.evidence_type in requirement.accepted_evidence_types
    }
    return tuple(sorted(provided, key=lambda kind: kind.value))


def satisfied_groups(
    protocol: ScientificProtocol, admissible: Mapping[str, tuple[str, ...]]
) -> dict[str, str]:
    """Group id to the member requirement that satisfied it."""
    satisfied: dict[str, str] = {}
    for group in protocol.groups:
        if group.satisfaction is GroupSatisfaction.ANY_ONE:
            for member in group.member_ids:
                if admissible.get(member):
                    satisfied[group.id] = member
                    break
        elif all(admissible.get(member) for member in group.member_ids):
            satisfied[group.id] = group.member_ids[0]
    return satisfied


@dataclass(frozen=True, slots=True)
class _RuleEffects:
    """What the declared rules say about a requirement.

    Four outcomes, kept apart because they mean four different things: the inputs are
    unusable, the question is unanswerable, the evidence rules the requirement out, or an
    expert must decide.
    """

    blocking: ValidationResult | None = None
    inconclusive: ValidationResult | None = None
    contradicting: ValidationResult | None = None
    expert: ValidationResult | None = None


def _rule_effects(
    requirement: EvidenceRequirement, rule_results: Mapping[str, ValidationResult]
) -> _RuleEffects:
    blocking: ValidationResult | None = None
    inconclusive: ValidationResult | None = None
    contradicting: ValidationResult | None = None
    expert: ValidationResult | None = None

    for rule_id in requirement.gating_rules:
        result = rule_results.get(rule_id)
        if result is None:
            continue
        if result.status in _GATING_FAILURES and blocking is None:
            blocking = result
        elif result.status is ValidationStatus.REQUIRES_EXPERT_REVIEW and expert is None:
            expert = result

    for rule_id in requirement.contradicting_rules:
        result = rule_results.get(rule_id)
        if result is None:
            continue
        if result.status is ValidationStatus.FAIL and contradicting is None:
            contradicting = result
        elif result.status is ValidationStatus.UNKNOWN and inconclusive is None:
            inconclusive = result
        elif result.status is ValidationStatus.REQUIRES_EXPERT_REVIEW and expert is None:
            expert = result

    return _RuleEffects(
        blocking=blocking,
        inconclusive=inconclusive,
        contradicting=contradicting,
        expert=expert,
    )


def _required_fact_absence(
    inventory: EvidenceInventory, requirement: EvidenceRequirement
) -> tuple[AssessmentStatus, str] | None:
    """Classify a missing required fact as a coverage gap or an access failure."""
    for key in requirement.required_facts:
        if inventory.facts_by_key(key):
            continue
        reason = inventory.unavailable_reason(key)
        if reason is None:
            return (
                AssessmentStatus.NOT_ASSESSABLE,
                f"No source recorded why {key.value} is absent, so the absence is "
                "unexplained and this requirement cannot be judged.",
            )
        if reason.is_access_failure:
            return (
                AssessmentStatus.NOT_ASSESSABLE,
                f"{key.value} could not be read ({reason.value}), so this requirement "
                "cannot be judged.",
            )
        return (
            AssessmentStatus.INSUFFICIENT,
            f"The calculation that would supply {key.value} was not provided.",
        )
    return None


def _with_conditions(requirement: EvidenceRequirement, rationale: str) -> str:
    """Restate the declared insufficiency conditions beside a coverage-gap rationale.

    ``insufficiency_conditions`` tells a reader what this requirement would have accepted, and
    nothing read it: the field was declared on six requirements and appeared in no report. Which
    condition a given gap matches is not machine-decidable -- the conditions are prose -- so they
    are all restated rather than one being guessed at. The reader gets the requirement's own
    account of what was missing alongside the engine's.
    """
    if not requirement.insufficiency_conditions:
        return rationale
    listed = " ".join(
        f"({index}) {text}"
        for index, text in enumerate(requirement.insufficiency_conditions, start=1)
    )
    return f"{rationale} This requirement declares as insufficient: {listed}"


def _missing_types(
    requirement: EvidenceRequirement, provided: tuple[EvidenceType, ...]
) -> tuple[EvidenceType, ...]:
    """Accepted types nothing was supplied for.

    A type that was supplied below the required strength is not "missing" -- it is present
    and insufficient, and saying otherwise would misdescribe the gap.
    """
    return tuple(
        kind for kind in requirement.accepted_evidence_types if kind not in provided
    )


def _evidence_support(
    requirement: EvidenceRequirement,
    *,
    own: tuple[str, ...],
    candidates: tuple[str, ...],
    provided: tuple[EvidenceType, ...],
    alternatives: Mapping[str, tuple[str, ...]],
    satisfied: Mapping[str, str],
) -> EvidenceAssessment:
    """Decide coverage from evidence alone, before gates and dependencies are applied."""
    if requirement.group_id is not None:
        satisfier = satisfied.get(requirement.group_id)
        if satisfier is not None and satisfier != requirement.id and not own:
            return EvidenceAssessment(
                requirement.id,
                AssessmentStatus.SUPPORTED,
                f"Satisfied by the accepted alternative {satisfier!r}; see its evidence.",
                evidence_ids=alternatives.get(satisfier, ()),
                met_via_alternative=satisfier,
            )
    if own:
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.SUPPORTED,
            "Met by evidence of the accepted type: " + ", ".join(own) + ".",
            evidence_ids=own,
        )
    if candidates:
        supplied = ", ".join(kind.value for kind in provided)
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.PARTIALLY_SUPPORTED,
            f"Evidence of an accepted type was supplied ({supplied}), but below the required "
            "strength or directness.",
            evidence_ids=candidates,
            missing_evidence_types=_missing_types(requirement, provided),
        )
    return EvidenceAssessment(
        requirement.id,
        AssessmentStatus.INSUFFICIENT,
        _with_conditions(requirement, "No evidence of an accepted type was supplied."),
        missing_evidence_types=_missing_types(requirement, provided),
    )


def _expert_boundary(
    ctx: AuditContext, requirement: EvidenceRequirement
) -> tuple[str, str] | None:
    """The expert boundary this requirement has reached, as (message, trigger), if any.

    Two surfaces, and both are needed. A researcher can report that they observed the
    condition a protocol describes -- "the donor/acceptor partition is ambiguous" is not
    something a parser can see. A protocol can also name a condition by key, so that a rule
    tests it instead of a guess being made about the numbers.
    """
    declared = requirement.expert_review_when
    if declared is None:
        return None
    flag = ctx.expert_flag(requirement.id)
    if flag is not None:
        return (f"{declared} Reported condition: {flag.reported_condition}", "reported")
    if requirement.expert_review_when_key is not None:
        reported = ctx.condition(requirement.expert_review_when_key)
        if reported is not None:
            return (f"{declared} Reported condition: {reported}", "condition")
    return None


def assess_requirement(
    ctx: AuditContext,
    requirement: EvidenceRequirement,
    *,
    rule_results: Mapping[str, ValidationResult],
    own: tuple[str, ...],
    candidates: tuple[str, ...],
    provided: tuple[EvidenceType, ...],
    alternatives: Mapping[str, tuple[str, ...]],
    satisfied: Mapping[str, str],
    completed: Mapping[str, EvidenceAssessment],
) -> EvidenceAssessment:
    if requirement.require_target_association and ctx.association_issue is not None:
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.NOT_ASSESSABLE,
            ctx.association_issue,
            missing_evidence_types=requirement.accepted_evidence_types,
        )
    effects = _rule_effects(requirement, rule_results)
    if effects.blocking is not None:
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.NOT_ASSESSABLE,
            f"The underlying calculation cannot be relied on: {effects.blocking.message}",
            missing_evidence_types=requirement.accepted_evidence_types,
            blocked_by=(effects.blocking.rule_id,),
        )

    # Absence is checked before contradiction, so "no frequency calculation was provided"
    # stays a coverage gap rather than becoming an unanswerable question.
    absence = _required_fact_absence(ctx.inventory, requirement)
    if absence is not None:
        status, rationale = absence
        return EvidenceAssessment(
            requirement.id,
            status,
            _with_conditions(requirement, rationale)
            if status is AssessmentStatus.INSUFFICIENT
            else rationale,
            missing_evidence_types=requirement.accepted_evidence_types,
        )

    if effects.inconclusive is not None:
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.NOT_ASSESSABLE,
            f"Cannot be judged: {effects.inconclusive.message}",
            missing_evidence_types=requirement.accepted_evidence_types,
            blocked_by=(effects.inconclusive.rule_id,),
        )
    if effects.contradicting is not None:
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.CONTRADICTED,
            f"Available evidence rules this out: {effects.contradicting.message}",
            blocked_by=(effects.contradicting.rule_id,),
        )

    unmet: list[str] = []
    for dependency_id in requirement.dependencies:
        premise = completed.get(dependency_id)
        if premise is None:
            unmet.append(dependency_id)
            continue
        if premise.status in _PREMISE_UNAVAILABLE:
            return EvidenceAssessment(
                requirement.id,
                AssessmentStatus.NOT_ASSESSABLE,
                f"The premise {dependency_id!r} is not established "
                f"({premise.status.value}), so this requirement cannot be judged.",
                missing_evidence_types=requirement.accepted_evidence_types,
                blocked_by=(dependency_id,),
            )
        if premise.status is not AssessmentStatus.SUPPORTED:
            unmet.append(dependency_id)
    if unmet:
        joined = ", ".join(sorted(unmet))
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.INSUFFICIENT,
            _with_conditions(
                requirement,
                f"Not reached: the prerequisite evidence {joined} is missing.",
            ),
            missing_evidence_types=requirement.accepted_evidence_types,
            blocked_by=tuple(sorted(unmet)),
        )

    # A boundary the researcher reported outranks what the facts alone would say: they have
    # seen something the parser cannot, and the protocol says that makes it a human question.
    boundary = _expert_boundary(ctx, requirement)
    if boundary is not None:
        message, _trigger = boundary
        return EvidenceAssessment(
            requirement.id,
            AssessmentStatus.REQUIRES_EXPERT_REVIEW,
            message,
            evidence_ids=own,
            missing_evidence_types=_missing_types(requirement, provided),
            expert_review_required=True,
        )

    assessment = _evidence_support(
        requirement,
        own=own,
        candidates=candidates,
        provided=provided,
        alternatives=alternatives,
        satisfied=satisfied,
    )
    if effects.expert is None:
        return assessment
    capped = (
        AssessmentStatus.PARTIALLY_SUPPORTED
        if assessment.status is AssessmentStatus.SUPPORTED
        else assessment.status
    )
    return EvidenceAssessment(
        requirement.id,
        capped,
        f"{assessment.rationale} {effects.expert.message}",
        evidence_ids=assessment.evidence_ids,
        missing_evidence_types=assessment.missing_evidence_types,
        expert_review_required=True,
        met_via_alternative=assessment.met_via_alternative,
    )


def assess_all(
    ctx: AuditContext, rule_results: Mapping[str, ValidationResult]
) -> tuple[EvidenceAssessment, ...]:
    """Assess every requirement, in dependency order, against the inventory."""
    ordered = order_requirements(ctx.protocol.requirements)
    admissible = {
        requirement.id: admissible_evidence_ids(ctx.inventory, requirement)
        for requirement in ordered
    }
    candidates = {
        requirement.id: candidate_evidence_ids(ctx.inventory, requirement)
        for requirement in ordered
    }
    provided = {
        requirement.id: provided_evidence_types(ctx.inventory, requirement)
        for requirement in ordered
    }
    satisfied = satisfied_groups(ctx.protocol, admissible)
    completed: dict[str, EvidenceAssessment] = {}
    for requirement in ordered:
        completed[requirement.id] = assess_requirement(
            ctx,
            requirement,
            rule_results=rule_results,
            own=admissible[requirement.id],
            candidates=candidates[requirement.id],
            provided=provided[requirement.id],
            alternatives=admissible,
            satisfied=satisfied,
            completed=completed,
        )
    return tuple(completed[requirement.id] for requirement in ordered)

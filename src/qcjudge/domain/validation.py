"""Deterministic validation outcomes and explicit expert-review boundaries.

Validation is deliberately split by axis, because the questions are different and merging
them would let one leak into the other:

``EXECUTION`` asks only whether a calculation finished and produced usable output. A
calculation that converges to a minimum has *succeeded*; reporting it as a failed execution
would be false.

``STRUCTURE`` asks what the computed object actually is. A complete Hessian with zero
imaginary modes is a valid result that simply is not a first-order saddle point.

``METHODOLOGY`` asks whether the inputs are mutually consistent, and stops at a warning or
an expert boundary. No rule here concludes that a method is scientifically adequate: that
depends on the system and the target state.
"""

from dataclasses import dataclass
from enum import StrEnum


class ValidationScope(StrEnum):
    EXECUTION = "execution"
    STRUCTURE = "structure"
    METHODOLOGY = "methodology"


class ValidationStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"
    REQUIRES_EXPERT_REVIEW = "requires_expert_review"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    rule_id: str
    scope: ValidationScope
    status: ValidationStatus
    message: str
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """What a rule returns.

    Deliberately carries no rule id or scope: those are supplied by the protocol
    declaration, so a rule implementation never needs to know which protocol invoked it.
    """

    status: ValidationStatus
    message: str
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationRuleSpec:
    """Protocol declaration for a rule implemented in deterministic code.

    ``implementation_key`` is resolved through the validator registry. A protocol that
    names a rule nobody implements is a load-time failure, never a silently skipped check.
    """

    id: str
    scope: ValidationScope
    description: str
    implementation_key: str
    expert_review_boundary: str | None = None

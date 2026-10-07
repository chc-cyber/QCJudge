"""The read-only context a validation rule or a matcher is given.

Deliberately narrow: a rule receives the question, the protocol, and the inventory, so it
can cite facts, but it is handed no way to mutate any of them.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from qcjudge.domain.evidence import EvidenceInventory, FactKey
from qcjudge.domain.protocol import ScientificProtocol
from qcjudge.domain.question import ResearchQuestion


@dataclass(frozen=True, slots=True)
class ExpertReviewFlag:
    """A condition a researcher reported that only they can observe.

    Not evidence: it cites no fact and supports no requirement. It records that a declared
    expert boundary has been reached, so the report can return ``REQUIRES_EXPERT_REVIEW``
    instead of quietly deciding a question the protocol says a human must decide.
    """

    requirement_id: str
    reported_condition: str
    reported_by: str | None = None


@dataclass(frozen=True, slots=True)
class AuditContext:
    question: ResearchQuestion
    protocol: ScientificProtocol
    inventory: EvidenceInventory
    # Conditions the researcher reported, by key. A protocol may name one of these with
    # ``expert_review_when_key`` to have a rule test it, which is what makes an expert boundary
    # fire on the situation it describes rather than on a guess about the numbers.
    conditions: Mapping[str, str] = field(default_factory=dict)
    expert_reviews: tuple[ExpertReviewFlag, ...] = ()
    association_issue: str | None = None

    def fact_values(self, key: FactKey) -> tuple[object, ...]:
        """Values recorded for a fact key, in inventory order."""
        return tuple(fact.value for fact in self.inventory.facts_by_key(key))

    def expert_flag(self, requirement_id: str) -> ExpertReviewFlag | None:
        """The flag a researcher raised for one requirement, if any."""
        for flag in self.expert_reviews:
            if flag.requirement_id == requirement_id:
                return flag
        return None

    def condition(self, key: str) -> str | None:
        return self.conditions.get(key)

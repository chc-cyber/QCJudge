"""Research questions, hypotheses, claims, and the assumptions an audit rests on.

The chain is three levels deep on purpose: a broad hypothesis may rest on several checkable
claims, so the report can say "claim A supported, claim B unevidenced, therefore the
hypothesis is not established" instead of collapsing everything into one verdict.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from qcjudge.domain.common import EpistemicKind
from qcjudge.errors import UnresolvedBindingError


class QuestionFamily(StrEnum):
    CHARGE_TRANSFER_EXCITATION = "ct_excitation"
    TADF_POTENTIAL = "tadf_potential"
    TRANSITION_STATE_VALIDATION = "transition_state"


_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def bind(template: str, bindings: Mapping[str, str]) -> str:
    """Substitute question context into a protocol template.

    Raises rather than guessing: an under-specified question must be refused at the
    boundary, not silently audited against a claim about the wrong state.
    """
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in bindings:
            return bindings[key]
        missing.append(key)
        return match.group(0)

    bound = _PLACEHOLDER.sub(_replace, template)
    if missing:
        raise UnresolvedBindingError(tuple(sorted(set(missing))))
    return bound


@dataclass(frozen=True, slots=True)
class MethodAssumption:
    """A premise the audit's validity rests on. Never a computed fact."""

    id: str
    statement: str
    epistemic_kind: EpistemicKind = EpistemicKind.METHOD_ASSUMPTION

    def __post_init__(self) -> None:
        if self.epistemic_kind is not EpistemicKind.METHOD_ASSUMPTION:
            raise ValueError("MethodAssumption must carry METHOD_ASSUMPTION")


@dataclass(frozen=True, slots=True)
class Interpretation:
    """Background interpretation a protocol carries. Never evidence."""

    id: str
    statement: str
    epistemic_kind: EpistemicKind = EpistemicKind.INTERPRETATION

    def __post_init__(self) -> None:
        if self.epistemic_kind is not EpistemicKind.INTERPRETATION:
            raise ValueError("Interpretation must carry INTERPRETATION")


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A proposition the researcher wants to support. Not itself checkable."""

    id: str
    statement: str


@dataclass(frozen=True, slots=True)
class Claim:
    """A narrower, checkable statement derived from a hypothesis."""

    id: str
    hypothesis_id: str
    statement: str
    epistemic_kind: EpistemicKind = EpistemicKind.CLAIM

    def __post_init__(self) -> None:
        if self.epistemic_kind is not EpistemicKind.CLAIM:
            raise ValueError("Claim must carry CLAIM")
        if not self.hypothesis_id:
            raise ValueError("A claim must belong to a hypothesis")


@dataclass(frozen=True, slots=True)
class ResearchQuestion:
    """What the researcher wants to answer, plus the context that binds a protocol."""

    family: QuestionFamily
    text: str
    hypotheses: tuple[Hypothesis, ...]
    context: tuple[tuple[str, str], ...] = ()
    assumptions: tuple[MethodAssumption, ...] = ()

    def __post_init__(self) -> None:
        if not self.hypotheses:
            raise ValueError("A research question must state at least one hypothesis")
        hypothesis_ids = [hypothesis.id for hypothesis in self.hypotheses]
        if len(set(hypothesis_ids)) != len(hypothesis_ids):
            raise ValueError("Hypothesis IDs must be unique within a question")
        keys = [key for key, _ in self.context]
        if len(set(keys)) != len(keys):
            raise ValueError("Context keys must be unique")

    @property
    def bindings(self) -> dict[str, str]:
        return dict(self.context)

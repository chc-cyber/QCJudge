"""Reject explicitly impossible excited-state indices without assigning state identity.

This rule is a bounds check, not an interpretation of which state is scientifically
relevant. Missing calculations remain the evidence requirements' responsibility, so a
PASS here only means that no explicit index impossibility was established.
"""

from __future__ import annotations

import re

from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import FactKey
from qcjudge.domain.validation import RuleOutcome, ValidationStatus
from qcjudge.validators.registry import register

_INDEXED_STATE = re.compile(r"(?P<manifold>[ST])(?P<index>[+-]?\d+)", re.IGNORECASE)


@register("ct_target_state_exists")
def ct_target_state_exists(ctx: AuditContext) -> RuleOutcome:
    """Check explicit S/T indices against provided bounds, never guess the manifold."""
    requested = ctx.question.bindings.get("state", "").strip()
    match = _INDEXED_STATE.fullmatch(requested)
    if match is None:
        return RuleOutcome(
            ValidationStatus.PASS,
            "No explicit S/T numeric target index could be determined; this check cannot "
            "infer state identity and found no explicit index impossibility.",
        )

    index = int(match.group("index"))
    manifold = match.group("manifold").upper()
    if index <= 0:
        return RuleOutcome(
            ValidationStatus.FAIL,
            f"The requested excited state {requested!r} has index {index}; excited-state "
            "indices must be positive.",
        )

    key = (
        FactKey.SINGLET_STATE_ENERGY_EV
        if manifold == "S"
        else FactKey.TRIPLET_STATE_ENERGY_EV
    )
    recorded_lists = tuple(
        fact for fact in ctx.inventory.facts_by_key(key) if isinstance(fact.value, tuple)
    )
    lists = tuple(fact for fact in recorded_lists if fact.value)
    if lists:
        # A shorter list cannot rule out an index explicitly present in a longer list.
        # The inventory has already been selected for the question's calculation/state.
        maximum = max(len(fact.value) for fact in lists if isinstance(fact.value, tuple))
        fact_ids = tuple(fact.id for fact in lists)
        if index > maximum:
            return RuleOutcome(
                ValidationStatus.FAIL,
                f"The requested state {requested!r} exceeds the provided {manifold} "
                f"manifold: at most {maximum} state(s) were recorded.",
                fact_ids,
            )
        return RuleOutcome(
            ValidationStatus.PASS,
            f"The index of {requested!r} is within the provided {manifold} manifold. "
            "This bounds check does not establish scientific target-state identity.",
            fact_ids,
        )

    recorded_counts = tuple(
        fact
        for fact in ctx.inventory.facts_by_key(FactKey.EXCITED_STATE_COUNT)
        if isinstance(fact.value, int) and not isinstance(fact.value, bool) and fact.value >= 0
    )
    counts = tuple(
        fact for fact in recorded_counts if isinstance(fact.value, int) and fact.value > 0
    )
    if counts:
        if recorded_lists:
            return RuleOutcome(
                ValidationStatus.FAIL,
                f"The provided {manifold} manifold is explicitly empty. A positive total "
                f"state count cannot establish the requested target {requested!r} in that "
                "manifold.",
                tuple(fact.id for fact in (*recorded_lists, *counts)),
            )
        total = max(fact.value for fact in counts if isinstance(fact.value, int))
        fact_ids = tuple(fact.id for fact in counts)
        if index > total:
            return RuleOutcome(
                ValidationStatus.FAIL,
                f"The requested state {requested!r} has index {index}, exceeding every "
                f"provided total state count (maximum {total}).",
                fact_ids,
            )
        return RuleOutcome(
            ValidationStatus.PASS,
            f"The index of {requested!r} does not exceed the provided total state count "
            f"(maximum {total}). A total count does not establish the {manifold} manifold's "
            "allocation or scientific target-state identity.",
            fact_ids,
        )

    if recorded_lists or recorded_counts:
        return RuleOutcome(
            ValidationStatus.PASS,
            "Only zero state counts or empty target-manifold lists were provided. These "
            "remain recorded facts but provide no state assignment; the evidence "
            "requirements classify the coverage gap.",
            tuple(fact.id for fact in (*recorded_lists, *recorded_counts)),
        )

    return RuleOutcome(
        ValidationStatus.PASS,
        "No target-manifold list or valid total state count was provided. Missing facts "
        "are classified by the evidence requirements; this check does not establish "
        "target-state identification.",
    )

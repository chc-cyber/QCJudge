"""Fact collection helpers shared by validation rules.

Rules may only read; they never write to the inventory, and they must say *why* a value is
absent rather than treating absence as failure.
"""

from __future__ import annotations

from qcjudge.domain.common import UnavailableReason
from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import FactKey

_ACCESS_EXPLANATIONS: dict[UnavailableReason, str] = {
    UnavailableReason.FILE_TRUNCATED: "the output file is incomplete",
    UnavailableReason.UNSUPPORTED_CONSTRUCT: "this output construct is not extracted yet",
    UnavailableReason.AMBIGUOUS_MATCH: (
        "several candidate values were found and none is authoritative"
    ),
}


def collect_bools(ctx: AuditContext, key: FactKey) -> tuple[tuple[bool, ...], tuple[str, ...]]:
    values: list[bool] = []
    fact_ids: list[str] = []
    for fact in ctx.inventory.facts_by_key(key):
        value = fact.value
        if isinstance(value, bool):
            values.append(value)
            fact_ids.append(fact.id)
    return tuple(values), tuple(fact_ids)


def collect_ints(ctx: AuditContext, key: FactKey) -> tuple[tuple[int, ...], tuple[str, ...]]:
    values: list[int] = []
    fact_ids: list[str] = []
    for fact in ctx.inventory.facts_by_key(key):
        value = fact.value
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        values.append(value)
        fact_ids.append(fact.id)
    return tuple(values), tuple(fact_ids)


def collect_strs(ctx: AuditContext, key: FactKey) -> tuple[tuple[str, ...], tuple[str, ...]]:
    values: list[str] = []
    fact_ids: list[str] = []
    for fact in ctx.inventory.facts_by_key(key):
        value = fact.value
        if isinstance(value, str):
            values.append(value)
            fact_ids.append(fact.id)
    return tuple(values), tuple(fact_ids)


def absence_note(ctx: AuditContext, key: FactKey, subject: str = "the value") -> str:
    """Explain an absence, so an unreadable input is never reported as a failed check."""
    reason = ctx.inventory.unavailable_reason(key)
    if reason is None:
        return (
            f" No source recorded why {key.value} is absent, so the absence is unexplained."
        )
    if reason is UnavailableReason.NOT_PROVIDED:
        return (
            f" The file is complete, and no calculation supplying {key.value} was provided."
        )
    return f" {key.value} could not be read: {_ACCESS_EXPLANATIONS[reason]}."

"""Methodology checks: warn, or defer to an expert. Never conclude adequacy.

Whether a method is appropriate depends on the system and the target state, so no rule here
returns ``PASS`` on a question of scientific suitability. ``PASS`` is reserved for internal
consistency, which is a statement about the inputs, not about the chemistry.
"""

from __future__ import annotations

from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import FactKey
from qcjudge.domain.validation import RuleOutcome, ValidationStatus
from qcjudge.validators.collect import absence_note, collect_strs
from qcjudge.validators.registry import register


@register("state_method_consistency")
def state_method_consistency(ctx: AuditContext) -> RuleOutcome:
    """Check that compared quantities came from a consistent method and basis set.

    A singlet-triplet gap built from two different functionals is not a gap. When methods
    differ the rule defers rather than declaring the comparison invalid, because whether a
    difference matters is a scientific judgement.
    """
    methods, method_ids = collect_strs(ctx, FactKey.METHOD_NAME)
    bases, basis_ids = collect_strs(ctx, FactKey.BASIS_NAME)
    fact_ids = (*method_ids, *basis_ids)
    if not methods and not bases:
        return RuleOutcome(
            ValidationStatus.UNKNOWN,
            "The method and basis set could not be determined, so consistency between "
            "compared quantities is unknown."
            + absence_note(ctx, FactKey.METHOD_NAME, "the method"),
        )
    distinct_methods = sorted(set(methods))
    distinct_bases = sorted(set(bases))
    if len(distinct_methods) > 1 or len(distinct_bases) > 1:
        return RuleOutcome(
            ValidationStatus.REQUIRES_EXPERT_REVIEW,
            "Compared quantities were produced with different methods "
            f"({distinct_methods}) or basis sets ({distinct_bases}); whether the values are "
            "comparable requires expert judgement.",
            fact_ids,
        )
    return RuleOutcome(
        ValidationStatus.PASS,
        "All recorded quantities share one method and basis set.",
        fact_ids,
    )


@register("ct_method_sensitivity")
def ct_method_sensitivity(ctx: AuditContext) -> RuleOutcome:
    """A standing warning, not a verdict.

    Conventional functionals underestimate intermolecular charge-transfer energies by
    roughly 2 eV on average, and the size of the error is system dependent. The rule states
    the concern and stops; it never declares a functional unsuitable.
    """
    methods, fact_ids = collect_strs(ctx, FactKey.METHOD_NAME)
    seen = f" Recorded method: {methods[0]}." if methods else ""
    return RuleOutcome(
        ValidationStatus.WARNING,
        "Charge-transfer excitation energies are strongly method dependent; long-range "
        "behaviour of the exchange-correlation functional should be considered for this "
        f"system.{seen}",
        fact_ids,
    )

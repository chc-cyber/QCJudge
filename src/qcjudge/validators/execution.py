"""Execution validity: did the calculation finish, and is what it produced usable?

Every rule here obeys one discipline: when the input is absent the answer is ``UNKNOWN``,
never ``FAIL``. Absence of evidence about convergence is not evidence of failure to
converge.
"""

from __future__ import annotations

from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import FactKey
from qcjudge.domain.validation import RuleOutcome, ValidationStatus
from qcjudge.validators.collect import absence_note, collect_bools, collect_ints
from qcjudge.validators.registry import register


@register("scf_converged")
def scf_converged(ctx: AuditContext) -> RuleOutcome:
    values, fact_ids = collect_bools(ctx, FactKey.SCF_CONVERGED)
    if not values:
        return RuleOutcome(
            ValidationStatus.UNKNOWN,
            "SCF convergence could not be determined." + absence_note(ctx, FactKey.SCF_CONVERGED),
        )
    if all(values):
        return RuleOutcome(ValidationStatus.PASS, "SCF converged.", fact_ids)
    return RuleOutcome(ValidationStatus.FAIL, "SCF did not converge.", fact_ids)


@register("opt_converged")
def opt_converged(ctx: AuditContext) -> RuleOutcome:
    values, fact_ids = collect_bools(ctx, FactKey.GEOMETRY_CONVERGED)
    if not values:
        return RuleOutcome(
            ValidationStatus.UNKNOWN,
            "Geometry convergence could not be determined."
            + absence_note(ctx, FactKey.GEOMETRY_CONVERGED),
        )
    if all(values):
        return RuleOutcome(ValidationStatus.PASS, "Geometry optimization converged.", fact_ids)
    return RuleOutcome(
        ValidationStatus.FAIL, "Geometry optimization did not converge.", fact_ids
    )


@register("tddft_completed")
def tddft_completed(ctx: AuditContext) -> RuleOutcome:
    values, fact_ids = collect_ints(ctx, FactKey.EXCITED_STATE_COUNT)
    if not values:
        return RuleOutcome(
            ValidationStatus.UNKNOWN,
            "The number of excited states could not be determined."
            + absence_note(ctx, FactKey.EXCITED_STATE_COUNT),
        )
    if all(value >= 1 for value in values):
        return RuleOutcome(
            ValidationStatus.PASS,
            f"Excited-state calculation reported {max(values)} state(s).",
            fact_ids,
        )
    return RuleOutcome(
        ValidationStatus.FAIL, "No excited states were reported.", fact_ids
    )


@register("first_order_saddle_point")
def first_order_saddle_point(ctx: AuditContext) -> RuleOutcome:
    """Establish the local Hessian order -- and nothing stronger than that.

    Two independent guards protect the count. The parser refuses to report a count from a
    file that did not end normally, and, where the parser can also supply the expected number
    of modes (3N-6, or 3N-5 for a linear molecule), a mismatch is treated as an incomplete
    list. When the expected count is unavailable no cross-check is possible, so the count
    rests on the parser's completeness judgement rather than on arithmetic.
    """
    imaginary, imaginary_ids = collect_ints(ctx, FactKey.FREQUENCY_IMAGINARY_COUNT)
    observed, observed_ids = collect_ints(ctx, FactKey.FREQUENCY_OBSERVED_MODE_COUNT)
    expected, expected_ids = collect_ints(ctx, FactKey.FREQUENCY_EXPECTED_MODE_COUNT)
    fact_ids = (*imaginary_ids, *observed_ids, *expected_ids)

    if not imaginary:
        return RuleOutcome(
            ValidationStatus.UNKNOWN,
            "The imaginary-frequency count could not be determined."
            + absence_note(ctx, FactKey.FREQUENCY_IMAGINARY_COUNT),
        )
    if observed and expected:
        if len(observed) != len(expected):
            return RuleOutcome(
                ValidationStatus.UNKNOWN,
                "Mode-list completeness could not be verified for every calculation.",
            )
        incomplete = [
            (present, wanted)
            for present, wanted in zip(observed, expected, strict=True)
            if present != wanted
        ]
        if incomplete:
            present, wanted = incomplete[0]
            return RuleOutcome(
                ValidationStatus.UNKNOWN,
                f"The mode list appears incomplete ({present} of {wanted} modes present), "
                "so the imaginary-frequency count is not meaningful.",
                fact_ids,
            )
    distinct = sorted(set(imaginary))
    if len(distinct) != 1:
        return RuleOutcome(
            ValidationStatus.UNKNOWN,
            f"Conflicting imaginary-frequency counts were reported: {distinct}.",
            fact_ids,
        )
    count = distinct[0]
    if count == 1:
        return RuleOutcome(
            ValidationStatus.PASS,
            "This Hessian is first-order at the computed stationary point.",
            fact_ids,
        )
    return RuleOutcome(
        ValidationStatus.FAIL,
        f"The computed Hessian has {count} imaginary frequencies, not one.",
        fact_ids,
    )

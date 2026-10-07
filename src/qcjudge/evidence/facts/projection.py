"""Lift parser observations into provenance-bearing facts.

This layer is mechanical, and that is the point. It attaches provenance, names the
calculation, and performs the arithmetic that turns lists of observations into counts. It
makes no judgement about meaning or strength: a list of frequencies is an observation, how
many of them is a computed fact, and *how much either is worth as evidence* is declared by a
protocol in ``evidence/derivation.py``.

Absences flow through with the calculation name attached -- the parser deliberately does not
know how a file is identified downstream. Keys a parser does not support at all are reported
as ``UNSUPPORTED_CONSTRUCT``, so a limitation of the reader is never presented as a property
of the calculation.

Two rules keep the reader's own limitation from being charged to the researcher:

* A key produced only by arithmetic over other facts reports the **reason its sources are
  missing**, not ``UNSUPPORTED_CONSTRUCT``. A job that simply never ran a frequency
  calculation still has ``frequency.cm1`` marked ``NOT_PROVIDED``; saying the derived count
  "is not extracted yet" would turn a coverage gap into an access failure and flip the
  requirement from ``INSUFFICIENT`` to ``NOT_ASSESSABLE``. "We cannot compute it because you
  did not run it" is a coverage gap.
* A list-valued observation from a file that did not end normally is **withheld**. A prefix of
  a mode list is indistinguishable from a complete one, so counting imaginary modes from a
  truncated Hessian would invent a result -- and a partial list of all-positive modes would
  fabricate ``CONTRADICTED`` for a claim nothing actually refutes. Scalars stay: a costed
  value like ``scf.converged`` is evidence on its own.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from qcjudge.domain.calculation import ParseOutcome, ParseResult
from qcjudge.domain.common import EpistemicKind, UnavailableReason
from qcjudge.domain.evidence import (
    EvidenceOrigin,
    ExtractedFact,
    FactKey,
    ScalarValue,
    Subject,
    UnavailableFact,
)

type _Observed = Mapping[FactKey, ScalarValue | tuple[ScalarValue, ...]]
type _Arithmetic = Callable[[_Observed], ScalarValue | None]

# Observations that are meaningful only as a whole. A truncated file can leave any prefix of
# such a list on disk, and a prefix cannot be told apart from the complete value, so a count
# derived from one is meaningless.
_TRUNCATION_SENSITIVE: frozenset[FactKey] = frozenset(
    {
        FactKey.FREQUENCY_CM1,
        FactKey.SINGLET_STATE_ENERGY_EV,
        FactKey.TRIPLET_STATE_ENERGY_EV,
        FactKey.OSCILLATOR_STRENGTH,
        FactKey.SPIN_EXPECTATION,
    }
)

_TRUNCATED_MESSAGE = (
    "The file did not end normally, so this list may be a prefix of what was computed and "
    "cannot be counted."
)


def _mode_count(observed: _Observed) -> ScalarValue | None:
    values = observed.get(FactKey.FREQUENCY_CM1)
    return len(values) if isinstance(values, tuple) else None


def _imaginary_mode_count(observed: _Observed) -> ScalarValue | None:
    values = observed.get(FactKey.FREQUENCY_CM1)
    if not isinstance(values, tuple):
        return None
    return sum(1 for value in values if isinstance(value, float) and value < 0)


def _state_count(observed: _Observed) -> ScalarValue | None:
    """Count states across whichever manifolds were reported, and only those."""
    total = 0
    found = False
    for key in (FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV):
        values = observed.get(key)
        if isinstance(values, tuple):
            total += len(values)
            found = True
    return total if found else None


# Derived key, unit, arithmetic, and the observations the arithmetic reads. Declared as data
# so the arithmetic is inspectable and testable on its own.
_DERIVED_FACTS: tuple[tuple[FactKey, str | None, _Arithmetic, tuple[FactKey, ...]], ...] = (
    (
        FactKey.FREQUENCY_OBSERVED_MODE_COUNT,
        "modes",
        _mode_count,
        (FactKey.FREQUENCY_CM1,),
    ),
    (
        FactKey.FREQUENCY_IMAGINARY_COUNT,
        "modes",
        _imaginary_mode_count,
        (FactKey.FREQUENCY_CM1,),
    ),
    (
        FactKey.EXCITED_STATE_COUNT,
        "states",
        _state_count,
        (FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV),
    ),
)


def _unreadable_list_keys(result: ParseResult) -> frozenset[FactKey]:
    """List-valued observations this result produces but that must not be counted.

    Only a file that did not end normally is affected, and only for the observations that are
    meaningless as a prefix.
    """
    if result.diagnostics.outcome is not ParseOutcome.TRUNCATED:
        return frozenset()
    return frozenset(
        observation.key
        for observation in result.observations
        if observation.key in _TRUNCATION_SENSITIVE
    )


def _source_reasons(
    result: ParseResult, withheld: frozenset[FactKey]
) -> dict[FactKey, UnavailableReason]:
    """Why each of this result's own keys is missing, whether or not it was ever read.

    A key can be absent for two reasons, and both must be visible to the keys computed from
    it. The parser authors a reason for the values it looked for and did not find; the
    projection adds one for a list it read but had to withhold. Consulting only the parser
    would make a withheld list look like a value that was never provided, which is the very
    confusion this module exists to prevent.
    """
    reasons: dict[FactKey, UnavailableReason] = {}
    for observation in result.observations:
        if observation.key in withheld:
            reasons[observation.key] = UnavailableReason.FILE_TRUNCATED
    for absent in result.diagnostics.unavailable:
        reasons.setdefault(absent.key, absent.reason)
    return reasons


def _inherited_reason(
    sources: tuple[FactKey, ...], reasons: Mapping[FactKey, UnavailableReason]
) -> UnavailableReason:
    """Why a key produced only by arithmetic is absent, in the vocabulary of its sources.

    Access failures win, because "we could not read it" must never be presented as "you did
    not provide it"; when no source reports an access failure the honest answer is that the
    calculation which would have supplied the inputs was not provided.
    """
    inherited = tuple(
        reason for source in sources if (reason := reasons.get(source)) is not None
    )
    for reason in inherited:
        if reason is not UnavailableReason.NOT_PROVIDED:
            return reason
    return UnavailableReason.NOT_PROVIDED


def _inherited_message(
    result: ParseResult,
    sources: tuple[FactKey, ...],
    reason: UnavailableReason,
    reasons: Mapping[FactKey, UnavailableReason],
) -> str:
    """Explain a projected absence without contradicting the reason recorded for it.

    The parser's own message for the source fact already states the cause precisely, so it is
    reused whenever there is one; only a source with no authored message needs a constructed
    explanation.
    """
    authored = next(
        (
            absent.message
            for absent in result.diagnostics.unavailable
            if absent.key in sources and absent.message
        ),
        None,
    )
    if authored is not None:
        return f"{authored} As a result this value could not be computed."
    if reason is UnavailableReason.FILE_TRUNCATED:
        return f"{_TRUNCATED_MESSAGE} This value could not be computed from it."
    supplied = ", ".join(source.value for source in sources)
    blocking = next(
        (source.value for source in sources if reasons.get(source) is reason),
        None,
    )
    if blocking is not None:
        return (
            f"{blocking} was not reported, so this value could not be computed "
            f"({reason.value})."
        )
    return (
        f"{supplied} was not reported, so this value could not be computed "
        f"({reason.value})."
    )


def _origin_of(result: ParseResult) -> EvidenceOrigin:
    """Whether this result's values were read from a calculation or imported from an analysis.

    Decided by which reader produced the result rather than inferred from a producer name: the
    projection is the layer that knows the difference, and a name-based rule would silently
    misattribute anything whose producer string did not match the pattern.
    """
    return (
        EvidenceOrigin.ADAPTER
        if result.origin is EvidenceOrigin.ADAPTER
        else EvidenceOrigin.PARSED
    )


def facts_from_parse_results(
    results: Sequence[ParseResult],
    *,
    supported_keys: frozenset[FactKey],
) -> tuple[tuple[ExtractedFact, ...], tuple[UnavailableFact, ...]]:
    """Return the facts and recorded absences implied by a set of parse results."""
    facts: list[ExtractedFact] = []
    absences: list[UnavailableFact] = []
    arithmetic_keys = frozenset(key for key, _unit, _fn, _sources in _DERIVED_FACTS)

    for index, result in enumerate(results, start=1):
        calculation_id = result.calculation_id or f"calc-{index}"
        origin = _origin_of(result)
        observed: dict[FactKey, ScalarValue | tuple[ScalarValue, ...]] = {
            observation.key: observation.value for observation in result.observations
        }
        unreadable = _unreadable_list_keys(result)
        for key in unreadable:
            del observed[key]

        derived = _derived_values(observed)
        reasons = _source_reasons(result, unreadable)
        facts.extend(
            _observed_facts(result, calculation_id, withheld=unreadable, origin=origin)
        )
        facts.extend(_derived_facts(result, calculation_id, derived, origin=origin))

        # Absences are projected first and everything else is filtered against them, so a key
        # can never be reported both as a fact we hold and as a value we cannot get.
        covered: set[FactKey] = set(unreadable)
        for key in unreadable:
            observation = result.observation(key)
            absences.append(
                UnavailableFact(
                    key=key,
                    reason=UnavailableReason.FILE_TRUNCATED,
                    provenance=result.provenanced(
                        observation.location if observation is not None else None
                    ),
                    subject=Subject(calculation_id=calculation_id),
                    message=_TRUNCATED_MESSAGE,
                )
            )

        for key, _unit, _fn, sources in _DERIVED_FACTS:
            if key in derived or key in observed:
                # Either the projection computed it, or the reader supplied it directly. Both
                # mean we hold the value; only a key we have in neither sense is missing. A
                # reader is allowed to report a value the projection would otherwise have to
                # compute -- an imported analysis states a state count outright -- and marking
                # it absent would contradict the fact we are holding.
                continue
            covered.add(key)
            reason = _inherited_reason(sources, reasons)
            absences.append(
                UnavailableFact(
                    key=key,
                    reason=reason,
                    provenance=result.provenanced(None),
                    subject=Subject(calculation_id=calculation_id),
                    message=_inherited_message(result, sources, reason, reasons),
                )
            )

        for absent in result.diagnostics.unavailable:
            covered.add(absent.key)
            absences.append(
                UnavailableFact(
                    key=absent.key,
                    reason=absent.reason,
                    provenance=absent.provenance,
                    subject=Subject(calculation_id=calculation_id),
                    message=absent.message,
                )
            )

        if result.diagnostics.outcome is ParseOutcome.UNRECOGNISED:
            for key in sorted(supported_keys, key=lambda item: item.value):
                if key in covered:
                    continue
                covered.add(key)
                absences.append(
                    UnavailableFact(
                        key=key,
                        reason=UnavailableReason.UNSUPPORTED_CONSTRUCT,
                        provenance=result.provenanced(None),
                        subject=Subject(calculation_id=calculation_id),
                        message="The file was not recognised, so no value could be read.",
                    )
                )

        # A key we neither read, nor derive, nor are told about is a limitation of this
        # reader: it would have to arrive through an adapter.
        for key in sorted(FactKey, key=lambda item: item.value):
            if key in supported_keys or key in covered or key in arithmetic_keys:
                continue
            absences.append(
                UnavailableFact(
                    key=key,
                    reason=UnavailableReason.UNSUPPORTED_CONSTRUCT,
                    provenance=result.provenanced(None),
                    subject=Subject(calculation_id=calculation_id),
                    message=(
                        f"{result.producer} does not attempt to read {key.value}; it would "
                        "have to arrive through an adapter."
                    ),
                )
            )

    return tuple(facts), tuple(absences)


def _observed_facts(
    result: ParseResult,
    calculation_id: str,
    *,
    withheld: frozenset[FactKey] = frozenset(),
    origin: EvidenceOrigin = EvidenceOrigin.PARSED,
) -> list[ExtractedFact]:
    """Observations as facts. List values we cannot trust as complete are left out."""
    return [
        ExtractedFact(
            id=f"{calculation_id}:{observation.key.value}",
            key=observation.key,
            value=observation.value,
            unit=observation.unit,
            subject=Subject(calculation_id=calculation_id),
            provenance=result.provenanced(observation.location),
            epistemic_kind=EpistemicKind.OBSERVATION,
            origin=origin,
        )
        for observation in result.observations
        if observation.key not in withheld
    ]


def _derived_values(observed: _Observed) -> dict[FactKey, ScalarValue]:
    """The computed facts implied by a set of observations."""
    derived: dict[FactKey, ScalarValue] = {}
    for key, _unit, arithmetic, _sources in _DERIVED_FACTS:
        value = arithmetic(observed)
        if value is not None:
            derived[key] = value
    return derived


def _derived_facts(
    result: ParseResult,
    calculation_id: str,
    derived: Mapping[FactKey, ScalarValue],
    *,
    origin: EvidenceOrigin = EvidenceOrigin.PARSED,
) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for key, unit, _arithmetic, sources in _DERIVED_FACTS:
        if key not in derived:
            continue
        location = next(
            (
                observation.location
                for source in sources
                if (observation := result.observation(source)) is not None
            ),
            None,
        )
        facts.append(
            ExtractedFact(
                id=f"{calculation_id}:{key.value}",
                key=key,
                value=derived[key],
                unit=unit,
                subject=Subject(calculation_id=calculation_id),
                provenance=result.provenanced(location),
                epistemic_kind=EpistemicKind.COMPUTED_FACT,
                origin=origin,
            )
        )
    return facts

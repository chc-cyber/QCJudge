"""Read the documented JSON export of an external analysis.

One format, one reader, no heuristics. Every value in the file states which registered fact it
is and in what unit, so nothing has to be guessed from a column position or a heading -- which is
what makes this seam different from a parser, and why it can be this small.

Example::

    {
      "format": "qcjudge.analysis_import/1",
      "analysis": "hole_electron",
      "producer": "Multiwfn",
      "producer_version": "3.8",
      "source_file": "dvb_s1_hole_electron.txt",
      "calculations": [
        {
          "calculation_id": "ext-1",
          "values": {
            "hole_electron.d_index_angstrom": {"value": 2.41, "unit": "angstrom"},
            "hole_electron.sr_index": {"value": 0.31, "unit": "dimensionless"}
          }
        }
      ]
    }
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qcjudge.domain.calculation import (
    Observation,
    ParseDiagnostics,
    ParseOutcome,
    ParseResult,
)
from qcjudge.domain.evidence import EvidenceOrigin, FactKey, ScalarValue
from qcjudge.errors import (
    AdapterFormatError,
    UnknownExportedQuantityError,
    WrongUnitError,
)

FORMAT_ID = "qcjudge.analysis_import/1"

# Imported facts are attributed to a producer outside the calculation, and the namespace is what
# evidence derivation keys on to tell the two apart.
ADAPTER_PRODUCER_PREFIX = "qcjudge.adapter."

# The unit each imported quantity is recorded in. A file stating anything else is refused, because
# a value in the wrong unit is worse than a missing one: it looks like an answer.
#
# The set is deliberately small and matches the derivations that need an external number. A
# quantity nobody consumes would be a fact that changes nothing, and registering one would imply
# an analysis QCJudge understands when it does not.
#
# `scf.converged` is here because an analysis of a calculation asserts something about that
# calculation. Without it every gated requirement comes out `NOT_ASSESSABLE` -- correctly, since a
# descriptor says nothing about whether the wavefunction behind it converged. A tool that computed
# the descriptor knows that much, so it states it. Booleans are recorded as 1 and 0, which is how
# the calculation's own output represents them too.
_EXPECTED_UNITS: Mapping[FactKey, str] = {
    FactKey.SCF_CONVERGED: "dimensionless",
    FactKey.EXCITED_STATE_COUNT: "dimensionless",
    FactKey.HOLE_ELECTRON_D_INDEX: "angstrom",
    FactKey.HOLE_ELECTRON_SR_INDEX: "dimensionless",
    FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION: "dimensionless",
    FactKey.SPIN_ORBIT_COUPLING_CM1: "cm**-1",
    FactKey.IRC_CONNECTS_TWO_MINIMA: "dimensionless",
}

SUPPORTED_QUANTITIES: frozenset[FactKey] = frozenset(_EXPECTED_UNITS)

# Scales a legitimate export might use for the same quantity. Only exact equivalents are accepted;
# anything else has to be converted by whoever exports it, because a silent conversion is a
# scientific claim nobody declared.
_ALTERNATIVE_UNITS: Mapping[str, Mapping[str, float]] = {
    "angstrom": {"angstrom": 1.0, "a": 1.0, "bohr": 0.529177210903},
    "cm**-1": {"cm**-1": 1.0, "cm-1": 1.0, "wavenumber": 1.0},
    "dimensionless": {
        "dimensionless": 1.0,
        "none": 1.0,
        "states": 1.0,
        "count": 1.0,
        "": 1.0,
        # A flag states "none" in practice, but accepting "bool" costs nothing and is what an
        # export is most likely to write for one.
        "bool": 1.0,
        "boolean": 1.0,
    },
}


# Sorted once so an error message lists the same names in the same order every time.
_ACCEPTED_NAMES: tuple[str, ...] = tuple(
    sorted(key.value for key in SUPPORTED_QUANTITIES)
)


def _reject_quantity(quantity: str, where: str) -> UnknownExportedQuantityError:
    """The refusal for a quantity this seam cannot carry, naming what it can."""
    return UnknownExportedQuantityError(quantity, source=where, accepted=_ACCEPTED_NAMES)


def _scaled(quantity: FactKey, value: float, unit: str) -> float:
    """The value in the fact's own unit, or a refusal."""
    expected = _EXPECTED_UNITS[quantity]
    alternatives = _ALTERNATIVE_UNITS.get(expected, {expected: 1.0})
    if unit not in alternatives:
        raise WrongUnitError(quantity.value, unit, expected)
    return value * alternatives[unit]


def _number(quantity: FactKey, raw: object, where: str) -> ScalarValue:
    """The value as recorded, refusing anything that is not a number or a flag.

    A boolean is kept as a boolean rather than flattened to 1 or 0: the readers that consume a
    convergence flag expect a flag, and coercing it to a float silently turns a PASS into
    UNKNOWN. The fact model already allows booleans, so there is no reason to lose the type.
    """
    if isinstance(raw, bool):
        return raw
    if not isinstance(raw, (int, float)):
        raise AdapterFormatError(
            f"{where}: {quantity.value!r} must be a number, received {type(raw).__name__}"
        )
    return float(raw)


class JsonAnalysisAdapter:
    """Reads one external-analysis export into observations, like a parser does.

    It implements the same shape as ``CalculationParser`` on purpose: everything downstream --
    projection, provenance, absence recording -- then works unchanged, and the report cannot tell
    an adapter's facts from a parser's except by their producer, which is exactly the distinction
    that should be visible.
    """

    name = "qcjudge.adapter.json_analysis"
    version = "0.1.0"

    @property
    def supported_keys(self) -> frozenset[FactKey]:
        """Every quantity an export may carry.

        Use the keys an individual parse reports instead when recording absences: a file that
        carried three descriptors has not failed to carry the fourth, and saying so would put an
        imaginary gap in the report. See :meth:`parse_all`.
        """
        return SUPPORTED_QUANTITIES

    def parse(self, path: Path) -> ParseResult:
        """Read the first calculation in one export, with what that export carried.

        An export may describe several calculations, and each becomes its own result so their
        facts stay separate -- see :meth:`parse_all`. This method exists so the adapter matches
        the reader contract every parser implements.
        """
        results, _ = self.parse_all(path)
        return results[0]

    def parse_all(self, path: Path) -> tuple[tuple[ParseResult, ...], frozenset[FactKey]]:
        """Read every calculation in one export, plus the quantities it carried.

        Separate results matter: a fact belongs to the calculation it describes, and merging two
        calculations' values into one subject would let a descriptor from one answer a claim
        about the other.
        """
        try:
            document: Any = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise AdapterFormatError(f"{path} is not valid JSON: {error}") from error
        except OSError as error:
            raise AdapterFormatError(f"{path} could not be read: {error}") from error

        if not isinstance(document, dict):
            raise AdapterFormatError(f"{path} must contain a JSON object at the top level")
        return self._from_document(path, document)

    def _from_document(
        self, path: Path, document: dict[str, Any]
    ) -> tuple[tuple[ParseResult, ...], frozenset[FactKey]]:
        formatted = document.get("format")
        if formatted != FORMAT_ID:
            raise AdapterFormatError(
                f"{path} declares format {formatted!r}; this reader understands "
                f"{FORMAT_ID!r}. The version is checked rather than assumed so a future "
                "format cannot be read as if it were this one."
            )

        producer = document.get("producer")
        if not isinstance(producer, str) or not producer.strip():
            raise AdapterFormatError(
                f"{path} does not name the tool that produced the analysis. A number without a "
                "producer cannot be attributed, and attribution is the point of this seam."
            )
        producer_version = document.get("producer_version")
        if not isinstance(producer_version, str) or not producer_version.strip():
            raise AdapterFormatError(f"{path} does not state the producer's version")

        calculations = document.get("calculations")
        if not isinstance(calculations, list) or not calculations:
            raise AdapterFormatError(
                f"{path} holds no calculations; there is nothing to import"
            )

        # The source file is recorded in provenance, so it must be what the export says rather
        # than where the export happens to sit -- unless it says nothing, in which case the path
        # is the only truthful answer available.
        declared_source = document.get("source_file")
        source_file = (
            declared_source
            if isinstance(declared_source, str) and declared_source
            else str(path)
        )

        extracted_at = datetime.now(UTC)
        results: list[ParseResult] = []
        carried: set[FactKey] = set()
        for index, calculation in enumerate(calculations, start=1):
            observations, calculation_id = self._observations_for(path, calculation, index)
            carried.update(observation.key for observation in observations)
            results.append(
                ParseResult(
                    source_file=source_file,
                    producer=f"{ADAPTER_PRODUCER_PREFIX}{producer}",
                    producer_version=producer_version,
                    extracted_at=extracted_at,
                    observations=observations,
                    diagnostics=ParseDiagnostics(outcome=ParseOutcome.COMPLETE),
                    origin=EvidenceOrigin.ADAPTER,
                    calculation_id=calculation_id,
                )
            )
        return tuple(results), frozenset(carried)

    def _observations_for(
        self, path: Path, calculation: object, index: int
    ) -> tuple[tuple[Observation, ...], str]:
        where = f"{path} calculation {index}"
        if not isinstance(calculation, dict):
            raise AdapterFormatError(f"{where} must be a JSON object")
        values = calculation.get("values")
        if not isinstance(values, dict) or not values:
            raise AdapterFormatError(f"{where} holds no values")

        declared_id = calculation.get("calculation_id")
        calculation_id = (
            declared_id
            if isinstance(declared_id, str) and declared_id.strip()
            else f"analysis-{index}"
        )

        observations: list[Observation] = []
        for quantity, entry in values.items():
            if not isinstance(quantity, str):
                raise AdapterFormatError(f"{where} has a non-string quantity name")
            try:
                key = FactKey(quantity)
            except ValueError:
                raise _reject_quantity(quantity, where) from None
            if key not in SUPPORTED_QUANTITIES:
                raise _reject_quantity(quantity, where)
            if not isinstance(entry, dict):
                raise AdapterFormatError(
                    f"{where}: {quantity!r} must be an object with a value and a unit"
                )
            unit = entry.get("unit")
            if not isinstance(unit, str):
                raise AdapterFormatError(
                    f"{where}: {quantity!r} states no unit. Every imported value declares its "
                    "unit so a conversion can never be assumed."
                )
            raw = _number(key, entry.get("value"), where)
            # A flag carries no scale, so only quantities with a real unit are converted.
            value: ScalarValue = (
                raw if isinstance(raw, bool) else _scaled(key, float(raw), unit)
            )
            observations.append(
                Observation(
                    key=key,
                    value=value,
                    unit=_EXPECTED_UNITS[key],
                    location=f"{path} calculation {calculation_id}",
                )
            )
        if not observations:
            raise AdapterFormatError(f"{where} held no usable quantities")
        return tuple(observations), calculation_id

"""What a parser produces: observations with their locations, plus an honest account of
what it could not read.

A parser reports what it *saw and where*. Turning an observation into a provenance-bearing
fact is a mechanical lift done in ``evidence/facts/``, and turning facts into evidence is a
judgement declared by a protocol in ``evidence/derivation.py``. Neither of those belongs
here.

The diagnostics matter as much as the observations. A result that simply omits a value
leaves the audit unable to tell whether the calculation was never run or whether our reader
missed it, and those two cases must not be reported the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from qcjudge.domain.common import Provenance, UnavailableReason
from qcjudge.domain.evidence import EvidenceOrigin, FactKey, ScalarValue, UnavailableFact


@dataclass(frozen=True, slots=True)
class Observation:
    """One value seen in an output file, and where it was seen.

    ``value`` is ``None`` only when the file positively reports the absence of a value; a
    value we did not find is not an observation at all.
    """

    key: FactKey
    value: ScalarValue | tuple[ScalarValue, ...]
    unit: str | None = None
    location: str | None = None


class ParseOutcome(StrEnum):
    """How much of the file we believe we saw."""

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNRECOGNISED = "unrecognised"


@dataclass(frozen=True, slots=True)
class ParseDiagnostics:
    """What the parser could not do, in the same vocabulary the audit uses.

    ``unavailable`` carries a reason for every supported value the parser did not produce.
    That is what lets a matcher distinguish a missing calculation from an unreadable file.
    ``unparsed_regions`` names blocks the parser recognised but deliberately does not read,
    so a limitation is visible rather than silent.
    """

    outcome: ParseOutcome = ParseOutcome.COMPLETE
    unavailable: tuple[UnavailableFact, ...] = ()
    unparsed_regions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unrecognised_keys: tuple[FactKey, ...] = ()

    @property
    def is_usable(self) -> bool:
        return self.outcome is not ParseOutcome.UNRECOGNISED

    def reason_for(self, source_file: str, key: FactKey) -> UnavailableReason | None:
        for absent in self.unavailable:
            if absent.provenance.source_file == source_file and absent.key is key:
                return absent.reason
        return None


@dataclass(frozen=True, slots=True)
class ParseResult:
    """One file's observations and the account of what was not read.

    The producer identity and the extraction timestamp live here rather than being supplied
    downstream, so one parse carries one coherent provenance and two runs on the same file
    differ only by that stamp.

    ``origin`` and ``calculation_id`` exist so an importer can say what it is. A reader that
    imported an external analysis is not a calculation, and its facts must be attributed
    differently from ones read out of a job's own output; ``calculation_id`` lets it name the
    calculation the analysis belongs to instead of being numbered positionally.
    """

    source_file: str
    producer: str
    producer_version: str
    extracted_at: datetime
    observations: tuple[Observation, ...] = ()
    diagnostics: ParseDiagnostics = ParseDiagnostics()
    origin: EvidenceOrigin = EvidenceOrigin.PARSED
    calculation_id: str | None = None
    source_calculation_id: str | None = None
    molecule: str | None = None
    state: str | None = None

    def __post_init__(self) -> None:
        if self.extracted_at.tzinfo is None:
            raise ValueError("extracted_at must be timezone-aware")
        if self.origin is EvidenceOrigin.USER_ASSERTION:
            raise ValueError(
                "A parse result cannot be a user assertion: it reads a file and cites it"
            )

    def observation(self, key: FactKey) -> Observation | None:
        for item in self.observations:
            if item.key is key:
                return item
        return None

    def provenanced(self, location: str | None) -> Provenance:
        return Provenance(
            source_file=self.source_file,
            producer=self.producer,
            producer_version=self.producer_version,
            extracted_at=self.extracted_at,
            source_location=location,
        )

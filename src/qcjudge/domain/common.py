"""Shared domain primitives.

Provenance deliberately does **not** carry a protocol version. A fact is a property of the
output file, not of a protocol; protocol versions are recorded on the report and on each
assessment, so that a report stays reproducible after a protocol is revised.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class EpistemicKind(StrEnum):
    """The role a statement plays in scientific reasoning."""

    OBSERVATION = "observation"
    COMPUTED_FACT = "computed_fact"
    METHOD_ASSUMPTION = "method_assumption"
    INTERPRETATION = "interpretation"
    EVIDENCE = "evidence"
    CLAIM = "claim"


class TruthValue(StrEnum):
    """Three-valued result for checks whose inputs may be absent."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class UnavailableReason(StrEnum):
    """Why a fact we needed is not in the inventory.

    The distinction decides whether a requirement comes out ``INSUFFICIENT`` (evidence
    coverage: the calculation was not provided) or ``NOT_ASSESSABLE`` (epistemic access:
    we could not read what was provided).
    """

    NOT_PROVIDED = "not_provided"
    FILE_TRUNCATED = "file_truncated"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    AMBIGUOUS_MATCH = "ambiguous_match"

    @property
    def is_access_failure(self) -> bool:
        """True when the absence is a limitation of our reader, not the user's omission."""
        return self is not UnavailableReason.NOT_PROVIDED


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a fact or evidence item came from; never inferred silently."""

    source_file: str
    producer: str
    producer_version: str
    extracted_at: datetime
    source_location: str | None = None

    def __post_init__(self) -> None:
        if self.extracted_at.tzinfo is None:
            raise ValueError("extracted_at must be timezone-aware")

    @classmethod
    def now(
        cls,
        *,
        source_file: str,
        producer: str,
        producer_version: str,
        source_location: str | None = None,
    ) -> Provenance:
        return cls(
            source_file=source_file,
            producer=producer,
            producer_version=producer_version,
            extracted_at=datetime.now(UTC),
            source_location=source_location,
        )

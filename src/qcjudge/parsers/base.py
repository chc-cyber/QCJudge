"""Format-neutral parser contract.

A parser reports observations and diagnostics. It decides nothing: it does not know what a
requirement is, whether a value is good news, or how strong a piece of evidence is.
"""

from pathlib import Path
from typing import Protocol

from qcjudge.domain.calculation import ParseResult
from qcjudge.domain.evidence import FactKey


class CalculationParser(Protocol):
    """Reads one output file into observations plus diagnostics."""

    name: str
    version: str

    @property
    def supported_keys(self) -> frozenset[FactKey]:
        """The fact keys this parser attempts to produce.

        Keys outside this set are reported as ``UNSUPPORTED_CONSTRUCT`` rather than being
        silently absent, so a limitation of the reader is never presented as a property of
        the calculation.
        """
        ...

    def parse(self, path: Path) -> ParseResult: ...

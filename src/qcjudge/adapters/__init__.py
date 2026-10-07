"""Importing analyses QCJudge does not compute.

The evidence that decides most real questions comes from analyses this project deliberately does
not implement: hole-electron descriptors, natural-transition-orbital composition, spin-orbit
couplings, intrinsic reaction coordinates. Multiwfn and its peers compute them, and reimplementing
any of it would be scope creep of the worst kind -- a second, worse implementation of someone
else's algorithm, inside a tool whose subject is evidence rather than wavefunctions.

So the values are *imported*, and the only thing this project owes them is honesty about where
they came from. That is what the seam is for:

* Nothing here computes or interprets a number. It reads a documented file and reports what it
  says, exactly as a parser does for a calculation's own output.
* The values arrive with a producer identity, so the report can say "Multiwfn 3.8" rather than
  presenting an imported number as something the calculation emitted. A derived piece of evidence
  inherits that identity (see ``evidence/derivation.py``), which is how ``EvidenceOrigin.ADAPTER``
  becomes reachable at all.
* A quantity must name a registered ``FactKey``. A free string here would turn a typo into
  silently missing evidence, which is the failure mode this project least wants.
* Units are checked, not assumed. A distance exported in bohr would otherwise enter an audit as
  angstrom and quietly change what the descriptor means.
* The importer never sets evidence strength. A protocol declares what an imported descriptor is
  worth, exactly as it does for a parsed one.

The file format is documented in ``docs/adapter-format.md``.
"""

from qcjudge.adapters.json_analysis import (
    ADAPTER_PRODUCER_PREFIX,
    FORMAT_ID,
    SUPPORTED_QUANTITIES,
    JsonAnalysisAdapter,
)

__all__ = [
    "ADAPTER_PRODUCER_PREFIX",
    "FORMAT_ID",
    "SUPPORTED_QUANTITIES",
    "JsonAnalysisAdapter",
]
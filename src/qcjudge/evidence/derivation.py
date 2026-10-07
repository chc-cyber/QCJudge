"""Turn facts into evidence, using the strengths a protocol declares.

This is where the project's epistemic boundary is drawn. A parser knows the file format;
this module knows only what a protocol says. Stating that a reported excited-state count
amounts to a ``MODERATE``, ``DIRECT`` assignment is a scientific judgement, so it is declared
by the protocol rather than written into extraction code -- and revising it is a protocol
version change, not a parser bug fix.
"""

from __future__ import annotations

from collections.abc import Sequence

from qcjudge.domain.common import Provenance
from qcjudge.domain.evidence import (
    Evidence,
    EvidenceDerivation,
    EvidenceInventory,
    EvidenceOrigin,
    ExtractedFact,
    FactKey,
)
from qcjudge.domain.protocol import ScientificProtocol


def _group_by_calculation(
    facts: Sequence[ExtractedFact],
) -> dict[str, dict[FactKey, ExtractedFact]]:
    grouped: dict[str, dict[FactKey, ExtractedFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.subject.calculation_id, {})[fact.key] = fact
    return grouped


def _provenance_of(
    available: dict[FactKey, ExtractedFact], derivation: EvidenceDerivation
) -> Provenance:
    """Cite the first required fact's origin, so derived evidence stays traceable."""
    return available[derivation.required_fact_keys[0]].provenance


def _origin_of(
    available: dict[FactKey, ExtractedFact], derivation: EvidenceDerivation
) -> EvidenceOrigin:
    """Where derived evidence belongs, according to where its facts came from.

    A fact states its own origin, so this is read rather than inferred: a value read out of a
    calculation's own output is ``PARSED``, and a value an external analysis exported is
    ``ADAPTER``. Recording every derivation as ``PARSED`` would misattribute an imported number
    to the calculation, which is exactly the provenance loss the project exists to prevent.
    """
    origins = {available[key].origin for key in derivation.required_fact_keys}
    if len(origins) == 1:
        return next(iter(origins))
    # A derivation that mixed sources is attributed to the weaker one, because that is the
    # claim a reader would otherwise be entitled to disbelieve.
    return EvidenceOrigin.ADAPTER


def derive_evidence(
    protocol: ScientificProtocol, inventory: EvidenceInventory
) -> tuple[Evidence, ...]:
    """Evidence that follows from facts, under the protocol's declared strengths.

    A derivation fires only when every fact it depends on is present for the same
    calculation. A partial match is not scaled down into weaker evidence: that would be a
    judgement nobody declared.
    """
    grouped = _group_by_calculation(inventory.facts)
    derived: list[Evidence] = []
    for derivation in protocol.derivations:
        for calculation_id in sorted(grouped):
            available = grouped[calculation_id]
            if not all(key in available for key in derivation.required_fact_keys):
                continue
            if not all(
                predicate.accepts(available[predicate.key].value)
                for predicate in derivation.fact_predicates
            ):
                continue
            derived.append(
                Evidence(
                    id=f"derived:{derivation.id}:{calculation_id}",
                    evidence_type=derivation.evidence_type,
                    description=derivation.description,
                    fact_ids=tuple(
                        available[key].id for key in derivation.required_fact_keys
                    ),
                    strength=derivation.strength,
                    directness=derivation.directness,
                    origin=_origin_of(available, derivation),
                    provenance=_provenance_of(available, derivation),
                )
            )
    return tuple(derived)


def with_derived_evidence(
    protocol: ScientificProtocol, inventory: EvidenceInventory
) -> EvidenceInventory:
    """A new inventory holding supplied evidence plus everything the protocol derives."""
    derived = derive_evidence(protocol, inventory)
    if not derived:
        return inventory
    existing = {item.id for item in inventory.evidence}
    return EvidenceInventory(
        facts=inventory.facts,
        evidence=inventory.evidence
        + tuple(item for item in derived if item.id not in existing),
        unavailable=inventory.unavailable,
    )

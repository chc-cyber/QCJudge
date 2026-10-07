"""Builders for hand-constructed inventories used by the tests.

Fixtures are built by hand rather than parsed, so the acceptance corpus exercises the
reasoning engine without depending on any parser. Every value is synthetic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from qcjudge.domain.common import EpistemicKind, Provenance, UnavailableReason
from qcjudge.domain.evidence import (
    Evidence,
    EvidenceDirectness,
    EvidenceInventory,
    EvidenceOrigin,
    EvidenceStrength,
    EvidenceType,
    ExtractedFact,
    FactKey,
    ScalarValue,
    Subject,
    UnavailableFact,
)
from qcjudge.domain.question import Hypothesis, QuestionFamily, ResearchQuestion
from qcjudge.protocols import get_protocol

CT = QuestionFamily.CHARGE_TRANSFER_EXCITATION
TADF = QuestionFamily.TADF_POTENTIAL
TS = QuestionFamily.TRANSITION_STATE_VALIDATION

STAMP = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
PRODUCER = "tests.support"
PRODUCER_VERSION = "0.0.0"
SOURCE_FILE = "synthetic/case.out"
CALCULATION_ID = "calc-1"

STATE_COUNT_FACT = f"{CALCULATION_ID}:{FactKey.EXCITED_STATE_COUNT.value}"
GEOMETRY_FACT = f"{CALCULATION_ID}:{FactKey.GEOMETRY_CONVERGED.value}"
IMAGINARY_FACT = f"{CALCULATION_ID}:{FactKey.FREQUENCY_IMAGINARY_COUNT.value}"
GAP_FACT = f"{CALCULATION_ID}:{FactKey.SINGLET_TRIPLET_GAP_EV.value}"


def provenance(
    *, source_file: str = SOURCE_FILE, location: str | None = "line 1"
) -> Provenance:
    return Provenance(
        source_file=source_file,
        producer=PRODUCER,
        producer_version=PRODUCER_VERSION,
        extracted_at=STAMP,
        source_location=location,
    )


def fact(
    key: FactKey,
    value: ScalarValue,
    *,
    calculation_id: str = CALCULATION_ID,
    unit: str | None = None,
    kind: EpistemicKind = EpistemicKind.COMPUTED_FACT,
    source_calculation_id: str | None = None,
) -> ExtractedFact:
    return ExtractedFact(
        id=f"{calculation_id}:{key.value}",
        key=key,
        value=value,
        unit=unit,
        subject=Subject(
            calculation_id=calculation_id, source_calculation_id=source_calculation_id
        ),
        provenance=provenance(),
        epistemic_kind=kind,
    )


def unavailable(
    key: FactKey,
    reason: UnavailableReason,
    *,
    calculation_id: str = CALCULATION_ID,
) -> UnavailableFact:
    return UnavailableFact(
        key=key,
        reason=reason,
        provenance=provenance(),
        subject=Subject(calculation_id=calculation_id),
    )


def evidence(
    evidence_id: str,
    evidence_type: EvidenceType,
    *,
    fact_ids: tuple[str, ...] = (STATE_COUNT_FACT,),
    strength: EvidenceStrength = EvidenceStrength.STRONG,
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT,
    origin: EvidenceOrigin = EvidenceOrigin.PARSED,
    description: str = "Synthetic evidence for the acceptance corpus.",
) -> Evidence:
    return Evidence(
        id=evidence_id,
        evidence_type=evidence_type,
        description=description,
        fact_ids=fact_ids,
        strength=strength,
        directness=directness,
        origin=origin,
        provenance=None if origin is EvidenceOrigin.USER_ASSERTION else provenance(),
    )


def inventory(
    *facts: ExtractedFact,
    evidence_items: tuple[Evidence, ...] = (),
    unavailable_items: tuple[UnavailableFact, ...] = (),
) -> EvidenceInventory:
    return EvidenceInventory(
        facts=facts, evidence=evidence_items, unavailable=unavailable_items
    )


def question(family: QuestionFamily, **context: str) -> ResearchQuestion:
    protocol = get_protocol(family)
    return ResearchQuestion(
        family=family,
        text=f"Synthetic {family.value} question.",
        hypotheses=tuple(
            Hypothesis(item.id, item.statement) for item in protocol.hypotheses
        ),
        context=tuple(sorted(context.items())),
    )


def converged_calculation() -> tuple[ExtractedFact, ...]:
    """The facts every assessable fixture needs: convergence, method, basis."""
    return (
        fact(FactKey.SCF_CONVERGED, True),
        fact(FactKey.METHOD_NAME, "B3LYP"),
        fact(FactKey.BASIS_NAME, "def2-TZVP"),
    )


def ct_question() -> ResearchQuestion:
    return question(CT, molecule="molA", state="S1")


def ct_state_count() -> ExtractedFact:
    return fact(FactKey.EXCITED_STATE_COUNT, 5, unit="states")


def excited_state_evidence() -> Evidence:
    return evidence(
        "ev-excited",
        EvidenceType.EXCITED_STATE_ASSIGNMENT,
        fact_ids=(STATE_COUNT_FACT,),
        strength=EvidenceStrength.MODERATE,
    )


def hole_electron_evidence(
    strength: EvidenceStrength = EvidenceStrength.STRONG,
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT,
) -> Evidence:
    return evidence(
        "ev-hole-electron",
        EvidenceType.HOLE_ELECTRON_ANALYSIS,
        strength=strength,
        directness=directness,
    )


def tadf_question() -> ResearchQuestion:
    return question(TADF, molecule="molA")


def tadf_facts() -> tuple[ExtractedFact, ...]:
    return (
        *converged_calculation(),
        fact(FactKey.SINGLET_STATE_ENERGY_EV, 2.85, unit="eV"),
        fact(FactKey.TRIPLET_STATE_ENERGY_EV, 2.77, unit="eV"),
        fact(FactKey.SINGLET_TRIPLET_GAP_EV, 0.08, unit="eV"),
    )


def tadf_gap_evidence() -> Evidence:
    return evidence("ev-gap", EvidenceType.SINGLET_TRIPLET_GAP, fact_ids=(GAP_FACT,))


def tadf_soc_evidence() -> Evidence:
    return evidence("ev-soc", EvidenceType.SPIN_ORBIT_COUPLING, fact_ids=(GAP_FACT,))


def ts_question() -> ResearchQuestion:
    return question(TS, molecule="molA")


def ts_facts(imaginary: int, *, observed: int = 54, expected: int = 54) -> tuple[
    ExtractedFact, ...
]:
    return (
        fact(FactKey.SCF_CONVERGED, True),
        fact(FactKey.GEOMETRY_CONVERGED, True),
        fact(FactKey.FREQUENCY_OBSERVED_MODE_COUNT, observed, unit="modes"),
        fact(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, expected, unit="modes"),
        fact(FactKey.FREQUENCY_IMAGINARY_COUNT, imaginary, unit="modes"),
    )


def ts_evidence() -> Evidence:
    return evidence(
        "ev-opt-freq",
        EvidenceType.OPTIMIZATION_AND_FREQUENCY,
        fact_ids=(GEOMETRY_FACT, IMAGINARY_FACT),
        strength=EvidenceStrength.MODERATE,
    )


def ts_irc_evidence() -> Evidence:
    return evidence("ev-irc", EvidenceType.IRC, fact_ids=(GEOMETRY_FACT,))

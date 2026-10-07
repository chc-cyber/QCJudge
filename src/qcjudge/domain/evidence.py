"""Facts, evidence, requirements, groups, and the inventory that holds them.

Facts are properties of output files and carry provenance. Evidence cites facts and records
how strong and how direct it is. Requirements declare what a claim needs. An inventory is
the frozen, referentially checked set of facts, evidence, and recorded absences that the
audit engine reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from qcjudge.domain.common import EpistemicKind, Provenance, UnavailableReason
from qcjudge.errors import InventoryError

type ScalarValue = str | int | float | bool


class FactKey(StrEnum):
    """Registered fact names. Free strings would turn typos into silent absent evidence.

    The first group is read verbatim from a file and is therefore an observation. The second
    group is arithmetically derived from observations and is therefore a computed fact; the
    two are never conflated.
    """

    SOFTWARE_NAME = "software.name"
    SOFTWARE_VERSION = "software.version"
    METHOD_NAME = "method.name"
    BASIS_NAME = "basis.name"
    CHARGE = "system.charge"
    MULTIPLICITY = "system.multiplicity"
    SCF_CONVERGED = "scf.converged"
    GEOMETRY_CONVERGED = "geometry.converged"
    FREQUENCY_CM1 = "frequency.cm1"
    SINGLET_STATE_ENERGY_EV = "excited_state.singlet_energy_ev"
    TRIPLET_STATE_ENERGY_EV = "excited_state.triplet_energy_ev"
    OSCILLATOR_STRENGTH = "excited_state.oscillator_strength"
    SPIN_EXPECTATION = "spin.s_squared"

    FREQUENCY_OBSERVED_MODE_COUNT = "frequency.observed_mode_count"
    FREQUENCY_EXPECTED_MODE_COUNT = "frequency.expected_mode_count"
    FREQUENCY_IMAGINARY_COUNT = "frequency.imaginary_count"
    EXCITED_STATE_COUNT = "tddft.state_count"
    SINGLET_TRIPLET_GAP_EV = "excited_state.singlet_triplet_gap_ev"

    # Facts that come from an external analysis rather than from a calculation's own output:
    # hole-electron descriptors, natural-transition-orbital composition, and spin-orbit
    # coupling. They are registered here so an import cannot introduce a free string, and a
    # protocol validates against them like any other key. No parser produces them; they arrive
    # through the adapter seam.
    HOLE_ELECTRON_D_INDEX = "hole_electron.d_index_angstrom"
    HOLE_ELECTRON_SR_INDEX = "hole_electron.sr_index"
    HOLE_ELECTRON_LAMBDA_ANGSTROM = "hole_electron.lambda_angstrom"
    NTO_DOMINANT_PAIR_CONTRIBUTION = "nto.dominant_pair_contribution"
    SPIN_ORBIT_COUPLING_CM1 = "spin_orbit.coupling_cm1"
    IRC_CONNECTS_TWO_MINIMA = "irc.connects_two_minima"


class EvidenceType(StrEnum):
    """Registered evidence types a requirement may accept or a supplier may provide."""

    EXCITED_STATE_ASSIGNMENT = "excited_state_assignment"
    HOLE_ELECTRON_ANALYSIS = "hole_electron_analysis"
    NTO_ANALYSIS = "nto_analysis"
    ATTACHMENT_DETACHMENT_DENSITY = "attachment_detachment_density"
    METHOD_COMPARISON = "method_comparison"
    RANGE_SEPARATION_VALIDATION = "range_separation_validation"
    SINGLET_TRIPLET_GAP = "singlet_triplet_gap"
    SPIN_ORBIT_COUPLING = "spin_orbit_coupling"
    RISC_RATE = "risc_rate"
    VIBRONIC_COUPLING_ANALYSIS = "vibronic_coupling_analysis"
    OSCILLATOR_STRENGTH = "oscillator_strength"
    RADIATIVE_RATE = "radiative_rate"
    OPTIMIZATION_AND_FREQUENCY = "optimization_and_frequency"
    NORMAL_MODE_INSPECTION = "normal_mode_inspection"
    IRC = "irc"
    REACTION_PATH_FOLLOWING = "reaction_path_following"


class RequirementLevel(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class RequirementRole(StrEnum):
    """Whether a requirement carries the substance of the claim or merely enables it.

    Identifying an excited state is a prerequisite for discussing its character; the
    spatial redistribution itself is the substance. Only substantive requirements decide
    whether a partly covered claim is partially supported or plainly unsupported.
    """

    SUBSTANTIVE = "substantive"
    PREREQUISITE = "prerequisite"


_STRENGTH_ORDER = ("weak", "moderate", "strong")
_DIRECTNESS_ORDER = ("indirect", "direct")


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"

    @property
    def rank(self) -> int:
        return _STRENGTH_ORDER.index(self.value)


class EvidenceDirectness(StrEnum):
    INDIRECT = "indirect"
    DIRECT = "direct"

    @property
    def rank(self) -> int:
        return _DIRECTNESS_ORDER.index(self.value)


class EvidenceOrigin(StrEnum):
    """Where evidence came from, which bounds how much weight it can carry."""

    PARSED = "parsed"
    ADAPTER = "adapter"
    USER_ASSERTION = "user_assertion"


class GroupSatisfaction(StrEnum):
    ANY_ONE = "any_one"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class Subject:
    """What a fact is about, so a value is never ambiguous."""

    calculation_id: str
    state: str | None = None
    mode_index: int | None = None


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    """A value taken from an output file or an imported analysis, with provenance."""

    id: str
    key: FactKey
    value: ScalarValue | tuple[ScalarValue, ...] | None
    unit: str | None
    subject: Subject
    provenance: Provenance
    epistemic_kind: EpistemicKind = EpistemicKind.COMPUTED_FACT
    origin: EvidenceOrigin = EvidenceOrigin.PARSED

    def __post_init__(self) -> None:
        if self.epistemic_kind not in {EpistemicKind.OBSERVATION, EpistemicKind.COMPUTED_FACT}:
            raise ValueError("Extracted facts must be observations or computed facts")
        if self.origin is EvidenceOrigin.USER_ASSERTION:
            raise ValueError(
                "A user assertion is not a fact: it cites no file and carries no provenance"
            )


@dataclass(frozen=True, slots=True)
class UnavailableFact:
    """A fact we do not have, together with the reason it is missing.

    An absent fact is not a false fact. Recording *why* it is absent is what lets the
    engine distinguish a missing calculation from an unreadable file, and the message is
    what lets a human check that judgement.
    """

    key: FactKey
    reason: UnavailableReason
    provenance: Provenance
    subject: Subject
    message: str | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    """A structured reason to believe a requirement is met."""

    id: str
    evidence_type: EvidenceType
    description: str
    fact_ids: tuple[str, ...]
    strength: EvidenceStrength
    directness: EvidenceDirectness
    origin: EvidenceOrigin
    provenance: Provenance | None = None
    epistemic_kind: EpistemicKind = EpistemicKind.EVIDENCE

    def __post_init__(self) -> None:
        if self.epistemic_kind is not EpistemicKind.EVIDENCE:
            raise ValueError("Evidence must carry EVIDENCE")
        if self.origin is EvidenceOrigin.USER_ASSERTION:
            if self.provenance is not None:
                raise ValueError("A user assertion has no file provenance")
            if (
                self.strength is not EvidenceStrength.WEAK
                or self.directness is not EvidenceDirectness.INDIRECT
            ):
                raise ValueError("User-asserted evidence is capped at WEAK and INDIRECT")
        elif self.provenance is None:
            raise ValueError("Parsed or adapted evidence must carry provenance")
        if not self.fact_ids and self.origin is not EvidenceOrigin.USER_ASSERTION:
            raise ValueError("Parsed or adapted evidence must cite at least one fact")


@dataclass(frozen=True, slots=True)
class EvidenceGroup:
    """Requirements that may satisfy each other, e.g. mode inspection or IRC.

    Modelling alternatives as a group makes the symmetry structural rather than a pair of
    hand-maintained cross-references.
    """

    id: str
    member_ids: tuple[str, ...]
    satisfaction: GroupSatisfaction = GroupSatisfaction.ANY_ONE

    def __post_init__(self) -> None:
        if len(self.member_ids) < 2:
            raise ValueError("A group needs at least two members")
        if len(set(self.member_ids)) != len(self.member_ids):
            raise ValueError("Group members must be unique")


@dataclass(frozen=True, slots=True)
class EvidenceRequirement:
    """What a claim needs, and how much of it.

    Two kinds of rule reference are kept apart because a rule failure can mean two very
    different things. ``gating_rules`` decide whether the inputs are usable at all: a failure
    there means we cannot judge, and the requirement becomes ``NOT_ASSESSABLE``.
    ``contradicting_rules`` decide whether the evidence actively rules the requirement out: a
    failure there means ``CONTRADICTED``. Zero imaginary frequencies, for instance, are not a
    failed calculation -- they are a successful calculation of a minimum.
    """

    id: str
    claim_id: str
    description: str
    level: RequirementLevel
    accepted_evidence_types: tuple[EvidenceType, ...]
    role: RequirementRole = RequirementRole.SUBSTANTIVE
    minimum_strength: EvidenceStrength = EvidenceStrength.WEAK
    minimum_directness: EvidenceDirectness = EvidenceDirectness.INDIRECT
    required_facts: tuple[FactKey, ...] = ()
    dependencies: tuple[str, ...] = ()
    group_id: str | None = None
    gating_rules: tuple[str, ...] = ()
    contradicting_rules: tuple[str, ...] = ()
    expert_review_when: str | None = None
    expert_review_when_key: str | None = None
    insufficiency_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.accepted_evidence_types:
            raise ValueError("A requirement must accept at least one evidence type")
        if self.id in self.dependencies:
            raise ValueError("A requirement cannot depend on itself")
        if self.expert_review_when_key is not None and self.expert_review_when is None:
            raise ValueError(
                "A machine-testable expert boundary needs the condition it reports: set "
                "expert_review_when to the prose a reader will see"
            )


@dataclass(frozen=True, slots=True)
class EvidenceDerivation:
    """A protocol's declaration that a certain evidence type follows from certain facts.

    The parser knows the file format; it does not know how strong a piece of evidence is.
    Stating that "a reported excited-state count constitutes a MODERATE, DIRECT assignment"
    is a scientific judgement, so it is declared here -- versioned, reviewable, and
    testable -- rather than written into extraction code.
    """

    id: str
    evidence_type: EvidenceType
    required_fact_keys: tuple[FactKey, ...]
    description: str
    strength: EvidenceStrength
    directness: EvidenceDirectness

    def __post_init__(self) -> None:
        if not self.required_fact_keys:
            raise ValueError("A derivation must depend on at least one fact")


@dataclass(frozen=True, slots=True)
class EvidenceInventory:
    """The frozen set of facts and evidence an audit reads. Absences are recorded too."""

    facts: tuple[ExtractedFact, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    unavailable: tuple[UnavailableFact, ...] = ()

    def __post_init__(self) -> None:
        fact_ids = [fact.id for fact in self.facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise InventoryError("Fact IDs must be unique")
        evidence_ids = [item.id for item in self.evidence]
        if len(set(evidence_ids)) != len(evidence_ids):
            raise InventoryError("Evidence IDs must be unique")
        known = set(fact_ids)
        for item in self.evidence:
            unknown = sorted(set(item.fact_ids) - known)
            if unknown:
                raise InventoryError(f"Evidence {item.id!r} cites unknown facts: {unknown}")
        present = {(fact.subject.calculation_id, fact.key) for fact in self.facts}
        for absent in self.unavailable:
            if (absent.subject.calculation_id, absent.key) in present:
                raise InventoryError(
                    f"{absent.key} is both present and marked unavailable"
                )

    def facts_by_key(self, key: FactKey) -> tuple[ExtractedFact, ...]:
        return tuple(fact for fact in self.facts if fact.key is key)

    def evidence_by_type(self, *types: EvidenceType) -> tuple[Evidence, ...]:
        wanted = set(types)
        return tuple(item for item in self.evidence if item.evidence_type in wanted)

    def reasons_for_key(self, key: FactKey) -> tuple[UnavailableReason, ...]:
        return tuple(absent.reason for absent in self.unavailable if absent.key is key)

    def unavailable_reason(self, key: FactKey) -> UnavailableReason | None:
        """Most severe reason recorded for a key, or None when nothing was recorded.

        An access failure outweighs an omission: if any source suggests we could not read
        the value, we must not report the absence as a coverage gap.
        """
        reasons = self.reasons_for_key(key)
        if not reasons:
            return None
        for reason in reasons:
            if reason.is_access_failure:
                return reason
        return UnavailableReason.NOT_PROVIDED

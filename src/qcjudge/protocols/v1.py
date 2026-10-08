"""Version 1 declarations for the deliberately narrow initial scope.

Each protocol declares hypotheses, the claims that make them checkable, the evidence those
claims need, which evidence follows from facts and how strong it is, the deterministic rules
that gate or contradict them, and the boundaries beyond which an expert must decide. Nothing
here asserts a universal numerical threshold.

The ``derivations`` blocks are where evidence strength is decided. A parser reports that an
excited-state block exists; whether that amounts to a MODERATE or a STRONG assignment is a
scientific judgement, and it belongs here rather than in extraction code.
"""

from qcjudge.domain.evidence import (
    EvidenceDerivation,
    EvidenceDirectness,
    EvidenceGroup,
    EvidenceRequirement,
    EvidenceStrength,
    EvidenceType,
    FactKey,
    FactPredicate,
    FactPredicateOperator,
    GroupSatisfaction,
    RequirementLevel,
    RequirementRole,
)
from qcjudge.domain.protocol import RecommendationSpec, ScientificProtocol
from qcjudge.domain.question import Claim, Hypothesis, Interpretation, QuestionFamily
from qcjudge.domain.validation import ValidationRuleSpec, ValidationScope

EXECUTION = ValidationScope.EXECUTION
STRUCTURE = ValidationScope.STRUCTURE
METHODOLOGY = ValidationScope.METHODOLOGY

_SCF_RULE = ValidationRuleSpec("exec.scf", EXECUTION, "SCF converged.", "scf_converged")

# --------------------------------------------------------------------------------------
# Charge-transfer excitation
# --------------------------------------------------------------------------------------

_CT_HYPOTHESIS = Hypothesis(
    "ct.hypothesis",
    "The low-energy excitation of this system is charge-transfer in character.",
)
_CT_STATE_CLAIM = Claim(
    "ct.state_identified",
    _CT_HYPOTHESIS.id,
    "The {state} excitation of {molecule} is an identified electronic transition with a "
    "reported energy.",
)
_CT_CHARACTER_CLAIM = Claim(
    "ct.character",
    _CT_HYPOTHESIS.id,
    "The {state} excitation of {molecule} involves substantial donor-to-acceptor charge "
    "redistribution.",
)

CHARGE_TRANSFER_V1 = ScientificProtocol(
    id="charge_transfer",
    version="1.1.1",
    question_family=QuestionFamily.CHARGE_TRANSFER_EXCITATION,
    hypotheses=(_CT_HYPOTHESIS,),
    claims=(_CT_STATE_CLAIM, _CT_CHARACTER_CLAIM),
    requirements=(
        EvidenceRequirement(
            id="ct.target_state",
            claim_id=_CT_STATE_CLAIM.id,
            description="Identify the target electronic excitation and its energy.",
            level=RequirementLevel.REQUIRED,
            role=RequirementRole.PREREQUISITE,
            accepted_evidence_types=(EvidenceType.EXCITED_STATE_ASSIGNMENT,),
            required_facts=(FactKey.EXCITED_STATE_COUNT,),
            gating_rules=("exec.scf", "method.ct_target_state"),
            insufficiency_conditions=(
                "No excited-state calculation was provided.",
                "Excited states were computed but not identified.",
            ),
        ),
        EvidenceRequirement(
            id="ct.spatial_redistribution",
            claim_id=_CT_CHARACTER_CLAIM.id,
            description=(
                "Quantify or directly characterize the hole-electron spatial "
                "redistribution of the target excitation."
            ),
            level=RequirementLevel.REQUIRED,
            role=RequirementRole.SUBSTANTIVE,
            accepted_evidence_types=(
                EvidenceType.HOLE_ELECTRON_ANALYSIS,
                EvidenceType.NTO_ANALYSIS,
                EvidenceType.ATTACHMENT_DETACHMENT_DENSITY,
            ),
            minimum_strength=EvidenceStrength.MODERATE,
            minimum_directness=EvidenceDirectness.DIRECT,
            dependencies=("ct.target_state",),
            gating_rules=("exec.scf",),
            expert_review_when=(
                "The donor/acceptor partition or the spatial interpretation is ambiguous."
            ),
            expert_review_when_key="donor_acceptor_partition",
            insufficiency_conditions=(
                "Only excitation energies and oscillator strengths were provided.",
                "A descriptor exists but the donor/acceptor partition is not stated.",
            ),
        ),
        EvidenceRequirement(
            id="ct.method_sensitivity",
            claim_id=_CT_CHARACTER_CLAIM.id,
            description=(
                "Assess the sensitivity of the computed transition to the excited-state "
                "method."
            ),
            level=RequirementLevel.RECOMMENDED,
            accepted_evidence_types=(
                EvidenceType.METHOD_COMPARISON,
                EvidenceType.RANGE_SEPARATION_VALIDATION,
            ),
        ),
    ),
    validation_rules=(
        _SCF_RULE,
        ValidationRuleSpec(
            "method.ct_target_state",
            METHODOLOGY,
            "Check that the requested excitation index is not ruled out by supplied states.",
            "ct_target_state_exists",
            "An index within the available range does not resolve state character or identity.",
        ),
        ValidationRuleSpec(
            "method.ct_sensitivity",
            METHODOLOGY,
            "Flag methodological sensitivity that is relevant to long-range charge transfer.",
            "ct_method_sensitivity",
            "Whether a given functional is adequate depends on the system and target state.",
        ),
    ),
    recommendations=(
        RecommendationSpec(
            "ct.add_spatial_analysis",
            "ct.spatial_redistribution",
            (
                "Perform hole-electron, natural-transition-orbital, or "
                "attachment/detachment-density analysis on the target state."
            ),
            "Excitation energy and oscillator strength alone do not establish CT character.",
        ),
    ),
    derivations=(
        EvidenceDerivation(
            id="ct.state_assignment_from_excited_states",
            evidence_type=EvidenceType.EXCITED_STATE_ASSIGNMENT,
            required_fact_keys=(FactKey.EXCITED_STATE_COUNT,),
            fact_predicates=(
                FactPredicate(FactKey.EXCITED_STATE_COUNT, FactPredicateOperator.POSITIVE_INTEGER),
            ),
            description=(
                "An excited-state calculation reported states with energies and oscillator "
                "strengths. This identifies the states by index and energy; it says nothing "
                "about their character, which is why it is only a MODERATE, DIRECT "
                "assignment rather than strong evidence about the transition."
            ),
            strength=EvidenceStrength.MODERATE,
            directness=EvidenceDirectness.DIRECT,
        ),
        EvidenceDerivation(
            id="ct.spatial_from_hole_electron",
            evidence_type=EvidenceType.HOLE_ELECTRON_ANALYSIS,
            required_fact_keys=(
                FactKey.HOLE_ELECTRON_D_INDEX,
                FactKey.HOLE_ELECTRON_SR_INDEX,
            ),
            fact_predicates=(
                FactPredicate(
                    FactKey.HOLE_ELECTRON_D_INDEX, FactPredicateOperator.NONNEGATIVE_FINITE,
                ),
                FactPredicate(FactKey.HOLE_ELECTRON_SR_INDEX, FactPredicateOperator.UNIT_INTERVAL),
            ),
            description=(
                "A hole-electron analysis exported the spatial descriptors of the target "
                "excitation: the average hole-electron distance and the overlap between "
                "them. Together they quantify how far the excitation moves charge and how "
                "much the two distributions still share. This is a DIRECT measurement of the "
                "redistribution rather than an inference from its energy, which is why it "
                "satisfies the requirement at STRONG."
            ),
            strength=EvidenceStrength.STRONG,
            directness=EvidenceDirectness.DIRECT,
        ),
        EvidenceDerivation(
            id="ct.spatial_from_nto_pair",
            evidence_type=EvidenceType.NTO_ANALYSIS,
            required_fact_keys=(FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION,),
            fact_predicates=(
                FactPredicate(
                    FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION, FactPredicateOperator.UNIT_INTERVAL,
                ),
            ),
            description=(
                "A natural-transition-orbital analysis reported how completely the transition "
                "is described by its dominant orbital pair. A single dominant pair means the "
                "excitation is one well-defined transition, which is what makes a "
                "donor-to-acceptor assignment meaningful. It measures the composition of the "
                "transition rather than its spatial extent, so it is reported as MODERATE."
            ),
            strength=EvidenceStrength.MODERATE,
            directness=EvidenceDirectness.DIRECT,
        ),
    ),
    background=(
        Interpretation(
            "ct.background.energy",
            "A low excitation energy is not by itself evidence of charge-transfer character.",
        ),
    ),
    limitations=(
        "No universal numerical threshold for charge-transfer character is asserted.",
        "The donor/acceptor partition is an assumption supplied with the question.",
    ),
    max_defensible_claim_strength=(
        "The available evidence does or does not establish substantial donor-to-acceptor "
        "charge redistribution for the target excitation."
    ),
)

# --------------------------------------------------------------------------------------
# TADF potential
# --------------------------------------------------------------------------------------

_TADF_HYPOTHESIS = Hypothesis(
    "tadf.hypothesis",
    "The available calculations provide evidence consistent with TADF potential.",
)
_TADF_GAP_CLAIM = Claim(
    "tadf.gap",
    _TADF_HYPOTHESIS.id,
    "The relevant singlet and triplet states of {molecule} are separated by a small energy "
    "gap under the stated method.",
)
_TADF_RISC_CLAIM = Claim(
    "tadf.risc",
    _TADF_HYPOTHESIS.id,
    "A spin-forbidden channel capable of repopulating the singlet state of {molecule} is "
    "supported by evidence.",
)
_TADF_EMISSIVE_CLAIM = Claim(
    "tadf.emissive",
    _TADF_HYPOTHESIS.id,
    "The radiative singlet decay channel of {molecule} is characterized.",
)

TADF_V1 = ScientificProtocol(
    id="tadf",
    version="1.1.1",
    question_family=QuestionFamily.TADF_POTENTIAL,
    hypotheses=(_TADF_HYPOTHESIS,),
    claims=(_TADF_GAP_CLAIM, _TADF_RISC_CLAIM, _TADF_EMISSIVE_CLAIM),
    requirements=(
        EvidenceRequirement(
            id="tadf.singlet_triplet_states",
            claim_id=_TADF_GAP_CLAIM.id,
            description=(
                "Identify the relevant singlet and triplet states and the energy gap between "
                "them, at a consistent level of theory."
            ),
            level=RequirementLevel.REQUIRED,
            role=RequirementRole.SUBSTANTIVE,
            accepted_evidence_types=(EvidenceType.SINGLET_TRIPLET_GAP,),
            minimum_strength=EvidenceStrength.MODERATE,
            required_facts=(
                FactKey.SINGLET_STATE_ENERGY_EV,
                FactKey.TRIPLET_STATE_ENERGY_EV,
            ),
            gating_rules=("exec.scf", "method.state_consistency"),
            expert_review_when=(
                "State character and the vibronic pathway require system-specific "
                "interpretation."
            ),
            expert_review_when_key="state_character_ambiguous",
            insufficiency_conditions=(
                "Only one of the two states was characterized.",
                "The gap was assembled from calculations at different levels of theory.",
            ),
        ),
        EvidenceRequirement(
            id="tadf.risc_coupling",
            claim_id=_TADF_RISC_CLAIM.id,
            description=(
                "Provide evidence about the spin-forbidden channel, such as spin-orbit "
                "coupling, a rate estimate, or a vibronic analysis."
            ),
            level=RequirementLevel.REQUIRED,
            role=RequirementRole.SUBSTANTIVE,
            accepted_evidence_types=(
                EvidenceType.SPIN_ORBIT_COUPLING,
                EvidenceType.RISC_RATE,
                EvidenceType.VIBRONIC_COUPLING_ANALYSIS,
            ),
            minimum_strength=EvidenceStrength.MODERATE,
            dependencies=("tadf.singlet_triplet_states",),
            expert_review_when=(
                "Whether a coupling is large enough to matter is system specific."
            ),
            expert_review_when_key="coupling_significance",
            insufficiency_conditions=(
                "Only a singlet-triplet gap was provided.",
                "Coupling was asserted without a structured value.",
            ),
        ),
        EvidenceRequirement(
            id="tadf.radiative_channel",
            claim_id=_TADF_EMISSIVE_CLAIM.id,
            description="Characterize the radiative singlet decay channel.",
            level=RequirementLevel.RECOMMENDED,
            accepted_evidence_types=(
                EvidenceType.OSCILLATOR_STRENGTH,
                EvidenceType.RADIATIVE_RATE,
            ),
        ),
    ),
    validation_rules=(
        _SCF_RULE,
        ValidationRuleSpec(
            "method.state_consistency",
            METHODOLOGY,
            "Check that compared state energies come from a consistent level of theory.",
            "state_method_consistency",
            "Whether a difference in method makes values incomparable is an expert judgement.",
        ),
    ),
    recommendations=(
        RecommendationSpec(
            "tadf.add_risc_evidence",
            "tadf.risc_coupling",
            (
                "Compute spin-orbit couplings and/or a justified kinetic model for the "
                "relevant singlet-triplet channels."
            ),
            "A small computed singlet-triplet gap alone is not evidence of efficient RISC.",
        ),
    ),
    derivations=(
        EvidenceDerivation(
            id="tadf.gap_from_state_manifolds",
            evidence_type=EvidenceType.SINGLET_TRIPLET_GAP,
            required_fact_keys=(
                FactKey.SINGLET_STATE_ENERGY_EV,
                FactKey.TRIPLET_STATE_ENERGY_EV,
            ),
            fact_predicates=(
                FactPredicate(
                    FactKey.SINGLET_STATE_ENERGY_EV,
                    FactPredicateOperator.NONEMPTY_FINITE_NUMERIC_TUPLE,
                ),
                FactPredicate(
                    FactKey.TRIPLET_STATE_ENERGY_EV,
                    FactPredicateOperator.NONEMPTY_FINITE_NUMERIC_TUPLE,
                ),
            ),
            description=(
                "Both the singlet and the triplet manifold were reported with energies. "
                "This is a MODERATE, DIRECT statement that the two manifolds were "
                "characterized; it is deliberately not STRONG, because a gap built from two "
                "manifolds is only as good as the consistency of the methods behind them. "
                "Which states are the relevant S1 and T1 remains the claim's business, not "
                "this declaration's."
            ),
            strength=EvidenceStrength.MODERATE,
            directness=EvidenceDirectness.DIRECT,
        ),
        EvidenceDerivation(
            id="tadf.risc_from_spin_orbit_coupling",
            evidence_type=EvidenceType.SPIN_ORBIT_COUPLING,
            required_fact_keys=(FactKey.SPIN_ORBIT_COUPLING_CM1,),
            fact_predicates=(
                FactPredicate(
                    FactKey.SPIN_ORBIT_COUPLING_CM1, FactPredicateOperator.NONZERO_FINITE,
                ),
            ),
            description=(
                "An external analysis exported a computed spin-orbit coupling between the "
                "relevant singlet and triplet states. This is evidence that the spin-forbidden "
                "channel is not forbidden, which is the part a gap cannot supply. It is "
                "MODERATE rather than STRONG because whether a given coupling is large enough "
                "to matter is system specific, and the protocol declines to assert a threshold."
            ),
            strength=EvidenceStrength.MODERATE,
            directness=EvidenceDirectness.DIRECT,
        ),
    ),
    background=(
        Interpretation(
            "tadf.background.risc",
            "A small singlet-triplet gap facilitates reverse intersystem crossing.",
        ),
        Interpretation(
            "tadf.background.cap",
            "A small computed gap is not by itself evidence of efficient RISC.",
        ),
    ),
    limitations=(
        "The protocol does not infer device-level TADF performance.",
        "Reported singlet-triplet gaps scatter by 0.1-0.15 eV in the literature and depend "
        "on the functional by up to roughly 0.6 eV, so no fixed numerical cut-off is used.",
    ),
    max_defensible_claim_strength=(
        "The available evidence is or is not consistent with TADF potential. The protocol "
        "never asserts that the molecule is a TADF emitter."
    ),
)

# --------------------------------------------------------------------------------------
# Transition-state validation
# --------------------------------------------------------------------------------------

_TS_HYPOTHESIS = Hypothesis(
    "ts.hypothesis",
    "The optimized structure is the transition state for the proposed reaction step.",
)
_TS_SADDLE_CLAIM = Claim(
    "ts.first_order_saddle",
    _TS_HYPOTHESIS.id,
    "The optimized structure of {molecule} is a first-order saddle point of the computed "
    "potential energy surface.",
)
_TS_PATHWAY_CLAIM = Claim(
    "ts.pathway_identified",
    _TS_HYPOTHESIS.id,
    "The saddle point connects the intended reactant and product of the proposed step.",
)

TRANSITION_STATE_V1 = ScientificProtocol(
    id="transition_state",
    version="1.1.1",
    question_family=QuestionFamily.TRANSITION_STATE_VALIDATION,
    hypotheses=(_TS_HYPOTHESIS,),
    claims=(_TS_SADDLE_CLAIM, _TS_PATHWAY_CLAIM),
    requirements=(
        EvidenceRequirement(
            id="ts.stationary_point",
            claim_id=_TS_SADDLE_CLAIM.id,
            description=(
                "Establish a converged stationary point whose computed Hessian has exactly "
                "one imaginary mode."
            ),
            level=RequirementLevel.REQUIRED,
            role=RequirementRole.SUBSTANTIVE,
            accepted_evidence_types=(EvidenceType.OPTIMIZATION_AND_FREQUENCY,),
            minimum_strength=EvidenceStrength.MODERATE,
            required_facts=(FactKey.FREQUENCY_IMAGINARY_COUNT,),
            gating_rules=("exec.scf", "exec.optimization"),
            contradicting_rules=("struct.frequency_count",),
            insufficiency_conditions=(
                "No frequency calculation was provided.",
                "The reported mode list is incomplete, so the count is not meaningful.",
            ),
        ),
        EvidenceRequirement(
            id="ts.mode_identity",
            claim_id=_TS_PATHWAY_CLAIM.id,
            description=(
                "Show that the imaginary mode follows the proposed reaction coordinate."
            ),
            level=RequirementLevel.REQUIRED,
            role=RequirementRole.SUBSTANTIVE,
            accepted_evidence_types=(EvidenceType.NORMAL_MODE_INSPECTION,),
            minimum_strength=EvidenceStrength.MODERATE,
            dependencies=("ts.stationary_point",),
            group_id="ts.connection",
            expert_review_when=(
                "Mode correspondence cannot be encoded as a reproducible structured "
                "assertion."
            ),
            expert_review_when_key="mode_correspondence",
            insufficiency_conditions=(
                "The imaginary frequency is known but its mode was never inspected.",
            ),
        ),
        EvidenceRequirement(
            id="ts.pathway_connection",
            claim_id=_TS_PATHWAY_CLAIM.id,
            description=(
                "Connect the saddle point to the intended reactant and product basins."
            ),
            level=RequirementLevel.RECOMMENDED,
            role=RequirementRole.SUBSTANTIVE,
            accepted_evidence_types=(
                EvidenceType.IRC,
                EvidenceType.REACTION_PATH_FOLLOWING,
            ),
            minimum_strength=EvidenceStrength.MODERATE,
            minimum_directness=EvidenceDirectness.DIRECT,
            dependencies=("ts.stationary_point",),
            group_id="ts.connection",
        ),
    ),
    validation_rules=(
        _SCF_RULE,
        ValidationRuleSpec(
            "exec.optimization",
            EXECUTION,
            "Geometry optimization converged.",
            "opt_converged",
        ),
        ValidationRuleSpec(
            "struct.frequency_count",
            STRUCTURE,
            (
                "The computed Hessian has exactly one imaginary mode. A complete Hessian "
                "with no imaginary mode is a successful calculation of a minimum, not a "
                "failed calculation."
            ),
            "first_order_saddle_point",
        ),
    ),
    recommendations=(
        RecommendationSpec(
            "ts.validate_connection",
            "ts.mode_identity",
            (
                "Inspect the imaginary mode and, where needed, follow the path in both "
                "directions."
            ),
            "One imaginary frequency identifies local Hessian order, not pathway identity.",
        ),
    ),
    groups=(
        EvidenceGroup(
            "ts.connection",
            ("ts.mode_identity", "ts.pathway_connection"),
            GroupSatisfaction.ANY_ONE,
        ),
    ),
    derivations=(
        EvidenceDerivation(
            id="ts.saddle_from_opt_and_freq",
            evidence_type=EvidenceType.OPTIMIZATION_AND_FREQUENCY,
            required_fact_keys=(
                FactKey.GEOMETRY_CONVERGED,
                FactKey.FREQUENCY_IMAGINARY_COUNT,
            ),
            description=(
                "A converged geometry optimization and a complete frequency calculation "
                "were both reported for this structure. This establishes that the stationary "
                "point and its Hessian were computed; whether that Hessian is first-order, "
                "and whether the structure is the intended transition state, are separate "
                "questions handled elsewhere."
            ),
            strength=EvidenceStrength.MODERATE,
            directness=EvidenceDirectness.DIRECT,
        ),
        EvidenceDerivation(
            id="ts.pathway_from_irc",
            evidence_type=EvidenceType.IRC,
            required_fact_keys=(FactKey.IRC_CONNECTS_TWO_MINIMA,),
            fact_predicates=(
                FactPredicate(FactKey.IRC_CONNECTS_TWO_MINIMA, FactPredicateOperator.IS_TRUE),
            ),
            description=(
                "An intrinsic-reaction-coordinate run was followed downhill from the saddle "
                "point and reached two distinct minima, one on each side. This is the part an "
                "imaginary-frequency count cannot supply: a Hessian establishes the order of a "
                "stationary point, not what lies either side of it. It is recorded as MODERATE "
                "rather than STRONG, and deliberately, because reaching two minima is not the "
                "same as reaching the intended ones -- identifying those is the question the "
                "researcher asked, and this protocol does not answer it for them."
            ),
            strength=EvidenceStrength.MODERATE,
            directness=EvidenceDirectness.DIRECT,
        ),
    ),
    background=(
        Interpretation(
            "ts.background.one_imaginary",
            "One imaginary frequency establishes the local Hessian order at the computed "
            "stationary point; it does not establish the chemical pathway.",
        ),
    ),
    limitations=(
        "Pathway identity is not inferred from the imaginary-frequency count alone.",
        "The proposed reaction coordinate must be stated in the question.",
    ),
    max_defensible_claim_strength=(
        "The structure is a first-order saddle point and the mode or path evidence connects "
        "it to the proposed step. The protocol never asserts that it is the transition state "
        "of the real reaction."
    ),
)

PROTOCOLS: dict[QuestionFamily, ScientificProtocol] = {
    protocol.question_family: protocol
    for protocol in (CHARGE_TRANSFER_V1, TADF_V1, TRANSITION_STATE_V1)
}


def get_protocol(question_family: QuestionFamily) -> ScientificProtocol:
    return PROTOCOLS[question_family]

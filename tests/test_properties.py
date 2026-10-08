"""Generated invariants of the public projection -> audit path.

Every property uses real Hypothesis generation and shrinking, with reproducible runs and
no example database. Cases vary association graphs, scientific observations, missing or
invalid values, and input order. The assertions concern scientific outcomes and provenance,
not a reimplementation of the matcher or of numerical derivation.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from string import ascii_lowercase, digits
from unittest.mock import patch

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.calculation import Observation, ParseOutcome, ParseResult
from qcjudge.domain.evidence import EvidenceInventory, EvidenceType, FactKey, ScalarValue
from qcjudge.domain.validation import ValidationStatus
from qcjudge.errors import InventoryError
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from tests.property_support import (
    assert_used_facts_are_selected,
    common_observations,
    project,
    reader_result,
    requirements,
    scientific_signature,
    spatial_observations,
)
from tests.support import CT, TADF, TS, fact, question

PROPERTY_SETTINGS = settings(max_examples=80, derandomize=True, database=None, deadline=None)
IDENTIFIER = st.text(alphabet=ascii_lowercase + digits + "_-", min_size=1, max_size=10)
FINITE_NUMBER = st.floats(allow_nan=False, allow_infinity=False, width=64)
NONFINITE = st.sampled_from([float("nan"), float("inf"), float("-inf")])
INVALID_COUNT = st.one_of(
    st.none(), st.booleans(), st.integers(min_value=-1000, max_value=0),
    st.floats(min_value=0.001, max_value=0.999, allow_nan=False, allow_infinity=False), NONFINITE,
)
INVALID_CHANNEL = st.one_of(st.none(), st.booleans(), st.just(0.0), NONFINITE)
INVALID_DESCRIPTOR = st.one_of(
    st.none(), st.booleans(), st.text(alphabet=ascii_lowercase, max_size=8), NONFINITE,
)
INVALID_MANIFOLD = st.one_of(
    st.none(), st.booleans(), st.just(()), FINITE_NUMBER,
    st.text(alphabet=ascii_lowercase, max_size=8),
    st.tuples(st.booleans()), st.tuples(FINITE_NUMBER, st.booleans()),
)
VALID_MANIFOLD = st.lists(
    st.one_of(st.integers(), FINITE_NUMBER), min_size=1, max_size=5,
).map(tuple)


@st.composite
def linked_ct_cases(draw: st.DrawFn) -> tuple[tuple[ParseResult, ...], str, str, str]:
    ids = draw(st.lists(IDENTIFIER, min_size=2, max_size=5, unique=True))
    molecule = draw(IDENTIFIER)
    energies = tuple(draw(st.lists(
        st.floats(min_value=0.1, max_value=10, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=5,
    )))
    state = f"S{draw(st.integers(min_value=1, max_value=len(energies)))}"
    results = [reader_result(
        ids[0], (*common_observations(), Observation(FactKey.SINGLET_STATE_ENERGY_EV, energies)),
        state=state, molecule=molecule,
    )]
    for index, calculation_id in enumerate(ids[1:], start=1):
        observations = (
            spatial_observations(
                draw(st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)),
                draw(st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)),
            )
            if index == len(ids) - 1
            else (Observation(FactKey.SOFTWARE_NAME, "linked-analysis"),)
        )
        results.append(reader_result(
            calculation_id, observations, source=ids[index - 1], state=state, molecule=molecule,
        ))
    selected = draw(st.sampled_from(ids))
    return tuple(results), selected, state, molecule


def _nonfinite(value: object) -> bool:
    return isinstance(value, float) and (value != value or abs(value) == float("inf"))


def _changed_value(
    inventory: EvidenceInventory, key: FactKey, value: ScalarValue | None,
) -> EvidenceInventory:
    return replace(inventory, facts=tuple(
        replace(item, value=value) if item.key is key else item for item in inventory.facts
    ))


@PROPERTY_SETTINGS
@given(case=linked_ct_cases())
def test_explicit_association_chains_support_only_the_selected_group(
    case: tuple[tuple[ParseResult, ...], str, str, str],
) -> None:
    results, selected, state, molecule = case
    report = audit(question(CT, state=state, molecule=molecule, calculation_id=selected),
                   project(results))
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert report.execution_status is ValidationStatus.PASS
    assert report.association_issue is None
    assert set(report.selected_calculation_ids) == {item.calculation_id for item in results}
    assert_used_facts_are_selected(report)


@PROPERTY_SETTINGS
@given(ids=st.lists(IDENTIFIER, min_size=2, max_size=6, unique=True))
def test_independent_roots_cannot_jointly_support_an_unspecified_target(ids: list[str]) -> None:
    results = [reader_result(calculation_id, common_observations()) for calculation_id in ids]
    results[0] = replace(results[0], observations=(
        *results[0].observations, Observation(FactKey.EXCITED_STATE_COUNT, 1),
    ))
    results[-1] = replace(results[-1], observations=(
        *results[-1].observations, *spatial_observations(),
    ))
    report = audit(question(CT, molecule="molecule", state="S1"), project(results))
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert all(item.status is AssessmentStatus.NOT_ASSESSABLE for item in requirements(report))


@PROPERTY_SETTINGS
@given(
    ids=st.lists(IDENTIFIER, min_size=4, max_size=8, unique=True),
    own_spatial=st.booleans(), unrelated_converged=st.booleans(),
)
def test_selected_root_never_borrows_an_unrelated_roots_analysis_or_failure(
    ids: list[str], own_spatial: bool, unrelated_converged: bool,
) -> None:
    results = [reader_result(ids[0], (
        *common_observations(), Observation(FactKey.EXCITED_STATE_COUNT, 1),
    ))]
    results.append(reader_result(
        ids[1], spatial_observations() if own_spatial else (
            Observation(FactKey.SOFTWARE_NAME, "analysis-without-spatial-values"),
        ), source=ids[0],
    ))
    results.append(reader_result(ids[2], (
        *common_observations(converged=unrelated_converged),
        Observation(FactKey.EXCITED_STATE_COUNT, 1),
    ), molecule="other-molecule", state="T9"))
    results.append(reader_result(ids[3], spatial_observations(), source=ids[2]))
    results.extend(reader_result(item, common_observations(converged=False)) for item in ids[4:])
    report = audit(question(CT, molecule="molecule", state="S1", calculation_id=ids[1]),
                   project(results))
    expected = AssessmentStatus.SUPPORTED if own_spatial else AssessmentStatus.INSUFFICIENT
    assert report.overall_evidence_status is expected
    assert report.execution_status is ValidationStatus.PASS
    assert set(report.selected_calculation_ids) == {ids[0], ids[1]}
    assert_used_facts_are_selected(report)


@PROPERTY_SETTINGS
@given(case=linked_ct_cases(), cyclic=st.booleans())
def test_unresolved_source_graphs_never_become_scientific_support(
    case: tuple[tuple[ParseResult, ...], str, str, str], cyclic: bool,
) -> None:
    results, selected, state, molecule = case
    missing = "missing-" + selected
    while missing in {item.calculation_id for item in results}:
        missing += "-missing"
    root = replace(
        results[0], source_calculation_id=results[-1].calculation_id if cyclic else missing,
    )
    report = audit(question(CT, state=state, molecule=molecule, calculation_id=selected),
                   project((root, *results[1:])))
    assert report.association_issue is not None
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


@PROPERTY_SETTINGS
@example(value=None)
@example(value=False)
@example(value=0)
@example(value=float("nan"))
@given(value=INVALID_COUNT)
def test_invalid_state_counts_never_become_positive_assignments(value: ScalarValue | None) -> None:
    base = project((reader_result("root", (
        *common_observations(), Observation(FactKey.EXCITED_STATE_COUNT, 1),
        *spatial_observations(),
    )),))
    if _nonfinite(value):
        with pytest.raises(ValueError, match="non-finite"):
            _changed_value(base, FactKey.EXCITED_STATE_COUNT, value)
        return
    report = audit(question(CT, state="S1", molecule="molecule"),
                   _changed_value(base, FactKey.EXCITED_STATE_COUNT, value))
    assert report.execution_status is ValidationStatus.PASS
    assert not report.inventory.evidence_by_type(EvidenceType.EXCITED_STATE_ASSIGNMENT)
    assert report.overall_evidence_status is not AssessmentStatus.SUPPORTED


@PROPERTY_SETTINGS
@given(omitted=st.sets(st.sampled_from([
    FactKey.EXCITED_STATE_COUNT, FactKey.HOLE_ELECTRON_D_INDEX, FactKey.HOLE_ELECTRON_SR_INDEX,
]), min_size=1))
def test_omitting_required_observations_cannot_be_repaired_by_execution_success(
    omitted: set[FactKey],
) -> None:
    observations = (
        *common_observations(), Observation(FactKey.EXCITED_STATE_COUNT, 1),
        *spatial_observations(),
    )
    report = audit(question(CT, molecule="molecule", state="S1"), project((reader_result(
        "root", tuple(item for item in observations if item.key not in omitted),
    ),)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT
    assert all(not report.inventory.facts_by_key(key) for key in omitted)


@PROPERTY_SETTINGS
@example(value=None)
@example(value=False)
@example(value=0.0)
@example(value=float("nan"))
@given(value=INVALID_CHANNEL)
def test_empty_or_invalid_soc_does_not_establish_a_channel(value: ScalarValue | None) -> None:
    base = project((reader_result("root", (
        *common_observations(),
        Observation(FactKey.SINGLET_STATE_ENERGY_EV, (2.85,)),
        Observation(FactKey.TRIPLET_STATE_ENERGY_EV, (2.77,)),
        Observation(FactKey.SPIN_ORBIT_COUPLING_CM1, 12.4),
    )),))
    if _nonfinite(value):
        with pytest.raises(ValueError, match="non-finite"):
            _changed_value(base, FactKey.SPIN_ORBIT_COUPLING_CM1, value)
        return
    report = audit(question(TADF, molecule="molecule"),
                   _changed_value(base, FactKey.SPIN_ORBIT_COUPLING_CM1, value))
    assert report.execution_status is ValidationStatus.PASS
    assert not report.inventory.evidence_by_type(EvidenceType.SPIN_ORBIT_COUPLING)
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


@PROPERTY_SETTINGS
@example(key=FactKey.SINGLET_STATE_ENERGY_EV, value=None)
@example(key=FactKey.SINGLET_STATE_ENERGY_EV, value=False)
@example(key=FactKey.SINGLET_STATE_ENERGY_EV, value=())
@example(key=FactKey.SINGLET_STATE_ENERGY_EV, value="unknown")
@example(key=FactKey.SINGLET_STATE_ENERGY_EV, value=(False,))
@example(key=FactKey.TRIPLET_STATE_ENERGY_EV, value=None)
@example(key=FactKey.TRIPLET_STATE_ENERGY_EV, value=False)
@example(key=FactKey.TRIPLET_STATE_ENERGY_EV, value=())
@example(key=FactKey.TRIPLET_STATE_ENERGY_EV, value="unknown")
@example(key=FactKey.TRIPLET_STATE_ENERGY_EV, value=(False,))
@given(
    key=st.sampled_from([FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV]),
    value=INVALID_MANIFOLD,
)
def test_invalid_energy_manifolds_cannot_be_rescued_by_a_valid_soc_channel(
    key: FactKey, value: ScalarValue | tuple[ScalarValue, ...] | None,
) -> None:
    observations = (
        *common_observations(),
        Observation(FactKey.SINGLET_STATE_ENERGY_EV, (2.85,)),
        Observation(FactKey.TRIPLET_STATE_ENERGY_EV, (2.77,)),
        Observation(FactKey.SPIN_ORBIT_COUPLING_CM1, 12.4),
    )
    result = reader_result("root", tuple(
        replace(item, value=value) if item.key is key else item for item in observations
    ))
    report = audit(question(TADF, molecule="molecule"), project((result,)))
    assert report.execution_status is ValidationStatus.PASS
    assert not report.inventory.evidence_by_type(EvidenceType.SINGLET_TRIPLET_GAP)
    assert report.inventory.evidence_by_type(EvidenceType.SPIN_ORBIT_COUPLING)
    assert report.overall_evidence_status is not AssessmentStatus.SUPPORTED


@PROPERTY_SETTINGS
@example(singlet=(-1, 0.0, 1.5), triplet=(-2.0, 0, 1.0), coupling=12.4)
@given(
    singlet=VALID_MANIFOLD, triplet=VALID_MANIFOLD,
    coupling=st.floats(min_value=0.001, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_finite_nonempty_numeric_energy_manifolds_preserve_tadf_support(
    singlet: tuple[int | float, ...], triplet: tuple[int | float, ...], coupling: float,
) -> None:
    root = reader_result("root", (
        *common_observations(),
        Observation(FactKey.SINGLET_STATE_ENERGY_EV, singlet),
        Observation(FactKey.TRIPLET_STATE_ENERGY_EV, triplet),
    ))
    analysis = reader_result("soc", (
        Observation(FactKey.SPIN_ORBIT_COUPLING_CM1, coupling),
    ), source="root")
    report = audit(question(TADF, molecule="molecule"), project((root, analysis)))
    assert report.execution_status is ValidationStatus.PASS
    assert report.inventory.evidence_by_type(EvidenceType.SINGLET_TRIPLET_GAP)
    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert_used_facts_are_selected(report)


@PROPERTY_SETTINGS
@example(value=None)
@example(value=False)
@example(value=0)
@example(value=float("nan"))
@given(value=st.one_of(st.none(), st.just(False), st.integers(max_value=0), NONFINITE))
def test_failed_or_missing_irc_cannot_establish_positive_path_evidence(
    value: ScalarValue | None,
) -> None:
    base = project((reader_result("root", (
        *common_observations(), Observation(FactKey.GEOMETRY_CONVERGED, True),
        Observation(FactKey.FREQUENCY_CM1, (-300.0, 100.0, 200.0)),
        Observation(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, 3),
        Observation(FactKey.IRC_CONNECTS_TWO_MINIMA, True),
    )),))
    if _nonfinite(value):
        with pytest.raises(ValueError, match="non-finite"):
            _changed_value(base, FactKey.IRC_CONNECTS_TWO_MINIMA, value)
        return
    report = audit(question(TS, molecule="molecule"),
                   _changed_value(base, FactKey.IRC_CONNECTS_TWO_MINIMA, value))
    assert report.execution_status is ValidationStatus.PASS
    assert not report.inventory.evidence_by_type(EvidenceType.IRC)
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


@PROPERTY_SETTINGS
@given(
    key=st.sampled_from([
        FactKey.HOLE_ELECTRON_D_INDEX, FactKey.HOLE_ELECTRON_SR_INDEX,
        FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION,
    ]), value=INVALID_DESCRIPTOR,
)
def test_non_numeric_descriptors_never_become_spatial_evidence(
    key: FactKey, value: ScalarValue | None,
) -> None:
    base = project((reader_result("root", (
        *common_observations(), Observation(FactKey.EXCITED_STATE_COUNT, 1),
        *(spatial_observations() if key is not FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION else (
            Observation(FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION, 0.91),
        )),
    )),))
    if _nonfinite(value):
        with pytest.raises(ValueError, match="non-finite"):
            _changed_value(base, key, value)
        return
    report = audit(question(CT, state="S1", molecule="molecule"), _changed_value(base, key, value))
    kind = EvidenceType.NTO_ANALYSIS if key is FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION else (
        EvidenceType.HOLE_ELECTRON_ANALYSIS
    )
    assert not report.inventory.evidence_by_type(kind)
    if key is not FactKey.NTO_DOMINANT_PAIR_CONTRIBUTION:
        assert report.overall_evidence_status is not AssessmentStatus.SUPPORTED


@PROPERTY_SETTINGS
@given(ids=st.lists(IDENTIFIER, min_size=2, max_size=2, unique=True), data=st.data())
def test_execution_status_does_not_promote_missing_scientific_evidence(
    ids: list[str], data: st.DataObject,
) -> None:
    state_count = data.draw(st.integers(min_value=1, max_value=100))
    root = reader_result(ids[0], (
        *common_observations(), Observation(FactKey.EXCITED_STATE_COUNT, state_count),
    ))
    analyses = reader_result(ids[1], spatial_observations(), source=ids[0])
    q = question(CT, molecule="molecule", state="S1", calculation_id=ids[0])
    insufficient = audit(q, project((root,)))
    supported = audit(q, project((root, analyses)))
    failed_root = replace(root, observations=(
        *(item for item in root.observations if item.key is not FactKey.SCF_CONVERGED),
        Observation(FactKey.SCF_CONVERGED, False),
    ))
    failed = audit(q, project((failed_root, analyses)))
    assert insufficient.execution_status is supported.execution_status is ValidationStatus.PASS
    assert insufficient.overall_evidence_status is AssessmentStatus.INSUFFICIENT
    assert supported.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert failed.execution_status is ValidationStatus.FAIL
    assert failed.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


@PROPERTY_SETTINGS
@given(case=linked_ct_cases(), data=st.data())
def test_result_observation_fact_and_absence_order_preserves_ct_scientific_decisions(
    case: tuple[tuple[ParseResult, ...], str, str, str], data: st.DataObject,
) -> None:
    results, selected, state, molecule = case
    q = question(CT, state=state, molecule=molecule, calculation_id=selected)
    baseline = project(results)
    permuted_results = tuple(replace(item, observations=tuple(data.draw(
        st.permutations(item.observations), label=f"observations-{item.calculation_id}",
    ))) for item in data.draw(st.permutations(results), label="results"))
    projected = project(permuted_results)
    permuted = replace(projected, facts=tuple(data.draw(st.permutations(projected.facts))),
                       unavailable=tuple(data.draw(st.permutations(projected.unavailable))))
    expected = scientific_signature(audit(q, baseline))
    actual = audit(q, permuted)
    assert scientific_signature(actual) == expected
    assert_used_facts_are_selected(actual)


@PROPERTY_SETTINGS
@given(
    ids=st.lists(IDENTIFIER, min_size=2, max_size=2, unique=True),
    counts=st.lists(st.integers(min_value=2, max_value=20), min_size=2, max_size=2, unique=True),
    data=st.data(),
)
def test_reordering_complete_linked_hessians_cannot_make_them_incomplete(
    ids: list[str], counts: list[int], data: st.DataObject,
) -> None:
    results = tuple(reader_result(calculation_id, (
        *common_observations(), Observation(FactKey.GEOMETRY_CONVERGED, True),
        Observation(FactKey.FREQUENCY_CM1, (-300.0, *((100.0,) * (count - 1)))),
        Observation(FactKey.FREQUENCY_EXPECTED_MODE_COUNT, count),
        Observation(FactKey.IRC_CONNECTS_TWO_MINIMA, True),
    ), source=ids[0] if index else None) for index, (calculation_id, count) in enumerate(
        zip(ids, counts, strict=True),
    ))
    baseline = project(results)
    q = question(TS, molecule="molecule", calculation_id=ids[0])
    before = audit(q, baseline)
    permuted = replace(baseline, facts=tuple(data.draw(st.permutations(baseline.facts))))
    after = audit(q, permuted)
    assert before.execution_status is after.execution_status is ValidationStatus.PASS
    assert before.structure_status is after.structure_status is ValidationStatus.PASS
    assert before.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert scientific_signature(after) == scientific_signature(before)


@PROPERTY_SETTINGS
@given(
    negative=st.integers(min_value=0, max_value=4),
    positive=st.integers(min_value=1, max_value=10),
    magnitude=st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False),
)
def test_actual_parsed_hessian_order_is_independent_of_execution_success(
    negative: int, positive: int, magnitude: float,
) -> None:
    frequencies = (-magnitude,) * negative + (magnitude,) * positive
    text = "\n".join((
        "Program Version 5.0.4", "| 1> ! B3LYP def2-TZVP OPT FREQ",
        "SCF CONVERGED AFTER 14 CYCLES", "VIBRATIONAL FREQUENCIES",
        *(f"{index}: {value:.6f} cm**-1" for index, value in enumerate(frequencies)),
        "THE OPTIMIZATION HAS CONVERGED", "ORCA TERMINATED NORMALLY",
    ))
    parser = OrcaOutputParser()
    with patch.object(Path, "read_text", return_value=text):
        parsed = replace(parser.parse(Path("synthetic/generated-ts.out")), calculation_id="root")
    irc = reader_result("irc", (Observation(FactKey.IRC_CONNECTS_TWO_MINIMA, True),), source="root")
    facts, unavailable = facts_from_parse_results(
        (parsed, irc), supported_keys=parser.supported_keys | {FactKey.IRC_CONNECTS_TWO_MINIMA},
    )
    report = audit(question(TS, molecule="molecule"),
                   EvidenceInventory(facts=facts, unavailable=unavailable))
    assert report.execution_status is ValidationStatus.PASS
    if negative == 1:
        assert report.structure_status is ValidationStatus.PASS
        assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    else:
        assert report.structure_status is ValidationStatus.FAIL
        assert report.overall_evidence_status is AssessmentStatus.CONTRADICTED


@PROPERTY_SETTINGS
@given(case=linked_ct_cases())
def test_truncated_state_lists_do_not_acquire_support_from_their_prefix(
    case: tuple[tuple[ParseResult, ...], str, str, str],
) -> None:
    results, selected, state, molecule = case
    root = replace(results[0], diagnostics=replace(
        results[0].diagnostics, outcome=ParseOutcome.TRUNCATED,
    ))
    report = audit(question(CT, state=state, molecule=molecule, calculation_id=selected),
                   project((root, *results[1:])))
    assert report.execution_status is ValidationStatus.PASS
    assert not report.inventory.evidence_by_type(EvidenceType.EXCITED_STATE_ASSIGNMENT)
    assert not report.inventory.facts_by_key(FactKey.SINGLET_STATE_ENERGY_EV)
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


@PROPERTY_SETTINGS
@given(calculation_id=IDENTIFIER, key=st.sampled_from(list(FactKey)), value=FINITE_NUMBER)
def test_ambiguous_duplicate_facts_are_rejected_before_order_can_choose_a_value(
    calculation_id: str, key: FactKey, value: float,
) -> None:
    first = fact(key, value, calculation_id=calculation_id)
    second = replace(first, id="another-fact-id", value=0.0)
    for facts in ((first, second), (second, first)):
        with pytest.raises(InventoryError, match="unique per calculation and fact key"):
            EvidenceInventory(facts=facts)


@PROPERTY_SETTINGS
@given(value=NONFINITE, as_list=st.booleans(), prefix=st.lists(FINITE_NUMBER, max_size=8))
def test_projection_rejects_nonfinite_scalars_and_list_elements(
    value: float, as_list: bool, prefix: list[float],
) -> None:
    observed: float | tuple[float, ...] = (*prefix, value) if as_list else value
    result = reader_result("root", (
        *common_observations(), Observation(FactKey.SINGLET_STATE_ENERGY_EV, observed),
    ))
    with pytest.raises(ValueError, match="non-finite"):
        project((result,))

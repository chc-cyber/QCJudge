"""An explicit impossible target must not be rescued by an unrelated state count."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from qcjudge.adapters import FORMAT_ID, JsonAnalysisAdapter
from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import EvidenceInventory, ExtractedFact, FactKey
from qcjudge.domain.validation import ValidationStatus
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol
from qcjudge.validators import resolve
from qcjudge.validators.target_state import ct_target_state_exists
from tests.support import CT, converged_calculation, fact, inventory, question
from tests.test_orca_parser import HEADER, SYSTEM, TERMINATION

ONE_STATE_PER_MANIFOLD = (
    "EXCITED STATES (SINGLETS)\nSTATE 1: E= 0.115 au 3.129 eV\n"
    "EXCITED STATES (TRIPLETS)\nSTATE 1: E= 0.112 au 3.048 eV\n"
)


def _context(state: str, *facts: ExtractedFact) -> AuditContext:
    return AuditContext(
        question=question(CT, molecule="molA", state=state),
        protocol=get_protocol(CT),
        inventory=inventory(*facts),
    )


def _manifold(key: FactKey, count: int, calculation_id: str = "calc-1") -> ExtractedFact:
    return replace(
        fact(key, 0, calculation_id=calculation_id),
        value=tuple(float(index + 1) for index in range(count)),
    )


def test_the_target_rule_is_registered() -> None:
    assert resolve("ct_target_state_exists") is ct_target_state_exists


def test_s100_cannot_be_established_by_a_single_reported_state() -> None:
    count = fact(FactKey.EXCITED_STATE_COUNT, 1)
    outcome = ct_target_state_exists(_context("S100", count))

    assert outcome.status is ValidationStatus.FAIL
    assert outcome.fact_ids == (count.id,)


@pytest.mark.parametrize("state", ["S0", "S-1", "T0", "T-2"])
def test_nonpositive_excited_state_indices_are_explicitly_invalid(state: str) -> None:
    outcome = ct_target_state_exists(_context(state))

    assert outcome.status is ValidationStatus.FAIL
    assert "must be positive" in outcome.message


@pytest.mark.parametrize("state", ["S2", "T2"])
def test_combined_counts_cannot_invent_an_index_in_one_manifold(state: str) -> None:
    outcome = ct_target_state_exists(
        _context(
            state,
            _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 1),
            _manifold(FactKey.TRIPLET_STATE_ENERGY_EV, 1),
            fact(FactKey.EXCITED_STATE_COUNT, 2),
        )
    )

    assert outcome.status is ValidationStatus.FAIL
    assert "manifold" in outcome.message


def test_normal_s1_passes_a_bounds_check_without_assigning_identity() -> None:
    outcome = ct_target_state_exists(
        _context("S1", _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 1))
    )

    assert outcome.status is ValidationStatus.PASS
    assert "does not establish scientific target-state identity" in outcome.message


def test_total_count_only_s1_preserves_the_existing_import_path() -> None:
    outcome = ct_target_state_exists(_context("S1", fact(FactKey.EXCITED_STATE_COUNT, 1)))

    assert outcome.status is ValidationStatus.PASS
    assert "does not establish the S manifold's allocation" in outcome.message


def test_a_total_count_must_not_be_treated_as_the_other_manifold_length() -> None:
    outcome = ct_target_state_exists(
        _context(
            "T2",
            _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 3),
            fact(FactKey.EXCITED_STATE_COUNT, 3),
        )
    )

    assert outcome.status is ValidationStatus.PASS
    assert "does not establish the T manifold's allocation" in outcome.message


def test_every_total_count_must_exclude_the_index_before_rejecting_it() -> None:
    first = fact(FactKey.EXCITED_STATE_COUNT, 1)
    second = fact(FactKey.EXCITED_STATE_COUNT, 3, calculation_id="calc-2")

    supported_range = ct_target_state_exists(_context("S2", first, second))
    impossible_range = ct_target_state_exists(_context("S4", first, second))

    assert supported_range.status is ValidationStatus.PASS
    assert impossible_range.status is ValidationStatus.FAIL
    assert impossible_range.fact_ids == (first.id, second.id)


def test_a_longer_provided_manifold_can_contain_the_requested_index() -> None:
    outcome = ct_target_state_exists(
        _context(
            "S2",
            _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 1),
            _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 2, calculation_id="calc-2"),
        )
    )

    assert outcome.status is ValidationStatus.PASS


def test_missing_calculations_are_left_for_requirement_absence_classification() -> None:
    outcome = ct_target_state_exists(_context("S100"))

    assert outcome.status is ValidationStatus.PASS
    assert outcome.fact_ids == ()
    assert "Missing facts are classified by the evidence requirements" in outcome.message


@pytest.mark.parametrize("state", ["CT", "S1/T1", "lowest singlet", "Sfoo"])
def test_unstructured_target_names_are_not_guessed(state: str) -> None:
    outcome = ct_target_state_exists(_context(state, fact(FactKey.EXCITED_STATE_COUNT, 1)))

    assert outcome.status is ValidationStatus.PASS
    assert outcome.fact_ids == ()
    assert "cannot infer state identity" in outcome.message


def test_a_boolean_is_not_a_total_state_count() -> None:
    outcome = ct_target_state_exists(_context("S100", fact(FactKey.EXCITED_STATE_COUNT, True)))

    assert outcome.status is ValidationStatus.PASS
    assert "No target-manifold list or valid total state count" in outcome.message


@pytest.mark.parametrize("state", ["S1", "S100"])
def test_zero_counts_leave_missing_assignment_for_requirements(state: str) -> None:
    zero = fact(FactKey.EXCITED_STATE_COUNT, 0)
    ctx = _context(state, zero)
    outcome = ct_target_state_exists(ctx)

    assert outcome.status is ValidationStatus.PASS
    assert "provide no state assignment" in outcome.message
    assert outcome.fact_ids == (zero.id,)
    assert ctx.inventory.facts == (zero,)


def test_an_empty_manifold_leaves_missing_assignment_for_requirements() -> None:
    empty = _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 0)
    ctx = _context("S100", empty)
    outcome = ct_target_state_exists(ctx)

    assert outcome.status is ValidationStatus.PASS
    assert "provide no state assignment" in outcome.message
    assert outcome.fact_ids == (empty.id,)
    assert ctx.inventory.facts == (empty,)


def test_an_empty_manifold_and_zero_count_remain_an_insufficient_audit() -> None:
    empty = _manifold(FactKey.SINGLET_STATE_ENERGY_EV, 0)
    zero = fact(FactKey.EXCITED_STATE_COUNT, 0)
    supplied = inventory(
        *converged_calculation(),
        empty,
        zero,
        fact(FactKey.HOLE_ELECTRON_D_INDEX, 2.4),
        fact(FactKey.HOLE_ELECTRON_SR_INDEX, 0.3),
    )
    report = audit(question(CT, molecule="molA", state="S1"), supplied)

    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT
    assert report.inventory.facts_by_key(FactKey.SINGLET_STATE_ENERGY_EV) == (empty,)
    assert report.inventory.facts_by_key(FactKey.EXCITED_STATE_COUNT) == (zero,)


@pytest.mark.parametrize(
    ("state", "key"),
    [("S1", FactKey.SINGLET_STATE_ENERGY_EV), ("T1", FactKey.TRIPLET_STATE_ENERGY_EV)],
)
def test_an_explicit_empty_target_manifold_cannot_fall_back_to_a_positive_total(
    state: str, key: FactKey,
) -> None:
    empty = _manifold(key, 0)
    total = fact(FactKey.EXCITED_STATE_COUNT, 1)
    outcome = ct_target_state_exists(_context(state, empty, total))

    assert outcome.status is ValidationStatus.FAIL
    assert outcome.fact_ids == (empty.id, total.id)
    assert "manifold is explicitly empty" in outcome.message


@pytest.mark.parametrize(
    ("state", "target_key", "other_key"),
    [
        ("S1", FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV),
        ("T1", FactKey.TRIPLET_STATE_ENERGY_EV, FactKey.SINGLET_STATE_ENERGY_EV),
    ],
)
def test_the_other_manifold_cannot_rescue_an_empty_target_through_an_audit(
    state: str, target_key: FactKey, other_key: FactKey,
) -> None:
    empty = _manifold(target_key, 0)
    populated = _manifold(other_key, 1)
    supplied = inventory(
        *converged_calculation(),
        empty,
        populated,
        fact(FactKey.EXCITED_STATE_COUNT, 1),
        fact(FactKey.HOLE_ELECTRON_D_INDEX, 2.4),
        fact(FactKey.HOLE_ELECTRON_SR_INDEX, 0.3),
    )
    report = audit(question(CT, molecule="molA", state=state), supplied)

    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.inventory.facts_by_key(target_key) == (empty,)
    target_result = next(
        result for result in report.validation_results if result.rule_id == "method.ct_target_state"
    )
    assert target_result.status is ValidationStatus.FAIL


@pytest.mark.parametrize(
    ("state", "states", "imported_count", "expected"),
    [
        ("S100", "", 1, AssessmentStatus.NOT_ASSESSABLE),
        ("S2", ONE_STATE_PER_MANIFOLD, None, AssessmentStatus.NOT_ASSESSABLE),
        ("S1", ONE_STATE_PER_MANIFOLD, None, AssessmentStatus.SUPPORTED),
        ("S1", "", None, AssessmentStatus.INSUFFICIENT),
        ("S1", "", 1, AssessmentStatus.SUPPORTED),
        ("S1", "", 0, AssessmentStatus.INSUFFICIENT),
        ("S100", "", 0, AssessmentStatus.INSUFFICIENT),
    ],
    ids=[
        "s100", "s2-not-total-two", "normal-s1", "no-state-calculation", "count-only-s1",
        "zero-count-s1", "zero-count-s100",
    ],
)
def test_target_indices_are_checked_through_parse_project_and_audit(
    tmp_path: Path,
    state: str,
    states: str,
    imported_count: int | None,
    expected: AssessmentStatus,
) -> None:
    """A range rejection changes evidence assessability while SCF remains successful."""
    output = tmp_path / "job.out"
    output.write_text(HEADER + SYSTEM + states + TERMINATION, encoding="utf-8")
    parser = OrcaOutputParser()
    primary = parser.parse(output)

    values = {
        "hole_electron.d_index_angstrom": {"value": 2.4, "unit": "angstrom"},
        "hole_electron.sr_index": {"value": 0.3, "unit": "dimensionless"},
    }
    if imported_count is not None:
        values["tddft.state_count"] = {"value": imported_count, "unit": "states"}
    exported = tmp_path / "spatial.json"
    exported.write_text(
        json.dumps(
            {
                "format": FORMAT_ID,
                "producer": "Synthetic external analysis",
                "producer_version": "1",
                "calculations": [
                    {
                        "calculation_id": "spatial-analysis",
                        "source_calculation_id": "calc-1",
                        "values": values,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    imported, carried = JsonAnalysisAdapter().parse_all(exported)
    facts, unavailable = facts_from_parse_results(
        (primary, *imported), supported_keys=parser.supported_keys | carried
    )
    report = audit(
        question(CT, molecule="molA", state=state),
        EvidenceInventory(facts=facts, unavailable=unavailable),
    )

    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is expected
    target_result = next(
        result for result in report.validation_results if result.rule_id == "method.ct_target_state"
    )
    assert target_result.status is (
        ValidationStatus.FAIL
        if expected is AssessmentStatus.NOT_ASSESSABLE
        else ValidationStatus.PASS
    )

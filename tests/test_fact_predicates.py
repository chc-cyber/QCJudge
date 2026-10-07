"""Explicit failed outcomes and empty calculations must not become positive evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qcjudge.adapters import FORMAT_ID, JsonAnalysisAdapter
from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.evidence import (
    EvidenceInventory,
    EvidenceType,
    FactKey,
    FactPredicate,
    FactPredicateOperator,
)
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from tests.support import ct_question, tadf_question, ts_question
from tests.test_adapter import COMPLETE_TADF, COMPLETE_TS


@pytest.mark.parametrize("irc_result", [True, False, None])
def test_irc_value_controls_positive_path_evidence(tmp_path: Path, irc_result: bool | None) -> None:
    source = tmp_path / "ts.out"
    source.write_text(COMPLETE_TS, encoding="utf-8")
    values = {"scf.converged": {"value": True, "unit": "none"}}
    if irc_result is not None:
        values["irc.connects_two_minima"] = {"value": irc_result, "unit": "none"}
    exported = tmp_path / "irc.json"
    exported.write_text(json.dumps({
        "format": FORMAT_ID, "producer": "review-fixture", "producer_version": "1",
        "calculations": [{
            "calculation_id": "irc", "source_calculation_id": "calc-1", "values": values,
        }],
    }), encoding="utf-8")
    parser = OrcaOutputParser()
    results, carried = JsonAnalysisAdapter().parse_all(exported)
    facts, unavailable = facts_from_parse_results(
        (parser.parse(source), *results), supported_keys=parser.supported_keys | carried,
    )
    report = audit(ts_question(), EvidenceInventory(facts=facts, unavailable=unavailable))
    assert report.execution_status.value == "pass"
    assert bool(report.inventory.evidence_by_type(EvidenceType.IRC)) is (irc_result is True)
    if irc_result is True:
        assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    else:
        assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED
    if irc_result is False:
        assert report.inventory.facts_by_key(FactKey.IRC_CONNECTS_TWO_MINIMA)[0].value is False


def test_zero_imported_states_do_not_identify_an_excitation(tmp_path: Path) -> None:
    path = tmp_path / "zero.json"
    path.write_text(json.dumps({
        "format": FORMAT_ID, "producer": "review-fixture", "producer_version": "1",
        "calculations": [{"calculation_id": "zero", "values": {
            "scf.converged": {"value": True, "unit": "none"},
            "tddft.state_count": {"value": 0, "unit": "states"},
            "hole_electron.d_index_angstrom": {"value": 2.4, "unit": "angstrom"},
            "hole_electron.sr_index": {"value": 0.3, "unit": "dimensionless"},
        }}],
    }), encoding="utf-8")
    results, carried = JsonAnalysisAdapter().parse_all(path)
    facts, unavailable = facts_from_parse_results(results, supported_keys=carried)
    report = audit(ct_question(), EvidenceInventory(facts=facts, unavailable=unavailable))
    assert report.inventory.facts_by_key(FactKey.EXCITED_STATE_COUNT)[0].value == 0
    assert not report.inventory.evidence_by_type(EvidenceType.EXCITED_STATE_ASSIGNMENT)
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


@pytest.mark.parametrize("value", [None, False, 0, -1, 0.5, float("inf"), float("nan")])
def test_invalid_counts_do_not_satisfy_the_protocol_predicate(value: object) -> None:
    predicate = FactPredicate(FactKey.EXCITED_STATE_COUNT, FactPredicateOperator.POSITIVE_INTEGER)
    assert not predicate.accepts(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("coupling", [0.0, 12.4, -12.4])
def test_zero_soc_does_not_establish_a_nonzero_channel(tmp_path: Path, coupling: float) -> None:
    source = tmp_path / "tadf.out"
    source.write_text(COMPLETE_TADF, encoding="utf-8")
    path = tmp_path / "soc.json"
    path.write_text(json.dumps({
        "format": FORMAT_ID, "producer": "review-fixture", "producer_version": "1",
        "calculations": [{
            "calculation_id": "soc", "source_calculation_id": "calc-1", "values": {
                "spin_orbit.coupling_cm1": {"value": coupling, "unit": "cm**-1"},
            },
        }],
    }), encoding="utf-8")
    parser = OrcaOutputParser()
    imported, carried = JsonAnalysisAdapter().parse_all(path)
    facts, unavailable = facts_from_parse_results(
        (parser.parse(source), *imported), supported_keys=parser.supported_keys | carried,
    )
    report = audit(tadf_question(), EvidenceInventory(facts=facts, unavailable=unavailable))
    assert report.inventory.facts_by_key(FactKey.SPIN_ORBIT_COUPLING_CM1)[0].value == coupling
    if coupling == 0:
        assert not report.inventory.evidence_by_type(EvidenceType.SPIN_ORBIT_COUPLING)
        assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED
    else:
        assert report.overall_evidence_status is AssessmentStatus.SUPPORTED

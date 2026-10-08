"""Synthetic reader results and semantic report views for generated audit cases.

The reader declares the registered quantities it understands. This lets missing values
exercise evidence gaps without claiming that ORCA can extract adapter-only quantities.
No helper decides whether the generated scientific claim is supported.
"""

from __future__ import annotations

from collections.abc import Sequence

from qcjudge.domain.assessment import EvidenceAssessment
from qcjudge.domain.audit import AuditReport
from qcjudge.domain.calculation import Observation, ParseDiagnostics, ParseOutcome, ParseResult
from qcjudge.domain.evidence import EvidenceInventory, EvidenceOrigin, FactKey
from qcjudge.evidence import facts_from_parse_results
from tests.support import STAMP


def reader_result(
    calculation_id: str,
    observations: Sequence[Observation],
    *,
    source: str | None = None,
    state: str | None = None,
    molecule: str | None = None,
    outcome: ParseOutcome = ParseOutcome.COMPLETE,
) -> ParseResult:
    return ParseResult(
        source_file=f"synthetic/{calculation_id}.out",
        producer="tests.generated_reader",
        producer_version="1",
        extracted_at=STAMP,
        observations=tuple(observations),
        calculation_id=calculation_id,
        source_calculation_id=source,
        state=state,
        molecule=molecule,
        origin=EvidenceOrigin.ADAPTER if source is not None else EvidenceOrigin.PARSED,
        diagnostics=ParseDiagnostics(outcome=outcome),
    )


def project(results: Sequence[ParseResult]) -> EvidenceInventory:
    facts, unavailable = facts_from_parse_results(results, supported_keys=frozenset(FactKey))
    return EvidenceInventory(facts=facts, unavailable=unavailable)


def common_observations(*, converged: bool = True) -> tuple[Observation, ...]:
    return (
        Observation(FactKey.SCF_CONVERGED, converged),
        Observation(FactKey.METHOD_NAME, "B3LYP"),
        Observation(FactKey.BASIS_NAME, "def2-TZVP"),
    )


def spatial_observations(distance: float = 2.4, overlap: float = 0.3) -> tuple[Observation, ...]:
    return (
        Observation(FactKey.HOLE_ELECTRON_D_INDEX, distance, unit="angstrom"),
        Observation(FactKey.HOLE_ELECTRON_SR_INDEX, overlap, unit="dimensionless"),
    )


def requirements(report: AuditReport) -> tuple[EvidenceAssessment, ...]:
    return tuple(
        requirement
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for requirement in claim.requirement_assessments
    )


def scientific_signature(report: AuditReport) -> tuple[object, ...]:
    """Compare scientific decisions and citations, allowing narrative/display order to vary."""
    return (
        report.execution_status,
        report.structure_status,
        report.methodology_status,
        report.overall_evidence_status,
        report.selected_calculation_ids,
        report.association_issue is not None,
        tuple(sorted(
            (item.rule_id, item.scope, item.status) for item in report.validation_results
        )),
        tuple(sorted((item.hypothesis_id, item.status) for item in report.hypothesis_assessments)),
        tuple(sorted(
            (claim.claim_id, claim.status)
            for hypothesis in report.hypothesis_assessments
            for claim in hypothesis.claim_assessments
        )),
        tuple(sorted(
            (
                item.requirement_id,
                item.status,
                tuple(sorted(item.evidence_ids)),
                tuple(sorted(item.blocked_by)),
                tuple(sorted(item.missing_evidence_types)),
                item.expert_review_required,
                item.met_via_alternative,
            )
            for item in requirements(report)
        )),
    )


def assert_used_facts_are_selected(report: AuditReport) -> None:
    """A full report retains unrelated inputs; only citations that support decisions matter."""
    selected = set(report.selected_calculation_ids)
    facts = {item.id: item for item in report.inventory.facts}
    evidence = {item.id: item for item in report.inventory.evidence}
    for assessment in requirements(report):
        for evidence_id in assessment.evidence_ids:
            for fact_id in evidence[evidence_id].fact_ids:
                assert facts[fact_id].subject.calculation_id in selected
    for validation in report.validation_results:
        for fact_id in validation.fact_ids:
            assert facts[fact_id].subject.calculation_id in selected

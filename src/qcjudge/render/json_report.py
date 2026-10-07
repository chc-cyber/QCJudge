"""Stable, machine-readable rendering of an audit report.

This is the contract other tools depend on. Key order is fixed, so two reports produced from
the same inputs differ only in ``generated_at`` and never by accident of dict iteration.
"""

from __future__ import annotations

import json
from typing import Any

from qcjudge.domain.assessment import HypothesisAssessment
from qcjudge.domain.audit import AuditReport
from qcjudge.domain.validation import ValidationResult, ValidationScope

SCHEMA = "qcjudge.audit_report/2"


def _validation(result: ValidationResult) -> dict[str, Any]:
    return {
        "rule_id": result.rule_id,
        "scope": result.scope.value,
        "status": result.status.value,
        "message": result.message,
        "fact_ids": list(result.fact_ids),
    }


def _hypothesis(assessment: HypothesisAssessment) -> dict[str, Any]:
    return {
        "hypothesis_id": assessment.hypothesis_id,
        "statement": assessment.statement,
        "status": assessment.status.value,
        "rationale": assessment.rationale,
        "claims": [
            {
                "claim_id": claim.claim_id,
                "statement": claim.statement,
                "status": claim.status.value,
                "rationale": claim.rationale,
                "requirements": [
                    {
                        "requirement_id": item.requirement_id,
                        "status": item.status.value,
                        "rationale": item.rationale,
                        "evidence_ids": list(item.evidence_ids),
                        "missing_evidence_types": [
                            missing.value for missing in item.missing_evidence_types
                        ],
                        "blocked_by": list(item.blocked_by),
                        "expert_review_required": item.expert_review_required,
                        "met_via_alternative": item.met_via_alternative,
                    }
                    for item in claim.requirement_assessments
                ],
            }
            for claim in assessment.claim_assessments
        ],
    }


def report_to_dict(report: AuditReport) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "tool_version": report.tool_version,
        "generated_at": report.generated_at.isoformat(),
        "audit_scope": {
            "selected_calculation_ids": list(report.selected_calculation_ids),
            "association_issue": report.association_issue,
        },
        "researcher_inputs": {
            "conditions": dict(report.conditions),
            "expert_reviews": [
                {
                    "requirement_id": flag.requirement_id,
                    "reported_condition": flag.reported_condition,
                    "reported_by": flag.reported_by,
                }
                for flag in report.expert_reviews
            ],
        },
        "protocol": {
            "id": report.protocol_id,
            "version": report.protocol_version,
            "max_defensible_claim": report.max_defensible_claim,
            "limitations": list(report.limitations),
            "background": list(report.background),
        },
        "question": {
            "family": report.question.family.value,
            "text": report.question.text,
            "context": {key: value for key, value in report.question.context},
            "assumptions": [item.statement for item in report.question.assumptions],
        },
        "execution": {
            "status": report.execution_status.value,
            "checks": [
                _validation(result)
                for result in report.results_in(ValidationScope.EXECUTION)
            ],
        },
        "structure": {
            "status": report.structure_status.value,
            "checks": [
                _validation(result)
                for result in report.results_in(ValidationScope.STRUCTURE)
            ],
        },
        "methodology": {
            "status": report.methodology_status.value,
            "checks": [
                _validation(result)
                for result in report.results_in(ValidationScope.METHODOLOGY)
            ],
        },
        "evidence": {
            "overall_status": report.overall_evidence_status.value,
            "hypotheses": [
                _hypothesis(assessment) for assessment in report.hypothesis_assessments
            ],
        },
        "recommendations": [
            {
                "id": item.id,
                "action": item.action,
                "rationale": item.rationale,
                "addresses_requirement_ids": list(item.addresses_requirement_ids),
                "priority": item.priority,
            }
            for item in report.recommendations
        ],
        "trace": [
            {"source": edge.source_id, "relation": edge.relation, "target": edge.target_id}
            for edge in report.trace
        ],
        "inventory": {
            "facts": [
                {
                    "id": fact.id,
                    "key": fact.key.value,
                    "value": fact.value,
                    "unit": fact.unit,
                    "subject": {
                        "calculation_id": fact.subject.calculation_id,
                        "state": fact.subject.state,
                        "mode_index": fact.subject.mode_index,
                        "source_calculation_id": fact.subject.source_calculation_id,
                        "molecule": fact.subject.molecule,
                    },
                    "epistemic_kind": fact.epistemic_kind.value,
                    "origin": fact.origin.value,
                    "provenance": {
                        "source_file": fact.provenance.source_file,
                        "producer": fact.provenance.producer,
                        "producer_version": fact.provenance.producer_version,
                        "source_location": fact.provenance.source_location,
                        "extracted_at": fact.provenance.extracted_at.isoformat(),
                    },
                }
                for fact in report.inventory.facts
            ],
            "evidence": [
                {
                    "id": item.id,
                    "evidence_type": item.evidence_type.value,
                    "description": item.description,
                    "fact_ids": list(item.fact_ids),
                    "strength": item.strength.value,
                    "directness": item.directness.value,
                    "origin": item.origin.value,
                    "source_file": (
                        item.provenance.source_file if item.provenance is not None else None
                    ),
                }
                for item in report.inventory.evidence
            ],
            "unavailable": [
                {
                    "key": absent.key.value,
                    "reason": absent.reason.value,
                    "source_file": absent.provenance.source_file,
                    "calculation_id": absent.subject.calculation_id,
                    "source_calculation_id": absent.subject.source_calculation_id,
                    "molecule": absent.subject.molecule,
                    "state": absent.subject.state,
                }
                for absent in report.inventory.unavailable
            ],
        },
        "disclaimer": report.disclaimer,
    }


def to_json(report: AuditReport, *, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent, ensure_ascii=False) + "\n"

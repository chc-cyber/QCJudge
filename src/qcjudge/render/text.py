"""Human-readable rendering of an audit report.

The renderer may only say what the structured report already says. Statuses are printed
verbatim, gaps keep their missing evidence types, and the disclaimer is always emitted, so
prose can never quietly claim more than the audit established.
"""

from __future__ import annotations

from qcjudge.domain.audit import AuditReport
from qcjudge.domain.validation import ValidationScope

_HEADINGS = (
    "QCJudge scientific audit",
    "Question",
    "Execution validity",
    "Structural validation",
    "Methodological checks",
    "Evidence",
    "Overall evidence assessment",
    "Suggested next evidence",
    "Important",
)


def report_to_text(report: AuditReport) -> str:
    lines: list[str] = [f"{_HEADINGS[0]}\n"]
    lines.append(f"{_HEADINGS[1]}\n{report.question.text}")
    context = ", ".join(f"{key}={value}" for key, value in report.question.context)
    if context:
        lines.append(f"context: {context}")
    lines.append(f"protocol: {report.protocol_id} {report.protocol_version}")
    if report.max_defensible_claim:
        lines.append(f"this protocol supports at most: {report.max_defensible_claim}")

    for heading, status, scope in (
        (_HEADINGS[2], report.execution_status, ValidationScope.EXECUTION),
        (_HEADINGS[3], report.structure_status, ValidationScope.STRUCTURE),
        (_HEADINGS[4], report.methodology_status, ValidationScope.METHODOLOGY),
    ):
        results = report.results_in(scope)
        lines.append(f"\n{heading}\n{status.value.upper()}")
        if not results:
            # A scope nobody checked must say so rather than disappear from the report.
            lines.append(f"- no {scope.value} check was declared by this protocol")
            continue
        for result in results:
            lines.append(f"- [{result.status.value.upper()}] {result.message}")

    lines.append(f"\n{_HEADINGS[5]}")
    for hypothesis in report.hypothesis_assessments:
        lines.append(f"\nHypothesis [{hypothesis.status.value.upper()}] {hypothesis.statement}")
        for claim in hypothesis.claim_assessments:
            lines.append(f"  Claim [{claim.status.value.upper()}] {claim.statement}")
            for item in claim.requirement_assessments:
                lines.append(
                    f"    [{item.status.value.upper()}] {item.requirement_id}: {item.rationale}"
                )
                if item.missing_evidence_types:
                    missing = ", ".join(kind.value for kind in item.missing_evidence_types)
                    lines.append(f"      missing: {missing}")
                if item.met_via_alternative:
                    lines.append(f"      met via alternative: {item.met_via_alternative}")

    lines.append(
        f"\n{_HEADINGS[6]}\n{report.overall_evidence_status.value.upper()}"
    )
    for recommendation in report.recommendations:
        lines.append(f"\n{_HEADINGS[7]}\n{recommendation.action}")
        lines.append(f"why: {recommendation.rationale}")
    if report.limitations:
        lines.append("\nWhat this protocol cannot establish")
        for limitation in report.limitations:
            lines.append(f"- {limitation}")
    lines.append(f"\n{_HEADINGS[8]}\n{report.disclaimer}")
    return "\n".join(lines) + "\n"

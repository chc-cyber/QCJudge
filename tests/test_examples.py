"""The worked examples must keep producing the verdicts their READMEs document.

These are the project's public illustrations of its central claim, so a change that silently
turns one of them into a different verdict would make the documentation wrong while every other
test stayed green. Each example needs no temporary directory and no fetched corpus, so this runs
in any environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.context import ExpertReviewFlag
from qcjudge.domain.evidence import EvidenceInventory, FactKey
from qcjudge.domain.question import Hypothesis, QuestionFamily, ResearchQuestion
from qcjudge.domain.validation import ValidationStatus
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CT_ANALYSIS_EXAMPLE = "04-charge-transfer-analysis"

# example directory, family, question, expected axes and overall status
CASES: tuple[tuple[str, QuestionFamily, str, str, str, str], ...] = (
    (
        "01-transition-state-mode-identity",
        QuestionFamily.TRANSITION_STATE_VALIDATION,
        "Is this structure the transition state for the C-C rotation step?",
        "pass",
        "pass",
        "partially_supported",
    ),
    (
        "02-converged-minimum-is-not-a-saddle",
        QuestionFamily.TRANSITION_STATE_VALIDATION,
        "Is this structure a saddle point for the proposed step?",
        "pass",
        "fail",
        "contradicted",
    ),
    (
        "03-tadf-gap-is-not-a-risc-channel",
        QuestionFamily.TADF_POTENTIAL,
        "Is the singlet-triplet gap small enough for this molecule to show TADF?",
        "pass",
        "unknown",
        "partially_supported",
    ),
)


def _audit_example(
    name: str,
    family: QuestionFamily,
    question_text: str,
    *,
    expert_reviews: tuple[ExpertReviewFlag, ...] = (),
):
    path = EXAMPLES / name / "job.out"
    parser = OrcaOutputParser()
    result = parser.parse(path)
    facts, absences = facts_from_parse_results(
        (result,), supported_keys=parser.supported_keys
    )
    protocol = get_protocol(family)
    question = ResearchQuestion(
        family=family,
        text=question_text,
        hypotheses=tuple(
            Hypothesis(item.id, item.statement) for item in protocol.hypotheses
        ),
        context=(("molecule", "dvb"),),
    )
    return result, audit(
        question,
        EvidenceInventory(facts=facts, unavailable=absences),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        expert_reviews=expert_reviews,
    )


@pytest.mark.parametrize("name", [*(case[0] for case in CASES), CT_ANALYSIS_EXAMPLE])
def test_every_example_ships_an_input_file(name: str) -> None:
    assert (EXAMPLES / name / "job.out").exists()
    assert (EXAMPLES / name / "README.md").exists()


@pytest.mark.parametrize(
    ("name", "family", "question_text", "execution", "structure", "overall"), CASES
)
def test_the_example_produces_the_verdict_its_readme_documents(
    name: str,
    family: QuestionFamily,
    question_text: str,
    execution: str,
    structure: str,
    overall: str,
) -> None:
    result, report = _audit_example(name, family, question_text)

    assert result.diagnostics.outcome.value == "complete", name
    assert report.execution_status.value == execution, name
    assert report.structure_status.value == structure, name
    assert report.overall_evidence_status.value == overall, name


def test_the_first_example_has_exactly_one_imaginary_mode() -> None:
    """The whole point of example 1 is a first-order saddle point."""
    _result, report = _audit_example(*CASES[0][:3])

    assert report.execution_status is ValidationStatus.PASS
    assert report.structure_status is ValidationStatus.PASS
    facts = report.inventory.facts_by_key(FactKey.FREQUENCY_IMAGINARY_COUNT)
    assert facts and facts[0].value == 1


def test_the_second_example_succeeds_as_a_calculation_while_refuting_the_claim() -> None:
    """The defining separation: a converged minimum is a successful job, not a saddle point."""
    _result, report = _audit_example(*CASES[1][:3])

    assert report.execution_status is ValidationStatus.PASS
    assert report.structure_status is ValidationStatus.FAIL
    assert report.overall_evidence_status is AssessmentStatus.CONTRADICTED


def test_the_third_example_is_capped_by_design() -> None:
    """However small the gap, gap-only evidence cannot exceed partial support."""
    _result, report = _audit_example(*CASES[2][:3])

    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED
    requirement_status = {
        assessment.requirement_id: assessment.status
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for assessment in claim.requirement_assessments
    }
    assert requirement_status["tadf.singlet_triplet_states"] is AssessmentStatus.SUPPORTED
    assert requirement_status["tadf.risc_coupling"] is AssessmentStatus.INSUFFICIENT


def test_parser_only_examples_do_not_claim_full_support() -> None:
    """These examples lack the external analyses needed for their required evidence."""
    for name, family, question_text, *_expected in CASES:
        _result, report = _audit_example(name, family, question_text)
        assert report.overall_evidence_status is not AssessmentStatus.SUPPORTED, name


def test_the_documented_expert_review_command_works() -> None:
    """The README tells a reader to run this, so it must do what it says."""
    _result, report = _audit_example(
        *CASES[0][:3],
        expert_reviews=(
            ExpertReviewFlag(
                "ts.mode_identity", "the imaginary mode mixes rotation with bending"
            ),
        ),
    )

    assert report.overall_evidence_status is AssessmentStatus.REQUIRES_EXPERT_REVIEW
    flagged = [
        assessment
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for assessment in claim.requirement_assessments
        if assessment.requirement_id == "ts.mode_identity"
    ]
    assert flagged and flagged[0].expert_review_required
    assert "mixes rotation with bending" in flagged[0].rationale


@pytest.mark.parametrize(
    ("with_analysis", "expected"),
    [(True, "supported"), (False, "insufficient")],
    ids=["linked-analysis", "calculation-only"],
)
def test_the_charge_transfer_example_runs_through_the_actual_cli(
    with_analysis: bool, expected: str
) -> None:
    """The documented import supplies the missing coverage without changing execution."""
    root = EXAMPLES.parent
    example = EXAMPLES / CT_ANALYSIS_EXAMPLE
    argv = [
        sys.executable,
        "-m",
        "qcjudge.cli.main",
        "audit",
        "--question",
        "ct_excitation",
        "--input",
        str(example / "job.out"),
        "--context",
        "molecule=demo-ct",
        "--context",
        "state=S1",
        "--format",
        "json",
    ]
    if with_analysis:
        argv.extend(["--analysis", str(example / "analysis.json")])
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{root / 'src'}{os.pathsep}{existing}" if existing else str(root / "src")
    )
    completed = subprocess.run(
        argv,
        cwd=root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)
    assert document["execution"]["status"] == "pass"
    assert document["evidence"]["overall_status"] == expected
    assert document["audit_scope"]["association_issue"] is None
    assert document["question"]["context"] == {"molecule": "demo-ct", "state": "S1"}
    expected_ids = ["calc-1", "demo-ct-s1-hole-electron"] if with_analysis else ["calc-1"]
    assert document["audit_scope"]["selected_calculation_ids"] == expected_ids
    adapted = [fact for fact in document["inventory"]["facts"] if fact["origin"] == "adapter"]
    if with_analysis:
        assert {fact["key"] for fact in adapted} == {
            "hole_electron.d_index_angstrom", "hole_electron.sr_index"
        }
        assert all(
            fact["provenance"]["producer"] == "qcjudge.adapter.synthetic-demo"
            and fact["subject"]["calculation_id"] == "demo-ct-s1-hole-electron"
            and fact["subject"]["source_calculation_id"] == "calc-1"
            and fact["subject"]["molecule"] == "demo-ct"
            and fact["subject"]["state"] == "S1"
            for fact in adapted
        )
    else:
        assert adapted == []

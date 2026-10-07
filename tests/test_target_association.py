"""A calculation may support only the question and analyses explicitly associated with it.

Run actual ORCA parsing and JSON imports through projection and audit. A hand-built inventory
would miss the boundaries where calculation identity or subject metadata can be lost.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from qcjudge.adapters import FORMAT_ID, JsonAnalysisAdapter
from qcjudge.audit import audit
from qcjudge.cli.main import main
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.audit import AuditReport
from qcjudge.domain.context import ExpertReviewFlag
from qcjudge.domain.evidence import EvidenceInventory, EvidenceOrigin, EvidenceType, FactKey
from qcjudge.domain.question import QuestionFamily, ResearchQuestion
from qcjudge.domain.validation import ValidationStatus
from qcjudge.errors import InventoryError
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol
from qcjudge.render import to_json

ORCA_OUTPUT = """\
                  *****************
                  * O   R   C   A *
                  *****************

Program Version 5.0.4 - RELEASE

------------------
INPUT FILE
------------------
|  1> ! B3LYP def2-TZVP
|  2> * xyz 0 1
|  3> C 0 0 0
|  4> *
|  5>

Total Charge    Charge    0
Multiplicity    Mult    1

SCF CONVERGED AFTER  11 CYCLES

------------------------------------
TD-DFT/TDA EXCITED STATES (SINGLETS)
------------------------------------
STATE  1:  E=   0.115000 au      3.129 eV    25235.0 cm**-1

ORCA TERMINATED NORMALLY
"""

DESCRIPTORS = {
    "hole_electron.d_index_angstrom": {"value": 2.41, "unit": "angstrom"},
    "hole_electron.sr_index": {"value": 0.31, "unit": "dimensionless"},
}


def _question(target: str | None = None) -> ResearchQuestion:
    protocol = get_protocol(QuestionFamily.CHARGE_TRANSFER_EXCITATION)
    context = (("molecule", "dvb"), ("state", "S1"))
    if target is not None:
        context = (*context, ("calculation_id", target))
    return ResearchQuestion(
        family=protocol.question_family,
        text="Does the S1 excitation of dvb redistribute charge?",
        hypotheses=protocol.hypotheses,
        context=context,
    )


def _output(tmp_path: Path, name: str, *, converged: bool = True) -> Path:
    path = tmp_path / f"{name}.out"
    text = ORCA_OUTPUT
    if not converged:
        text = text.replace("SCF CONVERGED AFTER  11 CYCLES", "SCF NOT CONVERGED")
    path.write_text(text, encoding="utf-8")
    return path


def _analysis(
    calculation_id: str = "descriptor",
    source: str | None = "A",
    **metadata: str,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "calculation_id": calculation_id,
        "molecule": "dvb",
        "state": "S1",
        "values": DESCRIPTORS,
    }
    if source is not None:
        entry["source_calculation_id"] = source
    entry.update(metadata)
    return entry


def _export(tmp_path: Path, entries: Sequence[dict[str, object]]) -> Path:
    path = tmp_path / "analyses.json"
    path.write_text(
        json.dumps(
            {
                "format": FORMAT_ID,
                "producer": "Multiwfn",
                "producer_version": "3.8",
                "calculations": list(entries),
            }
        ),
        encoding="utf-8",
    )
    return path


def _inventory(
    tmp_path: Path,
    entries: Sequence[dict[str, object]],
    *,
    sources: tuple[str, ...] = ("A",),
    failing: tuple[str, ...] = (),
) -> EvidenceInventory:
    parser = OrcaOutputParser()
    # ORCA output does not name an audit ID. Assign a stable ID to the reader result, without
    # modifying any observation, exactly as a caller may name an imported calculation.
    results = [
        replace(
            parser.parse(_output(tmp_path, source, converged=source not in failing)),
            calculation_id=source,
        )
        for source in sources
    ]
    supported = set(parser.supported_keys)
    if entries:
        imported, carried = JsonAnalysisAdapter().parse_all(_export(tmp_path, entries))
        results.extend(imported)
        supported.update(carried)
    facts, unavailable = facts_from_parse_results(results, supported_keys=frozenset(supported))
    return EvidenceInventory(facts=facts, unavailable=unavailable)


def _assessments(report: AuditReport) -> dict[str, AssessmentStatus]:
    return {
        assessment.requirement_id: assessment.status
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for assessment in claim.requirement_assessments
    }


def test_unlinked_states_and_descriptors_cannot_support_one_target(tmp_path: Path) -> None:
    report = audit(_question(), _inventory(tmp_path, [_analysis("B", source=None)]))

    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert "unassociated" in report.association_issue
    assert set(_assessments(report).values()) == {AssessmentStatus.NOT_ASSESSABLE}


def test_linked_analysis_supports_the_target_without_merging_provenance(tmp_path: Path) -> None:
    report = audit(_question(), _inventory(tmp_path, [_analysis()]))

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert report.association_issue is None
    assert report.selected_calculation_ids == ("A", "descriptor")
    assert {fact.origin for fact in report.inventory.facts} == {
        EvidenceOrigin.PARSED,
        EvidenceOrigin.ADAPTER,
    }
    imported = report.inventory.facts_by_key(FactKey.HOLE_ELECTRON_D_INDEX)[0]
    assert imported.subject.calculation_id == "descriptor"
    assert imported.subject.source_calculation_id == "A"
    assert imported.subject.molecule == "dvb"
    assert imported.subject.state == "S1"


@pytest.mark.parametrize("name,value", [("molecule", "other-molecule"), ("state", "S2")])
def test_an_explicit_subject_conflicting_with_the_question_is_unassessable(
    tmp_path: Path, name: str, value: str
) -> None:
    report = audit(_question(), _inventory(tmp_path, [_analysis(**{name: value})]))

    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert name in report.association_issue
    assert value in report.association_issue


def test_explicit_selection_excludes_unrelated_failed_scf_and_retains_full_inventory(
    tmp_path: Path,
) -> None:
    inventory = _inventory(tmp_path, [_analysis()], sources=("A", "B"), failing=("B",))
    report = audit(_question("A"), inventory)

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert report.execution_status is ValidationStatus.PASS
    assert report.selected_calculation_ids == ("A", "descriptor")
    assert report.association_issue is None
    assert any(
        fact.subject.calculation_id == "B" and fact.value is False
        for fact in report.inventory.facts_by_key(FactKey.SCF_CONVERGED)
    )
    assert not any(
        fact_id.startswith("B:")
        for validation in report.validation_results
        for fact_id in validation.fact_ids
    )
    assert report.inventory.facts == inventory.facts
    assert report.inventory.unavailable == inventory.unavailable
    document = json.loads(to_json(report))
    assert document["audit_scope"] == {
        "selected_calculation_ids": ["A", "descriptor"],
        "association_issue": None,
    }
    assert "B" in {
        fact["subject"]["calculation_id"] for fact in document["inventory"]["facts"]
    }


def test_selecting_a_target_does_not_assign_an_unlinked_descriptor_to_it(tmp_path: Path) -> None:
    report = audit(_question("A"), _inventory(tmp_path, [_analysis("B", source=None)]))

    assert report.association_issue is None
    assert report.selected_calculation_ids == ("A",)
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT
    assert _assessments(report)["ct.spatial_redistribution"] is AssessmentStatus.INSUFFICIENT


def test_selecting_a_linked_analysis_selects_its_source_group(tmp_path: Path) -> None:
    report = audit(_question("descriptor"), _inventory(tmp_path, [_analysis()]))

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert report.selected_calculation_ids == ("A", "descriptor")


def test_unrelated_subject_conflicts_do_not_contaminate_an_explicit_target(tmp_path: Path) -> None:
    unrelated = _analysis("B", source=None, molecule="other-molecule", state="S2")
    report = audit(_question("A"), _inventory(tmp_path, [_analysis(), unrelated]))

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert report.selected_calculation_ids == ("A", "descriptor")
    assert report.association_issue is None


def test_an_unknown_target_is_reported_without_using_an_available_one(tmp_path: Path) -> None:
    report = audit(_question("missing"), _inventory(tmp_path, [_analysis()]))

    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert "missing" in report.association_issue
    assert "not supplied" in report.association_issue


def test_a_missing_source_link_has_a_diagnostic(tmp_path: Path) -> None:
    report = audit(_question(), _inventory(tmp_path, [_analysis(source="missing-source")]))

    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert "missing-source" in report.association_issue
    assert "not supplied" in report.association_issue


@pytest.mark.parametrize("cycle", ["self", "two-results"])
def test_source_link_cycles_are_unassessable(tmp_path: Path, cycle: str) -> None:
    entries = [_analysis("B", source="B")]
    if cycle == "two-results":
        entries = [_analysis("B", source="C"), _analysis("C", source="B")]
    report = audit(_question(), _inventory(tmp_path, entries))

    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert "cycle" in report.association_issue


def test_conflicting_links_on_one_subject_are_unassessable(tmp_path: Path) -> None:
    inventory = _inventory(tmp_path, [_analysis()])
    descriptor = inventory.facts_by_key(FactKey.HOLE_ELECTRON_D_INDEX)[0]
    conflicting = replace(
        descriptor, subject=replace(descriptor.subject, source_calculation_id="B")
    )
    inventory = replace(
        inventory,
        facts=tuple(conflicting if fact.id == descriptor.id else fact for fact in inventory.facts),
    )
    report = audit(_question(), inventory)

    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE
    assert report.association_issue is not None
    assert "Conflicting source links" in report.association_issue


def test_multiple_linked_analyses_keep_separate_ids_and_can_support_one_target(
    tmp_path: Path,
) -> None:
    nto = _analysis("nto", source="A")
    nto["values"] = {"nto.dominant_pair_contribution": {"value": 0.91, "unit": "none"}}
    report = audit(_question(), _inventory(tmp_path, [_analysis(source="nto"), nto]))

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert report.selected_calculation_ids == ("A", "descriptor", "nto")
    assert len(report.inventory.evidence_by_type(EvidenceType.HOLE_ELECTRON_ANALYSIS)) == 1
    assert len(report.inventory.evidence_by_type(EvidenceType.NTO_ANALYSIS)) == 1


def test_an_analysis_cannot_replace_its_source_by_reusing_the_calculation_id(
    tmp_path: Path,
) -> None:
    with pytest.raises(InventoryError, match="source_calculation_id"):
        _inventory(tmp_path, [_analysis("A", source=None)])


def test_unused_researcher_conditions_survive_the_json_report(tmp_path: Path) -> None:
    conditions = {"partition_note": "Left fragment is the donor", "lab_note": "Checked twice"}
    report = audit(_question(), _inventory(tmp_path, [_analysis()]), conditions=conditions)
    document = json.loads(to_json(report))

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert dict(report.conditions) == conditions
    assert document["schema"] == "qcjudge.audit_report/2"
    assert document["protocol"]["version"] == "1.1.0"
    assert document["researcher_inputs"]["conditions"] == conditions


@pytest.mark.parametrize(
    "source,expected",
    [
        ("A", AssessmentStatus.REQUIRES_EXPERT_REVIEW),
        (None, AssessmentStatus.NOT_ASSESSABLE),
    ],
    ids=["associated", "unassociated"],
)
def test_expert_review_inputs_survive_json_without_overriding_association(
    tmp_path: Path, source: str | None, expected: AssessmentStatus,
) -> None:
    flag = ExpertReviewFlag("ct.spatial_redistribution", "Partition is ambiguous", "Researcher")
    report = audit(
        _question(),
        _inventory(tmp_path, [_analysis("B", source=source)]),
        expert_reviews=(flag,),
    )
    document = json.loads(to_json(report))

    assert report.overall_evidence_status is expected
    assert report.expert_reviews == (flag,)
    assert document["researcher_inputs"]["expert_reviews"] == [
        {
            "requirement_id": "ct.spatial_redistribution",
            "reported_condition": "Partition is ambiguous",
            "reported_by": "Researcher",
        }
    ]


@pytest.mark.parametrize(
    "selector", [["--target", "calc-2"], ["--context", "calculation_id=calc-2"]]
)
def test_cli_target_and_context_select_the_same_group(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], selector: list[str]
) -> None:
    _output(tmp_path, "A", converged=False)
    _output(tmp_path, "B")
    exported = _export(tmp_path, [_analysis(source="calc-2")])
    result = main(
        [
            "audit", "--question", "ct_excitation", "--input", str(tmp_path),
            "--analysis", str(exported), "--context", "molecule=dvb", "--context", "state=S1",
            "--format", "json", *selector,
        ]
    )
    captured = capsys.readouterr()
    document = json.loads(captured.out)

    assert result == 0
    assert document["execution"]["status"] == "pass"
    assert document["evidence"]["overall_status"] == "supported"
    assert document["audit_scope"]["selected_calculation_ids"] == ["calc-2", "descriptor"]
    assert document["question"]["context"]["calculation_id"] == "calc-2"


def test_cli_refuses_conflicting_target_selectors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _output(tmp_path, "A")
    result = main(
        [
            "audit", "--question", "ct_excitation", "--input", str(source),
            "--context", "molecule=dvb", "--context", "state=S1",
            "--context", "calculation_id=calc-2",
            "--target", "calc-1", "--format", "json",
        ]
    )
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert "conflict" in captured.err.lower()

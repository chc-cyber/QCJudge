"""Importing an external analysis: what it carries, and what it refuses to carry.

These tests exist because the seam is the boundary where a number computed by something else
enters an audit. Everything that could make an imported value indistinguishable from a parsed
one is a defect here, so most of this file is about refusal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qcjudge.adapters import ADAPTER_PRODUCER_PREFIX, FORMAT_ID, JsonAnalysisAdapter
from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.evidence import EvidenceInventory, EvidenceOrigin, FactKey
from qcjudge.domain.question import Hypothesis, QuestionFamily, ResearchQuestion
from qcjudge.errors import (
    AdapterFormatError,
    UnknownExportedQuantityError,
    WrongUnitError,
)
from qcjudge.evidence import facts_from_parse_results
from qcjudge.protocols import get_protocol

ADAPTER = JsonAnalysisAdapter()

# A quantity that is a registered fact key but which this seam cannot carry. Imported values are
# numeric descriptions of an analysis; a method name is a string read from a calculation's input
# echo, and letting it in would make an import a way to assert anything about the calculation.
UNSUPPORTED_BUT_REGISTERED = "method.name"


def _export(
    tmp_path: Path,
    *,
    name: str = "analysis.json",
    producer: object = "Multiwfn",
    producer_version: object = "3.8",
    calculations: object = None,
    **extra: Any,
) -> Path:
    document: dict[str, Any] = {
        "format": FORMAT_ID,
        "analysis": "hole_electron",
        "producer": producer,
        "producer_version": producer_version,
        "source_file": "dvb_s1_hole_electron.txt",
        "calculations": calculations
        if calculations is not None
        else [
            {
                "calculation_id": "dvb-s1",
                "values": {
                    "scf.converged": {"value": True, "unit": "none"},
                    "tddft.state_count": {"value": 5, "unit": "states"},
                    "hole_electron.d_index_angstrom": {"value": 2.41, "unit": "angstrom"},
                    "hole_electron.sr_index": {"value": 0.31, "unit": "dimensionless"},
                },
            }
        ],
    }
    document.update(extra)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _ct_question() -> ResearchQuestion:
    protocol = get_protocol(QuestionFamily.CHARGE_TRANSFER_EXCITATION)
    return ResearchQuestion(
        family=QuestionFamily.CHARGE_TRANSFER_EXCITATION,
        text="Does the target excitation move charge from donor to acceptor?",
        hypotheses=tuple(
            Hypothesis(item.id, item.statement) for item in protocol.hypotheses
        ),
        context=(("molecule", "dvb"), ("state", "S1")),
    )


def _project(results, supported: frozenset[FactKey]) -> EvidenceInventory:
    facts, absences = facts_from_parse_results(results, supported_keys=supported)
    return EvidenceInventory(facts=facts, unavailable=absences)


# -- what a good import gives the audit ------------------------------------------------------


def test_an_imported_value_becomes_a_fact_with_adapter_provenance(tmp_path: Path) -> None:
    """The whole point: a number from elsewhere is attributed to the tool that computed it."""
    results, carried = ADAPTER.parse_all(_export(tmp_path))
    inventory = _project(results, carried)
    values = {fact.key: fact for fact in inventory.facts}

    assert FactKey.HOLE_ELECTRON_D_INDEX in values
    fact = values[FactKey.HOLE_ELECTRON_D_INDEX]
    assert fact.value == 2.41
    assert fact.origin is EvidenceOrigin.ADAPTER
    assert fact.provenance.producer == f"{ADAPTER_PRODUCER_PREFIX}Multiwfn"
    assert fact.provenance.producer_version == "3.8"
    assert fact.provenance.source_file == "dvb_s1_hole_electron.txt"


def test_evidence_derived_from_an_import_is_attributed_to_the_adapter(tmp_path: Path) -> None:
    """Otherwise an imported descriptor would be reported as something the calculation said."""
    results, carried = ADAPTER.parse_all(_export(tmp_path))
    report = audit(_ct_question(), _project(results, carried))
    derived = [
        item for item in report.inventory.evidence if "hole_electron" in item.id
    ]

    assert derived, "the hole-electron derivation should have fired"
    assert all(item.origin is EvidenceOrigin.ADAPTER for item in derived)


def test_an_import_can_supply_what_the_calculation_did_not(tmp_path: Path) -> None:
    """The reason the seam exists: the spatial claim was unreachable without it."""
    results, carried = ADAPTER.parse_all(_export(tmp_path))
    report = audit(_ct_question(), _project(results, carried))
    statuses = {
        assessment.requirement_id: assessment.status
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for assessment in claim.requirement_assessments
    }

    assert statuses["ct.spatial_redistribution"] is AssessmentStatus.SUPPORTED


def test_an_import_only_declares_the_quantities_it_carried(tmp_path: Path) -> None:
    """A file with three descriptors has not failed to carry a fourth."""
    _results, carried = ADAPTER.parse_all(_export(tmp_path))

    assert FactKey.HOLE_ELECTRON_D_INDEX in carried
    assert FactKey.HOLE_ELECTRON_LAMBDA_ANGSTROM not in carried
    assert FactKey.SPIN_ORBIT_COUPLING_CM1 not in carried


def test_several_calculations_stay_separate(tmp_path: Path) -> None:
    """One calculation's descriptor must not answer a claim about another."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "first",
                "values": {"hole_electron.sr_index": {"value": 0.1, "unit": "none"}},
            },
            {
                "calculation_id": "second",
                "values": {"hole_electron.sr_index": {"value": 0.9, "unit": "none"}},
            },
        ],
    )
    results, carried = ADAPTER.parse_all(path)
    inventory = _project(results, carried)
    subjects = {fact.subject.calculation_id for fact in inventory.facts}

    assert subjects == {"first", "second"}
    assert len(inventory.facts) == 2


def test_an_exact_unit_equivalence_is_converted(tmp_path: Path) -> None:
    """Bohr to angstrom is exact arithmetic, so it needs no judgement."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {
                    "hole_electron.d_index_angstrom": {"value": 4.5547, "unit": "bohr"}
                },
            }
        ],
    )
    results, _carried = ADAPTER.parse_all(path)
    observation = results[0].observations[0]

    assert observation.value == pytest.approx(2.41024, abs=1e-4)
    assert observation.unit == "angstrom"


# -- what it refuses ---------------------------------------------------------------------------


def test_a_value_in_an_unexpected_unit_is_refused(tmp_path: Path) -> None:
    """A value in the wrong unit looks like an answer, which is worse than a missing one."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {
                    "hole_electron.d_index_angstrom": {"value": 4.55, "unit": "nanometer"}
                },
            }
        ],
    )

    with pytest.raises(WrongUnitError, match="nanometer"):
        ADAPTER.parse_all(path)


def test_a_value_with_no_unit_is_refused(tmp_path: Path) -> None:
    """Silence about the unit is not permission to assume one."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {"hole_electron.d_index_angstrom": {"value": 2.41}},
            }
        ],
    )

    with pytest.raises(AdapterFormatError, match="states no unit"):
        ADAPTER.parse_all(path)


def test_an_unregistered_quantity_is_refused(tmp_path: Path) -> None:
    """A typo must not become silently missing evidence."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {"hole_electron.d_index": {"value": 1.0, "unit": "angstrom"}},
            }
        ],
    )

    with pytest.raises(UnknownExportedQuantityError, match="unknown quantity"):
        ADAPTER.parse_all(path)


def test_the_refusal_lists_what_the_seam_does_carry(tmp_path: Path) -> None:
    """An export is written by hand or by a small script, so name what it should have written."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {"hole_electron.d_index": {"value": 1.0, "unit": "angstrom"}},
            }
        ],
    )

    with pytest.raises(UnknownExportedQuantityError) as raised:
        ADAPTER.parse_all(path)

    message = str(raised.value)
    assert "hole_electron.d_index_angstrom" in message
    assert "spin_orbit.coupling_cm1" in message
    assert raised.value.quantity == "hole_electron.d_index"


def test_the_listed_quantities_are_exactly_the_ones_accepted() -> None:
    """The message is generated from the same set the reader enforces, not a copy of it."""
    from qcjudge.adapters.json_analysis import _ACCEPTED_NAMES

    assert set(_ACCEPTED_NAMES) == {key.value for key in ADAPTER.supported_keys}
    assert list(_ACCEPTED_NAMES) == sorted(_ACCEPTED_NAMES)


def test_a_registered_but_unsupported_quantity_is_refused(tmp_path: Path) -> None:
    """A fact key existing is not the same as this seam being able to carry it."""
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {
                    UNSUPPORTED_BUT_REGISTERED: {"value": 1.0, "unit": "none"}
                },
            }
        ],
    )

    with pytest.raises(UnknownExportedQuantityError):
        ADAPTER.parse_all(path)


def test_a_non_numeric_value_is_refused(tmp_path: Path) -> None:
    path = _export(
        tmp_path,
        calculations=[
            {
                "calculation_id": "x",
                "values": {
                    "hole_electron.sr_index": {"value": "about a third", "unit": "none"}
                },
            }
        ],
    )

    with pytest.raises(AdapterFormatError, match="must be a number"):
        ADAPTER.parse_all(path)


@pytest.mark.parametrize("missing", ["producer", "producer_version"])
def test_an_unattributable_import_is_refused(tmp_path: Path, missing: str) -> None:
    """Attribution is the point of the seam, so it is required rather than defaulted."""
    path = _export(tmp_path, **{missing: None})

    with pytest.raises(AdapterFormatError, match="producer"):
        ADAPTER.parse_all(path)


def test_a_wrong_format_version_is_refused(tmp_path: Path) -> None:
    """The version is checked so a future format cannot be read as if it were this one."""
    path = _export(tmp_path, format="qcjudge.analysis_import/99")

    with pytest.raises(AdapterFormatError, match="declares format"):
        ADAPTER.parse_all(path)


def test_an_import_with_no_calculations_is_refused(tmp_path: Path) -> None:
    path = _export(tmp_path, calculations=[])

    with pytest.raises(AdapterFormatError, match="no calculations"):
        ADAPTER.parse_all(path)


def test_a_calculation_with_no_values_is_refused(tmp_path: Path) -> None:
    path = _export(tmp_path, calculations=[{"calculation_id": "x", "values": {}}])

    with pytest.raises(AdapterFormatError, match="no values"):
        ADAPTER.parse_all(path)


def test_invalid_json_is_refused_with_the_path(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(AdapterFormatError, match="not valid JSON"):
        ADAPTER.parse_all(path)


def test_a_non_object_document_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(AdapterFormatError, match="JSON object"):
        ADAPTER.parse_all(path)


# -- the seam does not judge -------------------------------------------------------------------


def test_the_adapter_does_not_choose_evidence_strength(tmp_path: Path) -> None:
    """Strength is a protocol declaration; a reader decides nothing about it.

    Asserted structurally: the adapter produces observations, and an observation has no strength
    field to set. This test fails if that ever changes.
    """
    import dataclasses

    results, _carried = ADAPTER.parse_all(_export(tmp_path))
    observation = results[0].observations[0]
    names = {field.name for field in dataclasses.fields(observation)}

    assert names == {"key", "value", "unit", "location"}
    assert not any("strength" in name or "directness" in name for name in names)


def test_the_adapter_declares_the_same_contract_as_a_parser() -> None:
    """Which is what lets projection and provenance work unchanged for both."""
    from qcjudge.parsers.orca import OrcaOutputParser

    for reader in (ADAPTER, OrcaOutputParser()):
        assert isinstance(reader.name, str)
        assert isinstance(reader.version, str)
        assert reader.supported_keys
        assert callable(reader.parse)


# -- what the seam exists for: the families become answerable --------------------------------

COMPLETE_TS = """\
                  *****************
                  * O   R   C   A *
                  *****************

Program Version 5.0.4 - RELEASE

------------------
INPUT FILE
------------------
|  1> ! B3LYP def2-TZVP OPT FREQ
|  2> * xyz 0 1
|  3> C 0 0 0
|  4> *
|  5>

Total Charge    Charge    0
Multiplicity    Mult    1

SCF CONVERGED AFTER  14 CYCLES

------------------------------
VIBRATIONAL FREQUENCIES
------------------------------
   0:       0.00 cm**-1
   1:     -412.57 cm**-1
   2:     190.35 cm**-1

THE OPTIMIZATION HAS CONVERGED

ORCA TERMINATED NORMALLY
"""

COMPLETE_TADF = """\
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

------------------------------------
TD-DFT/TDA EXCITED STATES (TRIPLETS)
------------------------------------
STATE  1:  E=   0.112000 au      3.048 eV    24579.0 cm**-1

ORCA TERMINATED NORMALLY
"""


def _audit_with_imports(
    tmp_path: Path,
    family: QuestionFamily,
    calculation: str | None,
    imports: list[Path],
    context: tuple[tuple[str, str], ...],
):
    """Audit a calculation plus any imports, exactly as the CLI does."""
    from qcjudge.parsers import OrcaOutputParser

    parser = OrcaOutputParser()
    results = []
    supported: set[FactKey] = set(parser.supported_keys)
    if calculation is not None:
        source = tmp_path / "job.out"
        source.write_text(calculation, encoding="utf-8")
        results.append(parser.parse(source))
    for path in imports:
        imported, carried = ADAPTER.parse_all(path)
        results.extend(imported)
        supported |= carried
    inventory = _project(tuple(results), frozenset(supported))
    protocol = get_protocol(family)
    question = ResearchQuestion(
        family=family,
        text="A question for this family.",
        hypotheses=tuple(
            Hypothesis(item.id, item.statement) for item in protocol.hypotheses
        ),
        context=context,
    )
    return audit(question, inventory)


def test_a_full_supported_verdict_is_reachable_for_every_family(tmp_path: Path) -> None:
    """Before this seam, no family could reach SUPPORTED through the tool at all.

    Each case here needs a value from an external analysis, because the analyses that decide
    these questions are the ones QCJudge declines to reimplement.
    """
    ct = _audit_with_imports(
        tmp_path / "ct",
        QuestionFamily.CHARGE_TRANSFER_EXCITATION,
        None,
        [
            _export(
                tmp_path / "ct",
                name="ct.json",
                calculations=[
                    {
                        "calculation_id": "dvb-s1",
                        "values": {
                            "scf.converged": {"value": True, "unit": "none"},
                            "tddft.state_count": {"value": 5, "unit": "states"},
                            "hole_electron.d_index_angstrom": {
                                "value": 2.41,
                                "unit": "angstrom",
                            },
                            "hole_electron.sr_index": {
                                "value": 0.31,
                                "unit": "dimensionless",
                            },
                        },
                    }
                ],
            )
        ],
        (("molecule", "dvb"), ("state", "S1")),
    )
    tadf = _audit_with_imports(
        tmp_path / "tadf",
        QuestionFamily.TADF_POTENTIAL,
        COMPLETE_TADF,
        [
            _export(
                tmp_path / "tadf",
                name="soc.json",
                calculations=[
                    {
                        "calculation_id": "soc",
                        "values": {
                            "spin_orbit.coupling_cm1": {"value": 12.4, "unit": "cm**-1"}
                        },
                    }
                ],
            )
        ],
        (("molecule", "dvb"),),
    )
    ts = _audit_with_imports(
        tmp_path / "ts",
        QuestionFamily.TRANSITION_STATE_VALIDATION,
        COMPLETE_TS,
        [
            _export(
                tmp_path / "ts",
                name="irc.json",
                calculations=[
                    {
                        "calculation_id": "irc",
                        "values": {
                            "scf.converged": {"value": True, "unit": "none"},
                            "irc.connects_two_minima": {"value": True, "unit": "none"},
                        },
                    }
                ],
            )
        ],
        (("molecule", "dvb"),),
    )

    assert ct.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert tadf.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert ts.overall_evidence_status is AssessmentStatus.SUPPORTED


def test_a_mixed_audit_keeps_the_two_provenances_apart(tmp_path: Path) -> None:
    """The report must not present an imported number as something the calculation said."""
    report = _audit_with_imports(
        tmp_path,
        QuestionFamily.TADF_POTENTIAL,
        COMPLETE_TADF,
        [
            _export(
                tmp_path,
                name="soc.json",
                calculations=[
                    {
                        "calculation_id": "soc",
                        "values": {
                            "spin_orbit.coupling_cm1": {"value": 12.4, "unit": "cm**-1"}
                        },
                    }
                ],
            )
        ],
        (("molecule", "dvb"),),
    )
    by_origin: dict[EvidenceOrigin, list[str]] = {}
    for item in report.inventory.evidence:
        by_origin.setdefault(item.origin, []).append(item.id)

    assert AssessmentStatus.SUPPORTED is report.overall_evidence_status
    assert any("gap_from_state_manifolds" in name for name in by_origin[EvidenceOrigin.PARSED])
    assert any(
        "risc_from_spin_orbit_coupling" in name for name in by_origin[EvidenceOrigin.ADAPTER]
    )


def test_irc_evidence_reaches_a_saddle_through_the_declared_group(tmp_path: Path) -> None:
    """A path satisfies both members of the ANY_ONE group, and says so.

    The group is a protocol declaration, not an accident: following the path justifies treating
    the connection as established. The report records that it happened this way rather than
    implying the mode was inspected.
    """
    report = _audit_with_imports(
        tmp_path,
        QuestionFamily.TRANSITION_STATE_VALIDATION,
        COMPLETE_TS,
        [
            _export(
                tmp_path,
                name="irc.json",
                calculations=[
                    {
                        "calculation_id": "irc",
                        "values": {
                            "scf.converged": {"value": True, "unit": "none"},
                            "irc.connects_two_minima": {"value": True, "unit": "none"},
                        },
                    }
                ],
            )
        ],
        (("molecule", "dvb"),),
    )
    assessments = {
        item.requirement_id: item
        for hypothesis in report.hypothesis_assessments
        for claim in hypothesis.claim_assessments
        for item in claim.requirement_assessments
    }

    assert report.overall_evidence_status is AssessmentStatus.SUPPORTED
    assert assessments["ts.pathway_connection"].status is AssessmentStatus.SUPPORTED
    assert assessments["ts.mode_identity"].met_via_alternative == "ts.pathway_connection"

"""Build one fixed audit report, byte-identical on every run.

Shared by the golden-report tests, which pin the JSON contract and the human rendering. Every
source of variation is fixed here, including the provenance stamp: a parser takes its
timestamp from the clock, so without this the same file would produce a different report two
seconds later, and a golden file could never be compared byte for byte.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qcjudge.audit import audit
from qcjudge.domain.audit import AuditReport
from qcjudge.domain.context import ExpertReviewFlag
from qcjudge.domain.evidence import EvidenceInventory
from qcjudge.domain.question import Hypothesis, QuestionFamily, ResearchQuestion
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
FIXED_SOURCE = "fixtures/first_order_saddle.out"
FIXED_QUESTION = "Is this structure the transition state for the rotation step?"

# A complete ORCA job: converged SCF, converged optimization, exactly one imaginary mode.
# Chosen so the report exercises every axis at once -- execution PASS, structure PASS, no
# methodology check declared, one claim supported and one not.
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

SCF CONVERGED AFTER  12 CYCLES

<S**2>                :     0.000000

------------------------------
VIBRATIONAL FREQUENCIES
------------------------------
   0:       0.00 cm**-1
   1:     -42.31 cm**-1
   2:     120.55 cm**-1

THE OPTIMIZATION HAS CONVERGED

ORCA TERMINATED NORMALLY
"""


def _freeze(inventory: EvidenceInventory) -> EvidenceInventory:
    """Re-stamp every provenance so the report does not depend on when it was built."""
    facts = tuple(
        dataclasses.replace(
            fact,
            provenance=dataclasses.replace(
                fact.provenance, source_file=FIXED_SOURCE, extracted_at=FIXED_TIME
            ),
        )
        for fact in inventory.facts
    )
    unavailable = tuple(
        dataclasses.replace(
            absent,
            provenance=dataclasses.replace(
                absent.provenance, source_file=FIXED_SOURCE, extracted_at=FIXED_TIME
            ),
        )
        for absent in inventory.unavailable
    )
    return EvidenceInventory(
        facts=facts, evidence=inventory.evidence, unavailable=unavailable
    )


def _audit(tmp_path: Path, *, expert_reviews: tuple[ExpertReviewFlag, ...] = ()) -> AuditReport:
    """Parse the fixture and audit it, with every varying input pinned."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "fixture.out"
    source.write_text(COMPLETE_TS, encoding="utf-8")
    parser = OrcaOutputParser()
    result = parser.parse(source)
    facts, absences = facts_from_parse_results(
        (result,), supported_keys=parser.supported_keys
    )
    inventory = _freeze(EvidenceInventory(facts=facts, unavailable=absences))
    protocol = get_protocol(QuestionFamily.TRANSITION_STATE_VALIDATION)
    question = ResearchQuestion(
        family=QuestionFamily.TRANSITION_STATE_VALIDATION,
        text=FIXED_QUESTION,
        hypotheses=tuple(
            Hypothesis(item.id, item.statement) for item in protocol.hypotheses
        ),
        context=(("molecule", "dvb"),),
    )
    return audit(
        question,
        inventory,
        generated_at=FIXED_TIME,
        expert_reviews=expert_reviews,
    )


def build_report(tmp_path: Path) -> AuditReport:
    """The plain audit of the fixture."""
    return _audit(tmp_path)


def build_report_with_boundary(tmp_path: Path) -> AuditReport:
    """The same audit, with a researcher-reported expert boundary reached.

    Used to prove that requesting expert review survives rendering rather than being
    flattened into a plain verdict.
    """
    return _audit(
        tmp_path,
        expert_reviews=(
            ExpertReviewFlag("ts.mode_identity", "the mode mixes two motions"),
        ),
    )


def _shape(value: object) -> object:
    """The structure of a JSON value: keys in order, and the shape of each value.

    Duplicated from the test module on purpose: the generator must not be able to import the
    test that validates its output, or a change to the comparison would silently regenerate
    the very file it is supposed to check.
    """
    if isinstance(value, dict):
        return {key: _shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _default_shape(scratch: Path) -> dict[str, Any]:
    """The shape a real report has, including the parts only a populated one exercises."""
    from qcjudge.render.json_report import report_to_dict

    return _shape(report_to_dict(build_report(scratch)))  # type: ignore[return-value]


def _write_golden(target: Path, *, scratch: Path | None = None) -> None:
    """Regenerate the golden files. Run deliberately, never as part of the suite.

    The shape is taken from an empty inventory so that it describes the contract rather than
    one fixture's contents, and the text files come from the same builders the tests use.
    ``scratch`` is where the fixture file is written; caller-supplied so this works under a
    sandbox that restricts the system temporary directory.
    """
    from qcjudge.render import report_to_text

    target.mkdir(parents=True, exist_ok=True)
    if scratch is None:
        import tempfile

        with tempfile.TemporaryDirectory() as generated:
            _write_golden(target, scratch=Path(generated))
        return
    plain_dir = scratch / "plain"
    boundary_dir = scratch / "boundary"
    plain_dir.mkdir(parents=True, exist_ok=True)
    boundary_dir.mkdir(parents=True, exist_ok=True)
    plain = build_report(plain_dir)
    boundary = build_report_with_boundary(boundary_dir)
    # Newlines are written explicitly as LF. `write_text` would translate them to CRLF on
    # Windows, and the golden files are compared byte for byte, so a regenerated file would
    # differ from the committed one on this platform alone.
    (target / "audit_report_shape.json").write_bytes(
        (json.dumps(_default_shape(plain_dir), indent=2) + "\n").encode("utf-8")
    )
    (target / "report_task.txt").write_bytes(report_to_text(plain).encode("utf-8"))
    (target / "report_expert_boundary.txt").write_bytes(
        report_to_text(boundary).encode("utf-8")
    )


if __name__ == "__main__":
    import sys

    destination = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("data")
    )
    # Under this project's sandbox the system temporary directory is not listable, so the
    # scratch space goes beside the generated files unless the caller says otherwise.
    _write_golden(destination, scratch=destination.with_name("_scratch"))
    print(f"golden files written to {destination}")

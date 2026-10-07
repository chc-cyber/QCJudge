"""The command-line surface: what an exit code means, and the two researcher channels.

Exit codes describe the run, not the verdict. An audit whose evidence is insufficient is a
successful run -- the report is the deliverable -- so it exits 0, and a caller branches on
``evidence.overall_status`` in the JSON. Only a run that could not produce an audit exits 2.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


def _environment() -> dict[str, str]:
    """The environment a subprocess needs to import qcjudge.

    Passed explicitly rather than relying on an editable install, so the test exercises the
    working tree whether or not the package happens to be installed.
    """
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{SOURCE_ROOT}{os.pathsep}{existing}" if existing else str(SOURCE_ROOT)
    )
    return environment


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


def _run(tmp_path: Path, *extra: str) -> tuple[int, dict[str, object] | None, str]:
    """Run the CLI in a subprocess and return (exit code, parsed JSON, stderr)."""
    source = tmp_path / "ts_with_freq.out"
    source.write_text(COMPLETE_TS, encoding="utf-8")
    stdout = tmp_path / "report.json"
    stderr = tmp_path / "report.err"
    argv = [
        sys.executable,
        "-m",
        "qcjudge.cli.main",
        "audit",
        "--question",
        "transition_state",
        "--input",
        str(source),
        "--context",
        "molecule=dvb",
        "--format",
        "json",
        *extra,
    ]
    with open(stdout, "wb") as out, open(stderr, "wb") as err:
        completed = subprocess.run(
            argv, stdout=out, stderr=err, cwd=str(ROOT), env=_environment()
        )
    payload = stdout.read_bytes()
    document = json.loads(payload.decode("utf-8")) if payload.strip() else None
    return completed.returncode, document, stderr.read_text(encoding="utf-8", errors="replace")


def _requirement(document: dict[str, object], requirement_id: str) -> dict[str, object]:
    evidence = document["evidence"]  # type: ignore[index]
    for hypothesis in evidence["hypotheses"]:  # type: ignore[index]
        for claim in hypothesis["claims"]:
            for requirement in claim["requirements"]:
                if requirement["requirement_id"] == requirement_id:
                    return requirement
    raise AssertionError(f"{requirement_id} is not in the report")


# -- the exit-code policy ------------------------------------------------------------------


def test_a_run_that_produced_a_report_exits_zero(tmp_path: Path) -> None:
    """Insufficient evidence is a finding, not a failure to run."""
    code, document, _ = _run(tmp_path)

    assert code == 0
    assert document is not None
    assert document["evidence"]["overall_status"] != "requires_expert_review"  # type: ignore[index]


def test_an_unreadable_input_exits_two(tmp_path: Path) -> None:
    """Nothing was audited, so no report exists to read a verdict from."""
    source = tmp_path / "not_orca.out"
    source.write_text("this is not an ORCA output file\n", encoding="utf-8")
    argv = [
        sys.executable,
        "-m",
        "qcjudge.cli.main",
        "audit",
        "--question",
        "transition_state",
        "--input",
        str(source),
        "--context",
        "molecule=dvb",
    ]

    completed = subprocess.run(argv, capture_output=True, cwd=str(ROOT), env=_environment())

    assert completed.returncode == 2


# -- a condition the researcher reports -----------------------------------------------------


def test_a_condition_naming_a_declared_key_reaches_the_expert_boundary(
    tmp_path: Path,
) -> None:
    """Only a researcher can see that a mode correspondence is unclear."""
    code, document, _ = _run(
        tmp_path, "--condition", "mode_correspondence=the mode mixes two motions"
    )

    assert code == 0
    assert document is not None
    requirement = _requirement(document, "ts.mode_identity")
    assert requirement["status"] == "requires_expert_review"
    assert requirement["expert_review_required"] is True
    assert document["evidence"]["overall_status"] == "requires_expert_review"  # type: ignore[index]


def test_the_boundary_quotes_both_the_protocol_and_the_researcher(tmp_path: Path) -> None:
    """A reader must see why the boundary fired, not just that it did."""
    _code, document, _ = _run(
        tmp_path, "--condition", "mode_correspondence=the mode mixes two motions"
    )

    assert document is not None
    rationale = str(_requirement(document, "ts.mode_identity")["rationale"])
    assert "Mode correspondence cannot be encoded" in rationale
    assert "the mode mixes two motions" in rationale


def test_a_condition_no_protocol_names_is_accepted_and_changes_nothing(
    tmp_path: Path,
) -> None:
    """It is still recorded, so the audit cannot be confused with one that was not told."""
    baseline_code, baseline, _ = _run(tmp_path)
    code, document, _ = _run(tmp_path, "--condition", "some_other_condition=whatever")

    assert code == baseline_code == 0
    assert document is not None and baseline is not None
    assert (
        document["evidence"]["overall_status"]  # type: ignore[index]
        == baseline["evidence"]["overall_status"]  # type: ignore[index]
    )


# -- a boundary the researcher reports directly ---------------------------------------------


def test_expert_review_reaches_a_declared_boundary(tmp_path: Path) -> None:
    code, document, _ = _run(tmp_path, "--expert-review", "ts.mode_identity")

    assert code == 0
    assert document is not None
    assert _requirement(document, "ts.mode_identity")["status"] == "requires_expert_review"


def test_a_requirement_with_no_declared_boundary_is_refused(tmp_path: Path) -> None:
    """A boundary that does not exist cannot be reached."""
    code, _document, stderr = _run(tmp_path, "--expert-review", "ts.stationary_point")

    assert code == 2
    assert "declares no expert boundary" in stderr


def test_an_unknown_requirement_is_refused(tmp_path: Path) -> None:
    """A typo must not look like a recorded judgement."""
    code, _document, stderr = _run(tmp_path, "--expert-review", "ts.does_not_exist")

    assert code == 2
    assert "unknown requirement" in stderr
    assert "known:" in stderr


# -- malformed input -------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["no_equals_sign", "=missing_key", "missing_value="])
def test_a_malformed_condition_is_refused(tmp_path: Path, bad: str) -> None:
    code, _document, _stderr = _run(tmp_path, "--condition", bad)

    assert code == 2


def test_a_repeated_condition_key_is_refused(tmp_path: Path) -> None:
    """Two values for one key would make the report ambiguous about what was reported."""
    code, _document, stderr = _run(tmp_path, "--condition", "a=1", "--condition", "a=2")

    assert code == 2
    assert "same key more than once" in stderr


# -- the question itself ---------------------------------------------------------------------


def test_the_researchers_own_question_reaches_the_report(tmp_path: Path) -> None:
    """The report must state the question that was asked, not the protocol's wording."""
    asked = "Is this structure the transition state for the C-C rotation step?"
    code, document, _ = _run(tmp_path, "--ask", asked)

    assert code == 0
    assert document is not None
    assert document["question"]["text"] == asked  # type: ignore[index]


def test_without_a_question_the_protocol_hypothesis_is_used(tmp_path: Path) -> None:
    """The field stays populated, but the fallback is not the same as being asked."""
    _code, fallback, _ = _run(tmp_path)
    _code, asked, _ = _run(tmp_path, "--ask", "A question of my own.")

    assert fallback is not None and asked is not None
    assert fallback["question"]["text"] != "A question of my own."  # type: ignore[index]
    assert fallback["question"]["text"]  # type: ignore[index]


def test_an_empty_question_is_refused(tmp_path: Path) -> None:
    """An empty question would silently become the protocol's hypothesis."""
    code, _document, stderr = _run(tmp_path, "--ask", "   ")

    assert code == 2
    assert "empty question" in stderr


def test_the_family_flag_still_selects_the_protocol(tmp_path: Path) -> None:
    """`--question` names a family; the audit must use that family's protocol."""
    _code, document, _ = _run(tmp_path, "--ask", "Something specific.")

    assert document is not None
    assert document["protocol"]["id"] == "transition_state"  # type: ignore[index]

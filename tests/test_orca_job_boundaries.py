"""One ORCA execution must not acquire scientific facts from another execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from qcjudge.domain.calculation import ParseOutcome, ParseResult
from qcjudge.domain.common import UnavailableReason
from qcjudge.domain.evidence import EvidenceInventory, EvidenceType, FactKey
from qcjudge.evidence import facts_from_parse_results
from qcjudge.evidence.derivation import derive_evidence
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol
from tests.support import TADF
from tests.test_orca_parser import (
    ABSORPTION,
    EXCITED_STATES,
    FREQUENCIES,
    HEADER,
    SYSTEM,
    TERMINATION,
)

SINGLET = "EXCITED STATES (SINGLETS)\nSTATE 1: E= 0.115 au 3.129 eV\n"
TRIPLET = "EXCITED STATES (TRIPLETS)\nSTATE 1: E= 0.112 au 3.048 eV\n"
JOB_ONE = "$$$$$$$$ JOB NUMBER 1 $$$$$$$$\n"
JOB_TWO = "$$$$$$$$ JOB NUMBER 2 $$$$$$$$\n"


def _parse(tmp_path: Path, text: str) -> ParseResult:
    path = tmp_path / "jobs.out"
    path.write_text(text, encoding="utf-8")
    return OrcaOutputParser().parse(path)


def _value(result: ParseResult, key: FactKey):
    observation = result.observation(key)
    return None if observation is None else observation.value


def _inventory(result: ParseResult) -> EvidenceInventory:
    facts, unavailable = facts_from_parse_results(
        (result,), supported_keys=OrcaOutputParser().supported_keys
    )
    return EvidenceInventory(facts=facts, unavailable=unavailable)


@pytest.mark.parametrize("second_termination", ["", TERMINATION])
def test_a_later_job_cannot_supply_the_other_state_manifold(
    tmp_path: Path, second_termination: str
) -> None:
    """A completed S calculation and an unrelated T calculation do not form one gap."""
    result = _parse(
        tmp_path,
        HEADER + SYSTEM + SINGLET + TERMINATION + HEADER + SYSTEM + TRIPLET + second_termination,
    )

    assert result.diagnostics.outcome is ParseOutcome.COMPLETE
    assert _value(result, FactKey.SINGLET_STATE_ENERGY_EV) == (3.129,)
    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) is None
    assert result.diagnostics.reason_for(result.source_file, FactKey.TRIPLET_STATE_ENERGY_EV) is (
        UnavailableReason.NOT_PROVIDED
    )
    derived = derive_evidence(get_protocol(TADF), _inventory(result))
    assert not any(item.evidence_type is EvidenceType.SINGLET_TRIPLET_GAP for item in derived)
    assert any("first execution" in warning for warning in result.diagnostics.warnings)


def test_a_later_normal_end_cannot_complete_the_first_interrupted_run(tmp_path: Path) -> None:
    result = _parse(
        tmp_path,
        HEADER + SYSTEM + FREQUENCIES + SINGLET + HEADER + SYSTEM + TRIPLET + TERMINATION,
    )

    assert result.diagnostics.outcome is ParseOutcome.TRUNCATED
    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) is None
    inventory = _inventory(result)
    for key in (FactKey.FREQUENCY_CM1, FactKey.SINGLET_STATE_ENERGY_EV):
        assert not inventory.facts_by_key(key)
        assert inventory.unavailable_reason(key) is UnavailableReason.FILE_TRUNCATED


def test_later_method_system_and_failed_convergence_cannot_change_the_first_job(
    tmp_path: Path,
) -> None:
    later_header = HEADER.replace("B3LYP def2-TZVP", "PBE0 def2-SVP")
    later_system = SYSTEM.replace("Charge    0", "Charge    1").replace(
        "SCF CONVERGED AFTER  12 CYCLES", "SCF NOT CONVERGED"
    )
    result = _parse(
        tmp_path,
        HEADER + SYSTEM + FREQUENCIES + TERMINATION + later_header + later_system + TERMINATION,
    )

    assert _value(result, FactKey.METHOD_NAME) == "B3LYP"
    assert _value(result, FactKey.BASIS_NAME) == "def2-TZVP"
    assert _value(result, FactKey.CHARGE) == 0
    assert _value(result, FactKey.SCF_CONVERGED) is True
    assert _value(result, FactKey.FREQUENCY_CM1) == (0.0, -42.31, 120.55)


def test_later_optimization_success_cannot_fill_a_missing_first_result(tmp_path: Path) -> None:
    result = _parse(
        tmp_path,
        HEADER + SYSTEM + TERMINATION + HEADER + SYSTEM + FREQUENCIES + TERMINATION,
    )

    assert _value(result, FactKey.GEOMETRY_CONVERGED) is None
    assert _value(result, FactKey.FREQUENCY_CM1) is None
    assert result.diagnostics.reason_for(result.source_file, FactKey.GEOMETRY_CONVERGED) is (
        UnavailableReason.NOT_PROVIDED
    )


def test_scientific_output_after_termination_is_ignored_without_a_second_banner(
    tmp_path: Path,
) -> None:
    result = _parse(tmp_path, HEADER + SYSTEM + SINGLET + TERMINATION + TRIPLET + ABSORPTION)

    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) is None
    assert _value(result, FactKey.OSCILLATOR_STRENGTH) is None
    assert result.diagnostics.warnings


@pytest.mark.parametrize("final_termination", ["", TERMINATION])
def test_explicit_compound_execution_boundaries_keep_only_the_first_job(
    tmp_path: Path, final_termination: str
) -> None:
    """Starting JOB NUMBER 2 closes JOB NUMBER 1, even if the successor is interrupted."""
    echo = (
        HEADER
        + "| 6> $new_job\n"
        + "| 7> ! PBE0 def2-SVP\n"
        + "| 8> * xyz 1 3\n"
    )
    text = (
        echo
        + JOB_ONE
        + SYSTEM
        + FREQUENCIES
        + SINGLET
        + JOB_TWO
        + "Total Charge    Charge    1\nSCF NOT CONVERGED\n"
        + TRIPLET
        + final_termination
    )
    result = _parse(tmp_path, text)

    assert result.diagnostics.outcome is ParseOutcome.COMPLETE
    assert _value(result, FactKey.SCF_CONVERGED) is True
    assert _value(result, FactKey.GEOMETRY_CONVERGED) is True
    assert _value(result, FactKey.METHOD_NAME) == "B3LYP"
    assert _value(result, FactKey.BASIS_NAME) == "def2-TZVP"
    assert _value(result, FactKey.CHARGE) == 0
    assert _value(result, FactKey.SINGLET_STATE_ENERGY_EV) == (3.129,)
    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) is None
    observation = result.observation(FactKey.SINGLET_STATE_ENERGY_EV)
    assert observation is not None
    line = text[: text.index("STATE 1: E= 0.115")].count("\n") + 1
    assert observation.location == f"line {line}"
    assert any("more than one job" in warning for warning in result.diagnostics.warnings)


def test_later_echoed_system_cannot_supply_the_first_compound_system(tmp_path: Path) -> None:
    echo = (
        "Program Version 5.0.4\n"
        "| 1> ! B3LYP def2-TZVP\n"
        "| 2> $new_job\n"
        "| 3> ! PBE0 def2-SVP\n"
        "| 4> * xyz 1 3\n"
    )
    result = _parse(tmp_path, echo + JOB_ONE + SINGLET + JOB_TWO + SYSTEM + TERMINATION)

    assert _value(result, FactKey.CHARGE) is None
    assert _value(result, FactKey.MULTIPLICITY) is None
    assert _value(result, FactKey.SCF_CONVERGED) is None
    assert _value(result, FactKey.METHOD_NAME) == "B3LYP"


def test_shared_preamble_cannot_supply_a_later_compound_basis(tmp_path: Path) -> None:
    echo = (
        "Program Version 5.0.4\n"
        "Your calculation utilizes the basis: def2-SVP\n"
        "| 1> ! B3LYP\n"
        "| 2> $new_job\n"
        "| 3> ! PBE0 def2-SVP\n"
    )
    result = _parse(tmp_path, echo + JOB_ONE + SYSTEM + JOB_TWO + SYSTEM + TERMINATION)

    assert _value(result, FactKey.METHOD_NAME) == "B3LYP"
    assert _value(result, FactKey.BASIS_NAME) is None
    assert result.diagnostics.reason_for(result.source_file, FactKey.BASIS_NAME) is (
        UnavailableReason.UNSUPPORTED_CONSTRUCT
    )


def test_ambiguous_compound_output_withholds_science_instead_of_combining_jobs(
    tmp_path: Path,
) -> None:
    result = _parse(
        tmp_path,
        HEADER + "| 6> $new_job\n| 7> ! PBE0 def2-SVP\n" + SYSTEM + EXCITED_STATES + TERMINATION,
    )

    assert _value(result, FactKey.SOFTWARE_VERSION) == "5.0.4"
    assert {observation.key for observation in result.observations} <= {
        FactKey.SOFTWARE_NAME,
        FactKey.SOFTWARE_VERSION,
    }
    inventory = _inventory(result)
    assert inventory.unavailable_reason(FactKey.SINGLET_STATE_ENERGY_EV) is (
        UnavailableReason.UNSUPPORTED_CONSTRUCT
    )
    assert not derive_evidence(get_protocol(TADF), inventory)


def test_compound_output_missing_job_one_cannot_use_its_first_echo(tmp_path: Path) -> None:
    result = _parse(
        tmp_path,
        HEADER + "| 6> $new_job\n" + JOB_TWO + SYSTEM + EXCITED_STATES + TERMINATION,
    )

    assert _value(result, FactKey.SCF_CONVERGED) is None
    assert _value(result, FactKey.METHOD_NAME) is None
    assert result.diagnostics.reason_for(result.source_file, FactKey.SCF_CONVERGED) is (
        UnavailableReason.UNSUPPORTED_CONSTRUCT
    )


def test_normal_footer_preserves_single_job_values_without_a_warning(tmp_path: Path) -> None:
    result = _parse(
        tmp_path,
        HEADER + SYSTEM + FREQUENCIES + EXCITED_STATES + ABSORPTION + TERMINATION
        + "TOTAL RUN TIME: 0 days 0 hours 0 minutes 1 second\n",
    )

    assert result.diagnostics.outcome is ParseOutcome.COMPLETE
    assert _value(result, FactKey.SINGLET_STATE_ENERGY_EV) == (5.352, 5.723)
    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) == (3.136,)
    assert _value(result, FactKey.OSCILLATOR_STRENGTH) == (0.005629700, 0.000205421)
    assert result.diagnostics.warnings == ()


def test_an_echoed_termination_string_cannot_mark_an_execution_complete(tmp_path: Path) -> None:
    result = _parse(
        tmp_path, HEADER + "| 6> # ORCA TERMINATED NORMALLY\n" + SYSTEM + FREQUENCIES
    )

    assert result.diagnostics.outcome is ParseOutcome.TRUNCATED
    assert not _inventory(result).facts_by_key(FactKey.FREQUENCY_IMAGINARY_COUNT)

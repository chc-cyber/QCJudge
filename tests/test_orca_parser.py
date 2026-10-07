"""Contract tests for the declared ORCA extraction.

The parser is the boundary where "we could not read it" must never become "it was not
there". These tests pin that: which keys are supported, that every observation carries a
location, that truncation is detected and reasoned about, and that nothing is ever invented.

Fixtures are inline synthetic text. No third-party output is vendored into the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qcjudge.domain.calculation import ParseOutcome
from qcjudge.domain.common import UnavailableReason
from qcjudge.domain.evidence import FactKey
from qcjudge.parsers import OrcaOutputParser

HEADER = """\
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
"""

SYSTEM = """\
Total Charge    Charge    0
Multiplicity    Mult    1

SCF CONVERGED AFTER  12 CYCLES

<S**2>                :     0.000000
"""

FREQUENCIES = """\
------------------------------
VIBRATIONAL FREQUENCIES
------------------------------
   0:       0.00 cm**-1
   1:     -42.31 cm**-1
   2:     120.55 cm**-1

THE OPTIMIZATION HAS CONVERGED
"""

EXCITED_STATES = """\
------------------------------------
TD-DFT/TDA EXCITED STATES (SINGLETS)
------------------------------------
STATE  1:  E=   0.196686 au      5.352 eV    43167.6 cm**-1
STATE  2:  E=   0.210307 au      5.723 eV    46157.0 cm**-1

------------------------------------
TD-DFT/TDA EXCITED STATES (TRIPLETS)
------------------------------------
STATE  1:  E=   0.115235 au      3.136 eV    25291.1 cm**-1
"""

ABSORPTION = """\
------------------------------------------------------------------------------
ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
------------------------------------------------------------------------------
State   Energy    Wavelength  fosc         T2        TX        TY        TZ
(cm-1)      (nm)                 (au**2)    (au)      (au)      (au)
------------------------------------------------------------------------------
  1   43167.6    231.7   0.005629700   0.04293  -0.15576  -0.13665  -0.00000
  2   46157.0    216.7   0.000205421   0.00006   0.00770  -0.00115   0.00000
"""

TERMINATION = "\nORCA TERMINATED NORMALLY\n"

UNREAD_BLOCK = "MULLIKEN ATOMIC CHARGES\n"


def _write(tmp_path: Path, text: str, name: str = "job.out") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _full() -> str:
    return HEADER + SYSTEM + FREQUENCIES + EXCITED_STATES + ABSORPTION + TERMINATION


def _parse(tmp_path: Path, text: str):
    return OrcaOutputParser().parse(_write(tmp_path, text))


def _value(result, key: FactKey):
    observation = result.observation(key)
    return None if observation is None else observation.value


# -- the declared subset ----------------------------------------------------------------


def test_every_declared_key_is_a_registered_fact_key() -> None:
    parser = OrcaOutputParser()
    assert parser.supported_keys <= set(FactKey)
    assert parser.supported_keys


def test_extracts_the_declared_subset(tmp_path: Path) -> None:
    result = _parse(tmp_path, _full())
    assert result.diagnostics.outcome is ParseOutcome.COMPLETE
    assert _value(result, FactKey.SOFTWARE_NAME) == "ORCA"
    assert _value(result, FactKey.SOFTWARE_VERSION) == "5.0.4"
    assert _value(result, FactKey.METHOD_NAME) == "B3LYP"
    assert _value(result, FactKey.BASIS_NAME) == "def2-TZVP"
    assert _value(result, FactKey.CHARGE) == 0
    assert _value(result, FactKey.MULTIPLICITY) == 1
    assert _value(result, FactKey.SCF_CONVERGED) is True
    assert _value(result, FactKey.GEOMETRY_CONVERGED) is True
    assert _value(result, FactKey.FREQUENCY_CM1) == (0.0, -42.31, 120.55)
    assert _value(result, FactKey.SINGLET_STATE_ENERGY_EV) == (5.352, 5.723)
    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) == (3.136,)
    assert _value(result, FactKey.OSCILLATOR_STRENGTH) == (0.005629700, 0.000205421)
    assert _value(result, FactKey.SPIN_EXPECTATION) == (0.0,)


def test_the_singlet_and_triplet_manifolds_are_kept_apart(tmp_path: Path) -> None:
    """A merged list of excitation energies could not support a singlet-triplet gap."""
    result = _parse(tmp_path, _full())
    singlets = _value(result, FactKey.SINGLET_STATE_ENERGY_EV)
    triplets = _value(result, FactKey.TRIPLET_STATE_ENERGY_EV)
    assert singlets == (5.352, 5.723)
    assert triplets == (3.136,)
    assert not set(singlets) & set(triplets)


def test_oscillator_strengths_come_from_the_electric_dipole_table(tmp_path: Path) -> None:
    """ORCA prints a velocity-dipole table too, and the two are different quantities."""
    text = _full().replace(
        "ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS",
        "ABSORPTION SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS",
    )
    result = _parse(tmp_path, text)
    assert _value(result, FactKey.OSCILLATOR_STRENGTH) is None
    assert result.diagnostics.reason_for(
        result.source_file, FactKey.OSCILLATOR_STRENGTH
    ) is (UnavailableReason.NOT_PROVIDED)


def test_every_observation_carries_a_location(tmp_path: Path) -> None:
    result = _parse(tmp_path, _full())
    assert result.observations
    for observation in result.observations:
        assert observation.location, observation.key
        assert "line" in observation.location


def test_multi_line_values_report_their_span(tmp_path: Path) -> None:
    result = _parse(tmp_path, _full())
    location = result.observation(FactKey.FREQUENCY_CM1).location
    assert location is not None
    assert "-" in location


def test_absent_values_are_absent_not_zero(tmp_path: Path) -> None:
    """Reporting 0.0 for a value never seen would be inventing a fact."""
    result = _parse(tmp_path, HEADER + TERMINATION)
    assert _value(result, FactKey.SCF_CONVERGED) is None
    assert _value(result, FactKey.FREQUENCY_CM1) is None
    assert _value(result, FactKey.SINGLET_STATE_ENERGY_EV) is None
    assert _value(result, FactKey.TRIPLET_STATE_ENERGY_EV) is None
    assert _value(result, FactKey.SPIN_EXPECTATION) is None


def test_a_failed_scf_is_false_rather_than_unknown(tmp_path: Path) -> None:
    result = _parse(tmp_path, HEADER + "SCF NOT CONVERGED\n" + TERMINATION)
    assert _value(result, FactKey.SCF_CONVERGED) is False


# -- truncation -------------------------------------------------------------------------


def test_missing_termination_marker_marks_the_file_truncated(tmp_path: Path) -> None:
    result = _parse(tmp_path, HEADER + SYSTEM)
    assert result.diagnostics.outcome is ParseOutcome.TRUNCATED
    assert result.diagnostics.warnings


def test_values_missing_from_a_truncated_file_are_unreadable_not_unprovided(
    tmp_path: Path,
) -> None:
    """A file that died mid-run must not be reported as a job that was never requested."""
    result = _parse(tmp_path, HEADER + SYSTEM)
    reason = result.diagnostics.reason_for(result.source_file, FactKey.FREQUENCY_CM1)
    assert reason is UnavailableReason.FILE_TRUNCATED


def test_values_missing_from_a_complete_file_are_not_provided(tmp_path: Path) -> None:
    result = _parse(tmp_path, HEADER + SYSTEM + TERMINATION)
    reason = result.diagnostics.reason_for(result.source_file, FactKey.FREQUENCY_CM1)
    assert reason is UnavailableReason.NOT_PROVIDED


def test_an_absent_absence_reason_is_distinguishable(tmp_path: Path) -> None:
    """A key the parser never attempted has no recorded reason, and that must be visible."""
    result = _parse(tmp_path, _full())
    assert (
        result.diagnostics.reason_for(result.source_file, FactKey.SINGLET_TRIPLET_GAP_EV)
        is None
    )


# -- refusal to guess -------------------------------------------------------------------


def test_several_candidate_method_keywords_are_reported_as_ambiguous(tmp_path: Path) -> None:
    text = HEADER.replace("! B3LYP def2-TZVP OPT FREQ", "! B3LYP BP86 def2-TZVP OPT FREQ")
    result = _parse(tmp_path, text + TERMINATION)
    assert result.diagnostics.reason_for(result.source_file, FactKey.METHOD_NAME) is (
        UnavailableReason.AMBIGUOUS_MATCH
    )
    assert _value(result, FactKey.METHOD_NAME) is None


def test_an_unrecognised_basis_keyword_makes_even_the_method_ambiguous(
    tmp_path: Path,
) -> None:
    """An unclassifiable token is a candidate method as far as the parser can tell.

    Refusing to guess is the point: naming two candidates and reporting AMBIGUOUS_MATCH is
    more useful than silently picking whichever looks more like a functional.
    """
    text = HEADER.replace("! B3LYP def2-TZVP", "! B3LYP someCustomBasis")
    result = _parse(tmp_path, text + TERMINATION)
    assert result.diagnostics.reason_for(result.source_file, FactKey.BASIS_NAME) is (
        UnavailableReason.UNSUPPORTED_CONSTRUCT
    )
    assert result.diagnostics.reason_for(result.source_file, FactKey.METHOD_NAME) is (
        UnavailableReason.AMBIGUOUS_MATCH
    )
    assert _value(result, FactKey.METHOD_NAME) is None


def test_a_method_without_a_basis_is_still_read(tmp_path: Path) -> None:
    text = HEADER.replace("! B3LYP def2-TZVP OPT FREQ", "! B3LYP OPT")
    result = _parse(tmp_path, text + TERMINATION)
    assert _value(result, FactKey.METHOD_NAME) == "B3LYP"
    assert _value(result, FactKey.BASIS_NAME) is None
    assert result.diagnostics.reason_for(result.source_file, FactKey.BASIS_NAME) is (
        UnavailableReason.UNSUPPORTED_CONSTRUCT
    )


def test_no_input_echo_leaves_method_unsupported(tmp_path: Path) -> None:
    result = _parse(tmp_path, SYSTEM + TERMINATION)
    assert result.diagnostics.reason_for(result.source_file, FactKey.METHOD_NAME) is (
        UnavailableReason.UNSUPPORTED_CONSTRUCT
    )


@pytest.mark.parametrize(
    "echo",
    [
        "! wB97X-D3 def2-TZVP TightSCF",
        "! PBE0 def2-SVP",
        "! B3LYP D3BJ def2-TZVP OPT",
        "! RHF 6-31G",
    ],
)
def test_method_and_basis_survive_realistic_keyword_combinations(
    tmp_path: Path, echo: str
) -> None:
    text = HEADER.replace("! B3LYP def2-TZVP OPT FREQ", echo)
    result = _parse(tmp_path, text + TERMINATION)
    assert _value(result, FactKey.METHOD_NAME) is not None
    assert _value(result, FactKey.BASIS_NAME) is not None


def test_state_line_padding_and_case_variants_are_tolerated(tmp_path: Path) -> None:
    """The original stub required the number to abut ``f=`` and lost every excited state."""
    for spacing in (
        "STATE  1:  E=   0.196686 au      5.352 eV    43167.6 cm**-1",
        "STATE 1: E= 0.196686 au 5.352 eV 43167.6 cm**-1",
        "state  1:  e=   0.196686 au      5.352 eV    43167.6 cm**-1",
    ):
        text = HEADER + "EXCITED STATES (SINGLETS)\n" + spacing + "\n" + TERMINATION
        result = _parse(tmp_path, text)
        assert _value(result, FactKey.SINGLET_STATE_ENERGY_EV) == (5.352,), spacing


# -- format recognition -----------------------------------------------------------------


def test_a_non_orca_file_is_not_recognised(tmp_path: Path) -> None:
    result = _parse(tmp_path, "hello world\nnothing to see here\n")
    assert result.diagnostics.outcome is ParseOutcome.UNRECOGNISED
    assert result.observations == ()
    assert not result.diagnostics.is_usable


def test_an_empty_file_is_not_recognised(tmp_path: Path) -> None:
    result = _parse(tmp_path, "")
    assert result.diagnostics.outcome is ParseOutcome.UNRECOGNISED


def test_unread_blocks_are_declared_rather_than_silent(tmp_path: Path) -> None:
    result = _parse(tmp_path, _full() + UNREAD_BLOCK)
    assert "mulliken population analysis" in result.diagnostics.unparsed_regions


def test_the_parser_reports_its_own_identity_for_provenance(tmp_path: Path) -> None:
    result = _parse(tmp_path, _full())
    parser = OrcaOutputParser()
    assert result.producer == parser.name
    assert result.producer_version == parser.version
    assert result.extracted_at.tzinfo is not None

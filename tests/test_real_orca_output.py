"""The parser against real ORCA output.

Skipped unless the pinned corpus has been fetched with
``python tools/fetch_benchmark_data.py``. Nothing is vendored: the files live under an
ignored directory and are verified against ``tools/benchmark_manifest.json``.

These are the tests that keep the parser's declared markers honest. Synthetic fixtures prove
the parser does what it was written to do; only real output proves it was written to do the
right thing.
"""

from __future__ import annotations

import pytest

from qcjudge.domain.calculation import ParseOutcome
from qcjudge.domain.evidence import FactKey
from qcjudge.parsers import OrcaOutputParser

CORPUS = __import__("pathlib").Path(__file__).resolve().parents[1] / ".benchmark-data"
pytestmark = pytest.mark.skipif(
    not CORPUS.exists(), reason="run tools/fetch_benchmark_data.py to fetch the corpus"
)

SP_FILES = ("ORCA/ORCA2.6/dvb_sp.out", "ORCA/ORCA4.2/dvb_sp.out")
TD_FILES = (
    "ORCA/ORCA2.9/dvb_td.out",
    "ORCA/ORCA4.0/dvb_td.out",
    "ORCA/ORCA4.2/dvb_td.out",
)
ALL_FILES = SP_FILES + TD_FILES + (
    "ORCA/ORCA3.0/dvb_ir.out",
    "ORCA/ORCA3.0/dvb_gopt_unconverged.out",
    "ORCA/ORCA4.1/dvb_gopt.out",
    "ORCA/ORCA4.2/dvb_ir.out",
    "ORCA/ORCA4.2/long-input.out",
    "ORCA/ORCA5.0/1177.out",
    "ORCA/ORCA5.0/dvb_soc.log",
)


def _parse(relative: str):
    path = CORPUS / relative
    if not path.exists():
        pytest.skip(f"{relative} is not in the fetched corpus")
    return OrcaOutputParser().parse(path)


def _value(result, key: FactKey):
    observation = result.observation(key)
    return None if observation is None else observation.value


def test_the_corpus_spans_several_orca_versions() -> None:
    versions = {
        str(_value(_parse(relative), FactKey.SOFTWARE_VERSION)) for relative in ALL_FILES
    }
    assert len(versions) >= 5


@pytest.mark.parametrize("relative", ALL_FILES)
def test_real_files_are_recognised_and_have_locations(relative: str) -> None:
    result = _parse(relative)
    assert result.diagnostics.outcome is ParseOutcome.COMPLETE
    assert result.observations
    for observation in result.observations:
        assert observation.location


@pytest.mark.parametrize("relative", ALL_FILES)
def test_every_real_file_yields_a_converged_scf_verdict(relative: str) -> None:
    assert _value(_parse(relative), FactKey.SCF_CONVERGED) is True


@pytest.mark.parametrize("relative", ALL_FILES)
def test_every_real_file_yields_a_version_and_a_system(relative: str) -> None:
    result = _parse(relative)
    assert _value(result, FactKey.SOFTWARE_NAME) == "ORCA"
    assert isinstance(_value(result, FactKey.CHARGE), int)
    assert isinstance(_value(result, FactKey.MULTIPLICITY), int)


@pytest.mark.parametrize("relative", ALL_FILES)
def test_every_real_file_states_the_basis_it_used(relative: str) -> None:
    assert _value(_parse(relative), FactKey.BASIS_NAME)


@pytest.mark.parametrize("relative", TD_FILES)
def test_excitation_energies_are_split_by_manifold(relative: str) -> None:
    result = _parse(relative)
    singlets = _value(result, FactKey.SINGLET_STATE_ENERGY_EV)
    triplets = _value(result, FactKey.TRIPLET_STATE_ENERGY_EV)
    assert singlets and triplets
    assert min(triplets) < min(singlets), "T1 should lie below S1 in these files"


@pytest.mark.parametrize("relative", TD_FILES)
def test_oscillator_strengths_are_read_from_the_electric_table(relative: str) -> None:
    assert _value(_parse(relative), FactKey.OSCILLATOR_STRENGTH)


@pytest.mark.parametrize("relative", SP_FILES)
def test_a_single_point_file_reports_no_frequencies_rather_than_zero(relative: str) -> None:
    """Absence must stay absence: a zero would be indistinguishable from a real result."""
    result = _parse(relative)
    assert _value(result, FactKey.FREQUENCY_CM1) is None
    assert _value(result, FactKey.GEOMETRY_CONVERGED) is None


def test_an_unconverged_optimisation_is_reported_as_not_converged() -> None:
    result = _parse("ORCA/ORCA3.0/dvb_gopt_unconverged.out")
    assert _value(result, FactKey.GEOMETRY_CONVERGED) is False


def test_a_cycle_limited_optimisation_is_reported_as_not_converged() -> None:
    """ORCA 5.0 wraps this message across two lines, which a naive marker misses."""
    result = _parse("ORCA/ORCA5.0/1177.out")
    assert _value(result, FactKey.GEOMETRY_CONVERGED) is False


def test_a_converged_optimisation_is_reported_as_converged() -> None:
    result = _parse("ORCA/ORCA4.1/dvb_gopt.out")
    assert _value(result, FactKey.GEOMETRY_CONVERGED) is True


def test_a_frequency_job_yields_a_complete_mode_list() -> None:
    """DVB has 22 atoms, so a non-linear Hessian has 3N-6 = 60 modes."""
    frequencies = _value(_parse("ORCA/ORCA3.0/dvb_ir.out"), FactKey.FREQUENCY_CM1)
    assert frequencies is not None
    assert len(frequencies) == 60


def test_a_file_holding_many_jobs_reports_only_the_first_command_line() -> None:
    """Two hundred identical jobs are not an ambiguity, and mixing them would be worse."""
    result = _parse("ORCA/ORCA4.2/long-input.out")
    assert _value(result, FactKey.METHOD_NAME) == "MP2"
    # Taken from the printed "utilizes the basis" line, which is authoritative output,
    # rather than from the keyword casing in the echoed input.
    assert _value(result, FactKey.BASIS_NAME) == "def2-TZVP"
    assert any("more than one job" in warning for warning in result.diagnostics.warnings)


def test_spin_expectation_values_are_read_when_printed() -> None:
    assert _value(_parse("ORCA/ORCA5.0/dvb_soc.log"), FactKey.SPIN_EXPECTATION)


@pytest.mark.parametrize("relative", ALL_FILES)
def test_no_real_file_produces_a_value_the_parser_does_not_support(relative: str) -> None:
    """Every observation must be a declared key, so nothing arrives by accident."""
    result = _parse(relative)
    supported = OrcaOutputParser().supported_keys
    assert {observation.key for observation in result.observations} <= supported

"""The parser-to-audit path, tested end to end.

The acceptance corpus builds inventories by hand, which proves the reasoning engine correct
but cannot show what the system does with a real file. That gap hid a defect class: a key
produced only by arithmetic reported ``UNSUPPORTED_CONSTRUCT`` when its sources were simply
never computed, so a converged optimization without a frequency job was reported
``NOT_ASSESSABLE`` -- blaming our reader for the researcher's omission -- where the plan
promises ``INSUFFICIENT``.

These tests drive the whole chain -- parse, project, derive, match, aggregate -- so a status
reachable only through the real pipeline is pinned by a test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qcjudge.audit import audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.audit import AuditReport
from qcjudge.domain.common import UnavailableReason
from qcjudge.domain.evidence import EvidenceInventory, FactKey
from qcjudge.domain.validation import ValidationScope, ValidationStatus
from qcjudge.evidence import facts_from_parse_results
from qcjudge.evidence.facts.projection import _DERIVED_FACTS
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol
from tests.support import TS, ts_question

CORPUS = Path(__file__).resolve().parents[1] / ".benchmark-data" / "ORCA"
CONVERGED_GEOMETRY_ONLY = CORPUS / "ORCA4.1" / "dvb_gopt.out"

HEADER = """\
                  *****************
                  * O   R   C   A *
                  *****************

Program Version 5.0.4 - RELEASE

------------------
INPUT FILE
------------------
|  1> ! B3LYP def2-TZVP OPT
|  2> * xyz 0 1
|  3> C 0 0 0
|  4> *
|  5>

Total Charge    Charge    0
Multiplicity    Mult    1

SCF CONVERGED AFTER  12 CYCLES

<S**2>                :     0.000000

THE OPTIMIZATION HAS CONVERGED

"""

FREQUENCIES = """\
------------------------------
VIBRATIONAL FREQUENCIES
------------------------------
   0:       0.00 cm**-1
   1:     -42.31 cm**-1
   2:     120.55 cm**-1

"""

TERMINATION = "ORCA TERMINATED NORMALLY\n"
FIRST_ORDER_SADDLE = "struct.frequency_count"


def _frequency_block(mode_values: tuple[float, ...]) -> str:
    """One vibrational frequency block, as ORCA prints it."""
    body = "".join(
        f"   {index}:  {value:>10.2f} cm**-1\n" for index, value in enumerate(mode_values)
    )
    return (
        "------------------------------\n"
        "VIBRATIONAL FREQUENCIES\n"
        "------------------------------\n"
        f"{body}\n"
    )


def _write(tmp_path: Path, text: str, name: str = "job.out") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _pipeline(path: Path) -> tuple[EvidenceInventory, AuditReport]:
    """Run one file through the whole chain and return its inventory and report."""
    parser = OrcaOutputParser()
    result = parser.parse(path)
    facts, absences = facts_from_parse_results(
        (result,), supported_keys=parser.supported_keys
    )
    inventory = EvidenceInventory(facts=facts, unavailable=absences)
    return inventory, audit(ts_question(), inventory)


# -- a derived key reports why its sources are missing -----------------------------------


def test_a_derived_count_inherits_the_reason_its_source_was_missing(tmp_path: Path) -> None:
    """No frequency calculation is a coverage gap, not a limitation of our reader."""
    inventory, _report = _pipeline(_write(tmp_path, HEADER + TERMINATION))

    assert inventory.unavailable_reason(FactKey.FREQUENCY_CM1) is UnavailableReason.NOT_PROVIDED
    assert (
        inventory.unavailable_reason(FactKey.FREQUENCY_IMAGINARY_COUNT)
        is UnavailableReason.NOT_PROVIDED
    )
    assert (
        inventory.unavailable_reason(FactKey.FREQUENCY_OBSERVED_MODE_COUNT)
        is UnavailableReason.NOT_PROVIDED
    )


def test_a_key_the_reader_never_attempts_stays_unsupported(tmp_path: Path) -> None:
    """Inheriting a reason must not swallow a genuine reader limitation."""
    inventory, _report = _pipeline(_write(tmp_path, HEADER + TERMINATION))

    assert (
        inventory.unavailable_reason(FactKey.FREQUENCY_EXPECTED_MODE_COUNT)
        is UnavailableReason.UNSUPPORTED_CONSTRUCT
    )


def test_an_absent_frequency_job_is_insufficient_through_the_real_pipeline(
    tmp_path: Path,
) -> None:
    """The plan's row: a converged calculation with no frequencies is a coverage gap."""
    _inventory, report = _pipeline(_write(tmp_path, HEADER + TERMINATION))

    assert report.execution_status is ValidationStatus.PASS
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


def test_an_access_failure_outranks_a_coverage_gap(tmp_path: Path) -> None:
    """A truncated source must keep its access-failure reason, not become "not provided"."""
    inventory, report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES))

    assert (
        inventory.unavailable_reason(FactKey.FREQUENCY_IMAGINARY_COUNT)
        is UnavailableReason.FILE_TRUNCATED
    )
    assert report.overall_evidence_status is AssessmentStatus.NOT_ASSESSABLE


# -- a truncated list must not be counted -------------------------------------------------


def test_a_truncated_file_withholds_the_mode_list(tmp_path: Path) -> None:
    """A prefix of a mode list cannot be told from the whole list, so it is not a fact."""
    inventory, _report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES))

    assert not inventory.facts_by_key(FactKey.FREQUENCY_CM1)
    assert not inventory.facts_by_key(FactKey.FREQUENCY_IMAGINARY_COUNT)
    assert not inventory.facts_by_key(FactKey.FREQUENCY_OBSERVED_MODE_COUNT)
    assert (
        inventory.unavailable_reason(FactKey.FREQUENCY_CM1)
        is UnavailableReason.FILE_TRUNCATED
    )


def test_a_truncated_file_cannot_report_a_hessian_order(tmp_path: Path) -> None:
    """A truncated Hessian is not evidence of anything, in either direction."""
    _inventory, report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES))

    structural = [
        result
        for result in report.validation_results
        if result.rule_id == "struct.frequency_count"
    ]
    assert structural and structural[0].status is ValidationStatus.UNKNOWN
    assert report.overall_evidence_status is not AssessmentStatus.CONTRADICTED


def test_a_complete_file_still_yields_its_imaginary_count(tmp_path: Path) -> None:
    """Withholding must be conditioned on truncation, not applied to every file."""
    inventory, report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES + TERMINATION))

    counts = inventory.facts_by_key(FactKey.FREQUENCY_IMAGINARY_COUNT)
    assert counts and counts[0].value == 1
    assert report.overall_evidence_status is AssessmentStatus.PARTIALLY_SUPPORTED


# -- a scope nobody checked must not read as a scope that passed --------------------------


def test_a_scope_with_no_declared_check_is_unknown_not_pass(tmp_path: Path) -> None:
    """TS declares no methodology rule, so its methodology axis has no verdict at all."""
    _inventory, report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES + TERMINATION))

    assert report.results_in(ValidationScope.METHODOLOGY) == ()
    assert report.methodology_status is ValidationStatus.UNKNOWN


def test_a_checked_scope_still_reports_its_verdict(tmp_path: Path) -> None:
    """UNKNOWN means "not examined", so attempting a declared check must be unaffected."""
    _inventory, report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES + TERMINATION))

    assert report.results_in(ValidationScope.EXECUTION)
    assert report.execution_status is ValidationStatus.PASS


def test_an_empty_scope_is_rendered_rather_than_omitted(tmp_path: Path) -> None:
    """A reader must be able to see that no methodology check ran."""
    from qcjudge.render import report_to_text

    _inventory, report = _pipeline(_write(tmp_path, HEADER + FREQUENCIES + TERMINATION))
    text = report_to_text(report)

    assert "Methodological checks" in text
    assert "no methodology check was declared" in text


# -- the absorption table, which has three ways to be read wrongly -------------------------


def test_oscillator_strengths_are_read_from_the_named_column(tmp_path: Path) -> None:
    """ORCA 4.x layout: the fourth column is the strength, and spin-forbidden rows follow.

    Ending the table at the first unreadable row would drop every state after it; the
    states here are strengths, then two rows with no strength, then a third strength.
    """
    table = (
        HEADER
        + "         ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS\n"
        + "---------------------------------------------------------------------\n"
        + "State   Energy    Wavelength  fosc         T2        TX        TY        TZ\n"
        + "        (cm-1)      (nm)                 (au**2)    (au)      (au)      (au)\n"
        + "---------------------------------------------------------------------\n"
        + "   1   43167.6    231.7   0.005629700   0.04293  -0.15576  -0.13665  -0.00000\n"
        + "   2   46157.0    216.7   1.165369790   8.31192   2.83128   0.54387   0.00000\n"
        + "   6   25291.1    395.4   spin forbidden (mult=3)\n"
        + "   7   34236.1    292.1   spin forbidden (mult=3)\n"
        + "   8   57338.1    174.4   0.220313769   1.26495  -0.26711  -1.09252  -0.00000\n"
        + "\n"
    )
    result = OrcaOutputParser().parse(_write(tmp_path, table + TERMINATION))
    observation = result.observation(FactKey.OSCILLATOR_STRENGTH)

    assert observation is not None
    assert observation.value == (0.005629700, 1.165369790, 0.220313769)


def test_a_soc_corrected_table_is_never_substituted_for_the_plain_one(
    tmp_path: Path,
) -> None:
    """ORCA 5.0 prints both. The first table carries the strengths and is the one read.

    The corrected table also has a wider state prefix, so reading it would both change which
    quantity is reported and shift the column the value is taken from.
    """
    table = (
        HEADER
        + "         ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS\n"
        + "State   Energy    Wavelength  fosc         T2\n"
        + "        (cm-1)      (nm)                 (au**2)\n"
        + "   1   43167.6    231.7   0.005629700   0.04293\n"
        + "\n"
        + "SPIN ORBIT CORRECTED ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS\n"
        + "   State    Energy  Wavelength   fosc         T2\n"
        + "            (cm-1)    (nm)                  (au**2)\n"
        + "   0   1   21641.4    462.1   0.999999999   0.00000\n"
        + "\n"
    )
    result = OrcaOutputParser().parse(_write(tmp_path, table + TERMINATION))
    observation = result.observation(FactKey.OSCILLATOR_STRENGTH)

    assert observation is not None
    assert observation.value == (0.005629700,)
    assert result.diagnostics.warnings, "the skipped corrected table must be reported"


def test_a_corrected_table_alone_is_a_reader_limitation_not_a_missing_value(
    tmp_path: Path,
) -> None:
    """A SOC-corrected table is a different quantity, so it is not silently substituted."""
    table = (
        HEADER
        + "SOC CORRECTED ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS*\n"
        + "   State    Energy  Wavelength   fosc\n"
        + "   0   1   21641.4    462.1   0.000000000\n"
        + "\n"
    )
    result = OrcaOutputParser().parse(_write(tmp_path, table + TERMINATION))
    observation = result.observation(FactKey.OSCILLATOR_STRENGTH)

    assert observation is None
    reasons = [
        absent.reason
        for absent in result.diagnostics.unavailable
        if absent.key is FactKey.OSCILLATOR_STRENGTH
    ]
    assert reasons


# -- several jobs in one file must not be merged -------------------------------------------


def test_two_frequency_blocks_are_not_merged_into_one_mode_count(
    tmp_path: Path,
) -> None:
    """Each Hessian belongs to its own geometry, so the counts cannot be added.

    Both blocks here hold exactly one imaginary mode. Merged, the count is 2, which the
    contradicting rule turns into ``CONTRADICTED`` -- a refutation of the first-order saddle
    claim, fabricated from an arithmetic mistake.
    """
    job = HEADER + _frequency_block((0.0, -42.31, 120.55)) + TERMINATION
    inventory, report = _pipeline(_write(tmp_path, job + "\n" + job, "two_jobs.out"))

    counts = inventory.facts_by_key(FactKey.FREQUENCY_IMAGINARY_COUNT)
    assert counts and counts[0].value == 1
    modes = inventory.facts_by_key(FactKey.FREQUENCY_CM1)
    assert modes and len(modes[0].value) == 3
    assert report.overall_evidence_status is not AssessmentStatus.CONTRADICTED


def test_a_second_frequency_block_is_reported_rather_than_ignored(
    tmp_path: Path,
) -> None:
    """The other jobs' values are dropped, and a reader is told that they were."""
    job = HEADER + _frequency_block((0.0, -42.31, 120.55)) + TERMINATION
    path = _write(tmp_path, job + "\n" + job, "two_jobs.out")
    result = OrcaOutputParser().parse(path)

    assert any("vibrational frequency" in warning for warning in result.diagnostics.warnings)


def test_one_frequency_block_is_read_without_warning(tmp_path: Path) -> None:
    """The single-job case must stay silent and unchanged."""
    path = _write(
        tmp_path, HEADER + _frequency_block((0.0, -42.31, 120.55)) + TERMINATION, "one.out"
    )
    result = OrcaOutputParser().parse(path)

    assert result.diagnostics.warnings == ()
    observation = result.observation(FactKey.FREQUENCY_CM1)
    assert observation is not None
    assert len(observation.value) == 3


def test_a_block_after_the_last_termination_marker_is_not_read(tmp_path: Path) -> None:
    """A job that never terminated left a partial Hessian, which is not a mode list."""
    text = (
        HEADER
        + _frequency_block((0.0, -42.31, 120.55))
        + TERMINATION
        + HEADER
        + _frequency_block((0.0, -42.31, 120.55, 900.0, 950.0))
    )
    path = _write(tmp_path, text, "interrupted_second.out")
    result = OrcaOutputParser().parse(path)

    observation = result.observation(FactKey.FREQUENCY_CM1)
    assert observation is not None
    assert len(observation.value) == 3, "the unfinished job's modes must not be counted"
    assert any("termination marker" in warning for warning in result.diagnostics.warnings)


# -- the real corpus, which is what exposed the defect ------------------------------------


@pytest.mark.skipif(
    not CONVERGED_GEOMETRY_ONLY.exists(),
    reason="real corpus not fetched; run tools/fetch_benchmark_data.py",
)
def test_real_converged_optimization_without_frequencies_is_insufficient() -> None:
    """The case that exposed the defect, on real ORCA output rather than a fixture.

    ``dvb_gopt.out`` is complete and its optimization converged; it simply never ran a
    frequency job. The audit must report a missing calculation, not an unreadable file.
    """
    parser = OrcaOutputParser()
    result = parser.parse(CONVERGED_GEOMETRY_ONLY)
    facts, absences = facts_from_parse_results(
        (result,), supported_keys=parser.supported_keys
    )
    inventory = EvidenceInventory(facts=facts, unavailable=absences)
    report = audit(ts_question(), inventory)

    assert result.diagnostics.outcome.value == "complete"
    assert report.execution_status is ValidationStatus.PASS
    assert (
        inventory.unavailable_reason(FactKey.FREQUENCY_IMAGINARY_COUNT)
        is UnavailableReason.NOT_PROVIDED
    )
    assert report.overall_evidence_status is AssessmentStatus.INSUFFICIENT


# -- the invariants behind the defect ------------------------------------------------------


def test_the_supported_key_set_never_covers_a_derived_key() -> None:
    """Why the defect happened: derived keys are outside ``supported_keys`` by construction."""
    parser = OrcaOutputParser()
    derived = frozenset(key for key, _unit, _fn, _sources in _DERIVED_FACTS)

    assert derived
    assert not (parser.supported_keys & derived)


def test_every_derived_key_declares_a_source_to_inherit_a_reason_from() -> None:
    """A derived key with no declared source could not inherit a reason at all."""
    for key, _unit, _arithmetic, sources in _DERIVED_FACTS:
        assert sources, f"{key.value} has no declared source to inherit from"


def test_the_protocol_these_tests_exercise_is_the_transition_state_one() -> None:
    assert get_protocol(TS).id == "transition_state"


@pytest.mark.skipif(
    not (CORPUS / "ORCA4.2" / "dvb_td.out").exists(),
    reason="real corpus not fetched; run tools/fetch_benchmark_data.py",
)
def test_real_absorption_tables_yield_strengths_not_wavelengths() -> None:
    """Every real TD file carries an electric-dipole table; all of them were read as empty.

    The table separates its heading from its rows with a separator line and closes with
    another one, so treating a separator as the end of the table stops before any data. The
    5.0 file also carries two SOC-corrected tables, whose headers contain the plain header as
    a substring and whose rows use a wider state prefix.
    """
    values = {
        "ORCA2.9/dvb_td.out": (0.002427413, 0.943346391, 0.0, 0.0, 0.000580852),
        "ORCA4.0/dvb_td.out": (0.005629700, 1.165369790, 0.0, 0.220313769, 0.0),
        "ORCA4.2/dvb_td.out": (0.005629700, 1.165369790, 0.0, 0.220313769, 0.0),
        "ORCA5.0/dvb_soc.log": (
            0.410162235,
            0.540842405,
            0.0,
            0.322705071,
            0.0,
            0.0,
            4.7073e-05,
            0.051117005,
            0.000142635,
            0.0,
        ),
    }
    parser = OrcaOutputParser()
    for relative, expected in values.items():
        path = CORPUS / relative
        if not path.exists():
            pytest.skip(f"{relative} is not in the fetched corpus")
        result = parser.parse(path)
        observation = result.observation(FactKey.OSCILLATOR_STRENGTH)
        assert observation is not None, relative
        assert observation.value == expected, relative
        # The SOC-corrected tables in this file must be reported as skipped, not used.
        if relative.endswith("dvb_soc.log"):
            assert result.diagnostics.warnings
            assert 462.1 not in observation.value
            assert 330.0 not in observation.value


@pytest.mark.skipif(
    not (CORPUS / "ORCA4.2" / "dvb_ir.out").exists(),
    reason="real corpus not fetched; run tools/fetch_benchmark_data.py",
)
def test_a_file_of_two_real_jobs_does_not_double_its_mode_count(tmp_path: Path) -> None:
    """Concatenating the same real job twice must not double the modes it reports.

    A doubled count would read as 120 modes for one geometry, and in a file where the two
    jobs disagreed about the imaginary mode it would flip the requirement to
    ``CONTRADICTED``.
    """
    text = (CORPUS / "ORCA4.2" / "dvb_ir.out").read_text(encoding="utf-8", errors="replace")
    single_path = CORPUS / "ORCA4.2" / "dvb_ir.out"
    double_path = _write(tmp_path, text.rstrip("\n") + "\n\n" + text, "doubled.out")

    parser = OrcaOutputParser()
    single = parser.parse(single_path).observation(FactKey.FREQUENCY_CM1)
    double = parser.parse(double_path).observation(FactKey.FREQUENCY_CM1)

    assert single is not None and double is not None
    assert len(single.value) == 60
    assert double.value == single.value

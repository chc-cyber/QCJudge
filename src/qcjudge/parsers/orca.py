"""Conservative parser for a small, explicitly declared subset of ORCA text output.

Design rules this module follows:

* It reports only what it can point at. Every observation carries a line number.
* It never guesses. Where a value could be one of several things, the key is reported as
  ``AMBIGUOUS_MATCH`` rather than resolved by preference.
* It distinguishes what it cannot read from what was never computed. A selected job that
  ended without a normal-termination marker or an explicit transition to the next compound
  job is ``TRUNCATED``; a complete job missing a value reports ``NOT_PROVIDED``.
* It reports blocks it recognises but does not read, so its own limitations are visible.
* Every scientific observation belongs to the first job. Later jobs cannot contribute a
  convergence flag, method, Hessian, or excited-state manifold to that job.

The marker strings below are this parser's entire knowledge of ORCA. They were derived by
inspecting real output rather than assumed: ``tests/test_real_orca_output.py`` checks them
against a pinned subset of the ``cclib-data`` corpus, covering ORCA 2.6 through 5.0, when
that corpus has been fetched. Where a construct is version-dependent and the parser cannot
read it, the key is reported as unsupported rather than approximated.

Known limits, deliberate and visible: only the first job and its first excited-state block per
manifold are read. Compound jobs need explicit ``JOB NUMBER`` execution boundaries; ambiguous
compound output is withheld. ``FREQUENCY_EXPECTED_MODE_COUNT`` is not attempted, because deriving
3N-6 needs an atom count and a linearity determination that this parser does not make.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import Path

from qcjudge.domain.calculation import (
    Observation,
    ParseDiagnostics,
    ParseOutcome,
    ParseResult,
)
from qcjudge.domain.common import Provenance, UnavailableReason
from qcjudge.domain.evidence import FactKey, ScalarValue, Subject, UnavailableFact

# --------------------------------------------------------------------------------------
# Declared knowledge of ORCA's text output
# --------------------------------------------------------------------------------------

_RECOGNITION_MARKERS = (
    re.compile(r"Program Version\s+[\d.]+"),
    re.compile(r"ORCA TERMINATED NORMALLY"),
    re.compile(r"^\s*\|?\s*\d+>\s*[!#]", re.MULTILINE),
    re.compile(r"\*\s*O\s+R\s+C\s+A\s*\*"),
)

_TERMINATION_MARKER = "ORCA TERMINATED NORMALLY"
_TERMINATION_LINE = re.compile(
    r"^[ \t]*\**[ \t]*ORCA TERMINATED NORMALLY[ \t]*\**[ \t]*$", re.MULTILINE
)

# Independent runs repeat their startup headings. Compound runs instead print one input
# echo for every job followed by explicitly numbered execution sections. These are actual
# output boundaries, unlike an echoed $new_job directive, which only declares future work.
_RUN_HEADINGS = (
    re.compile(r"^[ \t]*\*[ \t]*O[ \t]+R[ \t]+C[ \t]+A[ \t]*\*[ \t]*$", re.MULTILINE),
    re.compile(r"^[ \t]*Program Version[ \t]+[\d.]+[^\n]*$", re.MULTILINE),
    re.compile(r"^[ \t]*INPUT FILE[ \t]*$", re.MULTILINE),
)
_COMPOUND_JOB = re.compile(
    r"^[ \t]*\${2,}[ \t]*JOB NUMBER[ \t]+(?P<number>\d+)[ \t]*\${2,}[ \t]*$",
    re.MULTILINE,
)
_NEW_JOB_DIRECTIVE = re.compile(
    r"^[ \t]*(?:\|?[ \t]*\d+>[ \t]*)?\$new_job\b[^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)

_VERSION = re.compile(r"Program Version\s+([\d.]+)")

# ORCA pads these lines with a dot leader, e.g. "Total Charge    Charge    ....    0".
_CHARGE = re.compile(r"Total Charge\s+Charge[\s.]*(-?\d+)", re.IGNORECASE)
_MULTIPLICITY = re.compile(r"Multiplicity\s+Mult[\s.]*(\d+)", re.IGNORECASE)
# Fallback: the coordinate block echoes the system as "* xyz <charge> <multiplicity>".
_XYZ_LINE = re.compile(r"^\s*\|?\s*\d+>\s*\*\s*xyz\s+(-?\d+)\s+(\d+)", re.MULTILINE)
_SPIN = re.compile(r"<S\*\*2>\s*[:=]\s*(-?[\d.]+)")

# ORCA states the basis it actually used, which is more reliable than reading a keyword.
_PRINTED_BASIS = re.compile(r"utilizes the basis:\s*(\S+)", re.IGNORECASE)

# e.g. "   0:       0.00 cm**-1"
_FREQUENCY = re.compile(r"^\s*(\d+):\s+(-?[\d.]+)\s+cm\*\*-1", re.MULTILINE)
# The block those mode lines belong to; a file may contain several such blocks.
_FREQUENCY_BLOCK = re.compile(r"^[ \t]*VIBRATIONAL FREQUENCIES[ \t]*$", re.MULTILINE)

# e.g. "STATE  1:  E=   0.196686 au      5.352 eV    43167.6 cm**-1"
_EXCITED_BLOCK = re.compile(r"EXCITED STATES\s*\(\s*(SINGLETS|TRIPLETS)\s*\)", re.IGNORECASE)
_STATE_LINE = re.compile(
    r"STATE\s+(\d+):\s+E=\s*(-?[\d.]+)\s+au\s+(-?[\d.]+)\s+eV", re.IGNORECASE
)

# The electric-dipole absorption table. The header must match a whole line: ORCA prints
# several related tables, and two of them contain this phrase as a substring --
# "SPIN ORBIT CORRECTED ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS" and
# "SOC CORRECTED ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS*" -- with
# different row layouts and different numbers. A substring search silently reads one of those
# instead, so the table is located by an exact whole-line header.
_ABSORPTION_HEADER = re.compile(
    r"^(?P<prefix>[A-Z ]*?)ABSORPTION SPECTRUM VIA TRANSITION "
    r"(ELECTRIC|VELOCITY) DIPOLE MOMENTS(?P<suffix>\**)\s*$",
    re.MULTILINE,
)
_ELECTRIC_DIPOLE_KIND = "ELECTRIC"
# "SOC CORRECTED ..." tables are different quantities for the same states, so the uncorrected
# spectrum is always preferred and a corrected one is never substituted for it.
_ABSORPTION_CORRECTION_MARKERS = ("CORRECTED",)
# The column titles are read rather than assumed, because the number and meaning of the
# leading columns differ between versions: "State Energy Wavelength fosc" in 4.x against
# "State Energy Wavelength fosc" on a two-column state index in the SOC-corrected 5.0 table.
# ``[^\n]*`` rather than ``.*``: without MULTILINE's per-line behaviour the default dot still
# matches a newline, which would let the heading pattern span from one line to another.
_ABSORPTION_COLUMNS = re.compile(r"^[ \t]*State\b[^\n]*\bfosc\b", re.MULTILINE)
_ABSORPTION_SEPARATOR = re.compile(r"^\s*[-=*]{5,}\s*$")
_ROW_NUMBER = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eEdD][+-]?\d+)?$")
# How many consecutive lines without an oscillator strength end the table. A separator is
# not a terminator on its own: ORCA prints one after the heading and another before the next
# table, so a single one of them sits *before* the data rather than after it.
_ABSORPTION_ROWS_WITHOUT_VALUE_BEFORE_END = 3

_INPUT_ECHO = re.compile(r"^\s*\|?\s*\d+>\s*([!#].*)$", re.MULTILINE)

_SCF_SUCCESS = ("SCF CONVERGED AFTER", "SCF CONVERGED")
_SCF_FAILURE = ("SCF NOT CONVERGED", "SCF CONVERGENCE FAILURE")
_OPT_SUCCESS = ("THE OPTIMIZATION HAS CONVERGED", "OPTIMIZATION RUN DONE")
_OPT_FAILURE = (
    "THE OPTIMIZATION DID NOT CONVERGE",
    "OPTIMIZATION DID NOT CONVERGE",
)

_BASIS_PREFIXES = (
    "def2",
    "ma-def2",
    "cc-pv",
    "aug-cc-pv",
    "d-aug-cc-pv",
    "may-cc-pv",
    "6-31g",
    "6-311g",
    "6-31++g",
    "3-21g",
    "sto-",
    "pcseg-",
    "pc-",
    "sarc-",
    "x2c-",
    "tzvp",
    "tzvpp",
    "qzvp",
    "lanl",
    "sdd",
)

# Never a method name.
_JOB_KEYWORDS = frozenset(
    {
        "opt",
        "optts",
        "optx",
        "freq",
        "numfreq",
        "sp",
        "engrad",
        "numgrad",
        "tightscf",
        "verytightscf",
        "extremescf",
        "slowconv",
        "normalconv",
        "rijcosx",
        "rijonx",
        "rik",
        "rij",
        "ri",
        "sym",
        "nosym",
        "usesym",
        "tightopt",
        "looseopt",
        "verytightopt",
        "nofrozencore",
        "frozencore",
        "noautostart",
        "defgrid2",
        "defgrid3",
        "autoaux",
        "miniprint",
        "smallprint",
        "normalprint",
        "largeprint",
        "printlevel",
        "noprint",
        "d2",
        "d3",
        "d3bj",
        "d3zero",
        "d4",
        "smd",
        "cpcm",
        "cosmo",
    }
)

# A spin treatment rather than a functional, so it is only taken as the method when nothing
# else remains -- which is what "! RHF" means, and what "! RKS B3LYP" does not.
_SPIN_KEYWORDS = frozenset({"rks", "uks", "roks", "rohf", "rhf", "uhf"})

# Blocks the parser recognises but deliberately does not read. Declared as data so the
# limitation is inspectable rather than implied by omission.
_UNREAD_BLOCKS = (
    ("mulliken population analysis", "MULLIKEN ATOMIC CHARGES"),
    ("loewdin population analysis", "LOEWDIN ATOMIC CHARGES"),
    ("orbital energies", "ORBITAL ENERGIES"),
    ("cartesian coordinates", "CARTESIAN COORDINATES (ANGSTROEM)"),
    ("scf gradients", "SCF GRADIENTS"),
    ("ir spectrum", "IR SPECTRUM"),
    ("hirshfeld population analysis", "HIRSHFELD ANALYSIS"),
)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def _line_number(starts: list[int], offset: int) -> int:
    return bisect_right(starts, offset)


def _find(text: str, marker: str) -> int | None:
    match = re.search(re.escape(marker), text, re.IGNORECASE)
    return None if match is None else match.start()


def _mask_region(text: str, start: int, end: int) -> str:
    """Hide another job's input without moving any source line or character offset."""
    # A non-whitespace mask also prevents older row patterns using \s* from scanning
    # thousands of blank input lines repeatedly in large compound exports.
    return text[:start] + re.sub(r"[^\r\n]", "~", text[start:end]) + text[end:]


def _mask_compound_basis(text: str, execution_start: int) -> str:
    """Do not borrow a successor's basis from the shared compound preamble.

    ORCA can print basis setup for every job before any execution starts. The first
    printed basis is usable only when it agrees with the first job's own unique basis
    keyword; otherwise the usual input-keyword fallback remains, or the basis is unknown.
    A basis printed inside the selected execution is unaffected.
    """
    requested = _distinct(
        [
            token
            for match in _INPUT_ECHO.finditer(text, 0, execution_start)
            if match.group(1).startswith("!")
            for token in match.group(1).lstrip("!").split()
            if _is_basis(token)
        ]
    )
    printed = list(_PRINTED_BASIS.finditer(text, 0, execution_start))
    for index in range(len(printed) - 1, -1, -1):
        match = printed[index]
        if index == 0 and len(requested) == 1 and match.group(1).lower() == requested[0].lower():
            continue
        text = _mask_region(text, match.start(), match.end())
    return text


def _has_later_job_output(text: str) -> bool:
    """Recognise scientific output after a run, allowing its ordinary timing footer."""
    patterns = (
        *_RUN_HEADINGS,
        _COMPOUND_JOB,
        _NEW_JOB_DIRECTIVE,
        _FREQUENCY_BLOCK,
        _EXCITED_BLOCK,
        _ABSORPTION_HEADER,
        _CHARGE,
        _MULTIPLICITY,
        _INPUT_ECHO,
        _SPIN,
        _PRINTED_BASIS,
        _TERMINATION_LINE,
    )
    return any(pattern.search(text) for pattern in patterns) or any(
        _find(text, marker) is not None
        for marker in (*_SCF_SUCCESS, *_SCF_FAILURE, *_OPT_SUCCESS, *_OPT_FAILURE)
    )


def _first_job(
    text: str,
) -> tuple[str, ParseOutcome, tuple[str, ...], bool]:
    """Select one execution, preserving offsets and never borrowing its successor's end.

    The final flag means compound work was declared but its executed jobs cannot be
    separated. Identity may still be recorded, but scientific values must be withheld.
    """
    terminations = list(_TERMINATION_LINE.finditer(text))
    termination = terminations[0] if terminations else None
    repeated = [
        matches[1].start()
        for heading in _RUN_HEADINGS
        if len(matches := list(heading.finditer(text))) > 1
    ]
    end = min(repeated, default=len(text))
    completed = termination is not None and termination.start() < end
    if completed and termination is not None:
        end = termination.end()

    # Restrict compound detection to this independent run: a compound successor must not
    # retroactively change the interpretation of the selected first run.
    compound = list(_COMPOUND_JOB.finditer(text, 0, end))
    directive = _NEW_JOB_DIRECTIVE.search(text, 0, end)
    ambiguous = (directive is not None and not compound) or (
        bool(compound) and compound[0].group("number") != "1"
    )
    if len(compound) > 1:
        end = compound[1].start()
        # ORCA starting the next numbered job is an explicit end of the first execution,
        # even when a later job was interrupted before the entire compound run terminated.
        completed = True

    selected = text[:end]
    if directive is not None and compound and directive.start() < compound[0].start():
        # Later jobs' echoed charge, multiplicity, and keywords are future inputs, not
        # observations of the first execution. Keep the common preamble and first input.
        selected = _mask_region(selected, directive.start(), compound[0].start())
    if compound:
        selected = _mask_compound_basis(selected, compound[0].start())

    warnings: list[str] = []
    if ambiguous:
        warnings.append(
            "The file contains compound work, but the first JOB NUMBER execution boundary "
            "could not be identified. Scientific observations were withheld because "
            "they cannot be attributed to one job."
        )
    elif end < len(text) and _has_later_job_output(text[end:]):
        warnings.append(
            "The file contains more than one job; only the first execution was read, up to "
            "its termination marker or explicit job boundary. Later convergence, method, "
            "frequency, and excited-state output was ignored."
        )
        if _FREQUENCY_BLOCK.search(text[end:]):
            warnings.append(
                "Later vibrational frequency blocks were ignored at the first job's "
                "termination marker or execution boundary."
            )
    outcome = ParseOutcome.COMPLETE if completed else ParseOutcome.TRUNCATED
    return selected, outcome, tuple(warnings), ambiguous


def _is_basis(token: str) -> bool:
    lowered = token.lower()
    return any(lowered.startswith(prefix) for prefix in _BASIS_PREFIXES)


def _distinct(tokens: list[str]) -> list[str]:
    """Collapse repeats, since repetition is not ambiguity.

    A file holding two hundred identical jobs names two hundred identical methods, and
    reporting that as ambiguous would be a false alarm.
    """
    seen: dict[str, str] = {}
    for token in tokens:
        seen.setdefault(token.lower(), token)
    return list(seen.values())


def _is_corrected_absorption_table(match: re.Match[str]) -> bool:
    """Whether the table header marks a corrected spectrum rather than the plain one."""
    marker = f"{match.group('prefix')}{match.group('suffix')}"
    return any(name in marker.upper() for name in _ABSORPTION_CORRECTION_MARKERS)


def _read_absorption_table(text: str, start: int) -> tuple[int | None, list[float]]:
    """Read oscillator strengths from the absorption table that begins at ``start``.

    Returns the offset of the first data row and the strengths in table order, or ``None``
    with an empty list when the table has no readable heading or rows.

    The oscillator-strength column is located from the table's own heading row and then
    counted from the right, because the number of leading index columns varies with the ORCA
    version. Rows whose column holds something other than a number -- ``spin forbidden``, for
    one -- are skipped rather than treated as the end of the table.
    """
    body = text[start:]
    heading = _ABSORPTION_COLUMNS.search(body)
    if heading is None:
        return None, []

    lines = body.splitlines(keepends=True)
    offset = 0
    heading_index = -1
    for index, line in enumerate(lines):
        if offset >= heading.start():
            heading_index = index
            break
        offset += len(line)
    if heading_index < 0:
        return None, []

    heading_line = lines[heading_index]
    fosc_column = heading_line.split().index("fosc")
    base = start + sum(len(line) for line in lines[: heading_index + 1])

    values: list[float] = []
    first_row: int | None = None
    row_offset = base
    consecutive_unreadable = 0
    for line in lines[heading_index + 1 :]:
        stripped = line.strip()
        if not stripped and first_row is not None:
            break
        # The units row reads "(cm-1) (nm) (au**2) ..."; the separators are dashes.
        if stripped.startswith("(") or _ABSORPTION_SEPARATOR.match(line):
            row_offset += len(line)
            continue
        row = _absorption_row_value(stripped, fosc_column)
        if row is None:
            if first_row is not None:
                consecutive_unreadable += 1
                if consecutive_unreadable >= _ABSORPTION_ROWS_WITHOUT_VALUE_BEFORE_END:
                    break
        else:
            consecutive_unreadable = 0
            if first_row is None:
                first_row = row_offset
            values.append(row)
        row_offset += len(line)
    return first_row, values


def _absorption_row_value(line: str, fosc_column: int) -> float | None:
    """The oscillator strength in one absorption row, or None when it carries none.

    ``fosc_column`` is the strength's field index on the heading row, and it holds on a data
    row too: the only field whose width changes between the heading and the data is the state
    prefix, and ORCA widens the heading's own state column to keep the rest aligned. Rows
    whose field there holds something other than a number -- ``spin forbidden``, for one --
    return None and are skipped rather than ending the table.
    """
    tokens = line.split()
    if fosc_column >= len(tokens):
        return None
    candidate = tokens[fosc_column]
    if not _ROW_NUMBER.match(candidate):
        return None
    try:
        return float(candidate.replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


class OrcaOutputParser:
    """Reads a declared subset of ORCA output. Reports, never concludes."""

    name = "qcjudge.orca"
    version = "0.4.0"

    @property
    def supported_keys(self) -> frozenset[FactKey]:
        return frozenset(
            {
                FactKey.SOFTWARE_NAME,
                FactKey.SOFTWARE_VERSION,
                FactKey.METHOD_NAME,
                FactKey.BASIS_NAME,
                FactKey.CHARGE,
                FactKey.MULTIPLICITY,
                FactKey.SCF_CONVERGED,
                FactKey.GEOMETRY_CONVERGED,
                FactKey.FREQUENCY_CM1,
                FactKey.SINGLET_STATE_ENERGY_EV,
                FactKey.TRIPLET_STATE_ENERGY_EV,
                FactKey.OSCILLATOR_STRENGTH,
                FactKey.SPIN_EXPECTATION,
            }
        )

    def parse(self, path: Path) -> ParseResult:
        text = path.read_text(encoding="utf-8", errors="replace")
        source_file = str(path)
        extracted_at = datetime.now(UTC)
        if not any(marker.search(text) for marker in _RECOGNITION_MARKERS):
            return ParseResult(
                source_file=source_file,
                producer=self.name,
                producer_version=self.version,
                extracted_at=extracted_at,
                diagnostics=ParseDiagnostics(
                    outcome=ParseOutcome.UNRECOGNISED,
                    warnings=(
                        "No ORCA banner, version string, input echo, or termination marker "
                        "was found, so the format was not recognised.",
                    ),
                ),
            )

        selected, outcome, boundary_warnings, ambiguous = _first_job(text)
        collector = _Collector(
            source_file, self.name, self.version, _line_starts(text), outcome, extracted_at
        )
        collector.warnings.extend(boundary_warnings)

        self._collect_identity(collector, selected)
        if ambiguous:
            for key in sorted(self.supported_keys, key=lambda item: item.value):
                if key in {FactKey.SOFTWARE_NAME, FactKey.SOFTWARE_VERSION}:
                    continue
                collector.unavailable(
                    key,
                    UnavailableReason.UNSUPPORTED_CONSTRUCT,
                    "Compound jobs were declared, but their execution boundaries could not "
                    "be identified, so this value cannot be assigned to one calculation.",
                )
        else:
            self._collect_system(collector, selected)
            self._collect_convergence(collector, selected)
            self._collect_spin(collector, selected)
            self._collect_frequencies(collector, selected)
            self._collect_excited_states(collector, selected)
            self._collect_oscillator_strengths(collector, selected)
            self._collect_method_and_basis(collector, selected)

        return ParseResult(
            source_file=source_file,
            producer=self.name,
            producer_version=self.version,
            extracted_at=extracted_at,
            observations=tuple(collector.observations),
            diagnostics=ParseDiagnostics(
                outcome=outcome,
                unavailable=tuple(collector.absences),
                unparsed_regions=tuple(
                    label for label, marker in _UNREAD_BLOCKS if marker in text
                ),
                warnings=tuple(collector.warnings),
            ),
        )

    # -- individual observations ------------------------------------------------------

    def _collect_identity(self, collector: _Collector, text: str) -> None:
        version = _VERSION.search(text)
        if version is None:
            collector.unavailable(
                FactKey.SOFTWARE_VERSION,
                collector.default_reason,
                "No program version string was found.",
            )
            return
        collector.observe(FactKey.SOFTWARE_VERSION, version.group(1), None, version.start())
        collector.observe(FactKey.SOFTWARE_NAME, "ORCA", None, version.start())

    def _collect_system(self, collector: _Collector, text: str) -> None:
        """Read charge and multiplicity, preferring the printed system block.

        The printed block is authoritative output; the coordinate block echoes what was
        requested and is used only when the printed block is absent, as it is in some newer
        versions under reduced print levels.
        """
        self._system_value(
            collector, text, FactKey.CHARGE, _CHARGE, 1, "the total charge"
        )
        self._system_value(
            collector, text, FactKey.MULTIPLICITY, _MULTIPLICITY, 2, "the multiplicity"
        )

    def _system_value(
        self,
        collector: _Collector,
        text: str,
        key: FactKey,
        printed: re.Pattern[str],
        xyz_group: int,
        label: str,
    ) -> None:
        match = printed.search(text)
        if match is not None:
            collector.observe(key, int(match.group(1)), None, match.start())
            return
        echo = _XYZ_LINE.search(text)
        if echo is not None:
            collector.observe(key, int(echo.group(xyz_group)), None, echo.start())
            collector.warn(
                f"{key.value} was read from the input echo rather than the printed system "
                "block, which this file does not appear to contain."
            )
            return
        collector.unavailable(
            key,
            collector.default_reason,
            f"Neither the printed system block nor the input echo reported {label}.",
        )

    def _collect_convergence(self, collector: _Collector, text: str) -> None:
        collector.flag(FactKey.SCF_CONVERGED, text, _SCF_SUCCESS, _SCF_FAILURE)
        collector.flag(FactKey.GEOMETRY_CONVERGED, text, _OPT_SUCCESS, _OPT_FAILURE)

    def _collect_spin(self, collector: _Collector, text: str) -> None:
        matches = list(_SPIN.finditer(text))
        if not matches:
            collector.unavailable(
                FactKey.SPIN_EXPECTATION,
                collector.default_reason,
                "No expectation value of S**2 was found.",
            )
            return
        collector.observe(
            FactKey.SPIN_EXPECTATION,
            tuple(float(match.group(1)) for match in matches),
            None,
            matches[0].start(),
        )

    def _collect_frequencies(self, collector: _Collector, text: str) -> None:
        """Read one vibrational frequency block, never a merge of several.

        A file may hold more than one job, and each job's Hessian belongs to its own geometry.
        Concatenating the mode lists would produce a mode count that describes no calculation:
        two jobs with one imaginary mode each would be counted as two, and because the
        imaginary count feeds a contradicting rule, the audit would report the requirement as
        ``CONTRADICTED`` -- a scientific conclusion fabricated from an arithmetic mistake.
        The first block is read and the rest are reported, matching how excited-state blocks
        are handled.
        """
        blocks = list(_FREQUENCY_BLOCK.finditer(text))
        if not blocks:
            collector.unavailable(
                FactKey.FREQUENCY_CM1,
                collector.default_reason,
                "No vibrational frequency block was found.",
            )
            return

        # A block that appears after the last termination marker belongs to a job that did not
        # finish, so it is not a whole Hessian and must not be counted.
        terminated_at = text.rfind(_TERMINATION_MARKER)
        readable = [
            block for block in blocks if terminated_at < 0 or block.start() < terminated_at
        ]
        if not readable:
            collector.unavailable(
                FactKey.FREQUENCY_CM1,
                collector.default_reason,
                "The only vibrational frequency block follows the last termination marker, so "
                "it belongs to a job that did not run to completion.",
            )
            return
        if len(readable) < len(blocks):
            collector.warn(
                f"{len(blocks) - len(readable)} vibrational frequency block(s) appear after "
                "the last termination marker and were not read."
            )

        block = readable[0]
        end = blocks[blocks.index(block) + 1].start() if len(blocks) > 1 else len(text)
        matches = list(_FREQUENCY.finditer(text, block.end(), end))
        if not matches:
            collector.unavailable(
                FactKey.FREQUENCY_CM1,
                collector.default_reason,
                "The vibrational frequency block contained no parsable mode lines.",
            )
            return
        if len(readable) > 1:
            collector.warn(
                f"{len(readable)} vibrational frequency blocks were found; only the first is "
                "read, because each belongs to its own geometry and merging them would count "
                "modes that no single calculation produced."
            )
        collector.observe(
            FactKey.FREQUENCY_CM1,
            tuple(float(match.group(2)) for match in matches),
            "cm**-1",
            matches[0].start(),
            collector.span(matches[0].start(), matches[-1].start()),
        )

    def _collect_excited_states(self, collector: _Collector, text: str) -> None:
        """Read the singlet and triplet manifolds into separate keys.

        Keeping them apart matters: a single flat list of excitation energies cannot say
        which state belongs to which manifold, and a singlet-triplet gap read from a merged
        list would be meaningless.
        """
        blocks = list(_EXCITED_BLOCK.finditer(text))
        if not blocks:
            for key in (FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV):
                collector.unavailable(
                    key,
                    collector.default_reason,
                    "No excited-state block was found.",
                )
            return

        seen: set[FactKey] = set()
        for index, block in enumerate(blocks):
            manifold = block.group(1).upper()
            end = blocks[index + 1].start() if index + 1 < len(blocks) else len(text)
            states = list(_STATE_LINE.finditer(text, block.end(), end))
            key = (
                FactKey.SINGLET_STATE_ENERGY_EV
                if manifold == "SINGLETS"
                else FactKey.TRIPLET_STATE_ENERGY_EV
            )
            if not states:
                collector.unavailable(
                    key,
                    collector.default_reason,
                    f"The {manifold.lower()} block contained no parsable state lines.",
                )
                continue
            if key in seen:
                collector.warn(
                    f"A second {manifold.lower()} block was found and ignored; only the "
                    "first is read."
                )
                continue
            seen.add(key)
            collector.observe(
                key,
                tuple(float(match.group(3)) for match in states),
                "eV",
                states[0].start(),
                collector.span(states[0].start(), states[-1].start()),
            )

        for key in (FactKey.SINGLET_STATE_ENERGY_EV, FactKey.TRIPLET_STATE_ENERGY_EV):
            if key not in seen and not any(a.key is key for a in collector.absences):
                collector.unavailable(
                    key,
                    collector.default_reason,
                    "No excited-state block for this manifold was found.",
                )

    def _collect_oscillator_strengths(self, collector: _Collector, text: str) -> None:
        """Read the electric-dipole absorption table.

        Three things make this table easy to read wrongly, and all three are silent:

        * ORCA prints a velocity-dipole table too, and in 5.0 two further SOC-corrected
          tables whose headers contain the electric-dipole header as a substring. The header
          is therefore matched as a whole line, never as a substring.
        * The meaning of the leading columns changes between versions. In 4.x a row is
          ``State Energy Wavelength fosc ...``; in the 5.0 SOC-corrected table it is
          ``State i j Energy Wavelength fosc ...``. Counting columns blindly reads the
          wavelength as the oscillator strength, which is why the column is located by
          reading the ``fosc`` heading and then aligning on the numeric fields to its left.
        * Rows such as ``6  25291.1  395.4  spin forbidden (mult=3)`` carry no oscillator
          strength. Ending the table at the first such row drops every state after it, so
          unreadable rows are skipped and the table continues to its separator.
        """
        tables = list(_ABSORPTION_HEADER.finditer(text))
        if not tables:
            collector.unavailable(
                FactKey.OSCILLATOR_STRENGTH,
                collector.default_reason,
                "No absorption spectrum block was found.",
            )
            return

        electric = [
            item
            for item in tables
            if item.group(2) == _ELECTRIC_DIPOLE_KIND
            and not _is_corrected_absorption_table(item)
        ]
        if not electric:
            collector.unavailable(
                FactKey.OSCILLATOR_STRENGTH,
                collector.default_reason,
                "No uncorrected electric-dipole absorption table was found; the "
                "electric-dipole table carries the oscillator strengths, and any "
                "SOC-corrected table is a different quantity.",
            )
            return

        # Document order: ORCA prints the uncorrected spectrum before the SOC-corrected ones.
        header = electric[0]
        offset, values = _read_absorption_table(text, header.end())
        if offset is None or not values:
            collector.unavailable(
                FactKey.OSCILLATOR_STRENGTH,
                collector.default_reason,
                "The absorption spectrum block contained no parsable oscillator strengths.",
            )
            return
        corrected = sum(1 for item in tables if _is_corrected_absorption_table(item))
        if corrected:
            collector.warn(
                f"{corrected} SOC-corrected absorption table(s) are present and were not "
                "read; they report different quantities for the same states."
            )
        collector.observe(FactKey.OSCILLATOR_STRENGTH, tuple(values), None, offset)

    def _collect_method_and_basis(self, collector: _Collector, text: str) -> None:
        """Read the command line of the first job in the file.

        A file may echo several jobs back to back. Only the first command-line run is read,
        because mixing jobs would produce a method that describes none of them, and the
        merge is reported rather than performed silently.
        """
        all_echoes = list(_INPUT_ECHO.finditer(text))
        keywords: list[str] = []
        first_offset: int | None = None
        started = False
        consumed = 0
        for match in all_echoes:
            line = match.group(1)
            if not line.startswith("!"):
                if started:
                    break
                consumed += 1
                continue
            started = True
            if first_offset is None:
                first_offset = match.start()
            keywords.extend(line.lstrip("!").split())
            consumed += 1

        if not started or first_offset is None or not keywords:
            for key in (FactKey.METHOD_NAME, FactKey.BASIS_NAME):
                collector.unavailable(
                    key,
                    UnavailableReason.UNSUPPORTED_CONSTRUCT,
                    "No ORCA command line was echoed, and neither value is read from "
                    "anywhere else.",
                )
            return
        if any(item.group(1).startswith("!") for item in all_echoes[consumed:]):
            collector.warn(
                "The file echoes more than one job; only the first command line was read, "
                "so the method and basis describe that job alone."
            )

        printed_basis = _PRINTED_BASIS.search(text)
        basis_tokens = _distinct([token for token in keywords if _is_basis(token)])
        if printed_basis is not None:
            collector.observe(
                FactKey.BASIS_NAME, printed_basis.group(1), None, printed_basis.start()
            )
        elif len(basis_tokens) == 1:
            collector.observe(FactKey.BASIS_NAME, basis_tokens[0], None, first_offset)
        else:
            collector.unavailable(
                FactKey.BASIS_NAME,
                UnavailableReason.AMBIGUOUS_MATCH
                if basis_tokens
                else UnavailableReason.UNSUPPORTED_CONSTRUCT,
                "The file neither states the basis it used nor names exactly one "
                "basis-set keyword. "
                + (
                    f"Several keywords were present: {basis_tokens}."
                    if basis_tokens
                    else "No recognised basis-set keyword was present."
                ),
            )

        candidates = _distinct(
            [
                token
                for token in keywords
                if not _is_basis(token) and token.lower() not in _JOB_KEYWORDS
            ]
        )
        resolved = [
            token for token in candidates if token.lower() not in _SPIN_KEYWORDS
        ] or candidates
        if len(resolved) == 1:
            collector.observe(FactKey.METHOD_NAME, resolved[0], None, first_offset)
        else:
            collector.unavailable(
                FactKey.METHOD_NAME,
                UnavailableReason.AMBIGUOUS_MATCH
                if resolved
                else UnavailableReason.UNSUPPORTED_CONSTRUCT,
                "The command line contained "
                + (
                    f"several candidate method keywords: {resolved}."
                    if resolved
                    else "no method keyword this parser recognises."
                ),
            )


class _Collector:
    """Accumulates observations and absences for one file."""

    def __init__(
        self,
        source_file: str,
        producer: str,
        producer_version: str,
        starts: list[int],
        outcome: ParseOutcome,
        extracted_at: datetime,
    ) -> None:
        self.source_file = source_file
        self.starts = starts
        self.observations: list[Observation] = []
        self.absences: list[UnavailableFact] = []
        self.warnings: list[str] = []
        self._provenance = Provenance(
            source_file=source_file,
            producer=producer,
            producer_version=producer_version,
            extracted_at=extracted_at,
        )
        if outcome is ParseOutcome.TRUNCATED:
            self.default_reason = UnavailableReason.FILE_TRUNCATED
            self.warnings.append(
                "The selected job does not contain ORCA's normal-termination marker, so it appears "
                "to be truncated; missing values are reported as unreadable rather than as "
                "not provided."
            )
        else:
            self.default_reason = UnavailableReason.NOT_PROVIDED

    def span(self, first_offset: int, last_offset: int) -> str:
        first = _line_number(self.starts, first_offset)
        last = _line_number(self.starts, last_offset)
        return f"line {first}" if first == last else f"lines {first}-{last}"

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def observe(
        self,
        key: FactKey,
        value: ScalarValue | tuple[ScalarValue, ...],
        unit: str | None,
        offset: int,
        location: str | None = None,
    ) -> None:
        resolved = location or f"line {_line_number(self.starts, offset)}"
        self.observations.append(
            Observation(key=key, value=value, unit=unit, location=resolved)
        )

    def unavailable(self, key: FactKey, reason: UnavailableReason, message: str) -> None:
        """Record a key the parser could not produce, with its reason and an explanation.

        The calculation is not named here: naming is the projection's job, and the parser
        has no business deciding how a file is identified downstream.
        """
        self.absences.append(
            UnavailableFact(
                key=key,
                reason=reason,
                provenance=self._provenance,
                subject=Subject(calculation_id=""),
                message=message,
            )
        )

    def flag(
        self,
        key: FactKey,
        text: str,
        successes: tuple[str, ...],
        failures: tuple[str, ...],
    ) -> None:
        for marker in failures:
            offset = _find(text, marker)
            if offset is not None:
                self.observe(key, False, None, offset)
                return
        for marker in successes:
            offset = _find(text, marker)
            if offset is not None:
                self.observe(key, True, None, offset)
                return
        self.unavailable(
            key,
            self.default_reason,
            "Neither a success marker nor a failure marker was found.",
        )

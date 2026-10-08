# QCJudge

[![CI](https://github.com/chc-cyber/QCJudge/actions/workflows/ci.yml/badge.svg)](https://github.com/chc-cyber/QCJudge/actions/workflows/ci.yml)

QCJudge is an early-stage, open-source scientific evidence auditor for computational
chemistry. It asks whether the available computational results are appropriate and
sufficient evidence for a specified research question—not merely whether a job ran,
and not whether a scientific conclusion is ultimately true.

V0.1 is deliberately restricted to three question families:

- charge-transfer excitation character;
- TADF potential;
- transition-state validation.

The deterministic core keeps execution validity, methodological validity, and
scientific evidence adequacy separate. Facts retain provenance, missing information
remains unknown, and reports expose an evidence graph rather than collapsing the audit
to a score.

QCJudge is narrower than computational-chemistry agents and workflow orchestrators.
Its intended contribution is prospective, question-centered assessment of whether a
researcher's existing computational evidence is adequate for the question they intend
to answer.

## Status

The current version is `0.1.0.dev2`, a pre-alpha development preview. A stable
release has not been published. M0–M4 are complete; M5 hardening and release validation are in
progress. Local tests, the pinned ORCA corpus, and an independently installed wheel
have been checked on Windows with Python 3.12. The public repository is
[chc-cyber/QCJudge](https://github.com/chc-cyber/QCJudge). The
[first GitHub Actions run](https://github.com/chc-cyber/QCJudge/actions/runs/37732697580)
passed all seven jobs for commit `272d2de`: lint and strict types, plus six
Python 3.12/3.13 combinations across Linux, macOS, and Windows. Each test job
fetched the pinned corpus, ran the tests, built and installed the wheel, and
passed the isolated CLI smoke check.

The evidence kernel and the parser boundary are in place: a three-level reasoning chain from
question through hypothesis and claim to evidence requirement, registered vocabularies instead
of free strings, a protocol graph with alternative-evidence groups and dependency gating, a
validator registry keyed by `implementation_key`, three independent validation axes
(execution, structure, methodology), and a self-contained audit report with a trace graph and
a stable JSON schema.

Evidence strength is declared by the protocol, not written into extraction code: a protocol
states which evidence follows from which facts and how strong it is, and the engine applies
that. Parsers report observations with line locations and a reason for every value they could
not read, so "we could not read it" never becomes "it was not there".

The acceptance corpus proves the defining claim on every row: a calculation can be
technically successful while the evidence is still insufficient, contradicted, or
unassessable. The deterministic engine contains no requirement or rule identifiers at all.

The ORCA subset is validated against real output from ORCA 2.6 through 5.0, fetched on demand
by `tools/fetch_benchmark_data.py` and verified against a pinned manifest; no third-party data
is committed to this repository. Worked examples under [`examples/`](examples/README.md)
show what an audit concludes and what it refuses to. The adapter seam is implemented; current
work is M5 hardening and release validation. See [the working plan](docs/v0.1-plan.md) for the debt
register and milestone gates.

## Install locally

Get the source from [the public repository](https://github.com/chc-cyber/QCJudge):

```console
git clone https://github.com/chc-cyber/QCJudge.git
cd QCJudge
```

An existing checkout or a source archive from that repository can also be used.
Run the installation commands from the root containing `pyproject.toml` and
`examples/`. The project has not published a PyPI package; the instructions below
install from source or a local wheel.

QCJudge requires Python 3.12 or newer; the configured release checks target Python
3.12 and 3.13. The package has no runtime dependencies. Check that the interpreter
reports its version, then create an isolated environment and install from source.

Windows PowerShell:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
```

If the Windows Python launcher is unavailable, use the full path to a working
Python 3.12 or 3.13 interpreter in place of `py -3.12`.

Linux or macOS:

```sh
python3 --version
python3 -m venv .venv
./.venv/bin/python -m pip install .
```

A source installation obtains the build requirements declared in `pyproject.toml`.
To build a wheel instead, replace the final source-install command above with the
following two commands. The wheel installation itself is offline.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
.\.venv\Scripts\python.exe -m pip install --no-deps --no-index .\dist\qcjudge-0.1.0.dev2-py3-none-any.whl
```

Linux or macOS:

```sh
./.venv/bin/python -m pip wheel --no-deps --wheel-dir dist .
./.venv/bin/python -m pip install --no-deps --no-index ./dist/qcjudge-0.1.0.dev2-py3-none-any.whl
```

If the maintainer supplies a wheel, skip the build and use that wheel's actual
local path in the install command. Keep the checkout or source archive for the
example inputs; the wheel installs the Python package and command line entry point.

## Quick start

These three introductory examples use synthetic inputs included in the project.
They need no external data or chemistry software.

Windows PowerShell:

```powershell
.\.venv\Scripts\qcjudge.exe audit --question transition_state --input examples/01-transition-state-mode-identity/job.out --context molecule=dvb
.\.venv\Scripts\qcjudge.exe audit --question transition_state --input examples/02-converged-minimum-is-not-a-saddle/job.out --context molecule=dvb
.\.venv\Scripts\qcjudge.exe audit --question tadf_potential --input examples/03-tadf-gap-is-not-a-risc-channel/job.out --context molecule=dvb
```

Linux or macOS:

```sh
./.venv/bin/qcjudge audit --question transition_state --input examples/01-transition-state-mode-identity/job.out --context molecule=dvb
./.venv/bin/qcjudge audit --question transition_state --input examples/02-converged-minimum-is-not-a-saddle/job.out --context molecule=dvb
./.venv/bin/qcjudge audit --question tadf_potential --input examples/03-tadf-gap-is-not-a-risc-channel/job.out --context molecule=dvb
```

| Example | Execution | Structure | Evidence |
| --- | --- | --- | --- |
| 1. Transition-state mode identity | PASS | PASS | PARTIALLY_SUPPORTED |
| 2. A converged minimum is not a saddle | PASS | FAIL | CONTRADICTED |
| 3. A TADF gap is not a RISC channel | PASS | UNKNOWN | PARTIALLY_SUPPORTED |

All three commands exit `0`. Append `--format json` for a machine-readable report.
See the [example explanations](examples/README.md) for their scientific boundaries,
and [the CT analysis import example](examples/04-charge-transfer-analysis/README.md)
for a fully associated external analysis that reaches `SUPPORTED`.

## Using the command line

The commands below assume the environment's command directory is on your path.
Otherwise use the explicit `qcjudge` path shown in the quick start.

```console
qcjudge audit --question transition_state --input job.out --context molecule=dvb
qcjudge audit --question transition_state --input job.out --context molecule=dvb --format json
qcjudge audit --question transition_state --input job.out --context molecule=dvb --ask "Is this the transition state for the C-C rotation step?"
```

`--ask` records your question verbatim in the report; without it the report states the
protocol's own hypothesis. `--context KEY=VALUE` binds the protocol's claim templates, so a
missing key is refused rather than audited against the wrong state. `--condition KEY=VALUE`
reports something only you can observe -- the partition you chose, a mode you judged ambiguous --
and `--expert-review REQUIREMENT_ID` states that a declared expert boundary has been reached.
`--evidence TYPE` records that an analysis was performed outside QCJudge; it is capped at WEAK
and INDIRECT, so it is recorded honestly without masquerading as parsed data.

`--analysis FILE` imports an analysis QCJudge deliberately does not compute -- a hole-electron
descriptor, an NTO composition, a spin-orbit coupling, an IRC outcome. The values keep the
producer that computed them, so the report says which numbers the calculation emitted and which
an external tool supplied. The format is documented in
[the adapter format](docs/adapter-format.md). Each imported result has its own calculation ID;
`source_calculation_id` associates it with the main calculation. Separate unlinked results cannot
jointly support one claim. Use `--target calc-1` (or `--context calculation_id=calc-1`) to choose
among independent calculations; default parsed IDs are `calc-N` in sorted input-file order.
Optional `molecule` and `state` metadata are checked against the question.

Reports use `qcjudge.audit_report/2`, recording the selected calculations, unresolved association,
and complete researcher conditions and expert inputs. All three built-in
protocols are version `1.1.1`.
Explicit failed IRC outcomes and zero excited-state counts do not create positive evidence.
The ORCA reader evaluates only the first identifiable execution in a multi-job output and warns
about later output. Split other jobs into separate inputs if they need auditing.

**Exit codes describe the run, not the verdict.** An audit that ran exits `0` even when the
evidence is insufficient, because the report is the deliverable. `2` means no audit could be
produced. To branch on the finding, read `evidence.overall_status` from `--format json`.

## Preview limitations

The current scope is the three question families above and a documented subset of
ORCA output, with the reader restricted to the first identifiable execution. Nine
of the sixteen registered evidence types have no automated producer; other analyses
must be supplied explicitly with units and provenance. See [scientific scope](docs/scientific-scope.md)
and [the adapter format](docs/adapter-format.md) before interpreting a report.

Consumers should check the report's `schema` identifier, currently
`qcjudge.audit_report/2`, and its recorded protocol version. Local regression and
property checks and audit replay tooling help verify implementation behavior.
An independent expert-labelled adequacy benchmark and demonstrated compatibility
across version changes remain M5 work. Passing the current tests does not establish
the scientific truth of a conclusion.

## Development

For editable installation, developer dependencies, checks, and cache redirection,
see [the contribution guide](CONTRIBUTING.md). Ordinary users do not need the
development extras. [The release checklist](docs/release-checklist.md) records the
local wheel installation and candidate validation procedure.

The real-ORCA tests skip themselves until the pinned corpus has been fetched with
`python tools/fetch_benchmark_data.py`; nothing third-party is committed. See
[the contribution guide](CONTRIBUTING.md) for cache redirection and other environment notes.

CI runs lint and strict types in a separate job, plus tests, wheel construction,
installation, and an isolated CLI smoke check on Python 3.12 and 3.13 across
Linux, macOS, and Windows (`.github/workflows/ci.yml`). The
[first remote run](https://github.com/chc-cyber/QCJudge/actions/runs/37732697580)
passed all seven jobs. Inspect [GitHub Actions](https://github.com/chc-cyber/QCJudge/actions)
for the results of later revisions; a previous green run does not validate a
changed source revision.
Formatting is deliberately not a gate; see D-33 in the plan.

See [the architecture](docs/architecture.md), [scientific scope](docs/scientific-scope.md),
and [the working plan](docs/v0.1-plan.md).

## License

BSD 3-Clause. See [LICENSE](LICENSE).

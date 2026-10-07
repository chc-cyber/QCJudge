# QCJudge

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
is committed to this repository. Three worked examples under [`examples/`](examples/README.md)
show what an audit concludes and what it refuses to. The adapter seam is implemented; current
work is M5 hardening and release validation. See [the working plan](docs/v0.1-plan.md) for the debt
register and milestone gates.

## Using the command line

```console
qcjudge audit --question transition_state --input job.out --context molecule=dvb
qcjudge audit --question transition_state --input job.out --context molecule=dvb --format json
qcjudge audit --question transition_state --input job.out --context molecule=dvb \
  --ask "Is this the transition state for the C-C rotation step?"
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
and complete researcher conditions and expert inputs. Built-in protocols are version `1.1.0`;
explicit failed IRC outcomes and zero excited-state counts do not create positive evidence.
The ORCA reader evaluates only the first identifiable execution in a multi-job output and warns
about later output. Split other jobs into separate inputs if they need auditing.

**Exit codes describe the run, not the verdict.** An audit that ran exits `0` even when the
evidence is insufficient, because the report is the deliverable. `2` means no audit could be
produced. To branch on the finding, read `evidence.overall_status` from `--format json`.

## Development

Requires Python 3.12 or newer. Confirm it before anything else: on Windows a bare `python` may
be the Microsoft Store stub, which accepts the command and exits silently.

```console
python --version          # must report 3.12 or newer
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy src/qcjudge
```

The real-ORCA tests skip themselves until the pinned corpus has been fetched with
`python tools/fetch_benchmark_data.py`; nothing third-party is committed. See
[the contribution guide](CONTRIBUTING.md) for cache redirection and other environment notes.

CI runs the same three gates on Python 3.12 and 3.13 across Linux, macOS and Windows
(`.github/workflows/ci.yml`). Formatting is deliberately not a gate; see D-33 in the plan.

See [the architecture](docs/architecture.md), [scientific scope](docs/scientific-scope.md),
and [the working plan](docs/v0.1-plan.md).

## License

BSD 3-Clause. See [LICENSE](LICENSE).


# Local audit bundles

An audit bundle saves the raw input bytes, exact audit options, versions and baseline JSON
report together. It can be moved to another directory and checked without the original input
files. This is a local replay foundation; compatibility across real released versions remains
an M5 gate to validate later.

Install QCJudge first, using the source or wheel instructions in the README. Run the commands
below from the source checkout with that environment's Python. Use `.venv/Scripts/python` on
Windows or `.venv/bin/python` on Linux/macOS in place of `python` if the environment is not active.

## Save an audit

This single-line command works in PowerShell and POSIX shells:

```console
python tools/audit_bundle.py create --bundle .test-scratch/bundles/ts -- audit --question transition_state --input examples/01-transition-state-mode-identity/job.out --context molecule=dvb
```

The options after `--` are ordinary `qcjudge audit` arguments. Question text, assumptions,
contexts, selected target, conditions, expert flags and user assertions are preserved. Analyses
are copied in their original order. A directory input snapshots exactly the CLI's sorted `*.out`
file set, keeping its `calc-N` assignment. Every replay emits JSON regardless of the requested
display format; the original request is also recorded.

To save the complete, explicitly synthetic CT demonstration:

```console
python tools/audit_bundle.py create --bundle .test-scratch/bundles/ct -- audit --question ct_excitation --input examples/04-charge-transfer-analysis/job.out --analysis examples/04-charge-transfer-analysis/analysis.json --context molecule=demo-ct --context state=S1
```

A bundle destination must be new. A failed audit leaves no partial bundle and an existing bundle
is never overwritten. The examples use ignored test scratch; keep a durable copy wherever you
store research records. A bundle contains full source files and their original path names.

## Verify and replay

```console
python tools/audit_bundle.py replay --bundle .test-scratch/bundles/ct
```

The tool verifies SHA-256 and byte counts before execution, refuses paths outside the bundle,
and checks that no unrecorded calculation has entered the input directory. It runs QCJudge on
the copied inputs and compares the report and parser diagnostics with their saved baselines.
Replaying does not overwrite any bundle file.

The comparison excludes only report creation/extraction timestamps, the tool version and the
protocol version. Values, units, subjects, provenance locations, producer versions, rationales,
statuses and trace edges remain in the comparison. Version equality is checked separately and
is required by default. A later tool/protocol version can be tested explicitly:

```console
python tools/audit_bundle.py replay --bundle .test-scratch/bundles/ct --allow-version-change
```

This option permits a version difference only. It still fails on a changed report or diagnostic
and prints recorded/current versions plus changed top-level report sections. It does not assert
that a scientific rule change was appropriate. Schema 1 reports and future incompatible report
schemas are not supported by this initial tool.

Exit codes: `0` means a bundle was created or replay matched; `1` means a valid replay differed
or versions differed without permission; `2` means invalid arguments, missing/changed inputs,
an unsupported schema or an audit that could not run. These differ from QCJudge audit's own
exit policy: an evidence finding such as `INSUFFICIENT` remains a successful audit.

## Files and trust

`manifest.json` uses `qcjudge.audit_bundle/1`. It records file roles, SHA-256 hashes, byte counts,
original paths, original and portable arguments, Python/platform details and tool/report/protocol
versions. `report.json` and `diagnostics.txt` are included in the file checksums. Raw calculations
are under `inputs/calculations/`; external exports are under `inputs/analyses/`.

Checksums establish agreement with the supplied manifest, not authorship or independent truth.
Preserve the original bundle as a research record: replacing its manifest and baseline creates a
different baseline. The tool runs QCJudge only and does not execute quantum-chemistry jobs.
The child process runs in Python isolation mode and loads the trusted QCJudge location already
used by the calling environment, so a `qcjudge/` directory inside a bundle cannot replace it.

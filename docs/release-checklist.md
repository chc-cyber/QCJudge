# Local preview release checklist

The current candidate is `0.1.0.dev2`, a pre-alpha development preview. A stable
release has not been published. Reports use `qcjudge.audit_report/2`; all three built-in
protocols are `1.1.1`. Update the explicit
wheel filename below when the package version changes.

This procedure creates a reviewable candidate for
[chc-cyber/QCJudge](https://github.com/chc-cyber/QCJudge). Remote work has resumed;
the [first real CI run](https://github.com/chc-cyber/QCJudge/actions/runs/37732697580)
passed all seven jobs at commit `272d2de`. Complete the local checks and validate
the source revision intended for publication through CI below.

## 1. Obtain and identify the source

- Clone [the public repository](https://github.com/chc-cyber/QCJudge) or use an
  existing checkout or a source archive from it:

  ```console
  git clone https://github.com/chc-cyber/QCJudge.git
  cd QCJudge
  ```

- Run all commands from the root containing `pyproject.toml`, `src/`, `examples/`,
  and `tools/`.
- Check the interpreter with `py -3.12 --version` on Windows or `python3 --version`
  on Linux/macOS. It must be Python 3.12 or newer. Candidate checks target 3.12 and
  3.13; use the intended interpreter explicitly.
- Use fresh environment directories for each candidate. The names below assume
  that these environments have not already been created for another candidate.

If the Windows launcher is unavailable, replace `py -3.12` with the full path to a
working interpreter.

## 2. Build and independently install the wheel

Use separate build and installation environments. Building obtains the declared
Hatchling build requirements; it needs network access unless they are already
available. Installing the resulting wheel requires no dependency downloads.

Windows PowerShell:

```powershell
py -3.12 -m venv .test-scratch/release-build
.\.test-scratch\release-build\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
py -3.12 -m venv .test-scratch/release-install
.\.test-scratch\release-install\Scripts\python.exe -m pip install --no-deps --no-index .\dist\qcjudge-0.1.0.dev2-py3-none-any.whl
.\.test-scratch\release-install\Scripts\python.exe -I tools/verify_installed_package.py
```

Linux or macOS:

```sh
python3 -m venv .test-scratch/release-build
./.test-scratch/release-build/bin/python -m pip wheel --no-deps --wheel-dir dist .
python3 -m venv .test-scratch/release-install
./.test-scratch/release-install/bin/python -m pip install --no-deps --no-index ./dist/qcjudge-0.1.0.dev2-py3-none-any.whl
./.test-scratch/release-install/bin/python -I tools/verify_installed_package.py
```

The isolated smoke tool checks that imports come from the installed distribution,
that module and package metadata versions match the source declaration, and that
a real CLI audit returns the installed report schema and protocol version with
the expected verdict. Keep its output with the candidate record.

## 3. Run the introductory examples from the installed package

Windows PowerShell:

```powershell
.\.test-scratch\release-install\Scripts\qcjudge.exe audit --question transition_state --input examples/01-transition-state-mode-identity/job.out --context molecule=dvb --format json
.\.test-scratch\release-install\Scripts\qcjudge.exe audit --question transition_state --input examples/02-converged-minimum-is-not-a-saddle/job.out --context molecule=dvb --format json
.\.test-scratch\release-install\Scripts\qcjudge.exe audit --question tadf_potential --input examples/03-tadf-gap-is-not-a-risc-channel/job.out --context molecule=dvb --format json
```

Linux or macOS:

```sh
./.test-scratch/release-install/bin/qcjudge audit --question transition_state --input examples/01-transition-state-mode-identity/job.out --context molecule=dvb --format json
./.test-scratch/release-install/bin/qcjudge audit --question transition_state --input examples/02-converged-minimum-is-not-a-saddle/job.out --context molecule=dvb --format json
./.test-scratch/release-install/bin/qcjudge audit --question tadf_potential --input examples/03-tadf-gap-is-not-a-risc-channel/job.out --context molecule=dvb --format json
```

| Input | `execution.status` | `structure.status` | `evidence.overall_status` |
| --- | --- | --- | --- |
| Example 1 | `pass` | `pass` | `partially_supported` |
| Example 2 | `pass` | `fail` | `contradicted` |
| Example 3 | `pass` | `unknown` | `partially_supported` |

All three commands should exit `0`. Each report should identify the candidate
package version, its protocol version, and `qcjudge.audit_report/2`. Exit `0`
means an audit was produced; inspect the verdict fields separately.

Also follow [the CT analysis import example](../examples/04-charge-transfer-analysis/README.md)
with the installation environment's Python. Its synthetic linked analysis should
produce `supported`; omitting that analysis should produce `insufficient`.
These examples verify documented behavior, not the chemical truth of their
invented systems.

## 4. Run the local source checks and preserve replay inputs

Create a separate editable development environment with the declared extras.
Fetch and verify the pinned twelve-file ORCA corpus before the complete candidate
test run. The fetch requires network access; verification of an already fetched
corpus is local.

Windows PowerShell:

```powershell
py -3.12 -m venv .test-scratch/release-checks
.\.test-scratch\release-checks\Scripts\python.exe -m pip install -e ".[dev]"
.\.test-scratch\release-checks\Scripts\python.exe tools/fetch_benchmark_data.py
.\.test-scratch\release-checks\Scripts\python.exe tools/fetch_benchmark_data.py --verify
$env:QCJUDGE_TEST_SCRATCH = ".test-scratch"
$env:MYPY_CACHE_DIR = ".test-scratch/mypy"
.\.test-scratch\release-checks\Scripts\python.exe -m pytest -q -rs -o cache_dir=.test-scratch/pytest-cache
.\.test-scratch\release-checks\Scripts\python.exe -m ruff check --no-cache .
.\.test-scratch\release-checks\Scripts\python.exe -m mypy --strict src/qcjudge
```

Linux or macOS:

```sh
python3 -m venv .test-scratch/release-checks
./.test-scratch/release-checks/bin/python -m pip install -e ".[dev]"
./.test-scratch/release-checks/bin/python tools/fetch_benchmark_data.py
./.test-scratch/release-checks/bin/python tools/fetch_benchmark_data.py --verify
QCJUDGE_TEST_SCRATCH=.test-scratch ./.test-scratch/release-checks/bin/python -m pytest -q -rs -o cache_dir=.test-scratch/pytest-cache
./.test-scratch/release-checks/bin/python -m ruff check --no-cache .
MYPY_CACHE_DIR=.test-scratch/mypy ./.test-scratch/release-checks/bin/python -m mypy --strict src/qcjudge
```

- Record the OS, Python version, source revision, pass counts, and any skip
  reasons. Corpus tests skipped because their inputs are absent do not complete
  the real-output gate.
- Follow [the audit replay procedure](replay.md) to preserve representative raw
  inputs, analysis files, complete arguments, their SHA256 hashes, and baseline
  reports, then replay the bundles against the candidate.
- Same-version replay checks reproducibility. Version changes are rejected by
  default; overriding that guard does not establish compatibility. Review and
  validate changed reports before claiming cross-version compatibility.
- Formatting is not a release gate; lint and strict types are gates.

## 5. Record the artifact and source identity

Hash the exact wheel that passed independent installation and the examples.

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\dist\qcjudge-0.1.0.dev2-py3-none-any.whl
git status --short
git rev-parse HEAD
```

Linux or macOS:

```sh
./.test-scratch/release-install/bin/python -c 'import hashlib; from pathlib import Path; p = Path("dist/qcjudge-0.1.0.dev2-py3-none-any.whl"); print(hashlib.sha256(p.read_bytes()).hexdigest(), p.name)'
git status --short
git rev-parse HEAD
```

- Record the wheel filename, SHA256, source revision, and check results together.
  If the checkout is dirty, resolve or explicitly record those changes; a commit
  ID alone does not identify the built source.
- Rebuild after source, package metadata, or packaged README changes, then repeat
  independent installation and affected checks. Distribute the exact verified
  artifact.
- Keep environments, caches, third-party corpus files, and candidate scratch
  artifacts outside version control. Include the synthetic examples in the
  supplied source archive.
- Review installation instructions, protocol/report compatibility notes, known
  scope, and release notes. Label this candidate as a pre-alpha development
  preview, and state that the independent expert benchmark is still pending.

## 6. Verify remote CI and publish the preview

The public destination is [chc-cyber/QCJudge](https://github.com/chc-cyber/QCJudge).
The [first run](https://github.com/chc-cyber/QCJudge/actions/runs/37732697580) passed
the lint/type job and all six test jobs, including their corpus fetch, pytest,
wheel build, install, and isolated smoke steps. That validates commit `272d2de`;
repeat the remote gate for the final source revision:

1. Review the source revision and repository metadata destined for this
   repository, including the package and citation URLs.
2. Publish the reviewed source history, then run the configured Linux, macOS, and
   Windows jobs on Python 3.12 and 3.13, including wheel installation and isolated
   smoke checks.
3. Inspect the actual [Actions run](https://github.com/chc-cyber/QCJudge/actions).
   Confirm the corpus fetch succeeded and its tests ran. The current CI fetch is
   optional, so a green run alone can include skipped real-output cases.
4. Resolve platform failures and rerun affected jobs before publication.
5. Create an explicitly marked prerelease using the matching source revision,
   verified wheel, SHA256, and preview limitations. Keep the development-version
   label; a stable `0.1.0` release requires its own version and milestone review.

An independent expert-labelled evidence-adequacy benchmark and verified replay
compatibility across version changes remain M5 work. Local property tests and
replay bundles provide useful checks without completing those scientific and
compatibility gates.

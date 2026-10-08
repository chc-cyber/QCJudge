# Contributing

QCJudge welcomes narrowly scoped changes with explicit scientific assumptions and tests.

1. Describe the question family, evidence relationship, or engineering change before implementing it.
2. Keep parsing, deterministic validation, evidence assessment, and presentation separate.
3. Add provenance for every newly extracted fact. Preserve unknown values as unknown.
4. Add tests, type annotations, and documentation for scientific behavior.
5. Run the checks below before sharing a change for review.

The current version is the local pre-alpha preview `0.1.0.dev2`; it has not been
formally released. The project owner has deferred the remote repository and real
CI execution. The six configured OS/Python combinations await remote verification.
Ordinary users should follow [the installation and quick start](README.md#install-locally);
the development extras below are for contributors.

## Setting up an environment

Run these commands from the source root. QCJudge requires Python 3.12 or newer;
release checks target Python 3.12 and 3.13. Confirm that the interpreter reports
its version before creating the environment.

Windows PowerShell:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

If the Windows launcher is unavailable, replace `py -3.12` with the full path to
a working Python 3.12 or 3.13 interpreter. A bare `python` may be the Microsoft
Store stub, so its presence on the path is not sufficient.

Linux or macOS:

```sh
python3 --version
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

An existing `uv` installation can create the same environment and install the
extras. Use the path appropriate to the platform:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
```

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

`.venv/` is already ignored by git.

## Running the checks

Fetch and verify the pinned corpus before a release-candidate check. Fetching
requires network access and downloads third-party files into the ignored
`.benchmark-data/` directory.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/fetch_benchmark_data.py
.\.venv\Scripts\python.exe tools/fetch_benchmark_data.py --verify
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy --strict src/qcjudge
```

Linux or macOS:

```sh
./.venv/bin/python tools/fetch_benchmark_data.py
./.venv/bin/python tools/fetch_benchmark_data.py --verify
./.venv/bin/python -m pytest -q -rs
./.venv/bin/python -m ruff check .
./.venv/bin/python -m mypy --strict src/qcjudge
```

For offline unit work, fetching can be omitted; real-ORCA cases then skip if their
inputs are absent. Read the skip reasons. A full candidate validation should
verify all twelve manifest entries and run those cases. Do not commit the
downloaded corpus. Regression and generated property tests exercise implementation
invariants; they do not replace an independent scientific benchmark.

CI is configured to run lint, strict types, tests, wheel construction, and an
isolated installed-package check on Python 3.12/3.13 across Linux, macOS, and
Windows. Until remote execution resumes, this configuration is not evidence that
the complete matrix passes. Formatting is deliberately not a gate; adoption of a
formatter is a separate decision recorded as D-33 in the working plan.

### When caches or temporary directories are not writable

Tests normally use pytest's temporary directory. A confined environment may deny
access there or to `.pytest_cache/`, `.mypy_cache/`, and `.ruff_cache/`. Redirect
scratch and the mypy cache to a writable directory, and disable Ruff's cache.
`tests/conftest.py` reads `QCJUDGE_TEST_SCRATCH` and creates that scratch root.

Windows PowerShell:

```powershell
$env:QCJUDGE_TEST_SCRATCH = ".test-scratch"
$env:MYPY_CACHE_DIR = ".test-scratch/mypy"
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m ruff check --no-cache .
.\.venv\Scripts\python.exe -m mypy --strict src/qcjudge
```

Linux or macOS:

```sh
QCJUDGE_TEST_SCRATCH=.test-scratch ./.venv/bin/python -m pytest -q -rs
./.venv/bin/python -m ruff check --no-cache .
MYPY_CACHE_DIR=.test-scratch/mypy ./.venv/bin/python -m mypy --strict src/qcjudge
```

If pytest's cache is also denied, add `-o cache_dir=.test-scratch/pytest-cache` to
the pytest command. Without `QCJUDGE_TEST_SCRATCH`, pytest's `tmp_path` is unchanged.

Protocol changes that alter an audit outcome require a version change and a short scientific
rationale. Do not add universal thresholds without documented scope and evidence. Third-party code
or fixtures must have a compatible license and attribution.

See [the local release checklist](docs/release-checklist.md) for independent wheel
installation, example verification, artifact hashes, and the deferred remote
steps. Independent expert-labelled adequacy cases and compatibility checks across
version changes remain M5 work.

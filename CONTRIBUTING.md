# Contributing

QCJudge welcomes narrowly scoped changes with explicit scientific assumptions and tests.

1. Open an issue describing the question family, evidence relationship, or engineering change.
2. Keep parsing, deterministic validation, evidence assessment, and presentation separate.
3. Add provenance for every newly extracted fact. Preserve unknown values as unknown.
4. Add tests, type annotations, and documentation for scientific behavior.
5. Run `pytest`, `ruff check .`, and `mypy src/qcjudge` before submitting a pull request.

## Setting up an environment

QCJudge requires Python 3.12 or newer. A bare `python` on PATH is not always enough: on Windows
the Microsoft Store stub accepts the command and exits without doing anything, so check the
version first.

```console
python --version          # must report 3.12 or newer
```

If it does not, create a virtual environment with a 3.12 interpreter. With `uv`, which can also
provision the interpreter:

```console
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"   # POSIX: .venv/bin/python
```

Without `uv`, use any 3.12 interpreter you already have:

```console
py -3.12 -m venv .venv          # Windows launcher
.venv/Scripts/python -m pip install -e ".[dev]"
```

`.venv/` is already ignored by git.

## Running the checks

```console
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy src/qcjudge
```

Two directories under `.pytest_cache/`, `.mypy_cache/` and `.ruff_cache/` are caches; if a
sandboxed environment denies writing to them, redirect them rather than disabling the checks:

```console
MYPY_CACHE_DIR=/tmp/mypy .venv/bin/python -m mypy src/qcjudge
.venv/bin/python -m ruff check --no-cache .
```

Some tests write fixtures to a temporary directory, and the real-ORCA tests skip themselves
until the corpus is fetched:

```console
.venv/Scripts/python tools/fetch_benchmark_data.py
```

### When the system temporary directory is not usable

A confined environment may forbid listing the directory pytest creates under the system
temporary root, which makes every `tmp_path` test fail at setup for a reason unrelated to the
code. Point the scratch root somewhere writable and the whole suite runs again:

```console
QCJUDGE_TEST_SCRATCH=/tmp/qcjudge-scratch .venv/bin/python -m pytest
```

`tests/conftest.py` reads that variable; without it, pytest's own `tmp_path` is used unchanged.

Protocol changes that alter an audit outcome require a version change and a short scientific
rationale. Do not add universal thresholds without documented scope and evidence. Third-party code
or fixtures must have a compatible license and attribution.


"""The CI definition and the declared Python support must not drift apart.

A workflow that tests a version the package does not claim, or omits one it does, is worse than
no workflow: it reports green while leaving the supported range unverified. These checks are
textual on purpose -- parsing YAML would need a dependency the project does not have, and the
questions that matter here ("is this version listed?", "is this command run?") are answerable
without one.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = ROOT / "pyproject.toml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _declared_versions() -> list[str]:
    """The interpreter matrix, read from the workflow's own support policy."""
    match = re.search(r"^  SUPPORTED_PYTHON: '(\[.*?\])'$", _workflow(), re.MULTILINE)
    assert match is not None, "the workflow no longer declares SUPPORTED_PYTHON"
    return json.loads(match.group(1))


def _classifier_versions() -> list[str]:
    classifiers = _pyproject()["project"]["classifiers"]
    found = []
    for classifier in classifiers:
        match = re.fullmatch(r"Programming Language :: Python :: (\d+\.\d+)", classifier)
        if match:
            found.append(match.group(1))
    return sorted(found)


def test_the_workflow_exists() -> None:
    assert WORKFLOW.exists(), "D-13 asks for a CI workflow"


# -- the support policy, in three places ----------------------------------------------------


def test_the_workflow_declares_at_least_the_floor_and_the_next_version() -> None:
    versions = _declared_versions()

    assert versions, "an empty matrix would run no tests"
    assert versions == sorted(versions, key=lambda item: tuple(map(int, item.split("."))))


def test_the_classifiers_match_the_workflow_matrix() -> None:
    """A version tested but not claimed, or claimed but not tested, is a silent gap."""
    assert _classifier_versions() == _declared_versions()


def test_the_floor_version_satisfies_requires_python() -> None:
    """The lowest tested interpreter must be one the package says it supports."""
    requires = _pyproject()["project"]["requires-python"]
    floor = _declared_versions()[0]
    match = re.fullmatch(r">=(\d+)\.(\d+)", requires)
    assert match is not None, f"unexpected requires-python form: {requires!r}"

    assert tuple(map(int, floor.split("."))) >= (int(match.group(1)), int(match.group(2)))


# -- the checks the workflow must actually run ----------------------------------------------


def test_the_workflow_runs_the_three_gates() -> None:
    """ruff, mypy and pytest are the gates CONTRIBUTING tells a contributor to run."""
    text = _workflow()

    assert "ruff check" in text
    assert "mypy src/qcjudge" in text
    assert re.search(r"^\s*run: pytest", text, re.MULTILINE)


def test_the_workflow_does_not_gate_on_formatting() -> None:
    """Formatting was never adopted, so gating on it would fail on arrival.

    If this ever changes, the tree has to be formatted in the same change; D-33 records that.
    The check looks for an executed command, not a mention, so the workflow can explain the
    decision in a comment.
    """
    executed = [
        line.strip()
        for line in _workflow().splitlines()
        if line.strip().startswith(("run:", "- run:"))
    ]

    assert not any("ruff format" in line for line in executed)


def test_the_workflow_installs_the_development_extra() -> None:
    """`.[dev]` is where pytest, mypy and ruff are declared, so the gates depend on it."""
    assert '.[dev]' in _workflow()


def _indented_list(anchor: str) -> list[str]:
    """The items of a YAML list under a line matching ``anchor``.

    Enough YAML to read an inline list without a parser dependency. Handles both an inline list
    (`os: [a, b]`) and one written as dashes on following lines.
    """
    lines = _workflow().splitlines()
    for index, line in enumerate(lines):
        if not re.match(anchor, line):
            continue
        _, _, inline = line.partition(":")
        inline = inline.split("#")[0].strip()
        if inline.startswith("["):
            return [item.strip().strip("'\"") for item in inline.strip("[]").split(",")]
        indent = len(line) - len(line.lstrip())
        marker = f"{' ' * (indent + 2)}- "
        items = []
        for following in lines[index + 1 :]:
            if following.strip() and not following.startswith(" " * (indent + 1)):
                break
            if following.startswith(marker):
                items.append(following[len(marker) :].split("#")[0].strip())
        return items
    return []


def test_the_workflow_matrix_covers_all_three_platforms() -> None:
    """The parser reads files and the CLI writes them; both differ by platform."""
    runners = _indented_list(r"^        os:")

    assert runners == ["ubuntu-latest", "macos-latest", "windows-latest"]


def test_the_real_corpus_step_cannot_fail_the_build() -> None:
    """The corpus is optional by design: nothing third-party is committed or required.

    Without `continue-on-error` a network hiccup would fail a build that has nothing wrong
    with it, and the real-corpus tests skip themselves when the fetch did not happen.
    """
    text = _workflow()
    fetch_block = text.split("Fetch the real ORCA corpus", 1)
    assert len(fetch_block) == 2, "the corpus fetch step is gone"

    followed = fetch_block[1].split("- name:", 1)[0]
    assert "continue-on-error: true" in followed


def test_the_workflow_checks_out_the_repository() -> None:
    assert "actions/checkout" in _workflow()


# -- the ignore rules the workflow depends on ------------------------------------------------


def test_gitignore_excludes_the_fetched_corpus() -> None:
    """CI fetches real output, so it must not be commit-able as third-party data."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".benchmark-data/" in ignore
    assert ".venv/" in ignore


# -- the line-ending rules the golden files depend on -----------------------------------------


def test_gitattributes_normalises_line_endings() -> None:
    """A CRLF checkout would fail the byte-for-byte text tests on a clean clone."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert re.search(r"^\* text=auto eol=lf$", attributes, re.MULTILINE)


def test_golden_fixtures_are_excluded_from_conversion() -> None:
    """They are compared as bytes, so nothing may rewrite them on the way through git."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert re.search(r"^tests/data/\*\* -text$", attributes, re.MULTILINE)


def test_the_golden_fixtures_have_no_carriage_returns() -> None:
    """The checked-in files must already be LF, since that is what rendering produces."""
    for name in ("report_task.txt", "report_expert_boundary.txt"):
        raw = (ROOT / "tests" / "data" / name).read_bytes()
        assert b"\r\n" not in raw, f"{name} has CRLF line endings"

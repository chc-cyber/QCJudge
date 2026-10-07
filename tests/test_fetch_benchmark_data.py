"""The benchmark fetch script must not report an unverified file as verified.

The pin exists so that real ORCA output used to validate the parser is the same data every
time. A manifest that does not describe every fetched file silently weakens that to nothing:
the missing files still print ``ok`` and the run still exits 0, so a caller cannot tell a
verified corpus from an unverified one.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "fetch_benchmark_data.py"
MANIFEST = ROOT / "tools" / "benchmark_manifest.json"


def _tool() -> ModuleType:
    """Load the fetch script by path; it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("fetch_benchmark_data", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digests(module: ModuleType) -> dict[str, str]:
    return {path: "0" * 64 for path in module.ORCA_FILES}


def test_a_complete_manifest_has_no_problems() -> None:
    module = _tool()

    assert module._manifest_problems(_digests(module)) == []


def test_a_file_the_manifest_does_not_describe_is_a_problem() -> None:
    """This was the defect: such a file printed ``ok`` and the run exited 0."""
    module = _tool()
    incomplete = _digests(module)
    dropped = module.ORCA_FILES[0]
    del incomplete[dropped]

    problems = module._manifest_problems(incomplete)

    assert problems
    assert problems[0].startswith("the manifest records no checksum")
    assert dropped in problems[0]


def test_a_pin_for_a_file_that_is_never_fetched_is_a_problem() -> None:
    """An entry nothing checks is a pin in name only."""
    module = _tool()
    stale = _digests(module)
    stale["ORCA/ORCA9.9/ghost.out"] = "1" * 64

    problems = module._manifest_problems(stale)

    assert problems
    assert problems[0].startswith("the manifest records checksums for")


def test_an_empty_manifest_is_a_problem_rather_than_a_pass() -> None:
    """Every file is unverifiable, so the run must refuse rather than report success."""
    module = _tool()

    assert len(module._manifest_problems({})) == 1


@pytest.mark.skipif(not MANIFEST.exists(), reason="the manifest has not been generated")
def test_the_committed_manifest_describes_every_fetched_file() -> None:
    """The repository's own pin must satisfy the rule the script enforces."""
    module = _tool()
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert module._manifest_problems(
        {name: entry["sha256"] for name, entry in recorded["files"].items()}
    ) == []


@pytest.mark.skipif(not MANIFEST.exists(), reason="the manifest has not been generated")
def test_the_committed_manifest_pins_a_commit() -> None:
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert isinstance(recorded.get("commit"), str)
    assert len(recorded["commit"]) == 40


def test_the_tool_downloads_nothing_when_a_digest_would_fail() -> None:
    """A mismatch must be decided before the bytes reach the disk.

    Proven by inspection of ``_fetch_one``: the digest is compared against the in-memory
    payload, and the file is written only on the branch where it matched.
    """
    source = TOOL.read_text(encoding="utf-8")
    body = source.split("def _fetch_one", 1)[1].split("\ndef ", 1)[0]
    write_at = body.index("target.write_bytes")
    mismatch_at = body.index("MISMATCH")

    assert mismatch_at < write_at, "the mismatch must be raised before anything is written"

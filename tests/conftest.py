"""Route ``tmp_path`` outside the system temporary directory when asked to.

Nothing here is needed on a normal machine: pytest's own ``tmp_path`` works, and without
``QCJUDGE_TEST_SCRATCH`` this file changes nothing. It exists because some confined
environments cannot list the directory pytest creates under the system temporary root, which
makes every ``tmp_path`` test fail at setup for a reason that has nothing to do with the code.

    QCJUDGE_TEST_SCRATCH=/some/writable/dir pytest

Pointing it at a directory the process can create and list restores the whole suite, so a
sandbox limitation does not look like 72 broken tests.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

_ENV_VAR = "QCJUDGE_TEST_SCRATCH"


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Iterator[Path]:
    """A per-test directory under the configured scratch root, or pytest's own."""
    root = os.environ.get(_ENV_VAR)
    if not root:
        yield request.getfixturevalue("tmp_path_factory").mktemp(request.node.name)
        return
    safe = "".join(char if char.isalnum() or char in "-_." else "_" for char in request.node.name)
    directory = Path(root) / f"{safe}-{os.getpid()}"
    counter = 0
    while directory.exists():
        counter += 1
        directory = Path(root) / f"{safe}-{os.getpid()}-{counter}"
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)

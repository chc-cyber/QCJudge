"""Verify a built, installed QCJudge wheel using an example through its real CLI.

Run with ``python -I tools/verify_installed_package.py`` after replacing the editable
development installation with the wheel. The check reads the checkout's project declaration
and example without importing its source tree or writing to either.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path


def main() -> int:
    if not sys.flags.isolated:
        raise RuntimeError("Run this installation check with python -I.")

    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    distribution = metadata.distribution(project["name"])

    import qcjudge
    from qcjudge.domain.assessment import AssessmentStatus
    from qcjudge.domain.question import QuestionFamily
    from qcjudge.domain.validation import ValidationStatus
    from qcjudge.protocols import get_protocol
    from qcjudge.render.json_report import SCHEMA

    module_path = Path(qcjudge.__file__).resolve()
    if module_path.is_relative_to(root / "src"):
        raise RuntimeError(f"QCJudge was imported from the source tree: {module_path}")
    installed_path = Path(distribution.locate_file("qcjudge/__init__.py")).resolve()
    if module_path != installed_path:
        raise RuntimeError(f"QCJudge was not imported from its installed wheel: {module_path}")

    expected_version = project["version"]
    if distribution.version != expected_version or qcjudge.__version__ != expected_version:
        raise RuntimeError(
            "Package versions disagree: "
            f"project={expected_version}, distribution={distribution.version}, "
            f"module={qcjudge.__version__}"
        )

    protocol = get_protocol(QuestionFamily.TRANSITION_STATE_VALIDATION)
    example = root / "examples" / "01-transition-state-mode-identity" / "job.out"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            "-m",
            "qcjudge.cli.main",
            "audit",
            "--question",
            protocol.question_family.value,
            "--input",
            str(example),
            "--context",
            "molecule=dvb",
            "--format",
            "json",
        ],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Installed CLI exited {result.returncode}: {result.stderr.strip()}")
    report = json.loads(result.stdout)
    expected = {
        "schema": SCHEMA,
        "tool_version": expected_version,
        "protocol": {"id": protocol.id, "version": protocol.version},
        "execution": ValidationStatus.PASS.value,
        "structure": ValidationStatus.PASS.value,
        "evidence": AssessmentStatus.PARTIALLY_SUPPORTED.value,
    }
    actual = {
        "schema": report["schema"],
        "tool_version": report["tool_version"],
        "protocol": {"id": report["protocol"]["id"], "version": report["protocol"]["version"]},
        "execution": report["execution"]["status"],
        "structure": report["structure"]["status"],
        "evidence": report["evidence"]["overall_status"],
    }
    if actual != expected:
        raise RuntimeError(f"Installed CLI report disagrees with the example contract: {actual!r}")
    print(
        f"Installed wheel verified: {distribution.metadata['Name']} {expected_version}; "
        f"{SCHEMA}; {protocol.id} {protocol.version}; "
        "execution PASS, structure PASS, evidence PARTIALLY_SUPPORTED."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Save and replay a local audit with its exact inputs and arguments.

Requires an installed QCJudge (or an editable development installation). The bundle is a
portable directory, not a workflow executor. It never runs chemistry software or shell text.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "qcjudge.audit_bundle/1"
REPORT_SCHEMA = "qcjudge.audit_report/2"


class BundleError(ValueError):
    """An incomplete, changed or invalid bundle cannot be replayed."""


def _namespace(arguments: Sequence[str]) -> argparse.Namespace:
    from qcjudge.cli.main import build_parser

    if not arguments or arguments[0] != "audit":
        raise BundleError("Supply QCJudge audit arguments after --.")
    try:
        return build_parser().parse_args(arguments)
    except SystemExit as error:
        raise BundleError("Invalid QCJudge audit arguments.") from error


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BundleError(f"Expected a JSON object in {path.name}.")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _entry(path: Path, root: Path, role: str, original: Path | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "original_path": str(original.resolve()) if original is not None else None,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _versions(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != REPORT_SCHEMA:
        raise BundleError(f"Only {REPORT_SCHEMA} reports are supported by this bundle format.")
    return {
        "tool_version": report["tool_version"],
        "report_schema": report["schema"],
        "protocol": {"id": report["protocol"]["id"], "version": report["protocol"]["version"]},
    }


def _run(arguments: Sequence[str], directory: Path) -> tuple[dict[str, Any], str]:
    import qcjudge

    trusted_package_root = str(Path(qcjudge.__file__).resolve().parent.parent)
    bootstrap = (
        "import runpy,sys; "
        "sys.path.insert(0,sys.argv.pop(1)); "
        "sys.argv[0]='qcjudge'; "
        "runpy.run_module('qcjudge.cli.main',run_name='__main__')"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", bootstrap, trusted_package_root, *arguments],
        cwd=directory,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise BundleError(f"QCJudge exited {result.returncode}: {result.stderr.strip()}")
    report = json.loads(result.stdout)
    if not isinstance(report, dict):
        raise BundleError("QCJudge did not return a JSON report.")
    _versions(report)
    return report, result.stderr


def _portable_arguments(args: argparse.Namespace, analyses: list[str]) -> list[str]:
    result = ["audit", "--question", args.question, "--input", "inputs/calculations"]
    for option in ("ask", "target"):
        value = getattr(args, option)
        if value is not None:
            result.append(f"--{option}={value}")
    for option in ("context", "assumption", "evidence", "condition", "expert_review"):
        for value in getattr(args, option):
            result.append(f"--{option.replace('_', '-')}={value}")
    for path in analyses:
        result.extend(("--analysis", path))
    result.extend(("--format", "json"))
    return result


def create_bundle(destination: Path, arguments: Sequence[str]) -> dict[str, Any]:
    """Copy exact bytes, audit the copies, then publish an entirely new local directory."""
    args = _namespace(arguments)
    source = args.input.resolve()
    paths = sorted(source.glob("*.out")) if source.is_dir() else [source]
    if not paths or any(not path.is_file() for path in paths):
        raise BundleError("The input must be a file or a directory containing *.out files.")
    destination = destination.resolve()
    if destination.exists():
        raise BundleError("The bundle destination already exists; choose a new directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".qcjudge-bundle-", dir=destination.parent) as temp:
        staging = Path(temp)
        calculations = staging / "inputs" / "calculations"
        calculations.mkdir(parents=True)
        files: list[dict[str, Any]] = []
        # Stable prefixes preserve the CLI's sorted-file calc-N assignment after relocation.
        for index, original in enumerate(paths, start=1):
            target = calculations / f"{index:06d}.out"
            target.write_bytes(original.read_bytes())
            files.append(_entry(target, staging, "calculation", original))
        analyses: list[str] = []
        for index, original in enumerate(args.analysis, start=1):
            target = staging / "inputs" / "analyses" / f"{index:06d}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
            files.append(_entry(target, staging, "analysis", original))
            analyses.append(target.relative_to(staging).as_posix())
        portable = _portable_arguments(args, analyses)
        report, diagnostics = _run(portable, staging)
        report_path = staging / "report.json"
        _write_json(report_path, report)
        files.append(_entry(report_path, staging, "report"))
        diagnostics_path = staging / "diagnostics.txt"
        diagnostics_path.write_text(diagnostics, encoding="utf-8", newline="\n")
        files.append(_entry(diagnostics_path, staging, "diagnostics"))
        manifest = {
            "schema": SCHEMA,
            "created_at": datetime.now(UTC).isoformat(),
            "original_arguments": list(arguments),
            "audit_arguments": portable,
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "versions": _versions(report),
            "files": files,
        }
        _write_json(staging / "manifest.json", manifest)
        staging.rename(destination)
    return manifest


def _contained(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative or path.is_absolute() or ".." in path.parts
        or "\\" in relative or ":" in relative
    ):
        raise BundleError(f"Invalid bundle path: {relative!r}.")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise BundleError(f"Bundle path escapes its directory: {relative!r}.")
    return resolved


def _verified_manifest(root: Path) -> dict[str, Any]:
    manifest = _json(_contained(root, "manifest.json"))
    if manifest.get("schema") != SCHEMA:
        raise BundleError(f"Expected bundle schema {SCHEMA}.")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BundleError("The bundle must declare its files.")
    known: dict[str, str] = {}
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise BundleError("Invalid bundle file entry.")
        relative = entry["path"]
        if relative in known:
            raise BundleError(f"Duplicate bundle file: {relative}.")
        role = entry.get("role")
        if role not in {"calculation", "analysis", "report", "diagnostics"}:
            raise BundleError(f"Invalid role for bundle file: {relative}.")
        known[relative] = role
        target = _contained(root, relative)
        data = target.read_bytes()
        if (
            len(data) != entry.get("bytes")
            or hashlib.sha256(data).hexdigest() != entry.get("sha256")
        ):
            raise BundleError(f"Checksum mismatch: {relative}.")
    if known.get("report.json") != "report" or known.get("diagnostics.txt") != "diagnostics":
        raise BundleError("The baseline report and diagnostics must be declared.")
    arguments = manifest.get("audit_arguments")
    if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
        raise BundleError("Audit arguments must be a list of strings.")
    args = _namespace(arguments)
    if args.format != "json" or args.input.as_posix() != "inputs/calculations":
        raise BundleError("The recorded audit must read the bundled calculations and emit JSON.")
    input_dir = _contained(root, args.input.as_posix())
    actual_calculations = {path.relative_to(root).as_posix() for path in input_dir.glob("*.out")}
    declared_calculations = {path for path, role in known.items() if role == "calculation"}
    if not actual_calculations or actual_calculations != declared_calculations:
        raise BundleError("The calculation directory does not match the declared file set.")
    analysis_paths = [path.as_posix() for path in args.analysis]
    for path in analysis_paths:
        _contained(root, path)
    if set(analysis_paths) != {path for path, role in known.items() if role == "analysis"}:
        raise BundleError("Analysis arguments do not match the declared file set.")
    if _versions(_json(root / "report.json")) != manifest.get("versions"):
        raise BundleError("Recorded versions disagree with the baseline report.")
    return manifest


def _comparable(report: dict[str, Any]) -> dict[str, Any]:
    comparable = copy.deepcopy(report)
    comparable.pop("generated_at")
    comparable.pop("tool_version")
    comparable["protocol"].pop("version")
    for fact in comparable["inventory"]["facts"]:
        fact["provenance"].pop("extracted_at")
    return comparable


def replay_bundle(root: Path, *, allow_version_change: bool = False) -> dict[str, Any]:
    """Verify inputs and compare a fresh audit; leave the original bundle untouched."""
    root = root.resolve()
    manifest = _verified_manifest(root)
    report, diagnostics = _run(manifest["audit_arguments"], root)
    current = _versions(report)
    same_versions = current == manifest["versions"]
    baseline = _comparable(_json(root / "report.json"))
    actual = _comparable(report)
    changed = sorted(
        key for key in baseline.keys() | actual.keys()
        if key not in baseline or key not in actual or baseline[key] != actual[key]
    )
    same_diagnostics = diagnostics == (root / "diagnostics.txt").read_text(encoding="utf-8")
    return {
        "versions_match": same_versions,
        "report_matches": not changed,
        "diagnostics_match": same_diagnostics,
        "recorded_versions": manifest["versions"],
        "current_versions": current,
        "changed_report_sections": changed,
        "passed": (same_versions or allow_version_change) and not changed and same_diagnostics,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="save a new local bundle")
    create.add_argument("--bundle", required=True, type=Path)
    create.add_argument(
        "arguments", nargs=argparse.REMAINDER, help="QCJudge audit arguments after --",
    )
    replay = commands.add_parser("replay", help="verify and compare an existing bundle")
    replay.add_argument("--bundle", required=True, type=Path)
    replay.add_argument("--allow-version-change", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
            manifest = create_bundle(args.bundle, arguments)
            version = manifest["versions"]["tool_version"]
            print(f"Audit bundle saved: {args.bundle.resolve()} ({version})")
            return 0
        result = replay_bundle(args.bundle, allow_version_change=args.allow_version_change)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    except (BundleError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"audit_bundle: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

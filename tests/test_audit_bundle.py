"""Portable inputs and reproducible audits, including integrity and version boundaries."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tools import audit_bundle

ROOT = Path(__file__).resolve().parents[1]
TS = ROOT / "examples" / "01-transition-state-mode-identity" / "job.out"
CT = ROOT / "examples" / "04-charge-transfer-analysis"


def _arguments(source: Path = TS) -> list[str]:
    return [
        "audit", "--question", "transition_state", "--input", str(source),
        "--context", "molecule=dvb", "--ask", "Does this pathway belong to dvb?",
        "--assumption", "Gas-phase geometry", "--condition", "note=unconsumed",
        "--expert-review", "ts.mode_identity",
    ]


def _create(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    audit_bundle.create_bundle(root, _arguments())
    return root


def _manifest(root: Path) -> dict:
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def _write_manifest(root: Path, manifest: dict) -> None:
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_bundle_keeps_raw_bytes_complete_arguments_and_researcher_inputs(tmp_path: Path) -> None:
    root = _create(tmp_path)
    manifest = _manifest(root)
    source = root / "inputs" / "calculations" / "000001.out"
    assert source.read_bytes() == TS.read_bytes()
    assert manifest["original_arguments"] == _arguments()
    assert manifest["audit_arguments"][-2:] == ["--format", "json"]
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert report["question"]["text"] == "Does this pathway belong to dvb?"
    assert report["question"]["assumptions"] == ["Gas-phase geometry"]
    assert report["researcher_inputs"]["conditions"] == {"note": "unconsumed"}
    assert report["researcher_inputs"]["expert_reviews"][0]["requirement_id"] == "ts.mode_identity"
    for entry in manifest["files"]:
        assert hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]


def test_replay_survives_bundle_move_original_deletion_and_new_timestamps(tmp_path: Path) -> None:
    original = tmp_path / "original.out"
    original.write_bytes(TS.read_bytes())
    root = tmp_path / "first location"
    audit_bundle.create_bundle(root, _arguments(original))
    moved = tmp_path / "new location 日本語"
    root.rename(moved)
    original.unlink()
    before = {
        path.relative_to(moved): path.read_bytes()
        for path in moved.rglob("*") if path.is_file()
    }
    result = audit_bundle.replay_bundle(moved)
    assert result["passed"]
    assert result["versions_match"] and result["report_matches"] and result["diagnostics_match"]
    assert before == {
        path.relative_to(moved): path.read_bytes()
        for path in moved.rglob("*") if path.is_file()
    }


def test_bundle_replays_actual_linked_analysis(tmp_path: Path) -> None:
    root = tmp_path / "ct"
    audit_bundle.create_bundle(root, [
        "audit", "--question", "ct_excitation", "--input", str(CT / "job.out"),
        "--analysis", str(CT / "analysis.json"), "--context", "molecule=demo-ct",
        "--context", "state=S1", "--target", "calc-1",
    ])
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert report["evidence"]["overall_status"] == "supported"
    assert len(report["audit_scope"]["selected_calculation_ids"]) == 2
    assert audit_bundle.replay_bundle(root)["passed"]


def test_directory_snapshot_keeps_sorted_calculation_ids_and_target(tmp_path: Path) -> None:
    inputs = tmp_path / "outputs"
    inputs.mkdir()
    # Files are created in reverse order; lexical order must still determine calc-N.
    (inputs / "z.out").write_bytes(TS.read_bytes())
    (inputs / "a.out").write_bytes(TS.read_bytes())
    root = tmp_path / "many"
    audit_bundle.create_bundle(root, [*_arguments(inputs), "--target", "calc-2"])
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert report["audit_scope"]["selected_calculation_ids"] == ["calc-2"]
    assert audit_bundle.replay_bundle(root)["passed"]


@pytest.mark.parametrize(
    "relative", ["inputs/calculations/000001.out", "report.json", "diagnostics.txt"],
)
def test_changed_input_or_baseline_is_refused_before_execution(
    tmp_path: Path, relative: str, monkeypatch,
) -> None:
    root = _create(tmp_path)
    with (root / relative).open("ab") as stream:
        stream.write(b"changed")
    monkeypatch.setattr(
        audit_bundle, "_run", lambda *_: pytest.fail("Unverified bytes were executed"),
    )
    with pytest.raises(audit_bundle.BundleError, match="Checksum mismatch"):
        audit_bundle.replay_bundle(root)


def test_unrecorded_calculation_cannot_silently_change_calc_ids(tmp_path: Path) -> None:
    root = _create(tmp_path)
    shutil.copyfile(TS, root / "inputs" / "calculations" / "000000.out")
    with pytest.raises(audit_bundle.BundleError, match="declared file set"):
        audit_bundle.replay_bundle(root)


@pytest.mark.parametrize("unsafe", ["../outside.out", "C:/outside.out", "inputs\\outside.out"])
def test_bundle_path_escape_is_refused(tmp_path: Path, unsafe: str) -> None:
    root = _create(tmp_path)
    manifest = _manifest(root)
    manifest["files"][0]["path"] = unsafe
    _write_manifest(root, manifest)
    with pytest.raises(audit_bundle.BundleError, match="Invalid bundle path"):
        audit_bundle.replay_bundle(root)


def test_existing_bundle_is_never_overwritten(tmp_path: Path) -> None:
    root = _create(tmp_path)
    before = (root / "report.json").read_bytes()
    with pytest.raises(audit_bundle.BundleError, match="already exists"):
        audit_bundle.create_bundle(root, _arguments())
    assert (root / "report.json").read_bytes() == before


def test_failed_audit_does_not_leave_an_incomplete_bundle(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.out"
    invalid.write_text("not an ORCA output", encoding="utf-8")
    root = tmp_path / "failed"
    with pytest.raises(audit_bundle.BundleError, match="QCJudge exited 2"):
        audit_bundle.create_bundle(root, _arguments(invalid))
    assert not root.exists()
    assert not tuple(tmp_path.glob(".qcjudge-bundle-*"))


def test_version_drift_is_explicit_and_needs_opt_in(tmp_path: Path, monkeypatch) -> None:
    root = _create(tmp_path)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    changed = copy.deepcopy(report)
    changed["tool_version"] = "test-next-version"
    diagnostics = (root / "diagnostics.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(audit_bundle, "_run", lambda *_: (changed, diagnostics))
    result = audit_bundle.replay_bundle(root)
    assert not result["passed"] and not result["versions_match"] and result["report_matches"]
    assert audit_bundle.replay_bundle(root, allow_version_change=True)["passed"]


def test_allowing_version_drift_does_not_hide_changed_verdict(tmp_path: Path, monkeypatch) -> None:
    root = _create(tmp_path)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    report["tool_version"] = "test-next-version"
    report["evidence"]["overall_status"] = "contradicted"
    diagnostics = (root / "diagnostics.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(audit_bundle, "_run", lambda *_: (report, diagnostics))
    result = audit_bundle.replay_bundle(root, allow_version_change=True)
    assert not result["passed"] and result["changed_report_sections"] == ["evidence"]


@pytest.mark.parametrize("change", ["add", "remove"])
def test_nullable_section_changes_are_not_equal_to_absence(
    tmp_path: Path, monkeypatch, change: str,
) -> None:
    root = _create(tmp_path)
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if change == "add":
        report["new_section"] = None
    else:
        baseline = {**report, "new_section": None}
        baseline_path = root / "report.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        manifest = _manifest(root)
        data = baseline_path.read_bytes()
        for entry in manifest["files"]:
            if entry["path"] == "report.json":
                entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        _write_manifest(root, manifest)
    diagnostics = (root / "diagnostics.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(audit_bundle, "_run", lambda *_: (report, diagnostics))
    result = audit_bundle.replay_bundle(root, allow_version_change=True)
    assert not result["passed"] and result["changed_report_sections"] == ["new_section"]


def test_bundle_cli_create_and_replay_exit_codes(tmp_path: Path, capsys) -> None:
    root = tmp_path / "cli"
    assert audit_bundle.main(["create", "--bundle", str(root), "--", *_arguments()]) == 0
    assert "Audit bundle saved" in capsys.readouterr().out
    assert audit_bundle.main(["replay", "--bundle", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["passed"]
    (root / "report.json").write_text("{}", encoding="utf-8")
    assert audit_bundle.main(["replay", "--bundle", str(root)]) == 2
    assert "Checksum mismatch" in capsys.readouterr().err


def test_bundle_cannot_shadow_the_trusted_qcjudge_package(tmp_path: Path) -> None:
    root = _create(tmp_path)
    shadow = root / "qcjudge"
    (shadow / "cli").mkdir(parents=True)
    (shadow / "__init__.py").write_text(
        "raise RuntimeError('bundle code executed')", encoding="utf-8",
    )
    (shadow / "cli" / "__init__.py").write_text("", encoding="utf-8")
    (shadow / "cli" / "main.py").write_text("raise RuntimeError('shadow CLI')", encoding="utf-8")
    assert audit_bundle.replay_bundle(root)["passed"]


def test_leading_hyphen_and_unicode_option_values_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "options"
    audit_bundle.create_bundle(root, [
        *_arguments(), "--assumption=--special premise", "--ask=--日本語の質問",
    ])
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert report["question"]["text"] == "--日本語の質問"
    assert report["question"]["assumptions"][-1] == "--special premise"
    assert audit_bundle.replay_bundle(root)["passed"]


def test_manifest_is_contained_before_it_is_read(tmp_path: Path, monkeypatch) -> None:
    root = _create(tmp_path)
    real_contained = audit_bundle._contained

    def reject_manifest(directory: Path, relative: str) -> Path:
        if relative == "manifest.json":
            raise audit_bundle.BundleError("Manifest resolves outside the bundle")
        return real_contained(directory, relative)

    monkeypatch.setattr(audit_bundle, "_contained", reject_manifest)
    monkeypatch.setattr(audit_bundle, "_json", lambda *_: pytest.fail("External JSON was read"))
    with pytest.raises(audit_bundle.BundleError, match="outside the bundle"):
        audit_bundle.replay_bundle(root)

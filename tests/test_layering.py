"""Layer boundaries, enforced rather than assumed.

"Parsers must not decide science" and "the core must not depend on an LLM" are both claims
about the import graph. This module makes them checkable: it parses every source file and
asserts which QCJudge packages it reaches for. The dependency direction is inward, so a
violation is caught here rather than in review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "qcjudge"

_FORBIDDEN: dict[str, frozenset[str]] = {
    "domain": frozenset(
        {"protocols", "parsers", "adapters", "validators", "evidence", "audit", "render", "cli"}
    ),
    "protocols": frozenset(
        {"parsers", "adapters", "validators", "evidence", "audit", "render", "cli"}
    ),
    "parsers": frozenset(
        {"protocols", "validators", "evidence", "audit", "render", "cli"}
    ),
    "adapters": frozenset(
        {"protocols", "validators", "evidence", "audit", "render", "cli"}
    ),
    "validators": frozenset(
        {"protocols", "parsers", "adapters", "audit", "render", "cli"}
    ),
    "evidence": frozenset(
        {"protocols", "parsers", "adapters", "audit", "render", "cli"}
    ),
    "audit": frozenset({"parsers", "adapters", "render", "cli"}),
    "render": frozenset(
        {"protocols", "parsers", "adapters", "validators", "evidence", "audit", "cli"}
    ),
    "cli": frozenset(),
}

_DENIED_EXTERNAL = frozenset(
    {
        "openai",
        "anthropic",
        "google",
        "cohere",
        "mistralai",
        "langchain",
        "langchain_core",
        "llama_index",
        "transformers",
        "torch",
        "tensorflow",
        "fastapi",
        "flask",
        "django",
        "starlette",
        "uvicorn",
        "requests",
        "httpx",
        "aiohttp",
        "urllib3",
        "numpy",
        "pandas",
        "scipy",
        "rdkit",
        "pydantic",
        "sqlalchemy",
        "celery",
        "redis",
    }
)


def _source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _imported_roots(path: Path) -> tuple[set[str], set[str]]:
    """Return (internal QCJudge subpackages, external top-level modules) imported."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    internal: set[str] = set()
    external: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if parts[0] == "qcjudge":
                if len(parts) > 1:
                    internal.add(parts[1])
            else:
                external.add(parts[0])
    return internal, external


def _package_of(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT).parts
    return relative[0] if len(relative) > 1 else ""


@pytest.mark.parametrize("path", _source_files(), ids=lambda path: path.name)
def test_layering_rules_hold(path: Path) -> None:
    package = _package_of(path)
    forbidden = _FORBIDDEN.get(package)
    if forbidden is None:
        pytest.skip(f"{package or 'root'} is a facade with no declared restrictions")
    internal, _ = _imported_roots(path)
    violations = sorted(internal & forbidden)
    assert not violations, (
        f"{path.relative_to(SOURCE_ROOT)} ({package}) imports forbidden packages: {violations}"
    )


@pytest.mark.parametrize("path", _source_files(), ids=lambda path: path.name)
def test_no_core_module_imports_an_external_framework(path: Path) -> None:
    _, external = _imported_roots(path)
    violations = sorted(external & _DENIED_EXTERNAL)
    assert not violations, (
        f"{path.relative_to(SOURCE_ROOT)} imports disallowed third-party modules: {violations}"
    )


def test_the_walk_actually_finds_the_package() -> None:
    """Guard against a path change silently turning every layering check into a no-op."""
    files = _source_files()
    assert len(files) >= 15
    packages = {_package_of(path) for path in files}
    assert {"domain", "audit", "evidence", "protocols", "validators"} <= packages


def test_domain_imports_only_the_standard_library_and_itself() -> None:
    external_seen: set[str] = set()
    for path in (SOURCE_ROOT / "domain").rglob("*.py"):
        _, external = _imported_roots(path)
        external_seen |= external
    assert external_seen <= {
        "__future__", "collections", "dataclasses", "datetime", "enum", "math", "re",
    }


def test_no_module_imports_the_package_root() -> None:
    """Importing ``qcjudge`` from inside the package would make the facade load eagerly."""
    for path in _source_files():
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name != "qcjudge" for alias in node.names), path
